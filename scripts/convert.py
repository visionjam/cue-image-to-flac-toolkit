# scripts/convert.py
"""单专辑流水线：解码整轨 → 采样级切轨 → 编码 FLAC → 写标签/封面 → 逐轨 MD5 校验 → 原子入成品目录。"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path

import cuelib
from audio import (AudioError, decode_to_wav, encode_flac, flac_pcm_md5,
                   probe_audio, slice_wav, wav_info, wav_segment_md5)
from mutagen.flac import FLAC, Picture

DEFAULT_SOURCE = Path(r"E:\陶喆")
DEFAULT_OUTPUT = Path(r"E:\音乐库\陶喆")
DEFAULT_WORK = Path(r"E:\音乐库-工作区")

log = logging.getLogger("convert")


class AlbumError(RuntimeError):
    pass


def setup_logging(work_root: Path) -> None:
    if getattr(setup_logging, "_done", False):
        return
    setup_logging._done = True
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    (work_root / "logs").mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    sh = logging.StreamHandler(sys.stdout); sh.setFormatter(fmt)
    fh = logging.FileHandler(work_root / "logs" / "convert.log", encoding="utf-8"); fh.setFormatter(fmt)
    log.setLevel(logging.INFO); log.addHandler(sh); log.addHandler(fh)


def find_album_inputs(src_dir: Path) -> tuple[Path, Path]:
    cues = sorted(p for p in src_dir.iterdir() if p.suffix.lower() == ".cue")
    auds = sorted(p for p in src_dir.iterdir() if p.suffix.lower() in (".ape", ".flac", ".wav"))
    if len(cues) != 1 or len(auds) != 1:
        raise AlbumError(f"expected exactly 1 cue + 1 audio in {src_dir}, got {len(cues)}/{len(auds)}")
    return cues[0], auds[0]


def _sniff_image_mime(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    raise AlbumError("cover image is neither JPEG nor PNG")


def write_tags(flac_path: Path, cue: cuelib.CueSheet, trk: cuelib.CueTrack,
               date: str | None, total: int, meta: dict | None, cover_data: bytes) -> None:
    f = FLAC(str(flac_path))
    f.delete()
    f.clear_pictures()
    f["ARTIST"] = [trk.performer or cue.artist or "陶喆"]
    f["ALBUMARTIST"] = [cue.artist or "陶喆"]
    f["ALBUM"] = [cue.album]
    f["TITLE"] = [trk.title]
    f["TRACKNUMBER"] = [str(trk.number)]
    f["TRACKTOTAL"] = [str(total)]
    if date:
        f["DATE"] = [date]
    if cue.genre:
        f["GENRE"] = [cue.genre]

    if meta:
        mb = meta.get("musicbrainz") or {}
        for key, tag in (("release_id", "MUSICBRAINZ_ALBUMID"),
                         ("release_group_id", "MUSICBRAINZ_RELEASEGROUPID"),
                         ("artist_id", "MUSICBRAINZ_ARTISTID"),
                         ("label", "LABEL"), ("country", "RELEASECOUNTRY"),
                         ("catalog_number", "CATALOGNUMBER"), ("barcode", "BARCODE")):
            if mb.get(key):
                f[tag] = [str(mb[key])]
        credits = (meta.get("tracks") or {}).get(str(trk.number)) or {}
        for key, tag in (("composer", "COMPOSER"), ("lyricist", "LYRICIST"), ("arranger", "ARRANGER")):
            if credits.get(key):
                f[tag] = [str(v) for v in credits[key]]

    pic = Picture()
    pic.type = 3
    pic.mime = _sniff_image_mime(cover_data)
    pic.desc = "Cover"
    pic.data = cover_data
    f.add_picture(pic)
    f.save()


def _check_disk_space(output_root: Path, need_bytes: int) -> None:
    anchor = output_root
    while not anchor.exists() and anchor.parent != anchor:
        anchor = anchor.parent
    free = shutil.disk_usage(anchor).free
    if free < need_bytes:
        raise AlbumError(f"not enough disk space: need ~{need_bytes/1e9:.1f}GB, free {free/1e9:.1f}GB")


def _convert_album(folder_name: str, *, source_root: Path, output_root: Path,
                   work_root: Path, meta_dir: Path) -> dict:
    t0 = time.time()
    src_dir = source_root / folder_name
    if not src_dir.is_dir():
        raise AlbumError(f"source album dir not found: {src_dir}")
    cue_path, audio_path = find_album_inputs(src_dir)
    cue = cuelib.parse_cue(cue_path)

    meta = None
    meta_path = meta_dir / f"{folder_name}.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    date = (meta or {}).get("date") or cuelib.resolve_date(cue.date, folder_name)
    year = int(date[:4]) if date else None

    src_size = sum(p.stat().st_size for p in src_dir.iterdir() if p.is_file())
    _check_disk_space(output_root, int(src_size * 1.3) + 800_000_000)

    tmp_dir = work_root / "temp" / folder_name
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    out_tmp = tmp_dir / "out"
    out_tmp.mkdir(parents=True)

    log.info("[%s] decoding %s", folder_name, audio_path.name)
    full_wav = tmp_dir / "full.wav"
    try:
        decode_to_wav(audio_path, full_wav)
    except AudioError as e:
        raise AlbumError(f"decode failed: {e}") from e
    nframes, rate, ch, sw = wav_info(full_wav)
    if (rate, ch, sw) != (44100, 2, 2):
        raise AlbumError(f"unexpected source format: rate={rate} ch={ch} sampwidth={sw}")

    starts = [t.start_samples for t in cue.tracks]
    if starts[0] != 0:
        raise AlbumError(f"first track does not start at sample 0 (starts {starts[0]})")
    if any(s >= nframes for s in starts):
        raise AlbumError(f"track start beyond audio end (nframes={nframes}, starts={starts})")
    counts = [starts[i + 1] - starts[i] for i in range(len(starts) - 1)] + [nframes - starts[-1]]

    cover_path = src_dir / "cover.jpg"
    if not cover_path.exists():
        raise AlbumError("cover.jpg missing in source dir")
    cover_data = cover_path.read_bytes()
    _sniff_image_mime(cover_data)

    files: list[str] = []
    md5s: list[str] = []
    for trk, start, count in zip(cue.tracks, starts, counts):
        seg_wav = out_tmp / f"seg{trk.number:02d}.wav"
        tmp_flac = out_tmp / f"{trk.number:02d}.flac"
        slice_wav(full_wav, start, count, seg_wav)
        encode_flac(seg_wav, tmp_flac)
        seg_md5 = wav_segment_md5(full_wav, start, count)
        got_md5 = flac_pcm_md5(tmp_flac)
        if seg_md5 != got_md5:
            raise AlbumError(f"track {trk.number}: md5 mismatch (src={seg_md5} out={got_md5})")
        write_tags(tmp_flac, cue, trk, date, len(cue.tracks), meta, cover_data)
        probe = probe_audio(tmp_flac)
        if probe.get("codec_name") != "flac" or int(probe["channels"]) != 2:
            raise AlbumError(f"track {trk.number}: unexpected output format {probe}")
        back = FLAC(str(tmp_flac))
        if not back.pictures or "TRACKTOTAL" not in back:
            raise AlbumError(f"track {trk.number}: tag/cover read-back failed")
        md5s.append(seg_md5)
        files.append(cuelib.track_file_name(trk.number, trk.title))
        log.info("[%s] track %02d/%02d ok (%.1fs audio)", folder_name, trk.number, len(cue.tracks), count / rate)

    final_dir = output_root / cuelib.album_dir_name(year, cue.album or folder_name)
    final_dir.mkdir(parents=True, exist_ok=True)
    for trk, fname in zip(cue.tracks, files):
        dst = final_dir / fname
        if dst.exists():                     # 幂等：重跑时覆盖旧产物
            dst.unlink()
        shutil.move(str(out_tmp / f"{trk.number:02d}.flac"), str(dst))
    shutil.copyfile(cover_path, final_dir / "cover.jpg")

    result = {"folder": folder_name, "status": "ok", "tracks": len(cue.tracks),
              "files": files, "md5": md5s, "date": date, "album_dir": str(final_dir),
              "elapsed_s": round(time.time() - t0, 1)}
    (work_root / "logs").mkdir(parents=True, exist_ok=True)
    (work_root / "logs" / f"convert-{folder_name}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.rmtree(tmp_dir)
    log.info("[%s] done: %d tracks -> %s", folder_name, len(cue.tracks), final_dir)
    return result


def convert_album(folder_name: str, *, source_root: Path, output_root: Path,
                  work_root: Path, meta_dir: Path) -> dict:
    """公开入口：把内部实现的任何失败统一封装为 AlbumError（计划接口契约）。"""
    try:
        return _convert_album(folder_name, source_root=source_root, output_root=output_root,
                              work_root=work_root, meta_dir=meta_dir)
    except AlbumError:
        raise                                    # 已符合契约，原样透传（保留原始信息）
    except Exception as e:                       # noqa: BLE001 - 统一封装为 AlbumError
        raise AlbumError(str(e)) from e


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Convert image+CUE albums to per-track FLAC.")
    ap.add_argument("--album", action="append", default=[])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--source-root", default=str(DEFAULT_SOURCE))
    ap.add_argument("--output-root", default=str(DEFAULT_OUTPUT))
    ap.add_argument("--work-root", default=str(DEFAULT_WORK))
    args = ap.parse_args(argv)

    source_root = Path(args.source_root)
    work_root = Path(args.work_root)
    setup_logging(work_root)

    if args.all:
        folders = sorted(d.name for d in source_root.iterdir() if d.is_dir())
    else:
        folders = args.album
    if not folders:
        ap.error("give --album <folder-name> (repeatable) or --all")

    failures = []
    for folder in folders:
        try:
            convert_album(folder, source_root=source_root,
                          output_root=Path(args.output_root), work_root=work_root,
                          meta_dir=work_root / "meta")
        except Exception as e:                       # noqa: BLE001 - 隔离单专辑失败
            failures.append((folder, str(e)))
            log.error("[%s] FAILED: %s", folder, e)
    if failures:
        log.error("failures: %s", failures)
        return 1
    log.info("all %d album(s) converted ok", len(folders))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

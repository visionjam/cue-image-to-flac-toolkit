# scripts/verify.py
"""全库独立校验：重解源 → 逐轨 PCM MD5 比对 + 格式/标签/封面/补充字段 + 清单导出。"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import cuelib
from audio import (AudioError, decode_to_wav, flac_pcm_md5, probe_audio,
                   wav_info, wav_segment_md5)
from mutagen.flac import FLAC

DEFAULT_SOURCE = Path(r"E:\陶喆")
DEFAULT_OUTPUT = Path(r"E:\音乐库\陶喆")
DEFAULT_WORK = Path(r"E:\音乐库-工作区")

REQUIRED_TAGS = ("ARTIST", "ALBUMARTIST", "ALBUM", "TITLE", "TRACKNUMBER", "TRACKTOTAL")


def verify_album(folder_name: str, *, source_root: Path, output_root: Path,
                 work_root: Path, meta_dir: Path) -> dict:
    problems: list[str] = []
    src_dir = source_root / folder_name
    cue_files = sorted(p for p in src_dir.iterdir() if p.suffix.lower() == ".cue")
    aud_files = sorted(p for p in src_dir.iterdir() if p.suffix.lower() in (".ape", ".flac", ".wav"))
    if len(cue_files) != 1 or len(aud_files) != 1:
        return {"folder": folder_name, "status": "fail", "tracks": 0,
                "problems": ["cue/audio file count mismatch"]}
    cue = cuelib.parse_cue(cue_files[0])

    meta = None
    mp = meta_dir / f"{folder_name}.json"
    if mp.exists():
        meta = json.loads(mp.read_text(encoding="utf-8"))
    date = (meta or {}).get("date") or cuelib.resolve_date(cue.date, folder_name)
    year = int(date[:4]) if date else None
    album_dir = output_root / cuelib.album_dir_name(year, cue.album or folder_name)

    tmp = work_root / "temp" / ("verify-" + folder_name)
    tmp.mkdir(parents=True, exist_ok=True)
    full_wav = tmp / "full.wav"
    try:
        decode_to_wav(aud_files[0], full_wav)
    except AudioError as e:
        return {"folder": folder_name, "status": "fail", "tracks": 0,
                "problems": [f"source decode failed: {e}"]}
    nframes, rate, ch, sw = wav_info(full_wav)
    if (rate, ch, sw) != (44100, 2, 2):
        problems.append(f"source format unexpected: {rate}/{ch}/{sw}")

    starts = [t.start_samples for t in cue.tracks]
    counts = [starts[i + 1] - starts[i] for i in range(len(starts) - 1)] + [nframes - starts[-1]]

    rows = []
    total_frames = 0
    checked = 0
    for trk, start, count in zip(cue.tracks, starts, counts):
        fname = cuelib.track_file_name(trk.number, trk.title)
        fp = album_dir / fname
        if not fp.exists():
            problems.append(f"{trk.number:02d} missing file {fname}")
            continue
        try:
            exp = wav_segment_md5(full_wav, start, count)
            got = flac_pcm_md5(fp)
        except AudioError as e:
            problems.append(f"{trk.number:02d} decode error: {e}")
            continue
        if exp != got:
            problems.append(f"{trk.number:02d} md5 mismatch")
        # 产物实际帧数核对：总样本数证明必须来自成品解码结果，不能对 counts 自身求和
        chk_wav = tmp / f"chk{trk.number:02d}.wav"
        try:
            decode_to_wav(fp, chk_wav)
            got_frames = wav_info(chk_wav)[0]
        except AudioError as e:
            problems.append(f"{trk.number:02d} frame count decode error: {e}")
        else:
            total_frames += got_frames
            checked += 1
            if got_frames != count:
                problems.append(f"{trk.number:02d} frame count {got_frames} != expected {count}")
        finally:
            chk_wav.unlink(missing_ok=True)
        info = probe_audio(fp)
        if info.get("codec_name") != "flac" or int(info.get("sample_rate", 0)) != 44100 \
                or int(info.get("channels", 0)) != 2:
            problems.append(f"{trk.number:02d} format check failed: {info}")
        f = FLAC(str(fp))
        for tag in REQUIRED_TAGS:
            if tag not in f:
                problems.append(f"{trk.number:02d} missing tag {tag}")
        if not f.pictures:
            problems.append(f"{trk.number:02d} no embedded cover")
        if meta:
            mb = meta.get("musicbrainz") or {}
            if mb.get("release_id") and f.get("MUSICBRAINZ_ALBUMID", [""])[0] != mb["release_id"]:
                problems.append(f"{trk.number:02d} MUSICBRAINZ_ALBUMID mismatch")
            credits = (meta.get("tracks") or {}).get(str(trk.number)) or {}
            for key, tag in (("composer", "COMPOSER"), ("lyricist", "LYRICIST"), ("arranger", "ARRANGER")):
                if credits.get(key):
                    if [str(v) for v in credits[key]] != f.get(tag, []):
                        problems.append(f"{trk.number:02d} {tag} mismatch")
        rows.append({"album": cue.album, "track": trk.number, "title": trk.title,
                     "duration": f"{count // rate // 60}:{count // rate % 60:02d}",
                     "file": fname, "md5": got})

    if total_frames != nframes or checked != len(cue.tracks):
        problems.append(f"total sample count mismatch: tracks {checked}/{len(cue.tracks)}, "
                        f"frames {total_frames}/{nframes}")

    if album_dir.exists() and not (album_dir / "cover.jpg").exists():
        problems.append("cover.jpg missing in output album dir")
    try:
        import shutil
        shutil.rmtree(tmp)
    except OSError:
        pass
    return {"folder": folder_name, "status": "fail" if problems else "ok",
            "tracks": len(cue.tracks), "problems": problems, "rows": rows,
            "album_dir": str(album_dir)}


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Verify converted library against source.")
    ap.add_argument("--album", action="append", default=[])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--source-root", default=str(DEFAULT_SOURCE))
    ap.add_argument("--output-root", default=str(DEFAULT_OUTPUT))
    ap.add_argument("--work-root", default=str(DEFAULT_WORK))
    ap.add_argument("--tracklist-out", default=None)
    ap.add_argument("--report-out", default=None)
    args = ap.parse_args(argv)

    source_root = Path(args.source_root)
    work_root = Path(args.work_root)
    folders = sorted(d.name for d in source_root.iterdir() if d.is_dir()) if args.all else args.album
    if not folders:
        ap.error("give --album (repeatable) or --all")

    reports, all_rows, bad = [], [], 0
    for folder in folders:
        rep = verify_album(folder, source_root=source_root,
                           output_root=Path(args.output_root), work_root=work_root,
                           meta_dir=work_root / "meta")
        reports.append(rep)
        all_rows.extend(rep.get("rows", []))
        if rep["status"] != "ok":
            bad += 1
        print(f"[{'OK ' if rep['status']=='ok' else 'FAIL'}] {folder} ({rep['tracks']} tracks)")
        for p in rep.get("problems", []):
            print(f"    - {p}")

    tracklist_out = Path(args.tracklist_out) if args.tracklist_out else work_root / "reports" / "tracklist.csv"
    tracklist_out.parent.mkdir(parents=True, exist_ok=True)
    with tracklist_out.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["album", "track", "title", "duration", "file", "md5"])
        w.writeheader()
        w.writerows(all_rows)

    stamp = time.strftime("%Y-%m-%d-%H%M")
    report_out = Path(args.report_out) if args.report_out else work_root / "reports" / f"verification-{stamp}.md"
    lines = [f"# 全库校验报告 {stamp}", "",
             f"- 专辑：{len(reports)}，失败：{bad}", ""]
    for rep in reports:
        lines.append(f"## {rep['folder']} — {rep['status']}（{rep['tracks']} 轨）")
        lines.extend(f"- {p}" for p in rep.get("problems", []))
        lines.append("")
    report_out.write_text("\n".join(lines), encoding="utf-8")
    print(f"tracklist -> {tracklist_out}")
    print(f"report    -> {report_out}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())

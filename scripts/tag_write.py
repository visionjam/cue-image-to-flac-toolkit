# scripts/tag_write.py
"""带证明的 FLAC 标签写入器：写标签 / 内嵌封面 / 尾部残留清理，同时证明音频区未被触碰。

每个文件做四重核对（任一不过即 [FAIL]，进程退出码 1）：
 1) 音频区逐字节比对：按 FLAC 元数据块链定位音频起点；写标签前后音频区逐字节相同
 2) STREAMINFO 内声明的 MD5 不变（mutagen 读取）
 3) 完整解码 PCM MD5 == STREAMINFO MD5（scripts/audio.py，支持 16/24bit）
 4) 标签回读：albumartist / date / composer / lyricist / arranger（及 title / album / 封面数）与预期一致

两种模式：
  python scripts/tag_write.py album --dir <专辑目录> --meta <meta.json> --cover <jpg> --artist <名>
  python scripts/tag_write.py files --spec <spec.json>

album 模式：meta 为 check_meta.py 口径的专辑 JSON（folder/album/date/genre/musicbrainz/tracks），
           轨号匹配：内嵌 tracknumber → 文件名前缀回退（"01"→"1" 归一，见 "--" 注释）。
files 模式：spec = {"artist": "...", "items": [{file,title,album,date,genre?,composer,lyricist,
           arranger,cover?,mb?{release_id,release_group_id,artist_id,recording_id,release_track_id}}]}

可选 --trim-manifest <csv>（列：relpath,tail_junk_bytes,junk_sha1；relpath = 目录名/文件名）：
写前裁掉与 sha1 相符的尾部残留（幂等保护：字节已变则不再裁）。用于修复"下载截断/尾部垃圾"类源文件。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

from mutagen.flac import FLAC, Picture

import audio

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def flac_audio_start(data: bytes) -> int:
    """FLAC 文件音频起点：跳过头块 + 所有元数据块（含最后 1 个 is-last 标记块）。"""
    off = 4
    while True:
        last = data[off] >> 7
        length = int.from_bytes(data[off + 1:off + 4], "big")
        off += 4 + length
        if last:
            return off


def jpeg_size(data: bytes) -> tuple[int, int]:
    """从 JPEG 字节流解析宽高（SOF 标记），不依赖 Pillow。"""
    if data[:2] != b"\xff\xd8":
        raise ValueError("not a JPEG")
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker == 0xD8 or 0xD0 <= marker <= 0xD7 or marker == 0x01:
            i += 2
            continue
        seg_len = int.from_bytes(data[i + 2:i + 4], "big")
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            h = int.from_bytes(data[i + 5:i + 7], "big")
            w = int.from_bytes(data[i + 7:i + 9], "big")
            return w, h
        i += 2 + seg_len
    raise ValueError("JPEG SOF marker not found")


def normalize_track(num: str) -> str:
    """轨号归一："01" -> "1"（meta 键约定为无前导零的字符串）。"""
    return str(int(num)) if num.isdigit() else num


def load_trim_manifest(path: Path | None) -> dict[str, tuple[int, str]]:
    out: dict[str, tuple[int, str]] = {}
    if path and path.exists():
        with path.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                if row.get("error"):
                    continue
                out[row["relpath"]] = (int(row["tail_junk_bytes"]), row["junk_sha1"])
    return out


def apply_cover(f: FLAC, cover_data: bytes) -> None:
    w, h = jpeg_size(cover_data)
    pic = Picture()
    pic.type = 3
    pic.mime = "image/jpeg"
    pic.desc = "Cover"
    pic.width, pic.height, pic.depth, pic.colors = w, h, 24, 0
    pic.data = cover_data
    f.clear_pictures()
    f.add_picture(pic)


def write_one(fp: Path, expected: dict, artist: str, cover_data: bytes | None,
              junk: dict[str, tuple[int, str]], dry_run: bool) -> bool:
    """写单个文件并返回是否全部证明通过。expected 键：title/album/date/genre/composer/lyricist/
    arranger/tracknumber/tracktotal/mb（可缺省）。"""
    f = FLAC(str(fp))
    data_before = fp.read_bytes()
    a0 = flac_audio_start(data_before)
    junk_bytes, junk_sha1 = junk.get(f"{fp.parent.name}/{fp.name}", (0, ""))
    if junk_bytes > 0:
        tail = data_before[len(data_before) - junk_bytes:]
        if hashlib.sha1(tail).hexdigest() != junk_sha1:
            junk_bytes = 0  # 已清理过或字节已变——幂等保护
    audio_region = data_before[a0: len(data_before) - junk_bytes]
    md5_before = "%032x" % f.info.md5_signature
    bps = f.info.bits_per_sample

    if dry_run:
        print(f"[DRY] {fp.name}: track={expected['tracknumber']} junk_to_trim={junk_bytes} "
              f"title={expected['title']!r} cover={'yes' if cover_data else 'keep'}")
        return True

    t = f.tags
    t["artist"] = t.get("artist") or [artist]
    t["title"] = [expected["title"]]
    t["album"] = [expected["album"]]
    t["albumartist"] = [artist]
    t["date"] = [expected["date"]]
    t["genre"] = list(expected.get("genre") or [])
    t["tracknumber"] = [expected["tracknumber"]]
    t["tracktotal"] = [str(expected.get("tracktotal", expected["tracknumber"]))]
    t["discnumber"] = [str(expected.get("discnumber", 1))]
    t["disctotal"] = [str(expected.get("disctotal", 1))]
    t["composer"] = list(expected.get("composer") or [])
    t["lyricist"] = list(expected.get("lyricist") or [])
    t["arranger"] = list(expected.get("arranger") or [])
    mb = expected.get("mb") or {}
    if mb.get("release_id"):
        t["musicbrainz_albumid"] = [mb["release_id"]]
    if mb.get("artist_id"):
        t["musicbrainz_albumartistid"] = [mb["artist_id"]]
        t["musicbrainz_artistid"] = [mb["artist_id"]]
    if mb.get("release_group_id"):
        t["musicbrainz_releasegroupid"] = [mb["release_group_id"]]
    if mb.get("recording_id"):
        t["musicbrainz_trackid"] = [mb["recording_id"]]
    if mb.get("release_track_id"):
        t["musicbrainz_releasetrackid"] = [mb["release_track_id"]]
    if cover_data:
        apply_cover(f, cover_data)
    f.save()

    # 1) 音频区逐字节不变
    data_after = fp.read_bytes()
    a0n = flac_audio_start(data_after)
    same_audio = data_after[a0n: a0n + len(audio_region)] == audio_region
    extra = len(data_after) - (a0n + len(audio_region))
    if same_audio and extra > 0:
        with fp.open("r+b") as fh:
            fh.truncate(a0n + len(audio_region))

    # 2/3) 校验值不变 + 完整解码 PCM MD5 == STREAMINFO
    f2 = FLAC(str(fp))
    md5_after = "%032x" % f2.info.md5_signature
    pcm_ok = False
    try:
        pcm_ok = audio.flac_pcm_md5_bps(fp, bps) == md5_before or md5_before == "0" * 32
    except audio.AudioError:
        pcm_ok = False

    # 4) 标签回读
    tags_ok = all([
        f2.tags.get("title") == [expected["title"]],
        f2.tags.get("album") == [expected["album"]],
        f2.tags.get("albumartist") == [artist],
        f2.tags.get("date") == [expected["date"]],
        f2.tags.get("tracknumber") == [expected["tracknumber"]],
        (f2.tags.get("composer") or []) == list(expected.get("composer") or []),
        (f2.tags.get("lyricist") or []) == list(expected.get("lyricist") or []),
        (f2.tags.get("arranger") or []) == list(expected.get("arranger") or []),
        (not cover_data) or len(f2.pictures) == 1,
    ])
    ok = same_audio and md5_after == md5_before and pcm_ok and tags_ok
    print(f"[{'OK ' if ok else 'FAIL'}] {fp.name}: track={expected['tracknumber']} trim={extra}B "
          f"md5_same={md5_after == md5_before} pcm_ok={pcm_ok} tags_ok={tags_ok} "
          f"size {len(data_before)} -> {fp.stat().st_size}")
    return ok


def run_album(args) -> int:
    album_dir = Path(args.dir)
    meta = json.loads(Path(args.meta).read_text(encoding="utf-8"))
    cover_data = Path(args.cover).read_bytes() if args.cover else None
    if cover_data:
        assert cover_data[:3] == b"\xff\xd8\xff", "cover must be JPEG"
        cover_size = jpeg_size(cover_data)
    junk = load_trim_manifest(Path(args.trim_manifest) if args.trim_manifest else None)
    files = sorted(album_dir.glob("*.flac"))
    assert files, f"no flac files in {album_dir}"
    fails = 0
    for fp in files:
        f = FLAC(str(fp))
        num = str(f.tags.get("tracknumber", [""])[0]).split("/")[0].strip()
        if not num:  # 无内嵌轨号时退回文件名前缀（组装库均为 NN.曲名）
            m = re.match(r"^(\d+)", fp.name)
            num = m.group(1) if m else ""
        num = normalize_track(num)
        tmeta = meta["tracks"].get(num)
        if not tmeta:
            print(f"[SKIP] {fp.name}: no meta for track {num!r}")
            fails += 1
            continue
        expected = {
            "title": tmeta["title"], "album": meta["album"], "date": meta["date"],
            "genre": meta.get("genre"), "tracknumber": num,
            "tracktotal": len(meta["tracks"]),
            "composer": tmeta.get("composer"), "lyricist": tmeta.get("lyricist"),
            "arranger": tmeta.get("arranger"),
            "mb": dict(meta.get("musicbrainz") or {}, recording_id=tmeta.get("musicbrainz_recording_id"),
                       release_track_id=tmeta.get("musicbrainz_releasetrackid")),
        }
        expected["mb"] = {k: v for k, v in expected["mb"].items() if v}
        if not write_one(fp, expected, args.artist, cover_data, junk, args.dry_run):
            fails += 1
    if not args.dry_run and cover_data:
        (album_dir / "cover.jpg").write_bytes(cover_data)
        print(f"[cover] -> {album_dir / 'cover.jpg'} ({cover_size[0]}x{cover_size[1]})")
    print(f"done. fails={fails}")
    return 1 if fails else 0


def run_files(args) -> int:
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    artist = spec["artist"]
    junk = load_trim_manifest(Path(args.trim_manifest) if args.trim_manifest else None)
    fails = 0
    for it in spec["items"]:
        fp = Path(it["file"]) if Path(it["file"]).is_absolute() else Path(spec.get("dir", ".")) / it["file"]
        cover_data = None
        if it.get("cover"):
            cover_data = Path(it["cover"]).read_bytes()
            assert cover_data[:3] == b"\xff\xd8\xff", "cover must be JPEG"
        expected = {
            "title": it["title"], "album": it["album"], "date": it["date"],
            "genre": it.get("genre"), "tracknumber": normalize_track(str(it.get("tracknumber", 1))),
            "tracktotal": it.get("tracktotal", 1),
            "composer": it.get("composer"), "lyricist": it.get("lyricist"),
            "arranger": it.get("arranger"), "mb": it.get("mb"),
        }
        if not write_one(fp, expected, artist, cover_data, junk, args.dry_run):
            fails += 1
    print(f"done. fails={fails}")
    return 1 if fails else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="mode", required=True)
    a = sub.add_parser("album", help="专辑模式：目录 + meta.json + 封面")
    a.add_argument("--dir", required=True)
    a.add_argument("--meta", required=True)
    a.add_argument("--cover")
    a.add_argument("--artist", required=True)
    a.add_argument("--trim-manifest")
    a.add_argument("--dry-run", action="store_true")
    b = sub.add_parser("files", help="逐文件模式：spec.json（单曲/混合场景）")
    b.add_argument("--spec", required=True)
    b.add_argument("--trim-manifest")
    b.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    return run_album(args) if args.mode == "album" else run_files(args)


if __name__ == "__main__":
    raise SystemExit(main())

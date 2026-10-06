"""强制「无来源不落盘」：meta JSON 的每个非空补充值必须能在 provenance CSV 找到来源。"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import cuelib

CREDIT_FIELDS = ("composer", "lyricist", "arranger")
MB_FIELDS = ("release_id", "release_group_id", "artist_id", "label",
             "country", "catalog_number", "barcode", "matched_title", "source_url")
TOP_KEYS = {"folder", "album", "date", "year", "genre", "musicbrainz", "tracks"}
# 逐轨录音/发行轨 ID 属绑定发行版本体信息（其来源 URL 已记于专辑级 provenance 行），
# 不另立逐轨来源行；其余逐轨键均须有来源行支撑。
TRACK_MB_FIELDS = ("musicbrainz_recording_id", "musicbrainz_releasetrackid")
TRACK_KEYS = {"title"} | set(CREDIT_FIELDS) | set(TRACK_MB_FIELDS)
NOT_FOUND = "未查到"


def load_provenance(csv_path: Path) -> dict[tuple[str, str, str], dict]:
    prov: dict[tuple[str, str, str], dict] = {}
    with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            prov[(row["album_folder"], row["track"], row["field"])] = row
    return prov


def check_album(meta_path: Path, cue_path: Path | None, provenance: dict) -> list[str]:
    """cue_path 为 None 时跳过与 CUE 曲目表的交叉核对（适用于无 CUE 的下载组装库）。"""
    problems: list[str] = []
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    folder = meta.get("folder", "")
    cue = cuelib.parse_cue(cue_path) if cue_path else None

    unknown = set(meta) - TOP_KEYS
    if unknown:
        problems.append(f"unknown top-level keys: {sorted(unknown)}")
    if not meta.get("album") or not meta.get("year"):
        problems.append("album/year missing")

    cue_nums = {str(t.number): t.title for t in cue.tracks} if cue else {}
    meta_tracks = meta.get("tracks", {})
    if cue and set(meta_tracks) != set(cue_nums):
        problems.append(f"track numbers mismatch: meta={sorted(meta_tracks)} cue={sorted(cue_nums)}")
    for num, tmeta in meta_tracks.items():
        unknown_t = set(tmeta) - TRACK_KEYS
        if unknown_t:
            problems.append(f"track {num}: unknown keys {sorted(unknown_t)}")
        if num in cue_nums and tmeta.get("title") != cue_nums[num]:
            problems.append(f"track {num} title mismatch: meta={tmeta.get('title')!r} cue={cue_nums[num]!r}")
        if not tmeta.get("title"):
            problems.append(f"track {num}: title missing")
        for field in CREDIT_FIELDS:
            vals = tmeta.get(field) or []
            key = (folder, num, field)
            prow = provenance.get(key)
            if vals:
                if not prow or not prow.get("source_url") or prow.get("value", "") != "; ".join(map(str, vals)):
                    problems.append(f"track {num} {field}: value without matching source row (key {key})")
            else:
                if not prow or NOT_FOUND not in (prow.get("note") or ""):
                    problems.append(f"track {num} {field}: no value and no '{NOT_FOUND}' provenance row")

    mb = meta.get("musicbrainz") or {}
    unknown_mb = set(mb) - set(MB_FIELDS)
    if unknown_mb:
        problems.append(f"unknown musicbrainz keys: {sorted(unknown_mb)}")
    for field, value in mb.items():
        # source_url 本身即引用指针（不是待证事实），不要求再为它找来源行；
        # 其余字段的来源行 source_url 列即为该 URL。
        if field == "source_url" or value in (None, ""):
            continue
        prow = provenance.get((folder, "*", field))
        if not prow or not prow.get("source_url") or prow.get("value", "") != str(value):
            problems.append(f"musicbrainz.{field}: value '{value}' without matching source row")
    return problems


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--album", action="append", default=[])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--source-root", default=".")
    ap.add_argument("--work-root", default=".")
    args = ap.parse_args(argv)
    work = Path(args.work_root)
    src = Path(args.source_root)
    prov_path = work / "reports" / "metadata-provenance.csv"
    provenance = load_provenance(prov_path) if prov_path.exists() else {}

    metas = sorted(p for p in (work / "meta").glob("*.json") if not p.name.startswith("_")) if args.all else \
        [work / "meta" / f"{f}.json" for f in args.album]
    bad = 0
    for mp in metas:
        folder = mp.stem
        cue_candidates = sorted((src / folder).glob("*.cue"))
        if not mp.exists():
            print(f"[FAIL] {folder}: meta missing")
            bad += 1
            continue
        cue = cue_candidates[0] if len(cue_candidates) == 1 else None
        if cue is None:
            print(f"[INFO] {folder}: 无唯一 CUE（{len(cue_candidates)} 个），跳过曲目表交叉核对")
        problems = check_album(mp, cue, provenance)
        print(f"[{'OK ' if not problems else 'FAIL'}] {folder}")
        for p in problems:
            print(f"    - {p}")
        bad += 1 if problems else 0
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())

# scripts/mb_lookup.py
"""MusicBrainz 候选发行版查询（只读 API；请求间隔 ≥1.1s，尊重 1 req/s 限速）。"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import cuelib

MB_API = "https://musicbrainz.org/ws/2/release"
USER_AGENT = "DavidTaoLocalLibrary/1.0 (personal local library)"
ARTIST_ALIASES = ("陶喆", "David Tao", "Tao Zhe", "陶吉吉")


def parse_candidates(mb_json: dict, artist_names: tuple[str, ...] = ARTIST_ALIASES) -> list[dict]:
    out = []
    for r in mb_json.get("releases", []):
        names = [ac.get("name", "") for ac in r.get("artist-credit", [])]
        if names and not any(n in artist_names for n in names):
            continue
        label_info = (r.get("label-info") or [{}])[0]
        out.append({
            "id": r.get("id"), "title": r.get("title"), "date": r.get("date"),
            "country": r.get("country"), "score": r.get("score"),
            "label": (label_info.get("label") or {}).get("name"),
            "catalog_number": label_info.get("catalog-number"),
            "barcode": r.get("barcode"), "artists": names,
        })
    return out


def fetch(album_title: str, artist: str = "陶喆", limit: int = 10) -> dict:
    query = f'artist:"{artist}" AND release:"{album_title}"'
    url = MB_API + "?" + urllib.parse.urlencode({"query": query, "fmt": "json", "limit": limit})
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--album", action="append", default=[])
    ap.add_argument("--source-root", default=r"E:\陶喆")
    ap.add_argument("--work-root", default=r"E:\音乐库-工作区")
    args = ap.parse_args(argv)
    src = Path(args.source_root)
    work = Path(args.work_root)
    folders = sorted(d.name for d in src.iterdir() if d.is_dir()) if args.all else args.album
    if not folders:
        ap.error("give --all or --album")

    out_path = work / "meta" / "_mb_candidates.json"
    result = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    for i, folder in enumerate(folders):
        cue_files = sorted((src / folder).glob("*.cue"))
        if len(cue_files) != 1:
            print(f"[SKIP] {folder}: cue not unique")
            continue
        cue = cuelib.parse_cue(cue_files[0])
        if i or folder != folders[0]:
            time.sleep(1.1)
        try:
            raw = fetch(cue.album)
        except Exception as e:                      # noqa: BLE001
            print(f"[FAIL] {folder}: {e}")
            continue
        cands = parse_candidates(raw)
        result[folder] = {"album": cue.album, "candidates": cands}
        print(f"[OK ] {folder}: {len(cands)} candidate(s) for 《{cue.album}》")
        for c in cands:
            print(f"      - {c['id']}  {c['date']}  {c['country']}  {c['label']}  score={c['score']}")
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"-> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

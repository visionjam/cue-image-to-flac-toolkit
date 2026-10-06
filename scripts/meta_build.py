# scripts/meta_build.py
"""由「查证 spec + MusicBrainz release detail」编译专辑元数据 JSON 与来源账行。

产物与 check_meta.py 契约对齐：
  - meta JSON：{folder, album, date, year, genre, musicbrainz{...},
                tracks{"N": {title, composer, lyricist, arranger,
                             musicbrainz_recording_id?, musicbrainz_releasetrackid?}}}
  - provenance CSV（追加）：album_folder,track,field,value,source_url,retrieved_on,note
    原则「每值有据」：date/genre/tracklist_check/MB 字段各一行；每轨词曲编曲各一行（带 URL 与注记）

spec 结构（JSON）：
{
  "folder": "2004 - 专辑名", "album": "专辑名", "date": "2004-08-03",
  "genre": ["华语流行"],
  "sources": {"wiki": "https://…", "baike": "https://…"},   # baike 可缺省
  "detail": "detail_xxx.json",        # MusicBrainz release detail 原始响应（本地文件）
  "medium": 1,                        # 可选；缺省取曲目最多的 medium（CD+VCD 混合时显式指定）
  "date_source": "wiki",              # 可选：wiki / baike / mb，缺省 wiki
  "date_note": "…", "genre_note": "…", "label_note": "…", "album_note": "…",
  "crosscheck": "已与百度百科交叉核对（两源一致）",     # 可选：附到每条词曲编曲行的注记前缀
  "tracks": [{"n": 1, "title": "…", "composer": ["…"], "lyricist": ["…"],
              "arranger": ["…"], "note": "仅该轨的补充注记（可选）"}]
}
用法：
  python scripts/meta_build.py --spec spec.json [--meta-dir meta]
         [--prov-csv reports/metadata-provenance.csv] [--library-root <专辑父目录>]
         [--backup-dir <按专辑留档目录>] [--today YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HEADER = ["album_folder", "track", "field", "value", "source_url", "retrieved_on", "note"]


def build(spec: dict, detail: dict, today: str, library_root: Path | None) -> tuple[dict, list[dict]]:
    media = detail.get("media") or []
    if spec.get("medium"):
        m = media[spec["medium"] - 1]
    else:
        m = max(media, key=lambda x: x.get("track-count", 0))
    mb_tracks = {str(t["number"]): t for t in m.get("tracks", [])}
    tr_spec = spec["tracks"]
    assert len(mb_tracks) == len(tr_spec), f"MB tracks {len(mb_tracks)} != spec {len(tr_spec)}"

    li = (detail.get("label-info") or [{}])[0]
    mb = {
        "release_id": detail["id"],
        "release_group_id": detail["release-group"]["id"],
        "artist_id": detail["artist-credit"][0]["artist"]["id"],
        "label": (li.get("label") or {}).get("name"),
        "country": detail.get("country"),
        "catalog_number": li.get("catalog-number"),
        "barcode": detail.get("barcode"),
        "matched_title": detail.get("title"),
        "source_url": f"https://musicbrainz.org/release/{detail['id']}",
    }
    mb.update({k: v for k, v in (spec.get("mb_over") or {}).items()})

    meta = {
        "folder": spec["folder"], "album": spec["album"], "date": spec["date"],
        "year": int(spec["date"][:4]), "genre": spec.get("genre", ["华语流行"]),
        "musicbrainz": mb, "tracks": {},
    }
    rows: list[dict] = []

    def add(track: str, field: str, value, url: str, note: str = "") -> None:
        rows.append({"album_folder": spec["folder"], "track": track, "field": field,
                     "value": value, "source_url": url, "retrieved_on": today, "note": note})

    F = spec["folder"]
    wiki = spec["sources"]["wiki"]
    date_url = spec["sources"].get(spec.get("date_source", "wiki"), wiki)
    add("*", "date", spec["date"], date_url, spec.get("date_note", ""))
    add("*", "genre", "; ".join(meta["genre"]), wiki, spec.get("genre_note", ""))
    check_note = spec.get("album_note", "")
    if library_root is not None:
        n_lib = len(list((library_root / F).glob("*.flac")))
        if n_lib != len(tr_spec):
            check_note = (check_note + "；" if check_note else "") + f"注意：库内文件 {n_lib} 个与曲目数不符"
    add("*", "tracklist_check", f"1-{len(tr_spec)} 与 MusicBrainz 一一对应", mb["source_url"], check_note)
    for k in ("release_id", "release_group_id", "artist_id", "label", "country",
              "catalog_number", "barcode"):
        v = mb.get(k)
        if v:
            add("*", k, str(v), mb["source_url"], "")
        elif k == "label":
            add("*", "label", "", mb["source_url"], spec.get("label_note", "MB 该发行版未提供厂牌"))

    crosscheck = spec.get("crosscheck", "")
    for t in tr_spec:
        num = str(t["n"])
        mbt = mb_tracks[num]
        track_rec: dict = {"title": t["title"]}
        for field in ("composer", "lyricist", "arranger"):
            track_rec[field] = t[field]
        track_rec["musicbrainz_recording_id"] = mbt["recording"]["id"]
        track_rec["musicbrainz_releasetrackid"] = mbt["id"]
        meta["tracks"][num] = track_rec
        for field in ("composer", "lyricist", "arranger"):
            note = t.get(f"{field}_note") or t.get("note", "")
            parts = [p for p in (note, crosscheck) if p]
            add(num, field, "; ".join(t[field]), wiki, "；".join(parts))
    return meta, rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--spec", required=True)
    ap.add_argument("--meta-dir", default="meta")
    ap.add_argument("--prov-csv", default="reports/metadata-provenance.csv")
    ap.add_argument("--library-root", help="专辑目录父路径；提供时核对文件数与曲目数一致")
    ap.add_argument("--backup-dir", help="按专辑留档来源账行（<album>.csv）")
    ap.add_argument("--today")
    args = ap.parse_args(argv)
    spec_path = Path(args.spec)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    detail_path = Path(spec["detail"])
    if not detail_path.is_absolute():
        detail_path = spec_path.parent / detail_path
    detail = json.loads(detail_path.read_text(encoding="utf-8"))
    from datetime import date
    today = args.today or date.today().isoformat()
    library_root = Path(args.library_root) if args.library_root else None

    meta, rows = build(spec, detail, today, library_root)
    meta_dir = Path(args.meta_dir)
    meta_dir.mkdir(parents=True, exist_ok=True)
    out = meta_dir / f"{spec['album']}.json"
    out.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    prov = Path(args.prov_csv)
    prov.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if prov.exists() else "w"
    with prov.open(mode, encoding="utf-8" if mode == "a" else "utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=HEADER)
        if mode == "w":
            w.writeheader()
        w.writerows(rows)
    if args.backup_dir:
        bdir = Path(args.backup_dir)
        bdir.mkdir(parents=True, exist_ok=True)
        with (bdir / f"{spec['album']}.csv").open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=HEADER)
            w.writeheader()
            w.writerows(rows)
    print(f"[OK] {spec['album']}: meta -> {out}  (+{len(rows)} provenance rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

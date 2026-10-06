# scripts/cover_fetch.py
"""封面候选抓取：Cover Art Archive（CAA）与网易云音乐双来源，供人工目检后择一内嵌。

用法：
  python scripts/cover_fetch.py caa-rg <release_group_id> <base>        # CAA release-group 级
  python scripts/cover_fetch.py caa-release <release_id> <base>         # CAA release 级
  python scripts/cover_fetch.py netease-search "<关键词>"                # 网易云专辑候选（含封面 URL）
  python scripts/cover_fetch.py img <url> <out>                          # 通用图片下载
共同参数：--out-dir <目录>（默认 covers）、--proxy http://host:port（可选，境内外网络策略不同）

流程建议：两来源都抓 → 量尺寸 → 人工目检（确认是该专辑官方封面）→ 选方形大图
         → ffmpeg 转码为 JPEG 后交给 tag_write.py 内嵌。
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

UA_MB = "LocalLibraryToolkit/1.0 (personal local library)"
UA_BROWSER = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"
CAA_API = "https://coverartarchive.org"


def _get(url: str, ua: str, proxy: str | None, binary: bool = False):
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    openers = []
    if proxy:
        openers.append(urllib.request.build_opener(
            urllib.request.ProxyHandler({"https": proxy, "http": proxy})))
    openers.append(urllib.request.build_opener())
    last: Exception | None = None
    for opener in openers:
        try:
            with opener.open(req, timeout=60) as resp:
                data = resp.read()
            return data if binary else json.loads(data.decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last = e
    raise last  # type: ignore[misc]


def pick_caa_image(images: list[dict]) -> dict | None:
    """优先 approved 且 front 的图片，其次任一 front，最后第一张。"""
    fronts = [i for i in images if i.get("front")]
    approved = [i for i in fronts if i.get("approved")]
    pool = approved or fronts or images
    return pool[0] if pool else None


def caa(entity: str, mb_id: str, base: str, out_dir: Path, proxy: str | None) -> None:
    d = _get(f"{CAA_API}/{entity}/{mb_id}", UA_MB, proxy)
    (out_dir / f"{base}-rg.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    images = d.get("images", [])
    for im in images[:4]:
        print(f"  CAA image id={im.get('id')} types={im.get('types')} front={im.get('front')} approved={im.get('approved')}")
    im = pick_caa_image(images)
    if not im:
        print("  CAA: 无图片")
        return
    data = _get(im["image"], UA_MB, proxy, binary=True)
    out = out_dir / f"{base}-caa.jpg"
    out.write_bytes(data)
    print(f"  saved {out.name} {len(data)}B  src={im['image'][:90]}")


def parse_netease_search(payload: dict) -> list[dict]:
    albums = (payload.get("result") or {}).get("albums") or []
    out = []
    for al in albums:
        out.append({
            "id": al.get("id"), "name": al.get("name"),
            "artists": "/".join(a.get("name", "") for a in al.get("artists", [])),
            "size": al.get("size"), "pic_url": al.get("picUrl"),
        })
    return out


def netease_search(q: str, proxy: str | None) -> None:
    url = "https://music.163.com/api/search/get/web?" + urllib.parse.urlencode(
        {"s": q, "type": 10, "limit": 8})
    payload = _get(url, UA_BROWSER, proxy)
    rows = parse_netease_search(payload)
    if not rows:
        print("  无候选")
    for r in rows:
        print(f"  id={r['id']}  {r['name']}  [{r['artists']}]  size={r['size']}  pic={r['pic_url']}")


def download_img(url: str, out: Path, proxy: str | None) -> None:
    data = _get(url, UA_BROWSER, proxy, binary=True)
    out.write_bytes(data)
    print(f"  saved {out.name} {len(data)}B")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out-dir", default="covers")
    ap.add_argument("--proxy")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("caa-rg")
    a.add_argument("release_group_id")
    a.add_argument("base")
    b = sub.add_parser("caa-release")
    b.add_argument("release_id")
    b.add_argument("base")
    c = sub.add_parser("netease-search")
    c.add_argument("query")
    d = sub.add_parser("img")
    d.add_argument("url")
    d.add_argument("out")
    args = ap.parse_args(argv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.cmd == "caa-rg":
        caa("release-group", args.release_group_id, args.base, out_dir, args.proxy)
    elif args.cmd == "caa-release":
        caa("release", args.release_id, args.base, out_dir, args.proxy)
    elif args.cmd == "netease-search":
        netease_search(args.query, args.proxy)
    elif args.cmd == "img":
        download_img(args.url, out_dir / args.out, args.proxy)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

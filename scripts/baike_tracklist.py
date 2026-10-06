# scripts/baike_tracklist.py
"""百度百科词条抓取 + 曲目表解析（rowspan 合并单元格自动向下填充）。

人工核对词/曲/编曲时最容易出错的是百科的合并单元格：某行只显示一半署名，
其余靠 rowspan 继承上行。本工具解析时按 HTML 表格语义展开合并，替你填对。

用法：
  python scripts/baike_tracklist.py fetch <url> <out.html> [--proxy http://host:port]
  python scripts/baike_tracklist.py parse <html> [--table N]

fetch：默认直连；需要代理时显式 --proxy。移动版（wapbaike）页面结构稳定，建议为主。
parse：在页面中选出最像「专辑曲目表」的表格（表头含 作词/编曲 等），展开合并单元格后，
       输出「序号 | 曲目 | 作词 | 作曲 | 编曲」行，供与另找的来源逐项对照。
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MOBILE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"


def _int(v, default: int) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


class TableCollector(HTMLParser):
    """收集所有 <table>：tables[i][row][cell] = {text, rowspan, colspan}。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[dict]]] = []
        self._open: list[list[list[dict]]] = []

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            t: list[list[dict]] = []
            self.tables.append(t)
            self._open.append(t)
        elif tag == "tr" and self._open:
            self._open[-1].append([])
        elif tag in ("td", "th") and self._open and self._open[-1] and self._open[-1][-1] is not None:
            a = dict(attrs)
            self._open[-1][-1].append({
                "text": "", "rowspan": _int(a.get("rowspan"), 1),
                "colspan": _int(a.get("colspan"), 1)})

    def handle_endtag(self, tag):
        if tag == "table" and self._open:
            self._open.pop()

    def handle_data(self, data):
        if self._open and self._open[-1] and self._open[-1][-1]:
            row = self._open[-1][-1]
            if row:
                row[-1]["text"] += data


def expand_rowspans(table: list[list[dict]]) -> list[list[dict]]:
    """把带 rowspan 的表格展开为完整网格；被合并的格子在后续行原样出现。"""
    grid: list[list[dict]] = []
    carry: dict[int, tuple[dict, int]] = {}  # col -> (cell, 剩余行数)
    for row in table:
        cells: dict[int, dict] = {}
        for col, (cell, left) in list(carry.items()):
            cells[col] = cell
            if left <= 1:
                del carry[col]
            else:
                carry[col] = (cell, left - 1)
        next_col = 0
        for raw in row:
            while next_col in cells:
                next_col += 1
            cells[next_col] = raw
            if raw["rowspan"] > 1:
                carry[next_col] = (raw, raw["rowspan"] - 1)
            next_col += max(1, raw["colspan"])
        if cells:
            width = max(cells) + 1
            grid.append([cells.get(c, {"text": "", "rowspan": 1, "colspan": 1}) for c in range(width)])
    return grid


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_track_table(html: str) -> tuple[int, list[list[str]], list[str]]:
    """返回 (表号, 数据行, 列名)。找不到合适表格时抛 ValueError。"""
    collector = TableCollector()
    collector.feed(html)
    best = None
    for idx, table in enumerate(collector.tables):
        grid = expand_rowspans(table)
        header = None
        header_row = -1
        for r, row in enumerate(grid):
            texts = [clean(c["text"]) for c in row]
            if any(("作词" in t or "编曲" in t or "曲目" in t) for t in texts) and len(texts) >= 3:
                header, header_row = texts, r
                break
        score = 0
        if header:
            score += 10
        data_rows = 0
        for row in grid[header_row + 1:]:
            if row and clean(row[0]["text"]).isdigit():
                data_rows += 1
        score += data_rows
        if score < 5:
            continue
        if best is None or score > best[0]:
            best = (score, idx, grid, header, header_row)
    if best is None:
        raise ValueError("未找到含曲目表的 <table>（可人工查看原页面或用 --table 指定）")
    _, idx, grid, header, header_row = best

    def col_of(*names: str) -> int | None:
        for c, h in enumerate(header or []):
            if any(n in h for n in names):
                return c
        return None

    c_num = col_of("曲序") or 0
    c_title = col_of("曲目", "歌曲")
    c_lyr = col_of("作词")
    c_comp = col_of("作曲")
    c_arr = col_of("编曲")
    cols = [("序号", c_num), ("曲目", c_title), ("作词", c_lyr), ("作曲", c_comp), ("编曲", c_arr)]
    active = [(name, c) for name, c in cols if c is not None]

    out_rows = []
    for row in grid[header_row + 1:]:
        if not row:
            continue
        first = clean(row[c_num]["text"]) if c_num < len(row) else ""
        if not first.isdigit():
            continue
        out_rows.append([clean(row[c]["text"]) if c is not None and c < len(row) else "-"
                         for _, c in active])
    if not out_rows:
        raise ValueError("表头识别成功但未解析出数据行（可人工查看原页面）")
    return idx, out_rows, [name for name, _ in active]


def fetch(url: str, out: Path, proxy: str | None) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": MOBILE_UA})
    if proxy:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"https": proxy, "http": proxy}))
    else:
        opener = urllib.request.build_opener()
    with opener.open(req, timeout=60) as resp:
        data = resp.read()
    out.write_bytes(data)
    print(f"[OK] {len(data)}B -> {out}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("url")
    f.add_argument("out")
    f.add_argument("--proxy")
    p = sub.add_parser("parse")
    p.add_argument("html")
    args = ap.parse_args(argv)
    if args.cmd == "fetch":
        fetch(args.url, Path(args.out), args.proxy)
        return 0
    html = Path(args.html).read_text(encoding="utf-8", errors="replace")
    idx, rows, cols = parse_track_table(html)
    print(f"# 表 {idx}：{' | '.join(cols)}")
    for row in rows:
        print(" | ".join(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

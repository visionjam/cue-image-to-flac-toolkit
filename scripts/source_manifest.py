# scripts/source_manifest.py
"""源目录清单：证明做种源零改动（相对路径/大小/mtime_ns）。"""
from __future__ import annotations

import sys
from pathlib import Path


def manifest(root: Path) -> list[str]:
    root = Path(root)
    lines = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            st = p.stat()
            lines.append(f"{p.relative_to(root)}\t{st.st_size}\t{st.st_mtime_ns}")
    return lines


def compare(before: list[str], after: list[str]) -> list[str]:
    b, a = set(before), set(after)
    diff = [f"-  {x}" for x in sorted(b - a)] + [f"+  {x}" for x in sorted(a - b)]
    return diff


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2 or argv[0] not in ("before", "after", "compare"):
        print("usage: source_manifest.py before|after|compare <root> [file]")
        return 2
    mode, root = argv[0], Path(argv[1])
    out = Path(argv[2]) if len(argv) > 2 else root.parent / "reports" / f"source-manifest-{mode}.txt"
    if mode == "before":
        out.write_text("\n".join(manifest(root)) + "\n", encoding="utf-8")
        print(f"manifest -> {out} ({len(manifest(root))} files)")
        return 0
    if mode == "after":
        out.write_text("\n".join(manifest(root)) + "\n", encoding="utf-8")
        print(f"manifest -> {out} ({len(manifest(root))} files)")
        return 0
    # compare
    base = Path(argv[2]) if len(argv) > 2 else out.parent
    b = (base / "source-manifest-before.txt").read_text(encoding="utf-8").splitlines()
    a = (base / "source-manifest-after.txt").read_text(encoding="utf-8").splitlines()
    diff = compare(b, a)
    print("\n".join(diff) if diff else "NO CHANGES: source untouched")
    return 1 if diff else 0


if __name__ == "__main__":
    raise SystemExit(main())

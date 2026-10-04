# scripts/cuelib.py
"""CUE (EAC 格式, GBK 编码) 解析与命名工具。纯函数，无音频 I/O。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

CD_FRAME_SAMPLES = 588  # 44100 / 75


class CueParseError(ValueError):
    pass


@dataclass
class CueTrack:
    number: int
    title: str
    performer: str | None
    start_samples: int


@dataclass
class CueSheet:
    album: str
    artist: str
    date: str | None
    genre: str | None
    tracks: list[CueTrack]
    file_name: str | None = None


_TIME_RE = re.compile(r"^(\d{1,3}):(\d{2}):(\d{2})$")
_KEYVAL_RE = re.compile(r"^([A-Za-z]+)\s+(.*)$")


def cue_time_to_samples(t: str) -> int:
    m = _TIME_RE.match(t.strip())
    if not m:
        raise CueParseError(f"bad cue time: {t!r}")
    mm, ss, ff = (int(g) for g in m.groups())
    if ss > 59 or ff > 74:
        raise CueParseError(f"bad cue time: {t!r}")
    return (mm * 60 * 75 + ss * 75 + ff) * CD_FRAME_SAMPLES


def _unquote(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    return s


def parse_cue_bytes(data: bytes) -> CueSheet:
    text = data.decode("gb18030")
    album = artist = date = genre = file_name = None
    raw_tracks: list[dict] = []
    cur: dict | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        m = _KEYVAL_RE.match(line)
        if not m:
            continue
        key, val = m.group(1).upper(), m.group(2)
        val = _unquote(val)

        if key == "REM":
            body = val
            bu = body.upper()
            if bu.startswith("DATE"):
                date = body[4:].strip() or None
            elif bu.startswith("GENRE"):
                genre = body[5:].strip() or None
        elif key == "FILE":
            fm = re.match(r'^"(.*)"\s', val + " ") or re.match(r'^(\S+)', val)
            file_name = fm.group(1) if fm else None
        elif key == "TRACK":
            tnum = int(val.split()[0])
            cur = {"number": tnum, "title": None, "performer": None, "index01": None}
            raw_tracks.append(cur)
        elif key == "TITLE":
            if cur is None:
                album = val
            else:
                cur["title"] = val
        elif key == "PERFORMER":
            if cur is None:
                artist = val
            elif cur["performer"] is None:
                cur["performer"] = val
        elif key == "INDEX" and cur is not None:
            parts = val.split()
            if len(parts) >= 2 and parts[0] == "01" and cur["index01"] is None:
                cur["index01"] = parts[1]
        # ISRC / FLAGS / SONGWRITER 等忽略

    if not raw_tracks:
        raise CueParseError("no TRACK entries found")

    tracks: list[CueTrack] = []
    for t in raw_tracks:
        if t["index01"] is None:
            raise CueParseError(f"track {t['number']} missing INDEX 01")
        tracks.append(
            CueTrack(
                number=t["number"],
                title=t["title"] or f"Track {t['number']}",
                performer=t["performer"],
                start_samples=cue_time_to_samples(t["index01"]),
            )
        )
    starts = [t.start_samples for t in tracks]
    if starts != sorted(starts) or len(set(starts)) != len(starts):
        raise CueParseError(f"track start times not strictly increasing: {starts}")

    return CueSheet(
        album=album or "",
        artist=artist or "",
        date=date,
        genre=genre,
        tracks=tracks,
        file_name=file_name,
    )


def parse_cue(path: str | Path) -> CueSheet:
    return parse_cue_bytes(Path(path).read_bytes())


_ILLEGAL = {"\\": "＼", "/": "／", ":": "：", "*": "＊", "?": "？",
            '"': "＂", "<": "＜", ">": "＞", "|": "｜"}
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}


def sanitize_filename(name: str) -> str:
    out = "".join(_ILLEGAL.get(ch, ch) for ch in name).strip().rstrip(". ")
    if not out:
        out = "_"
    if out.split(".")[0].upper() in _RESERVED:
        out = "_" + out
    return out


def resolve_date(cue_date: str | None, folder_name: str) -> str | None:
    """日期回退链：CUE REM DATE → 文件夹日期前缀 → 文件夹年份。"""
    if cue_date:
        return cue_date
    m = re.match(r"^(\d{4})\.(\d{2})\.(\d{2})", folder_name)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"^(\d{4})", folder_name)
    return m.group(1) if m else None


def album_dir_name(year: int | None, album: str) -> str:
    name = sanitize_filename(album)
    return f"{year} - {name}" if year else name


def track_file_name(number: int, title: str) -> str:
    return f"{number:02d} - {sanitize_filename(title)}.flac"

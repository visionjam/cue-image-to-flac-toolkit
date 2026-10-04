# 陶喆专辑 FLAC 音乐库 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `E:\陶喆` 的 8 张整轨 APE/FLAC+CUE 专辑无损拆分为 107 首单曲 FLAC，写入完整标签（基础+查证类元数据）与内嵌封面，输出到 `E:\音乐库\陶喆\`，全程不触碰做种中的源目录。

**Architecture:** Python 脚本流水线：`cuelib.py`（纯函数解析 GBK CUE 与命名）→ `audio.py`（ffmpeg/ffprobe/WAV 封装，采样级切片）→ `convert.py`（单专辑编排：解码整轨→切片→编码→mutagen 写标签封面→逐轨 PCM MD5 校验→原子移动入成品目录）。元数据查证（MusicBrainz + 逐曲词曲作者）先落盘为 `meta\<专辑>.json`（人工可审阅），转换脚本只读该文件。`verify.py` 做全库独立校验，`check_meta.py` 强制「无来源不落盘」，`source_manifest.py` 证明源目录零改动。

**Tech Stack:** Python ≥3.10（本机 3.13/3.14）、ffmpeg/ffprobe（已在 PATH，gyan full build）、mutagen、pytest、urllib（stdlib，MusicBrainz 查询）、git（工作区版本化）。

**设计文档:** `E:\音乐库-工作区\docs\2026-10-04-david-tao-flac-library-design.md`

## Global Constraints

以下约束适用于每一个任务，不再重复：

- **源目录 `E:\陶喆` 全程只读**（正在做种）：禁止任何写入、移动、重命名、改属性。
- **所有写入仅发生在** `E:\音乐库\` 与 `E:\音乐库-工作区\`。
- 输出路径：`E:\音乐库\陶喆\<年份> - <专辑名>\NN - 曲名.flac`，每专辑附 `cover.jpg`。
- 音频参数保持 44.1kHz/16bit/双声道，**不重采样、不做增益处理**；源参数不符时中止该专辑并报告。
- 文件名净化：`\ / : * ? " < > |` 替换为对应全角字符（`＼ ／ ： ＊ ？ ＂ ＜ ＞ ｜`）；去首尾空格、去结尾句点；**标签内容保持原样不净化**。
- CUE 按 **gb18030** 解码；轨起点用 **INDEX 01**；INDEX 00→01 间隙归前一首；末轨终点=文件末尾。
- 采样换算（整数精确）：`samples = (MM*60*75 + SS*75 + FF) * 588`（因 44100/75=588）。
- 元数据**只写可查证的，查不到留空，绝不编造**；每个写入值在 `reports\metadata-provenance.csv` 有来源行。
- 逐轨无损校验：输出 FLAC 解码 PCM 的 MD5 == 源 WAV 对应区段 PCM 的 MD5。
- 所有脚本 stdout 强制 UTF-8（`sys.stdout.reconfigure(encoding='utf-8')`），避免 Windows 控制台 GBK 乱码。
- 工作区目录约定：`scripts\` 脚本、`scripts\tests\` 测试、`meta\` 查证数据、`temp\` 临时文件、`logs\` 日志、`reports\` 报告。

---

### Task 1: 工作区初始化（git + 依赖 + 环境记录）

**Files:**
- Create: `E:\音乐库-工作区\.gitignore`
- Create: `E:\音乐库-工作区\logs\env.txt`（环境记录，含 logs 目录）

**Interfaces:**
- Consumes: 无
- Produces: 已初始化的 git 仓库与可用的 `python -m pytest`、`import mutagen`

- [ ] **Step 1: 初始化 git 仓库**

```bash
cd "E:/音乐库-工作区" && git init 2>&1 | tail -1
git -C "E:/音乐库-工作区" config user.email >/dev/null 2>&1 || git -C "E:/音乐库-工作区" config user.email "local@localhost"
git -C "E:/音乐库-工作区" config user.name >/dev/null 2>&1 || git -C "E:/音乐库-工作区" config user.name "local"
```

（若全局 git 身份已配置，保持全局不动；仅缺省时设仓库级。）

- [ ] **Step 2: 写 .gitignore**

```gitignore
temp/
logs/
__pycache__/
*.pyc
.venv/
venv/
.pytest_cache/
```

- [ ] **Step 3: 安装依赖并验证**

```bash
cd "E:/音乐库-工作区" && python -m pip install mutagen pytest 2>&1 | tail -2
python -c "import sys, mutagen, pytest; print(sys.version); print('mutagen', mutagen.version); print('pytest', pytest.__version__)"
```

Expected: 三行输出均正常（Python ≥3.10）。若 pip 被拦（externally-managed 等），改用：`python -m venv "E:/音乐库-工作区/venv" && "E:/音乐库-工作区/venv/Scripts/python" -m pip install mutagen pytest`，之后所有命令用 venv 解释器替代 `python`。若两种方式都无法安装（无网络等），暂停并报告——备用方案（ffmpeg 原生打标签）需先修订本计划再执行。

- [ ] **Step 4: 记录环境到 logs\env.txt**

```bash
cd "E:/音乐库-工作区" && { python -c "import sys; print(sys.version)"; ffmpeg -version | head -1; ffprobe -version | head -1; git --version; } | tee logs/env.txt
```

- [ ] **Step 5: 首次提交**

```bash
cd "E:/音乐库-工作区" && git add -A && git commit -m "chore: init workspace (gitignore, env record); design doc

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: `cuelib.py` — CUE 解析与命名（纯函数，TDD）

**Files:**
- Create: `E:\音乐库-工作区\scripts\cuelib.py`
- Create: `E:\音乐库-工作区\scripts\tests\conftest.py`
- Create: `E:\音乐库-工作区\scripts\tests\test_cuelib.py`

**Interfaces:**
- Consumes: 无（纯 stdlib）
- Produces（后续任务依赖的精确签名）:
  - `cue_time_to_samples(t: str) -> int`
  - `parse_cue_bytes(data: bytes) -> CueSheet`、`parse_cue(path: str|Path) -> CueSheet`
  - `@dataclass CueTrack(number: int, title: str, performer: str|None, start_samples: int)`
  - `@dataclass CueSheet(album: str, artist: str, date: str|None, genre: str|None, tracks: list[CueTrack], file_name: str|None)`
  - `sanitize_filename(name: str) -> str`
  - `resolve_date(cue_date: str|None, folder_name: str) -> str|None`
  - `album_dir_name(year: int|None, album: str) -> str`
  - `track_file_name(number: int, title: str) -> str`
  - `class CueParseError(ValueError)`

- [ ] **Step 1: 写 conftest.py（让测试能 import 同级 scripts 模块）**

```python
# scripts/tests/conftest.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
```

- [ ] **Step 2: 写失败测试**

```python
# scripts/tests/test_cuelib.py
import pytest
from cuelib import (
    CueParseError, album_dir_name, cue_time_to_samples, parse_cue_bytes,
    resolve_date, sanitize_filename, track_file_name,
)

SAMPLE = '''REM GENRE R&B
REM DATE 2002-08-09
PERFORMER "陶喆"
TITLE "黑色柳丁"
FILE "陶喆.-.[黑色柳丁].专辑.台湾原版.(APE).ape" WAVE
  TRACK 01 AUDIO
    TITLE "黑色柳丁(Black Tangerine)"
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    TITLE "飞机场的 10:30"
    INDEX 00 03:20:00
    INDEX 01 03:20:10
  TRACK 03 AUDIO
    TITLE "Dear God"
    PERFORMER "陶喆"
    INDEX 01 04:15:20
'''

def test_parse_gb18030_full():
    cue = parse_cue_bytes(SAMPLE.encode("gb18030"))
    assert cue.album == "黑色柳丁"
    assert cue.artist == "陶喆"
    assert cue.date == "2002-08-09"
    assert cue.genre == "R&B"
    assert [t.number for t in cue.tracks] == [1, 2, 3]
    assert cue.tracks[1].title == "飞机场的 10:30"
    assert cue.tracks[2].performer == "陶喆"

def test_index01_used_00_ignored():
    cue = parse_cue_bytes(SAMPLE.encode("gb18030"))
    assert cue.tracks[1].start_samples == cue_time_to_samples("03:20:10")

def test_cue_time_to_samples_exact():
    assert cue_time_to_samples("00:00:00") == 0
    assert cue_time_to_samples("04:15:20") == 19145 * 588          # 4*60*75+15*75+20
    assert cue_time_to_samples("00:00:01") == 588

def test_missing_index01_raises():
    bad = SAMPLE.replace("INDEX 01 04:15:20", "INDEX 00 04:15:20")
    with pytest.raises(CueParseError):
        parse_cue_bytes(bad.encode("gb18030"))

def test_non_increasing_starts_raise():
    bad = SAMPLE.replace("INDEX 01 04:15:20", "INDEX 01 03:00:00")
    with pytest.raises(CueParseError):
        parse_cue_bytes(bad.encode("gb18030"))

def test_sanitize_filename():
    assert sanitize_filename('飞机场的 10:30') == '飞机场的 10：30'
    assert sanitize_filename('a/b\\c*d?e"f<g>h|i') == 'a／b＼c＊d？e＂f＜g＞h｜i'
    assert sanitize_filename('trailing. ') == 'trailing'
    assert sanitize_filename('CON') == '_CON'
    assert sanitize_filename('...') == '_'

def test_resolve_date_fallback_chain():
    assert resolve_date("2002-08-09", "2002.08.09 - 黑色柳丁") == "2002-08-09"
    assert resolve_date(None, "1997.12.06 - DAVID.TAO") == "1997-12-06"
    assert resolve_date(None, "1997 - x") == "1997"
    assert resolve_date(None, "no-date") is None

def test_album_dir_and_track_names():
    assert album_dir_name(2002, "黑色柳丁") == "2002 - 黑色柳丁"
    assert album_dir_name(None, "黑色柳丁") == "黑色柳丁"
    assert track_file_name(1, '飞机场的 10:30') == '01 - 飞机场的 10：30.flac'
```

- [ ] **Step 3: 运行测试确认失败**

Run: `cd "E:/音乐库-工作区" && python -m pytest scripts/tests/test_cuelib.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'cuelib'`）

- [ ] **Step 4: 实现 cuelib.py**

```python
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
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd "E:/音乐库-工作区" && python -m pytest scripts/tests/test_cuelib.py -v`
Expected: 8 passed

- [ ] **Step 6: 提交**

```bash
cd "E:/音乐库-工作区" && git add scripts/ && git commit -m "feat(cuelib): GBK CUE parser, sample-exact time conversion, filename sanitization

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: `audio.py` — ffmpeg/ffprobe/WAV 封装（TDD，合成夹具）

**Files:**
- Create: `E:\音乐库-工作区\scripts\audio.py`
- Create: `E:\音乐库-工作区\scripts\tests\test_audio.py`

**Interfaces:**
- Consumes: 无（仅 stdlib + ffmpeg/ffprobe）
- Produces:
  - `class AudioError(RuntimeError)`
  - `decode_to_wav(src: str|Path, dst: str|Path) -> None`（`-map 0:a:0 -c:a pcm_s16le`，失败抛 AudioError 含 stderr 尾部）
  - `wav_info(path) -> tuple[int, int, int, int]`（frames, rate, channels, sampwidth）
  - `slice_wav(src_wav, start_frame: int, count: int, dst_wav) -> None`（帧精确，越界抛 AudioError）
  - `encode_flac(wav_path, flac_path, level: int = 8) -> None`（`-map_metadata -1 -c:a flac -compression_level 8`）
  - `wav_segment_md5(path, start_frame: int, count: int) -> str`
  - `flac_pcm_md5(path) -> str`（解码为 pcm_s16le，取 `-f md5` 输出）
  - `probe_audio(path) -> dict`（codec/sample_rate/channels/bits_per_raw_sample/duration）

- [ ] **Step 1: 写失败测试（夹具用 ffmpeg 现场生成）**

```python
# scripts/tests/test_audio.py
import subprocess

import pytest
from audio import (
    AudioError, decode_to_wav, encode_flac, flac_pcm_md5, probe_audio,
    slice_wav, wav_info, wav_segment_md5,
)

FFMPEG = "ffmpeg"


@pytest.fixture
def fixture_wav(tmp_path):
    """10 秒 44.1k/16bit/2ch 确定性噪声 WAV。"""
    wav = tmp_path / "full.wav"
    subprocess.run(
        [FFMPEG, "-v", "error", "-y", "-f", "lavfi",
         "-i", "anoisesrc=d=10:c=pink:seed=42", "-ac", "2", "-ar", "44100",
         "-c:a", "pcm_s16le", str(wav)],
        check=True,
    )
    return wav


def test_wav_info(fixture_wav):
    frames, rate, ch, sw = wav_info(fixture_wav)
    assert (frames, rate, ch, sw) == (441000, 44100, 2, 2)


def test_flac_roundtrip_md5(fixture_wav, tmp_path):
    flac = tmp_path / "a.flac"
    encode_flac(fixture_wav, flac)
    assert flac_pcm_md5(flac) == wav_segment_md5(fixture_wav, 0, 441000)


def test_slice_then_encode_matches_segment(fixture_wav, tmp_path):
    seg = tmp_path / "seg.wav"
    slice_wav(fixture_wav, 154350, 154350, seg)      # 3.5s 起，3.5s 长
    assert wav_info(seg)[0] == 154350
    flac = tmp_path / "seg.flac"
    encode_flac(seg, flac)
    assert flac_pcm_md5(flac) == wav_segment_md5(fixture_wav, 154350, 154350)


def test_slice_beyond_eof_raises(fixture_wav, tmp_path):
    with pytest.raises(AudioError):
        slice_wav(fixture_wav, 440000, 5000, tmp_path / "x.wav")


def test_decode_bad_file_raises(tmp_path):
    bad = tmp_path / "bad.ape"
    bad.write_bytes(b"not audio")
    with pytest.raises(AudioError):
        decode_to_wav(bad, tmp_path / "x.wav")


def test_probe_flac(fixture_wav, tmp_path):
    flac = tmp_path / "a.flac"
    encode_flac(fixture_wav, flac)
    info = probe_audio(flac)
    assert info["codec_name"] == "flac"
    assert int(info["sample_rate"]) == 44100
    assert int(info["channels"]) == 2
    assert abs(float(info["duration"]) - 10.0) < 0.01
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd "E:/音乐库-工作区" && python -m pytest scripts/tests/test_audio.py -v`
Expected: FAIL（`No module named 'audio'`）

- [ ] **Step 3: 实现 audio.py**

```python
# scripts/audio.py
"""ffmpeg / ffprobe / WAV 封装：解码、帧精确切片、编码、PCM MD5、探测。"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
import wave
from pathlib import Path

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"
_CHUNK_FRAMES = 1 << 20


class AudioError(RuntimeError):
    pass


def _run(cmd: list[str], tool: str) -> subprocess.CompletedProcess:
    p = subprocess.run([str(c) for c in cmd], capture_output=True)
    if p.returncode != 0:
        tail = p.stderr.decode("utf-8", "replace").strip().splitlines()[-6:]
        raise AudioError(f"{tool} failed (rc={p.returncode}): " + " | ".join(tail))
    return p


def decode_to_wav(src: str | Path, dst: str | Path) -> None:
    _run([FFMPEG, "-v", "error", "-y", "-i", src, "-map", "0:a:0",
          "-c:a", "pcm_s16le", "-f", "wav", dst], "ffmpeg(decode)")


def wav_info(path: str | Path) -> tuple[int, int, int, int]:
    with wave.open(str(path), "rb") as w:
        return w.getnframes(), w.getframerate(), w.getnchannels(), w.getsampwidth()


def slice_wav(src_wav: str | Path, start_frame: int, count: int, dst_wav: str | Path) -> None:
    with wave.open(str(src_wav), "rb") as ws, wave.open(str(dst_wav), "wb") as wd:
        frame_size = ws.getnchannels() * ws.getsampwidth()
        if start_frame < 0 or count <= 0 or start_frame + count > ws.getnframes():
            raise AudioError(f"slice out of range: start={start_frame} count={count} total={ws.getnframes()}")
        wd.setnchannels(ws.getnchannels())
        wd.setsampwidth(ws.getsampwidth())
        wd.setframerate(ws.getframerate())
        ws.setpos(start_frame)
        remaining = count
        while remaining > 0:
            chunk = ws.readframes(min(remaining, _CHUNK_FRAMES))
            if not chunk:
                raise AudioError(f"unexpected EOF while slicing {src_wav}")
            wd.writeframes(chunk)
            remaining -= len(chunk) // frame_size


def encode_flac(wav_path: str | Path, flac_path: str | Path, level: int = 8) -> None:
    _run([FFMPEG, "-v", "error", "-y", "-i", wav_path, "-map_metadata", "-1",
          "-c:a", "flac", "-compression_level", str(level), flac_path], "ffmpeg(flac)")


def wav_segment_md5(path: str | Path, start_frame: int, count: int) -> str:
    h = hashlib.md5()
    with wave.open(str(path), "rb") as w:
        frame_size = w.getnchannels() * w.getsampwidth()
        if start_frame + count > w.getnframes():
            raise AudioError(f"segment out of range for {path}")
        w.setpos(start_frame)
        remaining = count
        while remaining > 0:
            chunk = w.readframes(min(remaining, _CHUNK_FRAMES))
            if not chunk:
                raise AudioError(f"unexpected EOF hashing {path}")
            h.update(chunk)
            remaining -= len(chunk) // frame_size
    return h.hexdigest()


_MD5_RE = re.compile(rb"MD5=([0-9a-f]{32})")


def flac_pcm_md5(path: str | Path) -> str:
    p = _run([FFMPEG, "-v", "error", "-i", path, "-c:a", "pcm_s16le", "-f", "md5", "-"],
             "ffmpeg(md5)")
    m = _MD5_RE.search(p.stdout)
    if not m:
        raise AudioError(f"cannot parse md5 output for {path}")
    return m.group(1).decode("ascii")


def probe_audio(path: str | Path) -> dict:
    p = _run([FFPROBE, "-v", "error", "-show_entries",
              "stream=codec_name,sample_rate,channels,bits_per_raw_sample:format=duration",
              "-of", "json", path], "ffprobe")
    import json
    data = json.loads(p.stdout.decode("utf-8", "replace"))
    info = (data.get("streams") or [{}])[0]
    info["duration"] = (data.get("format") or {}).get("duration")
    return info


if __name__ == "__main__":
    sys.exit("library module; not runnable")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd "E:/音乐库-工作区" && python -m pytest scripts/tests/test_audio.py -v`
Expected: 6 passed

- [ ] **Step 5: 提交**

```bash
cd "E:/音乐库-工作区" && git add scripts/audio.py scripts/tests/test_audio.py && git commit -m "feat(audio): ffmpeg wrappers with frame-exact wav slicing and PCM md5 verification

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: `convert.py` — 单专辑流水线（端到端 TDD，合成专辑）

**Files:**
- Create: `E:\音乐库-工作区\scripts\convert.py`
- Create: `E:\音乐库-工作区\scripts\tests\test_convert_e2e.py`

**Interfaces:**
- Consumes: `cuelib`（Task 2 全部签名）、`audio`（Task 3 全部签名）、mutagen
- Produces:
  - `class AlbumError(RuntimeError)`
  - `convert_album(folder_name: str, *, source_root: Path, output_root: Path, work_root: Path, meta_dir: Path) -> dict`
    返回 `{"folder", "status": "ok", "tracks": n, "files": [相对输出路径...], "md5": [逐轨 md5...]}`；失败抛 `AlbumError`
  - `main(argv=None) -> int`；CLI：`--album <名> [可重复] | --all`、`--source-root`（默认 `E:\陶喆`）、`--output-root`（默认 `E:\音乐库\陶喆`）、`--work-root`（默认 `E:\音乐库-工作区`）
  - 单专辑运行结果 JSON 写到 `<work_root>\logs\convert-<folder>.json`

- [ ] **Step 1: 写端到端失败测试（合成一张 3 轨「专辑」）**

```python
# scripts/tests/test_convert_e2e.py
import subprocess
from pathlib import Path

import pytest
from mutagen.flac import FLAC

import convert

CUE_TEXT = '''REM DATE 2005-01-21
PERFORMER "陶喆"
TITLE "合成测试专辑"
FILE "album.flac" WAVE
  TRACK 01 AUDIO
    TITLE "第一首"
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    TITLE "飞机场的 10:30"
    INDEX 01 00:03:30
  TRACK 03 AUDIO
    TITLE "Third / Song"
    INDEX 01 00:06:60
'''   # 轨界（采样级）：0 / 149940 / 299880（00:03:30=255帧、00:06:60=510帧，每帧588采样）


@pytest.fixture
def synthetic_source(tmp_path):
    src = tmp_path / "source" / "2005.01.21 - 合成测试专辑"
    src.mkdir(parents=True)
    wav = tmp_path / "full.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                    "-i", "anoisesrc=d=10:c=pink:seed=7", "-ac", "2", "-ar", "44100",
                    "-c:a", "pcm_s16le", str(wav)], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav),
                    "-c:a", "flac", str(src / "album.flac")], check=True)
    (src / "album.cue").write_bytes(CUE_TEXT.encode("gb18030"))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                    "-i", "color=c=red:s=300x300:d=1", "-frames:v", "1",
                    str(src / "cover.jpg")], check=True)
    return tmp_path


def run_convert(tmp_path, album="2005.01.21 - 合成测试专辑", meta=None):
    if meta is not None:
        (tmp_path / "meta").mkdir(exist_ok=True)
        (tmp_path / "meta" / f"{album}.json").write_text(meta, encoding="utf-8")
    return convert.convert_album(
        album,
        source_root=tmp_path / "source",
        output_root=tmp_path / "out",
        work_root=tmp_path / "work",
        meta_dir=tmp_path / "meta",
    )


def test_convert_writes_tracks_tags_cover(synthetic_source):
    tmp_path = synthetic_source
    result = run_convert(tmp_path)
    assert result["status"] == "ok"
    outdir = tmp_path / "out" / "2005 - 合成测试专辑"
    files = sorted(p.name for p in outdir.glob("*.flac"))
    assert files == ["01 - 第一首.flac", "02 - 飞机场的 10：30.flac", "03 - Third ／ Song.flac"]
    assert (outdir / "cover.jpg").exists()

    f = FLAC(str(outdir / "02 - 飞机场的 10：30.flac"))
    assert f["ARTIST"][0] == "陶喆"
    assert f["ALBUMARTIST"][0] == "陶喆"
    assert f["ALBUM"][0] == "合成测试专辑"
    assert f["TITLE"][0] == "飞机场的 10:30"          # 标签不净化
    assert f["TRACKNUMBER"][0] == "2"
    assert f["TRACKTOTAL"][0] == "3"
    assert f["DATE"][0] == "2005-01-21"
    assert len(f.pictures) == 1

    # 采样级时长：154350/154350/132300 帧
    import wave
    from audio import probe_audio
    assert abs(float(probe_audio(outdir / "01 - 第一首.flac")["duration"]) - 3.4) < 0.01
    assert abs(float(probe_audio(outdir / "03 - Third ／ Song.flac")["duration"]) - 3.2) < 0.01
    # 临时目录已清理
    assert not (tmp_path / "work" / "temp" / "2005.01.21 - 合成测试专辑").exists()


def test_convert_merges_meta_json(synthetic_source):
    tmp_path = synthetic_source
    meta = '''{
      "folder": "2005.01.21 - 合成测试专辑", "album": "合成测试专辑",
      "date": "2005-01-21", "year": 2005,
      "musicbrainz": {"release_id": "abc-123", "label": "Test Records", "country": "TW"},
      "tracks": {"2": {"composer": ["陶喆"], "lyricist": ["娃娃"]}}
    }'''
    result = run_convert(tmp_path, meta=meta)
    assert result["status"] == "ok"
    outdir = tmp_path / "out" / "2005 - 合成测试专辑"
    f2 = FLAC(str(outdir / "02 - 飞机场的 10：30.flac"))
    assert f2["MUSICBRAINZ_ALBUMID"][0] == "abc-123"
    assert f2["LABEL"][0] == "Test Records"
    assert f2["RELEASECOUNTRY"][0] == "TW"
    assert f2["COMPOSER"][0] == "陶喆"
    assert f2["LYRICIST"][0] == "娃娃"
    f1 = FLAC(str(outdir / "01 - 第一首.flac"))
    assert "COMPOSER" not in f1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd "E:/音乐库-工作区" && python -m pytest scripts/tests/test_convert_e2e.py -v`
Expected: FAIL（`No module named 'convert'`）

- [ ] **Step 3: 实现 convert.py**

```python
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


def convert_album(folder_name: str, *, source_root: Path, output_root: Path,
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd "E:/音乐库-工作区" && python -m pytest scripts/tests/test_convert_e2e.py -v`
Expected: 2 passed（首轮若失败，检查轨界换算：00:03:30=(3*75+30)*588=149940、00:06:60=(6*75+60)*588=299880。）

- [ ] **Step 5: 全量回归**

Run: `cd "E:/音乐库-工作区" && python -m pytest scripts/tests -v`
Expected: 全部通过（16 个）

- [ ] **Step 6: 提交**

```bash
cd "E:/音乐库-工作区" && git add scripts/convert.py scripts/tests/test_convert_e2e.py && git commit -m "feat(convert): per-album pipeline with sample-exact split, tags, cover, md5 verify

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: `verify.py` — 全库独立校验 + 清单 + `source_manifest.py`

**Files:**
- Create: `E:\音乐库-工作区\scripts\verify.py`
- Create: `E:\音乐库-工作区\scripts\source_manifest.py`
- Create: `E:\音乐库-工作区\scripts\tests\test_verify.py`

**Interfaces:**
- Consumes: `cuelib`、`audio`（签名同前）、`convert.convert_album`（仅测试用，构造已转换输出）
- Produces:
  - `verify_album(folder_name, *, source_root, output_root, work_root, meta_dir) -> dict`（`{"folder", "status": "ok"|"fail", "problems": [str...], "tracks": n}`；独立重新解码源、逐轨 MD5 比对、格式/标签/封面/补充字段检查、总样本数核对）
  - `main(argv=None) -> int`：`--album/--all`、`--tracklist-out`（默认 `<work>\reports\tracklist.csv`）、`--report-out`（默认 `<work>\reports\verification-<日期>.md`）
  - `source_manifest.manifest(root: Path) -> list[str]`；CLI：`before|after|compare <root>`（compare 读到差异则 exit 1）

- [ ] **Step 1: 写失败测试**

```python
# scripts/tests/test_verify.py
import json

import convert
import verify
import source_manifest
from test_convert_e2e import synthetic_source  # noqa: F401  pytest 会把 tests 目录加入 sys.path


def _prepared(tmp_path):
    convert.convert_album(
        "2005.01.21 - 合成测试专辑",
        source_root=tmp_path / "source", output_root=tmp_path / "out",
        work_root=tmp_path / "work", meta_dir=tmp_path / "meta",
    )
    return tmp_path


def test_verify_ok(synthetic_source):
    tmp = _prepared(synthetic_source)
    rep = verify.verify_album(
        "2005.01.21 - 合成测试专辑",
        source_root=tmp / "source", output_root=tmp / "out",
        work_root=tmp / "work", meta_dir=tmp / "meta",
    )
    assert rep["status"] == "ok", rep["problems"]
    assert rep["tracks"] == 3


def test_verify_detects_corruption(synthetic_source):
    tmp = _prepared(synthetic_source)
    victim = tmp / "out" / "2005 - 合成测试专辑" / "02 - 飞机场的 10：30.flac"
    data = bytearray(victim.read_bytes())
    data[len(data) // 2] ^= 0xFF
    victim.write_bytes(bytes(data))
    rep = verify.verify_album(
        "2005.01.21 - 合成测试专辑",
        source_root=tmp / "source", output_root=tmp / "out",
        work_root=tmp / "work", meta_dir=tmp / "meta",
    )
    assert rep["status"] == "fail"
    assert any("02" in p for p in rep["problems"])


def test_manifest_detects_change(tmp_path):
    root = tmp_path / "src"
    root.mkdir()
    (root / "a.txt").write_text("hello")
    before = source_manifest.manifest(root)
    assert source_manifest.compare(before, source_manifest.manifest(root)) == []
    (root / "a.txt").write_text("changed!")
    assert source_manifest.compare(before, source_manifest.manifest(root)) != []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd "E:/音乐库-工作区" && python -m pytest scripts/tests/test_verify.py -v`
Expected: FAIL（`No module named 'verify'`）

- [ ] **Step 3: 实现 source_manifest.py 与 verify.py**

```python
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
```

```python
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
    if sum(counts) != nframes:
        problems.append("sample count mismatch")

    rows = []
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd "E:/音乐库-工作区" && python -m pytest scripts/tests/test_verify.py -v`
Expected: 3 passed

- [ ] **Step 5: 全量回归 + 提交**

```bash
cd "E:/音乐库-工作区" && python -m pytest scripts/tests -v
git add scripts/ && git commit -m "feat(verify): library-wide md5/tag/cover verification, tracklist export, source manifest

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: `check_meta.py` — 元数据「无来源不落盘」强校验（TDD）

**Files:**
- Create: `E:\音乐库-工作区\scripts\check_meta.py`
- Create: `E:\音乐库-工作区\scripts\tests\test_check_meta.py`

**Interfaces:**
- Consumes: `cuelib.parse_cue`、pandas 无（纯 stdlib csv/json）
- Produces:
  - `check_album(meta_path: Path, cue_path: Path, provenance: dict[tuple, dict]) -> list[str]`（返回问题列表，空=通过）
  - `load_provenance(csv_path: Path) -> dict[tuple[str, str, str], dict]`（键 = (folder, track, field)）
  - `main(argv=None) -> int`：`--album <folder> [可重复] | --all`（对 `meta\*.json` 全查）
  - Provenance CSV 列：`album_folder,track,field,value,source_url,retrieved_on,note`；track 用 `*` 表示专辑级

校验规则（不通过则问题非空）:
1. meta JSON 只允许已知键：`folder, album, date, year, musicbrainz{release_id,release_group_id,artist_id,label,country,catalog_number,barcode,matched_title,source_url}, tracks{<n>:{title,composer,lyricist,arranger}}`
2. `tracks` 键集合 == CUE 轨号集合；每轨 title 与 CUE 标题不一致 → 问题
3. 每个 track 的 composer/lyricist/arranger：有非空值 → provenance 中必须存在同值行且 source_url 非空；无值/缺失 → provenance 中必须存在 `note` 含「未查到」的行
4. musicbrainz 各非空字段 → provenance 必须存在 `(folder, '*', 对应字段名)` 行且 source_url 非空

- [ ] **Step 1: 写失败测试**

```python
# scripts/tests/test_check_meta.py
import json
from pathlib import Path

import check_meta

CUE = '''PERFORMER "陶喆"
TITLE "合成测试专辑"
  TRACK 01 AUDIO
    TITLE "第一首"
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    TITLE "第二首"
    INDEX 01 00:03:00
'''

GOOD_META = {
    "folder": "2005.01.21 - 合成测试专辑", "album": "合成测试专辑",
    "date": "2005-01-21", "year": 2005,
    "musicbrainz": {"release_id": "abc", "label": "Test", "source_url": "https://mb.example/r/abc"},
    "tracks": {
        "1": {"title": "第一首", "composer": ["陶喆"], "lyricist": [], "arranger": []},
        "2": {"title": "第二首"},
    },
}

PROV_CSV = """album_folder,track,field,value,source_url,retrieved_on,note
2005.01.21 - 合成测试专辑,1,composer,陶喆,https://example/lyric/1,2026-10-04,
2005.01.21 - 合成测试专辑,1,lyricist,,,2026-10-04,未查到
2005.01.21 - 合成测试专辑,1,arranger,,,2026-10-04,未查到
2005.01.21 - 合成测试专辑,2,composer,,,2026-10-04,未查到
2005.01.21 - 合成测试专辑,2,lyricist,,,2026-10-04,未查到
2005.01.21 - 合成测试专辑,2,arranger,,,2026-10-04,未查到
2005.01.21 - 合成测试专辑,*,release_id,abc,https://mb.example/r/abc,2026-10-04,
2005.01.21 - 合成测试专辑,*,label,Test,https://mb.example/r/abc,2026-10-04,
"""


def _write(tmp_path, meta, prov=PROV_CSV):
    cue = tmp_path / "a.cue"
    cue.write_bytes(CUE.encode("gb18030"))
    mp = tmp_path / "meta.json"
    mp.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    pp = tmp_path / "prov.csv"
    pp.write_text(prov, encoding="utf-8-sig")
    return mp, cue, check_meta.load_provenance(pp)


def test_good_meta_passes(tmp_path):
    mp, cue, prov = _write(tmp_path, GOOD_META)
    assert check_meta.check_album(mp, cue, prov) == []


def test_value_without_source_fails(tmp_path):
    meta = json.loads(json.dumps(GOOD_META))
    meta["tracks"]["2"]["composer"] = ["陶喆"]      # 有值但 provenance 只有「未查到」行
    mp, cue, prov = _write(tmp_path, meta)
    problems = check_meta.check_album(mp, cue, prov)
    assert any("composer" in p and "2" in p for p in problems)


def test_unknown_key_fails(tmp_path):
    meta = json.loads(json.dumps(GOOD_META))
    meta["extra_junk"] = 1
    mp, cue, prov = _write(tmp_path, meta)
    assert any("unknown" in p.lower() or "未知" in p for p in check_meta.check_album(mp, cue, prov))


def test_track_set_mismatch_fails(tmp_path):
    meta = json.loads(json.dumps(GOOD_META))
    del meta["tracks"]["2"]
    mp, cue, prov = _write(tmp_path, meta)
    assert any("track" in p.lower() or "轨" in p for p in check_meta.check_album(mp, cue, prov))


def test_title_mismatch_fails(tmp_path):
    meta = json.loads(json.dumps(GOOD_META))
    meta["tracks"]["1"]["title"] = "改错标题"
    mp, cue, prov = _write(tmp_path, meta)
    assert any("title" in p.lower() for p in check_meta.check_album(mp, cue, prov))
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd "E:/音乐库-工作区" && python -m pytest scripts/tests/test_check_meta.py -v`
Expected: FAIL（`No module named 'check_meta'`）

- [ ] **Step 3: 实现 check_meta.py**

```python
# scripts/check_meta.py
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
TOP_KEYS = {"folder", "album", "date", "year", "musicbrainz", "tracks"}
TRACK_KEYS = {"title"} | set(CREDIT_FIELDS)
NOT_FOUND = "未查到"


def load_provenance(csv_path: Path) -> dict[tuple[str, str, str], dict]:
    prov: dict[tuple[str, str, str], dict] = {}
    with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            prov[(row["album_folder"], row["track"], row["field"])] = row
    return prov


def check_album(meta_path: Path, cue_path: Path, provenance: dict) -> list[str]:
    problems: list[str] = []
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    folder = meta.get("folder", "")
    cue = cuelib.parse_cue(cue_path)

    unknown = set(meta) - TOP_KEYS
    if unknown:
        problems.append(f"unknown top-level keys: {sorted(unknown)}")
    if not meta.get("album") or not meta.get("year"):
        problems.append("album/year missing")

    cue_nums = {str(t.number): t.title for t in cue.tracks}
    meta_tracks = meta.get("tracks", {})
    if set(meta_tracks) != set(cue_nums):
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
        if value in (None, ""):
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
    ap.add_argument("--source-root", default=r"E:\陶喆")
    ap.add_argument("--work-root", default=r"E:\音乐库-工作区")
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
        if not mp.exists() or len(cue_candidates) != 1:
            print(f"[FAIL] {folder}: meta or cue missing")
            bad += 1
            continue
        problems = check_album(mp, cue_candidates[0], provenance)
        print(f"[{'OK ' if not problems else 'FAIL'}] {folder}")
        for p in problems:
            print(f"    - {p}")
        bad += 1 if problems else 0
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd "E:/音乐库-工作区" && python -m pytest scripts/tests/test_check_meta.py -v`
Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
cd "E:/音乐库-工作区" && git add scripts/check_meta.py scripts/tests/test_check_meta.py && git commit -m "feat(check_meta): enforce provenance for every non-empty metadata value

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 7: `mb_lookup.py` — MusicBrainz 候选查询（TDD + 真实运行）

**Files:**
- Create: `E:\音乐库-工作区\scripts\mb_lookup.py`
- Create: `E:\音乐库-工作区\scripts\tests\test_mb_lookup.py`

**Interfaces:**
- Consumes: `cuelib`、stdlib `urllib`
- Produces:
  - `parse_candidates(mb_json: dict, artist_names=("陶喆","David Tao","Tao Zhe")) -> list[dict]`（元素：`{"id","title","date","country","label","catalog_number","barcode","score","artists"}`，仅保留 artist-credit 命中 artist_names 的条目）
  - `main(argv=None) -> int`：`--all`（对 `--source-root` 下全部专辑）或 `--album <folder>`；查询 `https://musicbrainz.org/ws/2/release?query=artist:"陶喆" AND release:"<专辑名>"&fmt=json&limit=10`；**请求间隔 ≥1.1s**；User-Agent `DavidTaoLocalLibrary/1.0 (personal local library)`；输出 `meta\_mb_candidates.json`（`{folder: {"album": <CUE 标题>, "candidates": [...]}}`）

- [ ] **Step 1: 写失败测试（内嵌假响应）**

```python
# scripts/tests/test_mb_lookup.py
import mb_lookup

FAKE = {
    "count": 2,
    "releases": [
        {"id": "r1", "title": "黑色柳丁", "date": "2002-08-09", "country": "TW",
         "score": 100,
         "artist-credit": [{"name": "陶喆"}],
         "label-info": [{"label": {"name": "Shock Records"}, "catalog-number": "SD-0201"}],
         "barcode": "4711234567890"},
        {"id": "r2", "title": "黑色柳丁", "date": "2002-08-06", "country": "CN",
         "score": 90, "artist-credit": [{"name": "Some Cover Band"}],
         "label-info": [], "barcode": None},
    ],
}


def test_parse_candidates_filters_and_maps():
    out = mb_lookup.parse_candidates(FAKE)
    assert len(out) == 1
    c = out[0]
    assert c["id"] == "r1"
    assert c["title"] == "黑色柳丁"
    assert c["date"] == "2002-08-09"
    assert c["country"] == "TW"
    assert c["label"] == "Shock Records"
    assert c["catalog_number"] == "SD-0201"
    assert c["barcode"] == "4711234567890"


def test_parse_candidates_empty():
    assert mb_lookup.parse_candidates({"releases": []}) == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd "E:/音乐库-工作区" && python -m pytest scripts/tests/test_mb_lookup.py -v`
Expected: FAIL（`No module named 'mb_lookup'`）

- [ ] **Step 3: 实现 mb_lookup.py**

```python
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
```

- [ ] **Step 4: 运行单测确认通过**

Run: `cd "E:/音乐库-工作区" && python -m pytest scripts/tests/test_mb_lookup.py -v`
Expected: 2 passed

- [ ] **Step 5: 真实运行（8 张专辑，约 10 秒）**

Run: `cd "E:/音乐库-工作区" && python scripts/mb_lookup.py --all`
Expected: 8 行 `[OK]`，`meta\_mb_candidates.json` 生成。若某专辑 0 candidates：记录，留待 Task 8 人工补查（不阻塞）。

- [ ] **Step 6: 提交**

```bash
cd "E:/音乐库-工作区" && git add scripts/mb_lookup.py scripts/tests/test_mb_lookup.py meta/_mb_candidates.json && git commit -m "feat(mb_lookup): MusicBrainz candidate lookup for all albums

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 8: 逐张核对并编写 `meta\<专辑>.json` + 来源记录（CHECKPOINT：用户可抽查）

**Files:**
- Create: `E:\音乐库-工作区\meta\2002.08.09 - 黑色柳丁.json`（其余 7 张同构，逐专辑一步）
- Create: `E:\音乐库-工作区\reports\metadata-provenance.csv`

**Interfaces:**
- Consumes: `meta\_mb_candidates.json`（Task 7）、`check_meta.check_album`（Task 6）、源 CUE
- Produces: 8 份通过 `check_meta` 的 meta JSON；provenance CSV 全量覆盖

**逐专辑操作模板（对以下 8 个文件夹各做一遍）**：
`1997.12.06 - DAVID.TAO`、`1999.12.10 - I'm.OK`、`2002.08.09 - 黑色柳丁`、`2003.08.08 - ULTRASOUND乐之路1997-2003`、`2005.01.21 - 太平盛世`、`2006.01.21 - 太美丽`、`2009.08.21 - 69乐章`、`2013.06.11 - 再见你好吗`

**(a) 选定 MusicBrainz 发行版**：读 `_mb_candidates.json` 该专辑条目，优先选与 CUE REM DATE 同日期或最接近、country=TW 的原版；把 `id → release_id`、label/catalog/barcode/country 写入 meta JSON `musicbrainz` 段并填 `source_url`（`https://musicbrainz.org/release/<id>`）。

**(a2) 取另两个 ID**（release_group_id / artist_id）：
```bash
curl -s --max-time 30 -A "DavidTaoLocalLibrary/1.0 (personal local library)" "https://musicbrainz.org/ws/2/release/<release_id>?inc=release-groups+artist-credits&fmt=json"
```
从响应里取 `release-group.id` 与 `artist-credit[0].artist.id` 填入（source_url 同样记 release 页）。

`date` 取所选匹配版本的日期（与 CUE REM DATE 不一致时以匹配版本为准；CUE 缺失则直接用版本日期）。0 候选时：用 WebFetch/WebSearch 查证后如实填写或整段省略（省略也要在 provenance 写「未查到」行）。

**(b) 逐曲词曲作者查证**：用 WebSearch/WebFetch 从两个来源交叉核对（推荐：魔镜歌词网 mojim.com 的歌曲页「作词/作曲」栏 + 中文维基百科专辑条目或百度百科曲目表）。**每曲每字段**写 provenance 行：
```csv
2002.08.09 - 黑色柳丁,1,composer,陶喆,https://mojim.com/cny100xxx.htm,2026-10-04,
2002.08.09 - 黑色柳丁,1,lyricist,娃娃,https://zh.wikipedia.org/wiki/黑色柳丁,2026-10-04,
2002.08.09 - 黑色柳丁,1,arranger,,,2026-10-04,未查到
```
多作者用 `; ` 连接成单值（与写入 FLAC 的列表一致）。**查不到就 `未查到`，绝不猜**。

**(c) 写 meta JSON**（文件名 = 源文件夹名 + `.json`）：
```json
{
  "folder": "2002.08.09 - 黑色柳丁",
  "album": "黑色柳丁",
  "date": "2002-08-09",
  "year": 2002,
  "musicbrainz": {
    "release_id": "161d7e8e-29de-4ca2-a755-dd3595650aa4",
    "release_group_id": "...", "artist_id": "...",
    "label": "Shock Records", "country": "TW",
    "catalog_number": "...", "barcode": "...",
    "matched_title": "黑色柳丁",
    "source_url": "https://musicbrainz.org/release/161d7e8e-29de-4ca2-a755-dd3595650aa4"
  },
  "tracks": {
    "1": {"title": "黑色柳丁(Black Tangerine)", "composer": ["陶喆"], "lyricist": ["陶喆"], "arranger": []},
    "2": {"title": "今天晚间新闻(Today Evening News)", "composer": ["陶喆"], "lyricist": ["陶喆"], "arranger": []}
  }
}
```

**(d) 校验**：`cd "E:/音乐库-工作区" && python scripts/check_meta.py --album "<文件夹名>"`
Expected: `[OK ] <文件夹名>`

- [ ] **Step 1: 黑色柳丁**（含 (a)(b)(c)(d) 全流程）
- [ ] **Step 2: David Tao (1997)**
- [ ] **Step 3: I'm OK (1999)**
- [ ] **Step 4: ULTRASOUND (2003)**
- [ ] **Step 5: 太平盛世 (2005)**
- [ ] **Step 6: 太美丽 (2006)**
- [ ] **Step 7: 69乐章 (2009)**
- [ ] **Step 8: 再见你好吗 (2013)**
- [ ] **Step 9: 全量校验 + 提交**

```bash
cd "E:/音乐库-工作区" && python scripts/check_meta.py --all
git add meta/ reports/metadata-provenance.csv && git commit -m "feat(meta): curated per-album metadata with provenance for all 8 albums

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

**CHECKPOINT（等用户）**：向用户汇报 8 张专辑的元数据覆盖情况（哪些字段查到、哪些未查到），请用户抽查 `meta\*.json` 与 `reports\metadata-provenance.csv` 若干条目的来源链接，确认后再进入 Task 9。

---

### Task 9: 试跑——黑色柳丁（源清单 before + 转换 + 双重验收）（CHECKPOINT：等用户）

**Files:**
- Create: `E:\音乐库-工作区\reports\source-manifest-before.txt`
- Create: `E:\音乐库\陶喆\2002 - 黑色柳丁\*.flac` + `cover.jpg`（首份真实产出）
- Create: `E:\音乐库-工作区\logs\convert-2002.08.09 - 黑色柳丁.json`

**Interfaces:**
- Consumes: Task 4 的 `convert.main`、Task 5 的 `source_manifest`、Task 8 的 meta JSON
- Produces: 首张专辑成品；供用户听感验收

- [ ] **Step 1: 源目录快照（before）**

```bash
cd "E:/音乐库-工作区" && python scripts/source_manifest.py before "E:/陶喆" "E:/音乐库-工作区/reports/source-manifest-before.txt"
```

- [ ] **Step 2: 转换黑色柳丁**

```bash
cd "E:/音乐库-工作区" && python scripts/convert.py --album "2002.08.09 - 黑色柳丁"
```

Expected: 日志逐轨 OK，13 轨全部通过 MD5 校验；`E:\音乐库\陶喆\2002 - 黑色柳丁\` 出现 13 个 flac + cover.jpg；临时目录已清理。若 APE 解码失败（日志含 `decode failed`），停在此处向用户报告，并启用备选方案：到 monkeysaudio.com 下载官方 `mac.exe` 放 `scripts\bin\`，`mac.exe <name>.ape <temp>.wav -d` 解码后，把该专辑音频替换为 WAV 再重跑（convert 已支持 .wav 输入）。

- [ ] **Step 3: 脚本级自检**

```bash
cd "E:/音乐库-工作区" && python scripts/verify.py --album "2002.08.09 - 黑色柳丁" --tracklist-out "E:/音乐库-工作区/reports/tracklist-黑色柳丁.csv" --report-out "E:/音乐库-工作区/reports/verification-黑色柳丁.md"
```

Expected: `[OK ] 2002.08.09 - 黑色柳丁 (13 tracks)`，退出码 0。

- [ ] **Step 4: 人工抽查（我执行并汇报）**

- 打开专辑目录核对：13 个文件名、序号、曲名（含 `：` 全角替换）与 CUE 一致
- 用 ffprobe 抽查首轨/末轨时长与 CUE 索引吻合；抽 1 轨与源整轨对应位置试听（播头尾 5 秒边界，确认无爆音/错位）
- 抽查封面在内嵌与目录两处都在；标签（曲名/专辑/年份/曲序/词曲/MBID）用 mutagen 打印核对
- 把上述结果连同 `reports\tracklist-黑色柳丁.csv` 交给用户

- [ ] **Step 5: CHECKPOINT——等用户验收**

请用户：① 在电脑上听 2–3 轨（重点听轨首/轨尾过渡）；② 若要，把 `E:\音乐库\陶喆\2002 - 黑色柳丁` 用 LocalSend 发到手机，用实际播放器验证 封面/曲名/专辑归类。**用户确认后才进入 Task 10；用户反馈问题 → 修复后重跑 Task 9 全流程。**

---

### Task 10: 批量处理其余 7 张

**Files:**
- Create: `E:\音乐库\陶喆\<年份> - <专辑名>\` ×7
- Create: `E:\音乐库-工作区\logs\convert-*.json` ×7

**Interfaces:**
- Consumes: Task 9 已验证的同一流水线
- Produces: 全库 8 张专辑成品

- [ ] **Step 1: 逐张转换（一张一校验，失败即停）**

```bash
cd "E:/音乐库-工作区" && for f in "1997.12.06 - DAVID.TAO" "1999.12.10 - I'm.OK" "2003.08.08 - ULTRASOUND乐之路1997-2003" "2005.01.21 - 太平盛世" "2006.01.21 - 太美丽" "2009.08.21 - 69乐章" "2013.06.11 - 再见你好吗"; do
  echo "=== $f ==="
  python scripts/convert.py --album "$f" || break
  python scripts/verify.py --album "$f" --report-out "E:/音乐库-工作区/reports/verification-${f//\//_}.md" || break
done
```

Expected: 7 张全部 `[OK]`。任何一张失败：停下来诊断（`logs\convert-<album>.json` + convert.log），修复后从该张续跑（脚本幂等，可重跑单张）。

- [ ] **Step 2: 记录产出统计**

```bash
cd "E:/音乐库-工作区" && ls "E:/音乐库/陶喆" && du -sh "E:/音乐库/陶喆"
```

Expected: 8 个专辑目录，合计约 2.5–3GB。

- [ ] **Step 3: 检查工作树（logs/ 按设计不入库）**

```bash
cd "E:/音乐库-工作区" && git status --short
```

Expected: 无 `logs/` 条目（已被 .gitignore 忽略，这是有意设计——逐轨 md5 证据在 `reports\tracklist.csv`，无需把运行日志入库）；除 reports/ 等预期变更外无异常。

---

### Task 11: 全库终验 + 源清单比对 + 汇总报告 + 收尾

**Files:**
- Create: `E:\音乐库-工作区\reports\source-manifest-after.txt`
- Create: `E:\音乐库-工作区\reports\tracklist.csv`（全库 107 轨）
- Create: `E:\音乐库-工作区\reports\verification-<时间戳>.md`
- Create: `E:\音乐库-工作区\reports\final-report.md`

**Interfaces:**
- Consumes: 全部既有脚本与产出
- Produces: 终验证据链；交给用户的最终交付说明

- [ ] **Step 1: 全库校验**

```bash
cd "E:/音乐库-工作区" && python scripts/verify.py --all
```

Expected: 8 张全部 `[OK]`，退出码 0，`reports\tracklist.csv` 含 107 行数据。

- [ ] **Step 2: 源目录零改动证明（after + compare）**

```bash
cd "E:/音乐库-工作区" && python scripts/source_manifest.py after "E:/陶喆" "E:/音乐库-工作区/reports/source-manifest-after.txt"
python scripts/source_manifest.py compare "E:/陶喆" "E:/音乐库-工作区/reports"
```

Expected: `NO CHANGES: source untouched`，退出码 0。（compare 读 reports 目录下 before/after 两文件。）

- [ ] **Step 3: 写 final-report.md**

内容（如实填写，不达标不许写「通过」）：
- 8 张专辑产出统计表（专辑/轨数/时长/文件数/目录大小）
- 校验结论：逐轨 MD5 全通过数、ffprobe 格式检查、标签/封面抽查结果
- 元数据覆盖统计：composer/lyricist/arranger 查到率（读 provenance CSV 统计）
- 源清单比对结论（零改动）
- 交付指引：`E:\音乐库\陶喆\` → LocalSend 传手机 → 建议手机侧放 `Music/陶喆/`；任何标准播放器（Poweramp/Musicolet/foobar2000）均可识别
- 遗留与备注（未查到的字段清单、已知限制）

- [ ] **Step 4: 清理与提交**

```bash
cd "E:/音乐库-工作区" && ls temp/ && rm -rf temp/* 2>/dev/null; git add -A && git commit -m "feat: final verification, tracklist, source manifest proof, final report

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

- [ ] **Step 5: 更新项目记忆**

更新 `C:\Users\29576\.claude\projects\C--Users-29576-Desktop-test\memory\david-tao-flac-library-project.md`：状态改为「已完成（日期）」、成品位置、校验结论、元数据查到率；保持 MEMORY.md 索引行同步。

- [ ] **Step 6: 向用户汇报**

交付：final-report.md 路径、tracklist.csv 路径、成品目录路径、校验证据摘要、下一步（LocalSend 自传）。任务完成。

---

## 附：任务依赖关系

```
T1 环境 → T2 cuelib → T3 audio → T4 convert → T5 verify(含 manifest)
T2 → T6 check_meta
T7 mb_lookup → T8 meta 核对[CHECKPOINT] 
T4+T5+T8 → T9 试跑[CHECKPOINT] → T10 批量 → T11 终验+收尾 → T12 推 GitHub[CHECKPOINT]
```

---

### Task 12: 推送到 GitHub（用户追加需求，2026-10-04）

**Files:**
- Create: `E:\音乐库-工作区\README.md`（项目说明）
- 仓库操作：添加 remote、推送

**前置**：T11 全部通过（校验/清单/终报齐备）。

- [ ] **Step 1: 内容边界核对**

```bash
cd "E:/音乐库-工作区" && git ls-files
```

Expected: 仅 scripts/ tests/ docs/ meta/ reports/ 与 .gitignore/README；**无音频、无日志、无 temp**（均已 gitignore）。如发现异常文件，停下报告。

- [ ] **Step 2: 验证 GitHub 通路（SSH 优先）**

```bash
ssh -T git@github.com 2>&1 | head -1
```

Expected: `Hi <用户名>! You've successfully authenticated...`。失败则回退 HTTPS（首次 push 由 Windows 凭据管理器弹窗完成登录）。

- [ ] **Step 3: 写 README.md 并提交**

README 内容：项目一句话简介、依赖（Python ≥3.10 / ffmpeg / mutagen / pytest）、用法（convert.py / verify.py / check_meta.py 的 CLI 示例）、目录结构、无损校验说明（逐轨 PCM MD5）。提交信息带 Co-Authored-By 尾注。

- [ ] **Step 4: 用户创建远程仓库**

用户决定**仓库名**与**公开/私有**（建议先私有）。用户在 GitHub 网页建空仓库（**不要**勾选初始化 README/.gitignore）；或装 `gh`（`winget install GitHub.cli` + `gh auth login`）后代建。

- [ ] **Step 5: 添加 remote 并推送**

```bash
cd "E:/音乐库-工作区" && git remote add origin <用户提供的URL> && git push -u origin master
```

注意：当前默认分支为 `master`；如用户希望用 `main`，推送前先 `git branch -m master main`。

- [ ] **Step 6: 推送后核对**

GitHub 页面文件列表与 `git ls-files` 数量一致；README 正常渲染。

**CHECKPOINT：推送前必须获得用户对「仓库名 + 公开/私有 + 分支名」的明确确认。**

---

### Task 8b: 维基/百度补充交叉复核（T8 检查点追加，2026-10-04）

- 背景：T8 检查点时用户指出维基百科可达（经代理）。实测：zh.wikipedia 需 `curl -x http://127.0.0.1:7890`（直连被墙）；baike.baidu.com 直连可达；mojim 真不可达；**WebFetch 工具在本机对所有域名不可用，一律改用 curl**。
- 对 8 张专辑用 zh.wikipedia（经代理）+ baike.baidu.com（直连）做第三方交叉验证：逐轨比对 作词/作曲/编曲。
- 产出 `reports\source-crosscheck-2026-10-04.md`：总览（可达性/确认数/分歧数/可填补数）→ 分歧清单（meta 值+来源URL ｜ 新源值+URL）→ 可填补清单（专辑/轨号/字段/值/URL）。
- **不改动** `meta\*.json` 与 `metadata-provenance.csv`；分歧只记录，向用户汇报后再定。
- 原始 HTML 证据存 SDD 工作区 `crosscheck\`（不入库）；报告提交入库。

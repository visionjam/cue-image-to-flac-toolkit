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
    with wave.open(str(src_wav), "rb") as ws:
        frame_size = ws.getnchannels() * ws.getsampwidth()
        # Validate before opening dst: raising AudioError with an open Wave_write
        # would be masked by wave.Error from its close() ("# channels not specified").
        if start_frame < 0 or count <= 0 or start_frame + count > ws.getnframes():
            raise AudioError(f"slice out of range: start={start_frame} count={count} total={ws.getnframes()}")
        with wave.open(str(dst_wav), "wb") as wd:
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
    # -map 0:a:0: 带内嵌封面的 FLAC 会把图片暴露为第二个流；不限定流时
    # ffmpeg -f md5 会把图片数据一并计入散列，导致与源 WAV 区段的 PCM MD5 不等。
    p = _run([FFMPEG, "-v", "error", "-i", path, "-map", "0:a:0",
              "-c:a", "pcm_s16le", "-f", "md5", "-"],
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

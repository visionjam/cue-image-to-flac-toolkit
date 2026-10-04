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

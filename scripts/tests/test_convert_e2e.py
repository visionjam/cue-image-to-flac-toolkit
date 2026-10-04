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

    # 采样级时长：149940/149940/141120 帧
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


def test_convert_wraps_non_decode_failures_as_album_error(synthetic_source, monkeypatch):
    tmp_path = synthetic_source
    from audio import AudioError

    # convert.py 里是 `from audio import ... encode_flac ...`，实际调用的是 convert
    # 模块内的绑定，所以必须 patch convert.encode_flac（patch audio.encode_flac 影响不到它）。
    def boom(*args, **kwargs):
        raise AudioError("encode exploded")

    monkeypatch.setattr(convert, "encode_flac", boom)
    with pytest.raises(convert.AlbumError) as ei:
        run_convert(tmp_path)
    assert isinstance(ei.value.__cause__, AudioError)

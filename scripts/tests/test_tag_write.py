import json
import subprocess

import pytest
from mutagen.flac import FLAC

import tag_write

FFMPEG = "ffmpeg"

META = {
    "folder": "2000 - Sample Album",
    "album": "示例专辑",
    "date": "2000-01-01",
    "year": 2000,
    "genre": ["华语流行"],
    "musicbrainz": {"release_id": "rel-1", "release_group_id": "rg-1", "artist_id": "ar-1",
                    "source_url": "https://musicbrainz.org/release/rel-1"},
    "tracks": {
        "1": {"title": "第一首", "composer": ["作曲甲"], "lyricist": ["作词乙"],
              "arranger": ["编曲丙"], "musicbrainz_recording_id": "rec-1",
              "musicbrainz_releasetrackid": "rt-1"},
        "2": {"title": "第二首", "composer": [], "lyricist": [], "arranger": []},
    },
}


@pytest.fixture
def album_dir(tmp_path):
    """2 首 3 秒 16bit FLAC，文件名 NN. 前缀、无内嵌轨号（触发文件名回退 + 归一）。"""
    d = tmp_path / "2000 - Sample Album"
    d.mkdir()
    for i, fn in enumerate(["01.第一首.flac", "02.第二首.flac"], start=1):
        subprocess.run(
            [FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i",
             f"anoisesrc=d=3:c=pink:seed={i * 7}", "-ac", "2", "-ar", "44100",
             "-c:a", "flac", str(d / fn)], check=True)
    return d


@pytest.fixture
def cover_jpg(tmp_path):
    cover = tmp_path / "cover.jpg"
    subprocess.run(
        [FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=64x64",
         "-frames:v", "1", str(cover)], check=True)
    return cover


def _meta_file(tmp_path, meta=META):
    p = tmp_path / "meta.json"
    p.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return p


def test_album_write_full_proofs(album_dir, cover_jpg, tmp_path):
    fp = album_dir / "01.第一首.flac"
    md5_before = "%032x" % FLAC(str(fp)).info.md5_signature
    rc = tag_write.main(["album", "--dir", str(album_dir), "--meta", str(_meta_file(tmp_path)),
                         "--cover", str(cover_jpg), "--artist", "测试歌手"])
    assert rc == 0
    f = FLAC(str(fp))
    assert f.tags["title"] == ["第一首"]
    assert f.tags["album"] == ["示例专辑"]
    assert f.tags["albumartist"] == ["测试歌手"]
    assert f.tags["tracknumber"] == ["1"]          # 文件名回退 + "01"→"1" 归一
    assert f.tags["composer"] == ["作曲甲"]
    assert f.tags["lyricist"] == ["作词乙"]
    assert f.tags["arranger"] == ["编曲丙"]
    assert f.tags["musicbrainz_albumid"] == ["rel-1"]
    assert f.tags["musicbrainz_trackid"] == ["rec-1"]
    assert len(f.pictures) == 1
    assert ("%032x" % f.info.md5_signature) == md5_before   # 音频未动
    assert (album_dir / "cover.jpg").exists()


def test_album_missing_meta_track_fails(album_dir, cover_jpg, tmp_path):
    meta = json.loads(json.dumps(META))
    del meta["tracks"]["2"]
    rc = tag_write.main(["album", "--dir", str(album_dir), "--meta", str(_meta_file(tmp_path, meta)),
                         "--cover", str(cover_jpg), "--artist", "测试歌手"])
    assert rc == 1


def test_album_dry_run_writes_nothing(album_dir, cover_jpg, tmp_path):
    fp = album_dir / "01.第一首.flac"
    size = fp.stat().st_size
    rc = tag_write.main(["album", "--dir", str(album_dir), "--meta", str(_meta_file(tmp_path)),
                         "--cover", str(cover_jpg), "--artist", "测试歌手", "--dry-run"])
    assert rc == 0
    assert fp.stat().st_size == size
    assert FLAC(str(fp)).tags.get("albumartist") is None


def test_files_mode_spec(album_dir, tmp_path):
    spec = {
        "artist": "测试歌手",
        "dir": str(album_dir),
        "items": [{"file": "02.第二首.flac", "title": "第二首", "album": "单曲",
                   "date": "2001-02-03", "genre": ["华语流行"],
                   "composer": [], "lyricist": [], "arranger": []}],
    }
    sp = tmp_path / "spec.json"
    sp.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    rc = tag_write.main(["files", "--spec", str(sp)])
    assert rc == 0
    f = FLAC(str(album_dir / "02.第二首.flac"))
    assert f.tags["album"] == ["单曲"]
    assert f.tags["tracknumber"] == ["1"]
    assert f.tags["date"] == ["2001-02-03"]


def test_jpeg_size(cover_jpg):
    assert tag_write.jpeg_size(cover_jpg.read_bytes()) == (64, 64)


def test_jpeg_size_rejects_non_jpeg():
    with pytest.raises(ValueError):
        tag_write.jpeg_size(b"not a jpeg")

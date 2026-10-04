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

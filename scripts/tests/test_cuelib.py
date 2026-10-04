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

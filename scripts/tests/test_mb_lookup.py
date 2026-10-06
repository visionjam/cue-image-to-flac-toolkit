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


DETAIL = {
    "id": "r1", "title": "黑色柳丁", "date": "2002-08-09", "country": "TW",
    "barcode": "4711234567890",
    "release-group": {"id": "rg1"},
    "label-info": [{"label": {"name": "Shock Records"}, "catalog-number": "SD-0201"}],
    "artist-credit": [{"artist": {"id": "artist1", "name": "陶喆"}}],
    "media": [
        {"position": 1, "format": "CD", "tracks": [
            {"number": "1", "title": "黑色柳丁", "length": 240000, "id": "t1",
             "recording": {"id": "rec1"}}]},
        {"position": 2, "format": "VCD", "tracks": [
            {"number": "1", "title": "MV", "length": 60000, "id": "t2",
             "recording": {"id": "rec2"}}]},
    ],
}


def test_summarize_detail():
    s = mb_lookup.summarize_detail(DETAIL)
    assert s["release_id"] == "r1"
    assert s["release_group_id"] == "rg1"
    assert s["artist_id"] == "artist1"
    assert s["label"] == "Shock Records"
    assert s["catalog_number"] == "SD-0201"
    assert s["barcode"] == "4711234567890"
    assert [len(m["tracks"]) for m in s["media"]] == [1, 1]
    assert s["media"][0]["tracks"][0]["recording_id"] == "rec1"
    assert s["media"][0]["tracks"][0]["track_id"] == "t1"

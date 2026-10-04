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

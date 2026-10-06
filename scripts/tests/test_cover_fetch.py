import cover_fetch as cf


def test_pick_caa_prefers_approved_front():
    imgs = [
        {"id": "a", "front": False, "approved": True},
        {"id": "b", "front": True, "approved": False},
        {"id": "c", "front": True, "approved": True},
    ]
    assert cf.pick_caa_image(imgs)["id"] == "c"


def test_pick_caa_falls_back_to_front_then_first():
    assert cf.pick_caa_image([{"id": "b", "front": True, "approved": False}])["id"] == "b"
    assert cf.pick_caa_image([{"id": "x", "front": False, "approved": False}])["id"] == "x"
    assert cf.pick_caa_image([]) is None


def test_parse_netease_search():
    payload = {"result": {"albums": [
        {"id": 123, "name": "示例专辑", "artists": [{"name": "歌手甲"}, {"name": "歌手乙"}],
         "size": 10, "picUrl": "https://p.example/x.jpg"}]}}
    rows = cf.parse_netease_search(payload)
    assert rows[0]["id"] == 123
    assert rows[0]["name"] == "示例专辑"
    assert rows[0]["artists"] == "歌手甲/歌手乙"
    assert rows[0]["pic_url"] == "https://p.example/x.jpg"


def test_parse_netease_empty():
    assert cf.parse_netease_search({}) == []
    assert cf.parse_netease_search({"result": {}}) == []

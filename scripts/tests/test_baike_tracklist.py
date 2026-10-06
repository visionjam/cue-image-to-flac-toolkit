import pytest

import baike_tracklist as bt

# 模拟百科曲目表：作曲整列 rowspan=3（全碟同一作曲），作词黄俊郎 rowspan=2（两行共用）
HTML = """<html><body>
<table>
  <tr><th>曲序</th><th>曲目</th><th>作词</th><th>作曲</th><th>编曲</th></tr>
  <tr><td>1</td><td>《歌一》</td><td>方文山</td><td rowspan="3">周杰伦</td><td>林迈可</td></tr>
  <tr><td>2</td><td>《歌二》</td><td rowspan="2">黄俊郎</td><td>洪敬尧</td></tr>
  <tr><td>3</td><td>《歌三》</td><td>钟兴民</td></tr>
</table>
</body></html>"""


def test_rowspan_fill():
    idx, rows, cols = bt.parse_track_table(HTML)
    assert cols == ["序号", "曲目", "作词", "作曲", "编曲"]
    assert rows[0] == ["1", "《歌一》", "方文山", "周杰伦", "林迈可"]
    assert rows[1] == ["2", "《歌二》", "黄俊郎", "周杰伦", "洪敬尧"]   # 作曲由 rowspan 继承
    assert rows[2] == ["3", "《歌三》", "黄俊郎", "周杰伦", "钟兴民"]   # 作词、作曲均为继承


def test_no_candidate_table_raises():
    with pytest.raises(ValueError):
        bt.parse_track_table("<p>没有表格</p>")


def test_nested_table_ignored():
    html = ("<table><tr><td>外层</td></tr></table>" + HTML)
    _, rows, _ = bt.parse_track_table(html)
    assert len(rows) == 3

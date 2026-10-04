# scripts/tests/test_verify.py
import json

import convert
import verify
import source_manifest
from test_convert_e2e import synthetic_source  # noqa: F401  pytest 会把 tests 目录加入 sys.path


def _prepared(tmp_path):
    convert.convert_album(
        "2005.01.21 - 合成测试专辑",
        source_root=tmp_path / "source", output_root=tmp_path / "out",
        work_root=tmp_path / "work", meta_dir=tmp_path / "meta",
    )
    return tmp_path


def test_verify_ok(synthetic_source):
    tmp = _prepared(synthetic_source)
    rep = verify.verify_album(
        "2005.01.21 - 合成测试专辑",
        source_root=tmp / "source", output_root=tmp / "out",
        work_root=tmp / "work", meta_dir=tmp / "meta",
    )
    assert rep["status"] == "ok", rep["problems"]
    assert rep["tracks"] == 3


def test_verify_detects_corruption(synthetic_source):
    tmp = _prepared(synthetic_source)
    victim = tmp / "out" / "2005 - 合成测试专辑" / "02 - 飞机场的 10：30.flac"
    data = bytearray(victim.read_bytes())
    data[len(data) // 2] ^= 0xFF
    victim.write_bytes(bytes(data))
    rep = verify.verify_album(
        "2005.01.21 - 合成测试专辑",
        source_root=tmp / "source", output_root=tmp / "out",
        work_root=tmp / "work", meta_dir=tmp / "meta",
    )
    assert rep["status"] == "fail"
    assert any("02" in p for p in rep["problems"])


def test_verify_detects_wrong_frame_count(synthetic_source):
    tmp = _prepared(synthetic_source)
    from audio import decode_to_wav, encode_flac, slice_wav

    # 用源整轨前 2.0 秒（88200 帧）重切一轨替换成品 01 轨：采样内容与帧数同时不符
    src_wav = tmp / "src.wav"
    decode_to_wav(tmp / "source" / "2005.01.21 - 合成测试专辑" / "album.flac", src_wav)
    short_wav = tmp / "short.wav"
    slice_wav(src_wav, 0, 88200, short_wav)
    short_flac = tmp / "short.flac"
    encode_flac(short_wav, short_flac)
    victim = tmp / "out" / "2005 - 合成测试专辑" / "01 - 第一首.flac"
    victim.write_bytes(short_flac.read_bytes())

    rep = verify.verify_album(
        "2005.01.21 - 合成测试专辑",
        source_root=tmp / "source", output_root=tmp / "out",
        work_root=tmp / "work", meta_dir=tmp / "meta",
    )
    assert rep["status"] == "fail"
    assert any("01" in p and "md5 mismatch" in p for p in rep["problems"])
    assert any("01" in p and "frame count" in p for p in rep["problems"])
    assert any("total sample count mismatch" in p for p in rep["problems"])


def test_manifest_detects_change(tmp_path):
    root = tmp_path / "src"
    root.mkdir()
    (root / "a.txt").write_text("hello")
    before = source_manifest.manifest(root)
    assert source_manifest.compare(before, source_manifest.manifest(root)) == []
    (root / "a.txt").write_text("changed!")
    assert source_manifest.compare(before, source_manifest.manifest(root)) != []

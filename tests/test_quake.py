# 地震の判定（設計書 7章：過去の電文で全パターンを確認）
import pytest

from app.quake import (UNREPORTED_5PLUS, intensity_label, nichinan_intensity, parse_feed, parse_report,
                       report_needs_alert, should_alert)

from .conftest import FIXTURES


def load(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_日南市の震度を取り出す():
    assert nichinan_intensity(load("vxse53_nichinan_5minus.xml")) == "5-"
    assert nichinan_intensity(load("vxse53_nichinan_4.xml")) == "4"


def test_日南市が載っていない電文はNone():
    assert nichinan_intensity(load("vxse53_no_nichinan.xml")) is None
    assert nichinan_intensity(load("vxse53_other_city.xml")) is None  # 気象庁の実物（熊本の地震）


def test_実物の電文から他の市町村は取れる():
    assert nichinan_intensity(load("vxse53_other_city.xml"), city_code="4351300") == "1"  # 球磨村


def test_5弱以上未入電():
    assert nichinan_intensity(load("vxse53_nichinan_unreported.xml")) == UNREPORTED_5PLUS
    assert should_alert(UNREPORTED_5PLUS, "5-")
    assert not should_alert(UNREPORTED_5PLUS, "6-")


@pytest.mark.parametrize("intensity,expected", [
    (None, False), ("1", False), ("4", False), ("5-", True), ("5+", True), ("6-", True), ("7", True),
    ("不明", False),
])
def test_しきい値5弱(intensity, expected):
    assert should_alert(intensity, "5-") is expected


def test_電文の情報():
    r = parse_report(load("vxse53_nichinan_5minus.xml"), "4520400")
    assert r.event_id == "20261120090200"
    assert r.status == "通常" and r.info_type == "発表"
    assert r.report_time.isoformat() == "2026-11-20T09:05:00+09:00"
    assert report_needs_alert(r)


def test_訓練_取消_では送らない():
    assert not report_needs_alert(parse_report(load("vxse53_training.xml"), "4520400"))
    assert not report_needs_alert(parse_report(load("vxse53_cancel.xml"), "4520400"))


def test_震度の表示():
    assert intensity_label("5-") == "5弱"
    assert intensity_label("6+") == "6強"
    assert intensity_label(UNREPORTED_5PLUS) == "5弱以上（推定）"


def test_フィードから震源震度情報だけ取り出す():
    entries = parse_feed(load("feed_sample.xml"))
    assert len(entries) == 2
    assert all("VXSE53" in e.url for e in entries)

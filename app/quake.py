"""気象庁 防災情報XML の解析（設計書 3章 機能③・4-5）。

ネットワークにはつながず、文字列を受け取って結果を返すだけの関数にしてある。
過去の電文（tests/fixtures）で全パターンをテストできる。
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime

NS = {
    "jmx": "http://xml.kishou.go.jp/jmaxml1/",
    "ib": "http://xml.kishou.go.jp/jmaxml1/informationBasis1/",
    "seis": "http://xml.kishou.go.jp/jmaxml1/body/seismology1/",
    "atom": "http://www.w3.org/2005/Atom",
}
ORDER = ["1", "2", "3", "4", "5-", "5+", "6-", "6+", "7"]  # 震度の順番
LABEL = {"1": "1", "2": "2", "3": "3", "4": "4", "5-": "5弱", "5+": "5強",
         "6-": "6弱", "6+": "6強", "7": "7"}
# 震度5弱以上と推定されるが、観測点からの入電がない市町村に付く
UNREPORTED_5PLUS = "5-?"
TARGET_TITLE = "震源・震度に関する情報"


@dataclass(frozen=True)
class QuakeReport:
    event_id: str
    status: str          # 通常 / 訓練 / 試験
    info_type: str       # 発表 / 訂正 / 取消
    report_time: datetime | None
    headline: str
    intensity: str | None  # 対象市町村の震度（ORDER の値か UNREPORTED_5PLUS）。観測なしは None


def city_intensity(root: ET.Element, city_code: str) -> str | None:
    """電文の中から、指定した市町村の震度を取り出す。"""
    for city in root.iterfind(".//seis:City", NS):
        if city.findtext("seis:Code", namespaces=NS) != city_code:
            continue
        max_int = city.findtext("seis:MaxInt", namespaces=NS)
        if max_int:
            return max_int
        # MaxInt が無く「震度５弱以上未入電」とだけある場合
        if "５弱以上未入電" in (city.findtext("seis:Condition", namespaces=NS) or ""):
            return UNREPORTED_5PLUS
    return None


def parse_report(xml_text: str | bytes, city_code: str) -> QuakeReport:
    root = ET.fromstring(xml_text)
    rt = root.findtext("ib:Head/ib:ReportDateTime", namespaces=NS)
    return QuakeReport(
        event_id=root.findtext("ib:Head/ib:EventID", default="", namespaces=NS),
        status=root.findtext("jmx:Control/jmx:Status", default="", namespaces=NS),
        info_type=root.findtext("ib:Head/ib:InfoType", default="", namespaces=NS),
        report_time=datetime.fromisoformat(rt) if rt else None,
        headline=(root.findtext("ib:Head/ib:Headline/ib:Text", default="", namespaces=NS) or "").strip(),
        intensity=city_intensity(root, city_code),
    )


def nichinan_intensity(xml_text: str, city_code: str = "4520400") -> str | None:
    """「震源・震度に関する情報」から日南市の震度を返す（観測なしは None）"""
    return city_intensity(ET.fromstring(xml_text), city_code)


def should_alert(intensity: str | None, threshold: str = "5-") -> bool:
    """しきい値以上なら True。「5弱以上未入電」は、しきい値が5弱以下なら安全側に倒して True。"""
    if intensity == UNREPORTED_5PLUS:
        return ORDER.index(threshold) <= ORDER.index("5-")
    return intensity in ORDER and ORDER.index(intensity) >= ORDER.index(threshold)


def report_needs_alert(r: QuakeReport, threshold: str = "5-") -> bool:
    """訓練・試験・取消の電文では送らない。"""
    return r.status == "通常" and r.info_type != "取消" and should_alert(r.intensity, threshold)


def intensity_label(intensity: str | None) -> str:
    if intensity == UNREPORTED_5PLUS:
        return "5弱以上（推定）"
    return LABEL.get(intensity or "", "不明")


@dataclass(frozen=True)
class FeedEntry:
    id: str
    title: str
    url: str


def parse_feed(xml_text: str | bytes) -> list[FeedEntry]:
    """Atom フィードから「震源・震度に関する情報」の電文URLを取り出す。"""
    root = ET.fromstring(xml_text)
    out = []
    for e in root.iterfind("atom:entry", NS):
        title = e.findtext("atom:title", default="", namespaces=NS)
        if title != TARGET_TITLE:
            continue
        link = e.find("atom:link", NS)
        url = link.get("href") if link is not None else e.findtext("atom:id", default="", namespaces=NS)
        out.append(FeedEntry(id=e.findtext("atom:id", default=url, namespaces=NS), title=title, url=url))
    return out

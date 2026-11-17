"""テスト用の電文を作る（気象庁 VXSE53 の実際の形式をもとにした「テスト用データ」）。

実在の地震の電文ではない。tests/fixtures/vxse53_other_city.xml だけは気象庁が公開した実物。
使い方: python tests/fixtures/make_fixtures.py
"""
from pathlib import Path

HERE = Path(__file__).parent

TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<Report xmlns="http://xml.kishou.go.jp/jmaxml1/" xmlns:jmx="http://xml.kishou.go.jp/jmaxml1/">
<Control>
<Title>震源・震度に関する情報</Title>
<DateTime>2026-11-20T00:05:00Z</DateTime>
<Status>{status}</Status>
<EditorialOffice>福岡管区気象台</EditorialOffice>
<PublishingOffice>気象庁</PublishingOffice>
</Control>
<Head xmlns="http://xml.kishou.go.jp/jmaxml1/informationBasis1/">
<Title>震源・震度情報</Title>
<ReportDateTime>2026-11-20T09:05:00+09:00</ReportDateTime>
<TargetDateTime>2026-11-20T09:05:00+09:00</TargetDateTime>
<EventID>{event_id}</EventID>
<InfoType>{info_type}</InfoType>
<Serial>1</Serial>
<InfoKind>地震情報</InfoKind>
<InfoKindVersion>1.0_1</InfoKindVersion>
<Headline>
<Text>２０日０９時０２分ころ、地震がありました。</Text>
</Headline>
</Head>
<Body xmlns="http://xml.kishou.go.jp/jmaxml1/body/seismology1/" xmlns:jmx_eb="http://xml.kishou.go.jp/jmaxml1/elementBasis1/">
<Earthquake>
<OriginTime>2026-11-20T09:02:00+09:00</OriginTime>
<ArrivalTime>2026-11-20T09:02:00+09:00</ArrivalTime>
<Hypocenter>
<Area>
<Name>日向灘</Name>
<Code type="震央地名">790</Code>
<jmx_eb:Coordinate description="北緯３１．７度　東経１３１．７度　深さ　３０ｋｍ" >+31.7+131.7-30000/</jmx_eb:Coordinate>
</Area>
</Hypocenter>
<jmx_eb:Magnitude type="Mj" description="Ｍ６．５">6.5</jmx_eb:Magnitude>
</Earthquake>
<Intensity>
<Observation>
<MaxInt>{max_int}</MaxInt>
<Pref><Name>宮崎県</Name><Code>45</Code><MaxInt>{max_int}</MaxInt>
<Area><Name>宮崎県南部平野部</Name><Code>762</Code><MaxInt>{max_int}</MaxInt>
{city}
<City><Name>宮崎市</Name><Code>4520100</Code><MaxInt>4</MaxInt>
<IntensityStation><Name>宮崎市松橋</Name><Code>4520120</Code><Int>4</Int></IntensityStation>
</City>
</Area>
</Pref>
</Observation>
</Intensity>
</Body>
</Report>
"""

NICHINAN = """<City><Name>日南市</Name><Code>4520400</Code><MaxInt>{i}</MaxInt>
<IntensityStation><Name>日南市中央通</Name><Code>4520430</Code><Int>{i}</Int></IntensityStation>
</City>"""
NICHINAN_UNREPORTED = """<City><Name>日南市</Name><Code>4520400</Code><Condition>震度５弱以上未入電</Condition>
</City>"""

CASES = {
    "vxse53_nichinan_5minus.xml": dict(status="通常", info_type="発表", event_id="20261120090200", max_int="5-",
                                       city=NICHINAN.format(i="5-")),
    "vxse53_nichinan_6minus.xml": dict(status="通常", info_type="発表", event_id="20261120090200", max_int="6-",
                                       city=NICHINAN.format(i="6-")),
    "vxse53_nichinan_4.xml": dict(status="通常", info_type="発表", event_id="20261120100000", max_int="4",
                                  city=NICHINAN.format(i="4")),
    "vxse53_nichinan_unreported.xml": dict(status="通常", info_type="発表", event_id="20261120110000",
                                           max_int="5+", city=NICHINAN_UNREPORTED),
    "vxse53_training.xml": dict(status="訓練", info_type="発表", event_id="20261120120000", max_int="6-",
                                city=NICHINAN.format(i="6-")),
    "vxse53_cancel.xml": dict(status="通常", info_type="取消", event_id="20261120090200", max_int="5-",
                              city=NICHINAN.format(i="5-")),
    "vxse53_no_nichinan.xml": dict(status="通常", info_type="発表", event_id="20261120130000", max_int="4",
                                   city=""),
}

if __name__ == "__main__":
    for name, kw in CASES.items():
        (HERE / name).write_text(TEMPLATE.format(**kw), encoding="utf-8")
        print("wrote", name)

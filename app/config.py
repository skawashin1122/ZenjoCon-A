"""設定（環境変数から読む）。秘密の値はコードに書かない。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
BASE_DIR = Path(__file__).resolve().parent.parent

# 案内先の電話番号・URL（設計書 1-4・3章）。文言・番号は市・消防本部の案内で確認すること
EMERGENCY_TEL = "119"
NICHINAN_SOUDAN_TEL = "0987-31-1111"  # 日南市救急医療電話相談（24時間365日・医師・看護師が対応）
QSUKE_URL = "https://www.fdma.go.jp/relocation/neuter/topics/filedList9_6/kyukyu_app/kyukyu_app_web/index.html"
JMA_FEED_URL = "https://www.data.jma.go.jp/developer/xml/feed/eqvol.xml"


def _load_dotenv(path: Path) -> None:
    """.env があれば読む（すでに設定済みの環境変数は上書きしない）。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


@dataclass
class Settings:
    channel_secret: str = ""
    channel_access_token: str = ""
    db_path: str = str(BASE_DIR / "mamorinet.sqlite3")
    public_url: str = "http://localhost:8000"
    watch_interval: int = 300
    quake_interval: int = 60
    quake_enabled: bool = True
    city_code: str = "4520400"
    quake_threshold: str = "5-"
    quake_max_age_hours: float = 3.0     # これより古い電文では送らない（サーバー再起動時の誤送信防止）
    safety_timeout_minutes: int = 30     # 地震の安否確認で「応答なし」とみなすまでの時間
    shelter_url: str = "https://www.city.nichinan.lg.jp/"

    @property
    def dry_run(self) -> bool:
        """LINEの鍵が無いときは実際には送らない。"""
        return not self.channel_access_token

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv(BASE_DIR / ".env")
        e = os.environ.get
        d = cls()
        return cls(
            channel_secret=e("LINE_CHANNEL_SECRET", ""),
            channel_access_token=e("LINE_CHANNEL_ACCESS_TOKEN", ""),
            db_path=e("MAMORI_DB_PATH", d.db_path),
            public_url=e("MAMORI_PUBLIC_URL", d.public_url).rstrip("/"),
            watch_interval=int(e("MAMORI_WATCH_INTERVAL", d.watch_interval)),
            quake_interval=int(e("MAMORI_QUAKE_INTERVAL", d.quake_interval)),
            quake_enabled=e("MAMORI_QUAKE_ENABLED", "1") not in ("0", "false", "False", ""),
            city_code=e("MAMORI_CITY_CODE", d.city_code),
            quake_threshold=e("MAMORI_QUAKE_THRESHOLD", d.quake_threshold),
            quake_max_age_hours=float(e("MAMORI_QUAKE_MAX_AGE_HOURS", d.quake_max_age_hours)),
            safety_timeout_minutes=int(e("MAMORI_SAFETY_TIMEOUT_MINUTES", d.safety_timeout_minutes)),
            shelter_url=e("MAMORI_SHELTER_URL", d.shelter_url),
        )

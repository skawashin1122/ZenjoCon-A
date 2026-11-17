"""LINE のリッチメニュー（トーク画面下の大きなボタン）を作って、全員の既定にする。設計書 3章 機能①

  python scripts/richmenu.py make-image            richmenu.png を作る（Pillow と日本語フォントが必要）
  python scripts/richmenu.py upload richmenu.png   LINE に登録して既定のメニューにする

  ┌─────────────────────────┐
  │      🌞 げんき！         │  ← 2500×1000
  ├────────────┬────────────┤
  │ 📞 家族に電話│ 🚑 迷ったら │  ← 1250×686 ずつ
  └────────────┴────────────┘
必要：環境変数 LINE_CHANNEL_ACCESS_TOKEN（.env でも可）
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import Settings  # noqa: E402

W, H, TOP = 2500, 1686, 1000

MENU = {
    "size": {"width": W, "height": H},
    "selected": True,
    "name": "mamorinet-main",
    "chatBarText": "メニュー（げんき）",
    "areas": [
        {"bounds": {"x": 0, "y": 0, "width": W, "height": TOP},
         "action": {"type": "postback", "data": "a=genki", "displayText": "げんき！"}},
        {"bounds": {"x": 0, "y": TOP, "width": W // 2, "height": H - TOP},
         "action": {"type": "postback", "data": "a=call_family", "displayText": "家族に電話"}},
        {"bounds": {"x": W // 2, "y": TOP, "width": W - W // 2, "height": H - TOP},
         "action": {"type": "postback", "data": "a=help", "displayText": "迷ったら"}},
    ],
}

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Bold.otf",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "C:/Windows/Fonts/meiryob.ttc",
]


def make_image(out: str = "richmenu.png") -> None:
    from PIL import Image, ImageDraw, ImageFont  # pip install pillow

    font_path = next((p for p in FONT_CANDIDATES if Path(p).exists()), None)
    if not font_path:
        sys.exit("日本語フォントが見つかりません（Ubuntu: sudo apt install fonts-noto-cjk）")
    img = Image.new("RGB", (W, H), "#ffffff")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, TOP], fill="#ffb300")              # げんき：明るい黄色
    d.rectangle([0, TOP, W // 2, H], fill="#2e7d32")          # 家族に電話：緑
    d.rectangle([W // 2, TOP, W, H], fill="#c62828")          # 迷ったら：赤
    d.line([W // 2, TOP, W // 2, H], fill="#ffffff", width=12)
    d.line([0, TOP, W, TOP], fill="#ffffff", width=12)

    def center(text, box, size, color):
        f = ImageFont.truetype(font_path, size)
        x0, y0, x1, y1 = box
        l, t, r, b = d.textbbox((0, 0), text, font=f)
        d.text(((x0 + x1 - (r - l)) / 2, (y0 + y1 - (b - t)) / 2 - t), text, font=f, fill=color)

    center("げんき！", (0, 0, W, TOP - 180), 330, "#1a1a1a")
    center("毎朝ここを1回押す", (0, TOP - 260, W, TOP - 40), 120, "#1a1a1a")
    center("家族に電話", (0, TOP, W // 2, H), 150, "#ffffff")
    center("迷ったら", (W // 2, TOP, W, H), 150, "#ffffff")
    img.save(out, optimize=True)
    print("wrote", out, f"{Path(out).stat().st_size // 1024}KB（1MBまで）")


def upload(image_path: str) -> None:
    s = Settings.from_env()
    if not s.channel_access_token:
        sys.exit("LINE_CHANNEL_ACCESS_TOKEN が未設定です")
    h = {"Authorization": f"Bearer {s.channel_access_token}"}
    with httpx.Client(timeout=30, headers=h) as c:
        r = c.post("https://api.line.me/v2/bot/richmenu", json=MENU)
        r.raise_for_status()
        rid = r.json()["richMenuId"]
        with open(image_path, "rb") as f:
            r = c.post(f"https://api-data.line.me/v2/bot/richmenu/{rid}/content",
                       content=f.read(), headers={"Content-Type": "image/png"})
        r.raise_for_status()
        c.post(f"https://api.line.me/v2/bot/user/all/richmenu/{rid}").raise_for_status()
    print("リッチメニューを登録して、全員の既定にしました:", rid)


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "make-image":
        make_image(sys.argv[2] if len(sys.argv) > 2 else "richmenu.png")
    elif len(sys.argv) >= 3 and sys.argv[1] == "upload":
        upload(sys.argv[2])
    else:
        print(__doc__)

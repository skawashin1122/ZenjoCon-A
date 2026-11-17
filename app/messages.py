"""LINE に送るメッセージの文面（設計書 3章）。

文字は大きく・短く。ボタンは1画面に少なく。医療の判断はしない。
"""
from __future__ import annotations

from urllib.parse import urlencode

from .config import EMERGENCY_TEL, NICHINAN_SOUDAN_TEL, QSUKE_URL

DISCLAIMER = "※このサービスは医療の判断をしません。迷ったら119番へ。"


def tel_uri(number: str) -> str:
    return "tel:" + "".join(ch for ch in number if ch.isdigit() or ch == "+")


def postback(label: str, display: str | None = None, **data) -> dict:
    a = {"type": "postback", "label": label, "data": urlencode(data)}
    if display:
        a["displayText"] = display
    return a


def uri(label: str, link: str) -> dict:
    return {"type": "uri", "label": label, "uri": link}


def text(t: str, quick: list[dict] | None = None) -> dict:
    m = {"type": "text", "text": t}
    if quick:
        m["quickReply"] = {"items": [{"type": "action", "action": a} for a in quick]}
    return m


def buttons(alt: str, body: str, actions: list[dict]) -> dict:
    """ボタン付きメッセージ（タイトル無し：本文160字・ボタン4つまで）。"""
    return {
        "type": "template",
        "altText": alt[:400],
        "template": {"type": "buttons", "text": body[:160], "actions": actions[:4]},
    }


GENKI_BUTTON = postback("🌞 げんき！", "げんき！", a="genki")


# ---------- 登録 ----------

def welcome(terms_url: str) -> list[dict]:
    return [
        text("にちなん・まもりネットです。\n"
             "毎朝「げんき」を1回押すだけの見守りサービスです。\n"
             "決めた時刻までに押されないと、家族にお知らせします。\n\n"
             f"始める前に、利用のきまりを読んでください。\n{terms_url}"),
        buttons("どちらで始めますか？",
                "きまりに同意して、どちらかを選んでください。",
                [postback("見守られる人（本人）", "本人として始めます", a="start", r="self"),
                 postback("家族（通知を受ける人）", "家族として始めます", a="start", r="family")]),
    ]


def registered_self(name: str, code: str) -> list[dict]:
    return [text(f"{name}さん、登録しました。\n\n"
                 "毎朝、下のメニューの「げんき！」を押してください。\n\n"
                 f"家族に、この【招待コード】を伝えてください。\n\n　{code}\n\n"
                 "家族がこのアカウントを友だち追加して、コードを送ると見守りが始まります。")]


def registered_family() -> list[dict]:
    return [text("家族として登録しました。\n見守る方の【招待コード】（6けたの数字）を送ってください。")]


def linked(family_name: str, self_name: str, priority: int, start_date: str) -> list[dict]:
    return [text(f"{self_name}さんとつながりました（あなたは第{priority}連絡先です）。\n"
                 f"見守りは {start_date} から始まります。\n\n"
                 "「げんき」が決めた時刻までに押されないと、あなたにお知らせします。"
                 "毎日の記録は送りません（何もない日は通知なし）。\n\n"
                 "「設定」と送ると、時刻の確認・変更のしかたが出ます。",
                 quick=[postback("設定を見る", "設定", a="settings")])]


# ---------- げんきボタン ----------

def genki_reply(hour: int, name: str) -> list[dict]:
    if hour < 11:
        greet = "おはようございます。"
    elif hour < 17:
        greet = "こんにちは。"
    else:
        greet = "こんばんは。"
    return [text(f"{greet}{name}さん、今日もげんきやね！\nまた明日も押してね。")]


def genki_already(name: str) -> list[dict]:
    return [text(f"{name}さん、今日の「げんき」はもう届いちょります。ありがとう！")]


def remind_self(name: str) -> list[dict]:
    return [buttons(f"{name}さん、げんきですか？",
                    f"{name}さん、げんきですか？\n下のボタンを押してください。",
                    [GENKI_BUTTON])]


def notify_family(self_name: str, self_phone: str, self_id: int, date: str, second: bool = False,
                  again: bool = False) -> list[dict]:
    if again:
        body = f"{self_name}さんの「げんき」がまだです。まだ確認されていません。電話してみてください。"
    elif second:
        body = f"{self_name}さんの「げんき」がまだで、第1連絡先の方もまだ確認できていません。電話してみてください。"
    else:
        body = f"{self_name}さんの「げんき」がまだです。電話してみてください。"
    actions = []
    if self_phone:
        actions.append(uri(f"📞 {self_name}さんに電話"[:20], tel_uri(self_phone)))
    actions.append(postback("✅ 確認できた", "確認できました", a="confirm", s=self_id, d=date))
    actions.append(uri("🚑 救急車（119）", tel_uri(EMERGENCY_TEL)))
    return [buttons(body, body, actions)]


def confirmed_reply(self_name: str) -> list[dict]:
    return [text(f"ありがとうございます。{self_name}さんの確認ができたことを記録しました。")]


def tell_family_genki(self_name: str, hhmm: str) -> list[dict]:
    return [text(f"{self_name}さんが {hhmm} に「げんき」を押しました。ひと安心です。")]


# ---------- 迷ったら（判定はしない。案内するだけ） ----------

def help_menu() -> list[dict]:
    def row(color: str, title: str, sub: str, label: str, link: str, style: str) -> dict:
        contents = [
            {"type": "text", "text": title, "weight": "bold", "size": "lg", "wrap": True, "color": color},
        ]
        if sub:
            contents.append({"type": "text", "text": sub, "size": "md", "wrap": True, "color": "#333333"})
        contents.append({"type": "button", "style": style, "height": "md", "margin": "md",
                         "color": color if style == "primary" else None,
                         "action": uri(label, link)})
        # None の color は入れない
        contents[-1] = {k: v for k, v in contents[-1].items() if v is not None}
        return {"type": "box", "layout": "vertical", "spacing": "sm", "paddingAll": "md",
                "contents": contents}

    bubble = {
        "type": "bubble",
        "size": "giga",
        "body": {
            "type": "box", "layout": "vertical", "spacing": "md",
            "contents": [
                row("#C62828", "🔴 意識がない・息が苦しい・胸が痛い", "", "119番に電話", tel_uri(EMERGENCY_TEL),
                    "primary"),
                {"type": "separator"},
                row("#8D6E00", "🟡 救急車を呼ぶか迷う・夜間や休日",
                    f"日南市救急医療電話相談\n{NICHINAN_SOUDAN_TEL}（24時間365日）\n医師・看護師が答えてくれます",
                    "電話相談にかける", tel_uri(NICHINAN_SOUDAN_TEL), "primary"),
                {"type": "separator"},
                row("#455A64", "⚪ 自分で調べたい", "全国版救急受診アプリ「Q助」（消防庁）", "Q助をひらく",
                    QSUKE_URL, "secondary"),
                {"type": "text", "text": DISCLAIMER, "size": "sm", "wrap": True, "color": "#666666"},
            ],
        },
    }
    return [{"type": "flex", "altText": "迷ったら：119番／日南市救急医療電話相談 0987-31-1111／Q助",
             "contents": bubble}]


def call_family(families: list[tuple[str, str]]) -> list[dict]:
    """(呼び名, 電話番号) の一覧から電話ボタンを作る。"""
    with_phone = [(n, p) for n, p in families if p]
    if not with_phone:
        return [text("家族の電話番号がまだ登録されていません。\n"
                     "家族の方が、このアカウントに「電話 09012345678」のように送ると登録できます。")]
    actions = [uri(f"📞 {n}"[:20], tel_uri(p)) for n, p in with_phone[:4]]
    return [buttons("家族に電話", "だれに電話しますか？", actions)]


# ---------- ひとこと（優先度を上げることはあっても下げない） ----------

WORRY_WORDS = ("きつい", "キツい", "転んだ", "ころんだ", "こけた", "痛い", "いたい", "助けて", "たすけて",
               "苦しい", "くるしい", "動けない", "うごけない", "具合が悪い", "ぐあいがわるい")


def has_worry_word(t: str) -> str | None:
    for w in WORRY_WORDS:
        if w in t:
            return w
    return None


def worry_to_family(self_name: str, said: str, self_phone: str) -> list[dict]:
    body = f"{self_name}さんから「{said[:40]}」とメッセージがありました。電話してみてください。"
    actions = [uri(f"📞 {self_name}さんに電話"[:20], tel_uri(self_phone))] if self_phone else []
    actions.append(uri("🚑 救急車（119）", tel_uri(EMERGENCY_TEL)))
    return [buttons(body, body, actions)]


def worry_reply() -> list[dict]:
    return [text("家族にお知らせしました。\nつらいときは、がまんせずに相談してください。")] + help_menu()


# ---------- 地震の安否確認 ----------

def quake_ask(event_id: str, label: str) -> list[dict]:
    body = f"大きな地震がありました（日南市 震度{label}）。\n無事ですか？"
    return [buttons(body, body, [
        postback("🙆 無事", "無事です", a="safe", eq=event_id),
        postback("🆘 助けが必要", "助けが必要です", a="needhelp", eq=event_id),
    ])]


def quake_safe_reply() -> list[dict]:
    return [text("無事でよかったです。家族にお知らせしました。\n余震に気をつけてください。")]


def quake_help_reply(shelter_url: str) -> list[dict]:
    return [buttons("家族にお知らせしました。",
                    "家族にお知らせしました。\nけが・急病のときは119番に電話してください。",
                    [uri("🚑 119番に電話", tel_uri(EMERGENCY_TEL)),
                     uri("避難所の案内（市）", shelter_url)])]


def quake_to_family(self_name: str, answer: str, label: str, self_phone: str) -> list[dict]:
    if answer == "safe":
        return [text(f"【地震（日南市 震度{label}）】{self_name}さんから「無事です」と返事がありました。")]
    if answer == "help":
        body = f"【至急】地震のあと、{self_name}さんから「助けが必要」と返事がありました。すぐに連絡してください。"
    else:
        body = f"【地震】{self_name}さんから、地震のあとの返事がありません。電話してみてください。"
    actions = [uri(f"📞 {self_name}さんに電話"[:20], tel_uri(self_phone))] if self_phone else []
    actions.append(uri("🚑 救急車（119）", tel_uri(EMERGENCY_TEL)))
    return [buttons(body, body, actions)]


# ---------- 設定・その他 ----------

HELP_TEXT = (
    "【使い方】\n"
    "・げんき … 毎朝1回押す（メニューのボタン）\n"
    "・迷ったら … 119番・市の電話相談の案内\n"
    "・設定 … 時刻・お休みの確認\n"
    "・時刻 10:00 11:00 13:00 … 再通知・家族通知・第2通知の時刻を変える\n"
    "・お休み 11/20-11/22 … 旅行・入院などで押せない日\n"
    "・お休み解除\n"
    "・電話 09012345678 … 自分の電話番号（家族の電話ボタン用）\n"
    "・名前 ○○ … 呼び名を変える\n"
    "・コード … 招待コードを見る（本人）\n"
    "・登録解除 … やめる（記録を消します）"
)


def unknown_reply(is_self: bool) -> list[dict]:
    if is_self:
        return [text("毎朝、下のメニューの「げんき！」を押してください。\n使い方は「使い方」と送ると出ます。",
                     quick=[GENKI_BUTTON])]
    return [text("使い方は「使い方」と送ると出ます。")]


def unregister_confirm() -> list[dict]:
    return [buttons("登録を解除しますか？",
                    "登録を解除しますか？\n見守りの記録とつながりはすべて消えます。",
                    [postback("解除する", "解除します", a="unregister"),
                     postback("やめておく", "やめておきます", a="noop")])]

"""まもりネットの中心となる処理。

- LINE からのイベント（友だち追加・ボタン・文字）の処理
- 見守り判定（5分ごと）：状態遷移 watch.next_step を使う
- 地震の安否確認：quake.py で解析した電文をもとに送信
時刻 now は外から渡せるようにして、テストで「10時5分」などを再現できるようにしている。
"""
from __future__ import annotations

import logging
import re
import secrets
import sqlite3
from datetime import date, datetime, time, timedelta
from urllib.parse import parse_qs

from . import messages as M
from .config import JST, Settings
from .line_api import Messenger
from .quake import QuakeReport, intensity_label, report_needs_alert
from .watch import Action, Schedule, State, next_step, on_family_confirm, on_genki

log = logging.getLogger("mamorinet.service")

STATE_BY_NAME = {s.name: s for s in State}


def jst_now() -> datetime:
    return datetime.now(JST)


def iso(dt: datetime) -> str:
    return dt.astimezone(JST).isoformat(timespec="seconds")


def parse_hhmm(s: str) -> time | None:
    m = re.fullmatch(r"\s*(\d{1,2})[:：時](\d{1,2})?分?\s*", s)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if 0 <= h <= 23 and 0 <= mi <= 59:
        return time(h, mi)
    return None


def fmt_hhmm(t: time) -> str:
    return f"{t.hour}:{t.minute:02d}"


def schedule_of(u: sqlite3.Row) -> Schedule:
    return Schedule(parse_hhmm(u["remind_time"]), parse_hhmm(u["family1_time"]), parse_hhmm(u["family2_time"]))


def parse_holiday(arg: str, today: date) -> tuple[date, date] | None:
    """「11/20」「11/20-11/22」「11月20日〜22日」「今日」「明日」などを読む。"""
    arg = arg.strip().translate(str.maketrans("０１２３４５６７８９／－〜～", "0123456789/---"))
    if arg in ("今日", "きょう"):
        return today, today
    if arg in ("明日", "あした"):
        d = today + timedelta(days=1)
        return d, d
    nums = re.findall(r"\d+", arg.replace("月", "/").replace("日", " "))
    try:
        if len(nums) == 2:
            a = _md(int(nums[0]), int(nums[1]), today)
            return a, a
        if len(nums) == 3:  # 11/20-22
            a = _md(int(nums[0]), int(nums[1]), today)
            b = _md(int(nums[0]), int(nums[2]), today)
        elif len(nums) == 4:
            a = _md(int(nums[0]), int(nums[1]), today)
            b = _md(int(nums[2]), int(nums[3]), today)
        else:
            return None
    except ValueError:
        return None
    if b < a:
        b = b.replace(year=b.year + 1)
    if (b - a).days > 60:
        return None
    return a, b


def _md(month: int, day: int, today: date) -> date:
    d = date(today.year, month, day)
    if d < today - timedelta(days=30):  # 12月に「1/3」と書いたら来年の1月3日
        d = d.replace(year=today.year + 1)
    return d


def jp_date(d: date | str) -> str:
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return f"{d.month}月{d.day}日"


class Service:
    def __init__(self, conn: sqlite3.Connection, line: Messenger, settings: Settings):
        self.db = conn
        self.line = line
        self.s = settings

    # ------------------------------------------------------------------ DB の小道具
    def user_by_line(self, line_id: str) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM users WHERE line_user_id=?", (line_id,)).fetchone()

    def user(self, uid: int) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()

    def families_of(self, self_id: int) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT u.*, l.priority FROM links l JOIN users u ON u.id=l.family_id "
            "WHERE l.self_id=? ORDER BY l.priority", (self_id,)).fetchall()

    def selves_of(self, family_id: int) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT u.* FROM links l JOIN users u ON u.id=l.self_id WHERE l.family_id=? ORDER BY u.id",
            (family_id,)).fetchall()

    def today_status(self, self_id: int, d: date, now: datetime) -> sqlite3.Row:
        self.db.execute(
            "INSERT OR IGNORE INTO daily_status(self_id, date, state, updated_at) VALUES (?,?,?,?)",
            (self_id, d.isoformat(), State.WAITING.name, iso(now)))
        return self.db.execute("SELECT * FROM daily_status WHERE self_id=? AND date=?",
                               (self_id, d.isoformat())).fetchone()

    def set_state(self, self_id: int, d: date, state: State, now: datetime, **cols) -> None:
        sets = ", ".join(["state=?", "updated_at=?"] + [f"{k}=?" for k in cols])
        self.db.execute(f"UPDATE daily_status SET {sets} WHERE self_id=? AND date=?",
                        (state.name, iso(now), *cols.values(), self_id, d.isoformat()))

    def log_notice(self, kind: str, to_id: int | None, about_id: int | None, is_push: bool, now: datetime):
        self.db.execute("INSERT INTO notifications(at, kind, to_id, about_id, is_push) VALUES (?,?,?,?,?)",
                        (iso(now), kind, to_id, about_id, int(is_push)))

    async def push(self, to: sqlite3.Row, msgs: list[dict], kind: str, about_id: int | None, now: datetime):
        await self.line.push(to["line_user_id"], msgs)
        self.log_notice(kind, to["id"], about_id, True, now)

    async def reply(self, token: str, msgs: list[dict], kind: str, to: sqlite3.Row | None, now: datetime):
        await self.line.reply(token, msgs)
        self.log_notice(kind, to["id"] if to else None, None, False, now)

    def on_holiday(self, u: sqlite3.Row, d: date) -> bool:
        return bool(u["holiday_from"] and u["holiday_to"]
                    and u["holiday_from"] <= d.isoformat() <= u["holiday_to"])

    def new_invite_code(self) -> str:
        while True:
            code = f"{secrets.randbelow(1_000_000):06d}"
            if not self.db.execute("SELECT 1 FROM users WHERE invite_code=?", (code,)).fetchone():
                return code

    def watch_start_date(self, u: sqlite3.Row, now: datetime) -> date:
        """登録した日の再通知時刻を過ぎていたら、見守りは翌日から（登録直後に家族へ誤報が飛ばないように）。"""
        sch = schedule_of(u)
        today = now.date()
        return today if now.time() < sch.remind else today + timedelta(days=1)

    # ------------------------------------------------------------------ LINE イベント
    async def handle_event(self, ev: dict, now: datetime | None = None) -> None:
        now = now or jst_now()
        etype = ev.get("type")
        src = ev.get("source", {})
        if src.get("type") != "user":   # グループ・トークルームでは動かさない
            return
        line_id = src.get("userId", "")
        token = ev.get("replyToken", "")
        u = self.user_by_line(line_id)

        if etype == "follow":
            await self.line.reply(token, M.welcome(f"{self.s.public_url}/terms/"))
            return
        if etype == "unfollow":
            if u:
                self.delete_user(u["id"])
            return
        if etype == "postback":
            data = {k: v[0] for k, v in parse_qs(ev.get("postback", {}).get("data", "")).items()}
            await self.on_postback(data, u, line_id, token, now)
            return
        if etype == "message" and ev.get("message", {}).get("type") == "text":
            await self.on_text(ev["message"]["text"].strip(), u, line_id, token, now)

    async def on_postback(self, data: dict, u, line_id: str, token: str, now: datetime) -> None:
        a = data.get("a")
        if a == "start":
            await self.register(line_id, data.get("r", ""), token, now)
            return
        if a == "noop":
            return
        if u is None:
            await self.line.reply(token, M.welcome(f"{self.s.public_url}/terms/"))
            return
        if a == "genki":
            await self.press_genki(u, token, now)
        elif a == "help":
            await self.reply(token, M.help_menu(), "help_menu", u, now)
        elif a == "call_family":
            await self.reply_call_family(u, token, now)
        elif a == "confirm":
            await self.family_confirm(u, int(data.get("s", 0)), data.get("d", ""), token, now)
        elif a in ("safe", "needhelp"):
            await self.safety_answer(u, data.get("eq", ""), "safe" if a == "safe" else "help", token, now)
        elif a == "settings":
            await self.reply(token, [M.text(self.settings_text(u, now))], "settings", u, now)
        elif a == "unregister":
            self.delete_user(u["id"])
            await self.line.reply(token, [M.text("登録を解除しました。記録はすべて消しました。ご協力ありがとうございました。")])

    async def on_text(self, t: str, u, line_id: str, token: str, now: datetime) -> None:
        if u is None:
            await self.line.reply(token, M.welcome(f"{self.s.public_url}/terms/"))
            return
        is_self = u["role"] == "self"
        head, _, arg = t.partition(" ") if " " in t else t.partition("　")
        head = head.strip()

        if is_self and t in ("げんき", "げんき！", "げんき!", "元気", "元気！"):
            await self.press_genki(u, token, now)
        elif t in ("迷ったら", "救急", "119"):
            await self.reply(token, M.help_menu(), "help_menu", u, now)
        elif t in ("使い方", "ヘルプ", "つかいかた"):
            await self.reply(token, [M.text(M.HELP_TEXT)], "help_text", u, now)
        elif t == "設定":
            await self.reply(token, [M.text(self.settings_text(u, now))], "settings", u, now)
        elif t == "家族に電話" and is_self:
            await self.reply_call_family(u, token, now)
        elif t == "コード" and is_self:
            await self.reply(token, [M.text(f"招待コード：{u['invite_code']}")], "code", u, now)
        elif t == "登録解除":
            await self.reply(token, M.unregister_confirm(), "unregister_confirm", u, now)
        elif head == "時刻":
            await self.cmd_times(u, arg, token, now)
        elif head == "お休み" or t == "お休み解除":
            await self.cmd_holiday(u, "解除" if t == "お休み解除" else arg, token, now)
        elif head == "電話":
            await self.cmd_phone(u, arg, token, now)
        elif head == "名前" and arg.strip():
            self.db.execute("UPDATE users SET nickname=? WHERE id=?", (arg.strip()[:20], u["id"]))
            await self.reply(token, [M.text(f"呼び名を「{arg.strip()[:20]}」にしました。")], "name", u, now)
        elif not is_self and re.fullmatch(r"\d{6}", t.translate(str.maketrans("０１２３４５６７８９", "0123456789"))):
            await self.link_family(u, t.translate(str.maketrans("０１２３４５６７８９", "0123456789")), token, now)
        elif is_self and M.has_worry_word(t):
            await self.worry(u, t, token, now)
        else:
            await self.reply(token, M.unknown_reply(is_self), "unknown", u, now)

    # ------------------------------------------------------------------ 登録・つながり
    async def register(self, line_id: str, role: str, token: str, now: datetime) -> None:
        if role not in ("self", "family"):
            return
        u = self.user_by_line(line_id)
        if u:
            await self.line.reply(token, [M.text("すでに登録されています。「設定」で確認できます。")])
            return
        name = (await self.line.display_name(line_id)) or "利用者"
        code = self.new_invite_code() if role == "self" else None
        self.db.execute(
            "INSERT INTO users(line_user_id, nickname, role, invite_code, consent_at, created_at) "
            "VALUES (?,?,?,?,?,?)", (line_id, name[:20], role, code, iso(now), iso(now)))
        u = self.user_by_line(line_id)
        if role == "self":
            self.db.execute("UPDATE users SET watch_from=? WHERE id=?",
                            (self.watch_start_date(u, now).isoformat(), u["id"]))
            await self.reply(token, M.registered_self(name, code), "registered", u, now)
        else:
            await self.reply(token, M.registered_family(), "registered", u, now)

    async def link_family(self, fam, code: str, token: str, now: datetime) -> None:
        target = self.db.execute("SELECT * FROM users WHERE invite_code=? AND role='self'", (code,)).fetchone()
        if not target:
            await self.reply(token, [M.text("その招待コードは見つかりませんでした。もう一度たしかめてください。")],
                             "link_fail", fam, now)
            return
        current = self.families_of(target["id"])
        if any(f["id"] == fam["id"] for f in current):
            await self.reply(token, [M.text(f"{target['nickname']}さんとは、もうつながっています。")],
                             "link_dup", fam, now)
            return
        used = {f["priority"] for f in current}
        free = [p for p in (1, 2) if p not in used]
        if not free:
            await self.reply(token, [M.text("連絡先は2人までです。いまの連絡先の方に相談してください。")],
                             "link_full", fam, now)
            return
        self.db.execute("INSERT INTO links(self_id, family_id, priority) VALUES (?,?,?)",
                        (target["id"], fam["id"], free[0]))
        # まだ見守りが始まっていなければ、つながった時刻を基準に始める日を決め直す
        if not current:
            self.db.execute("UPDATE users SET watch_from=? WHERE id=?",
                            (self.watch_start_date(target, now).isoformat(), target["id"]))
            target = self.user(target["id"])
        await self.reply(token, M.linked(fam["nickname"], target["nickname"], free[0],
                                         jp_date(target["watch_from"])), "linked", fam, now)

    def delete_user(self, uid: int) -> None:
        """登録解除。つながり・見守り記録も消える（ON DELETE CASCADE）。"""
        self.db.execute("DELETE FROM users WHERE id=?", (uid,))

    # ------------------------------------------------------------------ げんきボタン
    async def press_genki(self, u, token: str, now: datetime) -> None:
        if u["role"] != "self":
            await self.reply(token, [M.text("「げんき」は見守られる方が押すボタンです。")], "genki_family", u, now)
            return
        d = now.date()
        st = self.today_status(u["id"], d, now)
        state = STATE_BY_NAME[st["state"]]
        if state == State.GENKI:
            await self.reply(token, M.genki_already(u["nickname"]), "genki_again", u, now)
            return
        new_state, action = on_genki(state)
        self.set_state(u["id"], d, new_state, now, genki_at=iso(now))
        # 毎朝の返信は「応答メッセージ」なので無料の通数に数えない
        await self.reply(token, M.genki_reply(now.hour, u["nickname"]), "genki", u, now)
        if action == Action.TELL_FAMILY_GENKI:
            for f in self.families_of(u["id"]):
                await self.push(f, M.tell_family_genki(u["nickname"], fmt_hhmm(now.time())),
                                "family_genki", u["id"], now)

    async def family_confirm(self, fam, self_id: int, d: str, token: str, now: datetime) -> None:
        if not any(s["id"] == self_id for s in self.selves_of(fam["id"])):
            return
        st = self.db.execute("SELECT * FROM daily_status WHERE self_id=? AND date=?", (self_id, d)).fetchone()
        target = self.user(self_id)
        if not st or not target:
            return
        new_state = on_family_confirm(STATE_BY_NAME[st["state"]])
        if new_state == State.CONFIRMED:
            self.set_state(self_id, date.fromisoformat(d), new_state, now, confirmed_at=iso(now))
            await self.reply(token, M.confirmed_reply(target["nickname"]), "confirmed", fam, now)
            # もう一人の家族にも「確認できた」と知らせる（同じことを二重にしないため）
            for f in self.families_of(self_id):
                if f["id"] != fam["id"] and STATE_BY_NAME[st["state"]] == State.FAMILY2:
                    await self.push(f, [M.text(f"{target['nickname']}さんの確認ができました（{fam['nickname']}さん）。")],
                                    "family_confirmed_shared", self_id, now)
        else:
            await self.reply(token, [M.text(f"{target['nickname']}さんの記録はもう更新されています"
                                            f"（{STATE_BY_NAME[st['state']].value}）。")], "confirm_noop", fam, now)

    async def reply_call_family(self, u, token: str, now: datetime) -> None:
        fams = [(f["nickname"], f["phone"]) for f in self.families_of(u["id"])]
        await self.reply(token, M.call_family(fams), "call_family", u, now)

    async def worry(self, u, said: str, token: str, now: datetime) -> None:
        """「きつい」「転んだ」など：家族へすぐ知らせる（優先度を上げる方向だけ）。"""
        for f in self.families_of(u["id"]):
            await self.push(f, M.worry_to_family(u["nickname"], said, u["phone"]), "worry", u["id"], now)
        await self.reply(token, M.worry_reply(), "worry_reply", u, now)

    # ------------------------------------------------------------------ 設定
    def targets_for_settings(self, u) -> list[sqlite3.Row]:
        return [u] if u["role"] == "self" else self.selves_of(u["id"])

    def settings_text(self, u, now: datetime) -> str:
        lines = [f"【{u['nickname']}さんの設定】（{'本人' if u['role'] == 'self' else '家族'}）"]
        if u["phone"]:
            lines.append(f"電話：{u['phone']}")
        targets = self.targets_for_settings(u)
        if not targets:
            lines.append("まだ見守る方とつながっていません。招待コード（6けた）を送ってください。")
        for t in targets:
            fams = self.families_of(t["id"])
            lines.append("")
            lines.append(f"▼ {t['nickname']}さんの見守り")
            lines.append(f"再通知 {t['remind_time']}／家族へ {t['family1_time']}／第2連絡先へ {t['family2_time']}")
            if t["holiday_from"]:
                lines.append(f"お休み：{jp_date(t['holiday_from'])}〜{jp_date(t['holiday_to'])}")
            if fams:
                lines.append("連絡先：" + "、".join(f"第{f['priority']} {f['nickname']}" for f in fams))
            else:
                lines.append(f"⚠ 家族がまだつながっていません（招待コード {t['invite_code']}）")
            if t["watch_from"] and t["watch_from"] > now.date().isoformat():
                lines.append(f"見守り開始：{jp_date(t['watch_from'])}")
        lines.append("")
        lines.append("変更：「時刻 10:00 11:00 13:00」「お休み 11/20-11/22」「お休み解除」")
        return "\n".join(lines)

    async def cmd_times(self, u, arg: str, token: str, now: datetime) -> None:
        parts = [p for p in re.split(r"[\s　,、]+", arg.strip()) if p]
        ts = [parse_hhmm(p) for p in parts]
        if len(ts) != 3 or None in ts or not Schedule(*ts).is_valid():
            await self.reply(token, [M.text("「時刻 10:00 11:00 13:00」のように、\n再通知・家族へ・第2連絡先へ の順に"
                                            "早い時刻から3つ送ってください。")], "times_fail", u, now)
            return
        targets = self.targets_for_settings(u)
        for t in targets:
            self.db.execute("UPDATE users SET remind_time=?, family1_time=?, family2_time=? WHERE id=?",
                            (*[fmt_hhmm(x) for x in ts], t["id"]))
        names = "、".join(t["nickname"] + "さん" for t in targets)
        await self.reply(token, [M.text(f"{names}の時刻を変えました。\n再通知 {fmt_hhmm(ts[0])}／家族へ {fmt_hhmm(ts[1])}"
                                        f"／第2連絡先へ {fmt_hhmm(ts[2])}")], "times", u, now)

    async def cmd_holiday(self, u, arg: str, token: str, now: datetime) -> None:
        targets = self.targets_for_settings(u)
        if not targets:
            await self.reply(token, [M.text("まだ見守る方とつながっていません。")], "holiday_fail", u, now)
            return
        if arg.strip() == "解除":
            for t in targets:
                self.db.execute("UPDATE users SET holiday_from=NULL, holiday_to=NULL WHERE id=?", (t["id"],))
            await self.reply(token, [M.text("お休みを解除しました。")], "holiday_clear", u, now)
            return
        rng = parse_holiday(arg, now.date())
        if not rng:
            await self.reply(token, [M.text("「お休み 11/20」や「お休み 11/20-11/22」のように送ってください"
                                            "（60日まで）。")], "holiday_fail", u, now)
            return
        a, b = rng
        for t in targets:
            self.db.execute("UPDATE users SET holiday_from=?, holiday_to=? WHERE id=?",
                            (a.isoformat(), b.isoformat(), t["id"]))
        names = "、".join(t["nickname"] + "さん" for t in targets)
        await self.reply(token, [M.text(f"{names}は {jp_date(a)}〜{jp_date(b)} をお休みにしました。"
                                        "この間は家族に通知しません。")], "holiday", u, now)

    async def cmd_phone(self, u, arg: str, token: str, now: datetime) -> None:
        num = arg.strip().translate(str.maketrans("０１２３４５６７８９－ー", "0123456789--"))
        if not re.fullmatch(r"0\d[\d-]{7,12}", num):
            await self.reply(token, [M.text("「電話 09012345678」のように送ってください。")], "phone_fail", u, now)
            return
        self.db.execute("UPDATE users SET phone=? WHERE id=?", (num, u["id"]))
        await self.reply(token, [M.text(f"電話番号を {num} にしました。")], "phone", u, now)

    # ------------------------------------------------------------------ 見守り判定（5分ごと）
    async def watch_tick(self, now: datetime | None = None) -> int:
        """全員の状態を確認し、必要な通知を送る。送った件数を返す。"""
        now = now or jst_now()
        today = now.date()
        sent = 0
        selves = self.db.execute("SELECT * FROM users WHERE role='self'").fetchall()
        for u in selves:
            if u["watch_from"] and u["watch_from"] > today.isoformat():
                continue
            fams = self.families_of(u["id"])
            if not fams:
                continue  # 知らせる相手がいない
            st = self.today_status(u["id"], today, now)
            state = STATE_BY_NAME[st["state"]]
            new_state, action = next_step(state, now.time(), schedule_of(u), self.on_holiday(u, today))
            if action == Action.NONE:
                continue
            try:
                await self.do_watch_action(u, fams, action, today, now)
            except Exception:
                log.exception("watch action failed (user %s). 次の確認で再送します", u["id"])
                continue
            self.set_state(u["id"], today, new_state, now)
            sent += 1
        return sent

    async def do_watch_action(self, u, fams, action: Action, today: date, now: datetime) -> None:
        f1 = next((f for f in fams if f["priority"] == 1), fams[0])
        f2 = next((f for f in fams if f["priority"] == 2), None)
        d = today.isoformat()
        if action == Action.REMIND_SELF:
            await self.push(u, M.remind_self(u["nickname"]), "remind_self", u["id"], now)
        elif action == Action.NOTIFY_FAMILY1:
            await self.push(f1, M.notify_family(u["nickname"], u["phone"], u["id"], d), "notify_family1",
                            u["id"], now)
        elif action == Action.NOTIFY_FAMILY2:
            if f2:
                await self.push(f2, M.notify_family(u["nickname"], u["phone"], u["id"], d, second=True),
                                "notify_family2", u["id"], now)
            else:  # 第2連絡先がいなければ、第1連絡先にもう一度
                await self.push(f1, M.notify_family(u["nickname"], u["phone"], u["id"], d, again=True),
                                "notify_family2", u["id"], now)

    # ------------------------------------------------------------------ 地震の安否確認
    def seen(self, entry_id: str) -> bool:
        return self.db.execute("SELECT 1 FROM seen_feed WHERE entry_id=?", (entry_id,)).fetchone() is not None

    def mark_seen(self, entry_id: str, now: datetime) -> None:
        self.db.execute("INSERT OR IGNORE INTO seen_feed(entry_id, at) VALUES (?,?)", (entry_id, iso(now)))

    async def handle_quake_report(self, r: QuakeReport, now: datetime | None = None) -> int:
        """電文1つを処理する。安否確認を送った人数を返す（送らないときは 0）。"""
        now = now or jst_now()
        if not report_needs_alert(r, self.s.quake_threshold):
            return 0
        if r.report_time and now - r.report_time > timedelta(hours=self.s.quake_max_age_hours):
            log.info("古い電文なので送りません: %s %s", r.event_id, r.report_time)
            return 0
        try:  # 地震ID で重複チェック（同じ地震の続報では送らない）
            self.db.execute("INSERT INTO quake_events(event_id, intensity, headline, sent_at) VALUES (?,?,?,?)",
                            (r.event_id, r.intensity, r.headline, iso(now)))
        except sqlite3.IntegrityError:
            return 0
        label = intensity_label(r.intensity)
        n = 0
        for u in self.db.execute("SELECT * FROM users WHERE role='self'").fetchall():
            try:
                await self.push(u, M.quake_ask(r.event_id, label), "quake_ask", u["id"], now)
                n += 1
            except Exception:
                log.exception("quake push failed (user %s)", u["id"])
        return n

    async def safety_answer(self, u, event_id: str, answer: str, token: str, now: datetime) -> None:
        ev = self.db.execute("SELECT * FROM quake_events WHERE event_id=?", (event_id,)).fetchone()
        if not ev or u["role"] != "self":
            return
        prev = self.db.execute("SELECT answer FROM safety_responses WHERE event_id=? AND self_id=?",
                               (event_id, u["id"])).fetchone()
        # 「無事」のあとに「助けが必要」は受け付ける（優先度を上げる方向）。逆は家族の不安を消さないよう両方伝える
        if prev and prev["answer"] == answer:
            await self.reply(token, [M.text("返事はもう届いています。")], "safety_dup", u, now)
            return
        self.db.execute("INSERT OR REPLACE INTO safety_responses(event_id, self_id, answer, at) VALUES (?,?,?,?)",
                        (event_id, u["id"], answer, iso(now)))
        label = intensity_label(ev["intensity"])
        for f in self.families_of(u["id"]):
            await self.push(f, M.quake_to_family(u["nickname"], answer, label, u["phone"]),
                            f"quake_{answer}", u["id"], now)
        msgs = M.quake_safe_reply() if answer == "safe" else M.quake_help_reply(self.s.shelter_url)
        await self.reply(token, msgs, f"safety_{answer}", u, now)

    async def quake_followup(self, now: datetime | None = None) -> int:
        """安否確認を送ってから一定時間（30分）返事がない人は、家族に知らせる。"""
        now = now or jst_now()
        limit = iso(now - timedelta(minutes=self.s.safety_timeout_minutes))
        n = 0
        for ev in self.db.execute("SELECT * FROM quake_events WHERE followup_done=0 AND sent_at<=?",
                                  (limit,)).fetchall():
            label = intensity_label(ev["intensity"])
            # 安否確認を送った相手（notifications に記録がある人）のうち、返事がない人
            rows = self.db.execute(
                "SELECT DISTINCT u.* FROM notifications n JOIN users u ON u.id=n.to_id "
                "WHERE n.kind='quake_ask' AND n.at>=? AND u.role='self' AND u.id NOT IN "
                "(SELECT self_id FROM safety_responses WHERE event_id=?)",
                (ev["sent_at"], ev["event_id"])).fetchall()
            for u in rows:
                self.db.execute("INSERT OR IGNORE INTO safety_responses(event_id, self_id, answer, at) "
                                "VALUES (?,?,?,?)", (ev["event_id"], u["id"], "no_response", iso(now)))
                for f in self.families_of(u["id"]):
                    await self.push(f, M.quake_to_family(u["nickname"], "no_response", label, u["phone"]),
                                    "quake_no_response", u["id"], now)
                n += 1
            self.db.execute("UPDATE quake_events SET followup_done=1 WHERE event_id=?", (ev["event_id"],))
        return n

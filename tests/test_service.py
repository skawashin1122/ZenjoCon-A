# まもりネット全体の動き（2-3 のペルソナ「Aさんと子のBさん」のシナリオ）
from datetime import datetime, timedelta

from app.config import JST
from app.quake import parse_report
from app.service import parse_holiday

from .conftest import FIXTURES, run

A, B, C = "U_A_mother", "U_B_child", "U_C_grandchild"


def at(day, hh, mm=0):
    return datetime(2026, 11, day, hh, mm, tzinfo=JST)


def ev_postback(user, data):
    return {"type": "postback", "source": {"type": "user", "userId": user}, "replyToken": f"rt-{user}",
            "postback": {"data": data}}


def ev_text(user, t):
    return {"type": "message", "source": {"type": "user", "userId": user}, "replyToken": f"rt-{user}",
            "message": {"type": "text", "text": t}}


def setup_family(svc, now=None):
    """Aさん（本人）とBさん（第1）・Cさん（第2）を登録してつなぐ。"""
    now = now or at(16, 9)
    run(svc.handle_event({"type": "follow", "source": {"type": "user", "userId": A}, "replyToken": "x"}, now))
    run(svc.handle_event(ev_postback(A, "a=start&r=self"), now))
    a = svc.user_by_line(A)
    svc.db.execute("UPDATE users SET nickname='Aさん', phone='0987-00-0000' WHERE id=?", (a["id"],))
    for who in (B, C):
        run(svc.handle_event(ev_postback(who, "a=start&r=family"), now))
        run(svc.handle_event(ev_text(who, a["invite_code"]), now))
    return svc.user_by_line(A)


def state_of(svc, uid, day):
    r = svc.db.execute("SELECT state FROM daily_status WHERE self_id=? AND date=?",
                       (uid, f"2026-11-{day:02d}")).fetchone()
    return r["state"] if r else None


def pushes(svc):
    return [(to, m) for k, to, m in svc.line.sent if k == "push"]


def test_登録とつながり(svc):
    a = setup_family(svc)
    fams = svc.families_of(a["id"])
    assert [f["line_user_id"] for f in fams] == [B, C]
    assert [f["priority"] for f in fams] == [1, 2]
    assert a["consent_at"]  # 同意日時を記録
    assert len(a["invite_code"]) == 6


def test_連絡先は2人まで(svc):
    a = setup_family(svc)
    run(svc.handle_event(ev_postback("U_D", "a=start&r=family"), at(16, 9)))
    run(svc.handle_event(ev_text("U_D", a["invite_code"]), at(16, 9)))
    assert len(svc.families_of(a["id"])) == 2
    assert "2人まで" in svc.line.texts(kind="reply")[-1]


def test_間違った招待コード(svc):
    setup_family(svc)
    run(svc.handle_event(ev_postback("U_D", "a=start&r=family"), at(16, 9)))
    run(svc.handle_event(ev_text("U_D", "000000" if svc.user_by_line(A)["invite_code"] != "000000" else "111111"),
                         at(16, 9)))
    assert "見つかりません" in svc.line.texts(kind="reply")[-1]


def test_げんきを押した日は家族に何も届かない(svc):
    a = setup_family(svc)
    run(svc.handle_event(ev_postback(A, "a=genki"), at(17, 7, 30)))
    assert "げんきやね" in svc.line.texts(kind="reply")[-1]
    for h in range(8, 24):
        run(svc.watch_tick(at(17, h)))
    assert pushes(svc) == []          # プッシュ（通数を使う送信）はゼロ
    assert state_of(svc, a["id"], 17) == "GENKI"


def test_押されない日の流れ_再通知_家族_第2連絡先(svc):
    a = setup_family(svc)
    run(svc.watch_tick(at(17, 9, 55)))
    assert pushes(svc) == []
    run(svc.watch_tick(at(17, 10, 0)))
    assert pushes(svc)[-1][0] == A                        # 本人に再通知
    run(svc.watch_tick(at(17, 10, 30)))
    assert len(pushes(svc)) == 1                          # 同じ通知を何度も送らない
    run(svc.watch_tick(at(17, 11, 0)))
    to, msgs = pushes(svc)[-1]
    assert to == B and "まだです" in msgs[0]["altText"]   # 第1連絡先
    actions = msgs[0]["template"]["actions"]
    assert actions[0]["uri"] == "tel:0987000000"          # 電話ボタン
    run(svc.watch_tick(at(17, 13, 0)))
    assert pushes(svc)[-1][0] == C                        # 第2連絡先
    assert state_of(svc, a["id"], 17) == "FAMILY2"
    run(svc.watch_tick(at(17, 20, 0)))
    assert len(pushes(svc)) == 3


def test_家族が確認できたを押す(svc):
    a = setup_family(svc)
    for t in (at(17, 10), at(17, 11)):
        run(svc.watch_tick(t))
    run(svc.handle_event(ev_postback(B, f"a=confirm&s={a['id']}&d=2026-11-17"), at(17, 11, 5)))
    assert state_of(svc, a["id"], 17) == "CONFIRMED"
    run(svc.watch_tick(at(17, 13, 0)))
    assert all(to != C for to, _ in pushes(svc))         # 確認済みなので第2連絡先には送らない


def test_つながっていない家族は確認できない(svc):
    a = setup_family(svc)
    for t in (at(17, 10), at(17, 11)):
        run(svc.watch_tick(t))
    run(svc.handle_event(ev_postback("U_X", "a=start&r=family"), at(17, 11)))
    run(svc.handle_event(ev_postback("U_X", f"a=confirm&s={a['id']}&d=2026-11-17"), at(17, 11, 5)))
    assert state_of(svc, a["id"], 17) == "FAMILY1"


def test_家族通知のあとにげんき_家族に知らせる(svc):
    a = setup_family(svc)
    for t in (at(17, 10), at(17, 11)):
        run(svc.watch_tick(t))
    run(svc.handle_event(ev_postback(A, "a=genki"), at(17, 11, 20)))
    assert "11:20" in svc.line.texts(kind="push", to=B)[-1]
    assert state_of(svc, a["id"], 17) == "GENKI"


def test_翌日はまた待機中から(svc):
    a = setup_family(svc)
    run(svc.handle_event(ev_postback(A, "a=genki"), at(17, 7)))
    run(svc.watch_tick(at(18, 9)))
    assert state_of(svc, a["id"], 18) == "WAITING"


def test_お休みの日は通知しない(svc):
    a = setup_family(svc)
    run(svc.handle_event(ev_text(B, "お休み 11/17-11/18"), at(16, 20)))
    for t in (at(17, 10), at(17, 11), at(18, 13)):
        run(svc.watch_tick(t))
    assert pushes(svc) == []
    run(svc.watch_tick(at(19, 10)))
    assert pushes(svc)[-1][0] == A
    run(svc.handle_event(ev_text(B, "お休み解除"), at(19, 12)))
    assert svc.user(a["id"])["holiday_from"] is None


def test_時刻の変更(svc):
    a = setup_family(svc)
    run(svc.handle_event(ev_text(B, "時刻 8:30 9:30 12:00"), at(16, 20)))
    assert svc.user(a["id"])["remind_time"] == "8:30"
    run(svc.watch_tick(at(17, 8, 30)))
    assert pushes(svc)[-1][0] == A
    run(svc.handle_event(ev_text(B, "時刻 12:00 11:00 13:00"), at(16, 20)))  # 順番がおかしい
    assert svc.user(a["id"])["remind_time"] == "8:30"


def test_登録した日の再通知時刻を過ぎていたら翌日から(svc):
    a = setup_family(svc, now=at(16, 15))
    assert a["watch_from"] == "2026-11-17"
    run(svc.watch_tick(at(16, 16)))
    assert pushes(svc) == []


def test_家族がいない本人には通知しない(svc):
    run(svc.handle_event(ev_postback(A, "a=start&r=self"), at(16, 8)))
    run(svc.watch_tick(at(16, 12)))
    assert pushes(svc) == []


def test_迷ったらは案内だけ(svc):
    setup_family(svc)
    run(svc.handle_event(ev_postback(A, "a=help"), at(17, 22)))
    _, _, msgs = svc.line.sent[-1]
    body = str(msgs)
    assert "tel:119" in body and "tel:0987311111" in body and "医療の判断をしません" in body


def test_家族に電話ボタン(svc):
    setup_family(svc)
    run(svc.handle_event(ev_text(B, "電話 090-1234-5678"), at(16, 9)))
    run(svc.handle_event(ev_postback(A, "a=call_family"), at(17, 9)))
    assert "tel:09012345678" in str(svc.line.sent[-1][2])


def test_ひとことで家族にすぐ知らせる(svc):
    setup_family(svc)
    run(svc.handle_event(ev_text(A, "転んだ、足が痛い"), at(17, 9)))
    assert "転んだ" in svc.line.texts(kind="push", to=B)[-1]
    assert svc.line.texts(kind="push", to=C)


def test_登録解除で記録が消える(svc):
    a = setup_family(svc)
    run(svc.handle_event(ev_postback(A, "a=genki"), at(17, 7)))
    run(svc.handle_event(ev_postback(A, "a=unregister"), at(17, 8)))
    assert svc.user(a["id"]) is None
    assert svc.db.execute("SELECT COUNT(*) FROM daily_status").fetchone()[0] == 0
    assert svc.db.execute("SELECT COUNT(*) FROM links").fetchone()[0] == 0


def test_毎朝の返信は無料の応答メッセージ(svc):
    a = setup_family(svc)
    run(svc.handle_event(ev_postback(A, "a=genki"), at(17, 7)))
    row = svc.db.execute("SELECT is_push FROM notifications WHERE kind='genki'").fetchone()
    assert row["is_push"] == 0


def test_お休みの日付の読み取り():
    today = at(16, 9).date()
    assert parse_holiday("11/20", today) == (today.replace(day=20),) * 2
    assert parse_holiday("11/20-11/22", today)[1].day == 22
    assert parse_holiday("１１／２０〜２２", today)[1].day == 22
    assert parse_holiday("12/30-1/3", today)[1].year == 2027
    assert parse_holiday("今日", today) == (today, today)
    assert parse_holiday("あいうえお", today) is None


# ---------------- 地震 ----------------

def report(name):
    return parse_report((FIXTURES / name).read_text(encoding="utf-8"), "4520400")


QUAKE_NOW = datetime(2026, 11, 20, 9, 6, tzinfo=JST)


def test_震度5弱で全員に安否確認(svc):
    setup_family(svc)
    n = run(svc.handle_quake_report(report("vxse53_nichinan_5minus.xml"), QUAKE_NOW))
    assert n == 1
    assert "震度5弱" in svc.line.texts(kind="push", to=A)[-1]


def test_同じ地震の続報では送らない(svc):
    setup_family(svc)
    run(svc.handle_quake_report(report("vxse53_nichinan_5minus.xml"), QUAKE_NOW))
    assert run(svc.handle_quake_report(report("vxse53_nichinan_6minus.xml"), QUAKE_NOW)) == 0


def test_送らない電文(svc):
    setup_family(svc)
    for name in ("vxse53_nichinan_4.xml", "vxse53_training.xml", "vxse53_cancel.xml", "vxse53_no_nichinan.xml"):
        assert run(svc.handle_quake_report(report(name), QUAKE_NOW)) == 0, name
    assert pushes(svc) == []


def test_古い電文では送らない(svc):
    setup_family(svc)
    assert run(svc.handle_quake_report(report("vxse53_nichinan_5minus.xml"), QUAKE_NOW + timedelta(hours=5))) == 0


def test_無事_と_助けが必要(svc):
    setup_family(svc)
    r = report("vxse53_nichinan_5minus.xml")
    run(svc.handle_quake_report(r, QUAKE_NOW))
    run(svc.handle_event(ev_postback(A, f"a=safe&eq={r.event_id}"), QUAKE_NOW + timedelta(minutes=2)))
    assert "無事です" in svc.line.texts(kind="push", to=B)[-1]
    run(svc.handle_event(ev_postback(A, f"a=needhelp&eq={r.event_id}"), QUAKE_NOW + timedelta(minutes=3)))
    assert "至急" in svc.line.texts(kind="push", to=B)[-1]
    assert "tel:119" in str(svc.line.sent[-1][2])      # 本人には119番を案内（アプリは通報しない）


def test_30分応答なしで家族に通知(svc):
    setup_family(svc)
    run(svc.handle_quake_report(report("vxse53_nichinan_5minus.xml"), QUAKE_NOW))
    assert run(svc.quake_followup(QUAKE_NOW + timedelta(minutes=29))) == 0
    assert run(svc.quake_followup(QUAKE_NOW + timedelta(minutes=30))) == 1
    assert "返事がありません" in svc.line.texts(kind="push", to=B)[-1]
    assert run(svc.quake_followup(QUAKE_NOW + timedelta(minutes=60))) == 0   # 2回は送らない


def test_返事した人には応答なし通知をしない(svc):
    setup_family(svc)
    r = report("vxse53_nichinan_5minus.xml")
    run(svc.handle_quake_report(r, QUAKE_NOW))
    run(svc.handle_event(ev_postback(A, f"a=safe&eq={r.event_id}"), QUAKE_NOW + timedelta(minutes=5)))
    assert run(svc.quake_followup(QUAKE_NOW + timedelta(minutes=31))) == 0

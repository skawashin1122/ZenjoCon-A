"""管理用コマンド（実証実験の運用と振り返り：設計書 7章）。

  python -m app.admin users                       登録者の一覧
  python -m app.admin report [--from 2026-11-27 --to 2026-12-06]
                                                  評価指標（げんきを押した日の割合・押した時刻・通知の数）
  python -m app.admin tick [--at "2026-11-28 11:00"]
                                                  見守り判定を1回だけ動かす（動作確認用）
  python -m app.admin quake FILE.xml [--yes]      気象庁の電文ファイルで安否確認を試す（--yes で実際に送る）
  python -m app.admin outbox [-n 20]              ドライランで送ったはずのメッセージ
  python -m app.admin purge --yes                 実証実験の終了後、すべての記録を削除
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
from collections import Counter
from datetime import date, datetime, timedelta

from .config import JST, Settings
from .db import connect
from .line_api import DryRunClient, LineClient
from .quake import parse_report
from .service import Service, jst_now, parse_hhmm


def make_service(force_dry: bool = False) -> Service:
    s = Settings.from_env()
    conn = connect(s.db_path)
    line = DryRunClient(conn) if (s.dry_run or force_dry) else LineClient(s.channel_access_token)
    return Service(conn, line, s)


def cmd_users(svc: Service, _a) -> None:
    rows = svc.db.execute("SELECT * FROM users ORDER BY role DESC, id").fetchall()
    for u in rows:
        extra = ""
        if u["role"] == "self":
            fams = ", ".join(f"第{f['priority']}:{f['nickname']}" for f in svc.families_of(u["id"]))
            extra = (f" 時刻 {u['remind_time']}/{u['family1_time']}/{u['family2_time']} 開始 {u['watch_from']}"
                     f" コード {u['invite_code']} 家族[{fams or 'なし'}]")
            if u["holiday_from"]:
                extra += f" お休み {u['holiday_from']}〜{u['holiday_to']}"
        print(f"#{u['id']:<3} {'本人' if u['role'] == 'self' else '家族'} {u['nickname']}{extra}")
    print(f"計 {len(rows)} 人")


def daterange(a: date, b: date):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


def cmd_report(svc: Service, a) -> None:
    today = jst_now().date()
    d_to = date.fromisoformat(a.to) if a.to else today - timedelta(days=1)
    d_from = date.fromisoformat(a.frm) if a.frm else d_to - timedelta(days=9)
    print(f"■ 期間 {d_from} 〜 {d_to}\n")
    all_days = all_genki = 0
    in_time = total_pressed = 0
    for u in svc.db.execute("SELECT * FROM users WHERE role='self' ORDER BY id").fetchall():
        start = max(d_from, date.fromisoformat(u["watch_from"])) if u["watch_from"] else d_from
        days = [d for d in daterange(start, d_to) if not svc.on_holiday(u, d)]
        st = {r["date"]: r for r in svc.db.execute(
            "SELECT * FROM daily_status WHERE self_id=? AND date BETWEEN ? AND ?",
            (u["id"], d_from.isoformat(), d_to.isoformat()))}
        genki_days = [d for d in days if st.get(d.isoformat()) and st[d.isoformat()]["genki_at"]]
        times = [datetime.fromisoformat(st[d.isoformat()]["genki_at"]) for d in genki_days]
        remind = parse_hhmm(u["remind_time"])
        before = sum(1 for t in times if t.time() < remind)
        minutes = [t.hour * 60 + t.minute for t in times]
        med = statistics.median(minutes) if minutes else None
        fam = Counter(r["state"] for r in st.values())
        print(f"#{u['id']} {u['nickname']}：対象 {len(days)}日 / げんき {len(genki_days)}日"
              f"（{len(genki_days) / len(days) * 100 if days else 0:.0f}%）"
              f" / 押した時刻の中央値 {f'{int(med) // 60}:{int(med) % 60:02d}' if med is not None else '-'}"
              f" / 再通知時刻より前 {before}/{len(times)}")
        print(f"     家族に通知した日 {fam['FAMILY1'] + fam['FAMILY2'] + fam['CONFIRMED']}"
              f"（うち第2連絡先まで {fam['FAMILY2']}・家族が確認 {fam['CONFIRMED']}）")
        all_days += len(days)
        all_genki += len(genki_days)
        in_time += before
        total_pressed += len(times)

    print("\n■ 全体（設計書 7章の目標）")
    if all_days:
        print(f"  げんきを押した日の割合 {all_genki / all_days * 100:.1f}%（目標 80%以上）")
    if total_pressed:
        print(f"  設定時刻の前に押した割合 {in_time / total_pressed * 100:.1f}%（目標 90%以上）")

    # 誤報の候補：家族に通知したあとで「げんき」が押された日（本人は元気だった）
    rows = svc.db.execute(
        "SELECT u.nickname, s.date, s.genki_at FROM daily_status s JOIN users u ON u.id=s.self_id "
        "WHERE s.date BETWEEN ? AND ? AND s.genki_at IS NOT NULL AND EXISTS ("
        " SELECT 1 FROM notifications n WHERE n.about_id=s.self_id AND n.kind='notify_family1'"
        " AND substr(n.at,1,10)=s.date AND n.at < s.genki_at)",
        (d_from.isoformat(), d_to.isoformat())).fetchall()
    print(f"  誤報の候補（家族に通知後、げんきが押された日） {len(rows)}件")
    for r in rows:
        print(f"    - {r['nickname']} {r['date']}（げんき {r['genki_at'][11:16]}）")

    lo, hi = d_from.isoformat(), (d_to + timedelta(days=1)).isoformat()
    print("\n■ 送った通知（プッシュ＝無料通数を使う／応答＝数えない）")
    for r in svc.db.execute("SELECT kind, is_push, COUNT(*) c FROM notifications WHERE at>=? AND at<? "
                            "GROUP BY kind, is_push ORDER BY is_push DESC, c DESC", (lo, hi)):
        print(f"  {'プッシュ' if r['is_push'] else '応答  '} {r['kind']:<24} {r['c']}")
    month = today.strftime("%Y-%m")
    pushes = svc.db.execute("SELECT COUNT(*) FROM notifications WHERE is_push=1 AND substr(at,1,7)=?",
                            (month,)).fetchone()[0]
    print(f"\n  今月（{month}）のプッシュ通数 {pushes} 通（無料プランの目安 200通/月 ※公式の料金ページで確認）")


def parse_at(s: str | None) -> datetime:
    if not s:
        return jst_now()
    return datetime.fromisoformat(s).replace(tzinfo=JST)


def cmd_tick(svc: Service, a) -> None:
    n = asyncio.run(svc.watch_tick(parse_at(a.at)))
    m = asyncio.run(svc.quake_followup(parse_at(a.at)))
    print(f"見守りの通知 {n} 件、地震の応答なし通知 {m} 件")


def cmd_quake(svc: Service, a) -> None:
    if not a.yes:
        # 本物のDBは変えずに、コピー（メモリ上）で試す
        mem = connect(":memory:")
        svc.db.backup(mem)
        svc = Service(mem, DryRunClient(), svc.s)
        print("（お試し：実際には送らず、記録も残しません。送るときは --yes）")
    r = parse_report(open(a.file, "rb").read(), svc.s.city_code)
    print(f"地震ID {r.event_id} / {r.status} / {r.info_type} / 日南市の震度 {r.intensity}")
    n = asyncio.run(svc.handle_quake_report(r, r.report_time or jst_now()))
    print(f"安否確認を送った人数 {n}")


def cmd_outbox(svc: Service, a) -> None:
    for r in reversed(svc.db.execute("SELECT * FROM outbox ORDER BY id DESC LIMIT ?", (a.n,)).fetchall()):
        print(f"{r['at']} {r['kind']:<5} → {r['to_line']}: {r['body'][:200]}")


def cmd_purge(svc: Service, a) -> None:
    if not a.yes:
        print("すべての記録を削除します。よければ --yes をつけてもう一度実行してください。")
        return
    for t in ("safety_responses", "quake_events", "daily_status", "links", "notifications", "outbox",
              "seen_feed", "users"):
        svc.db.execute(f"DELETE FROM {t}")
    svc.db.execute("VACUUM")
    print("すべての記録を削除しました。S3 のバックアップも削除してください。")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m app.admin", description="まもりネット 管理用コマンド")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("users")
    r = sub.add_parser("report")
    r.add_argument("--from", dest="frm")
    r.add_argument("--to")
    t = sub.add_parser("tick")
    t.add_argument("--at", help='"2026-11-28 11:00" のように')
    q = sub.add_parser("quake")
    q.add_argument("file")
    q.add_argument("--yes", action="store_true")
    o = sub.add_parser("outbox")
    o.add_argument("-n", type=int, default=20)
    pg = sub.add_parser("purge")
    pg.add_argument("--yes", action="store_true")
    a = p.parse_args(argv)
    svc = make_service()
    {"users": cmd_users, "report": cmd_report, "tick": cmd_tick, "quake": cmd_quake,
     "outbox": cmd_outbox, "purge": cmd_purge}[a.cmd](svc, a)


if __name__ == "__main__":
    main()

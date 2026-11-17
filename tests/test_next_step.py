# 設計書 4-5 のテスト（そのまま）＋α
from datetime import time

from app.watch import Action, Schedule, State, next_step, on_family_confirm, on_genki

S = Schedule()


def test_押される前は何もしない():
    assert next_step(State.WAITING, time(9, 0), S) == (State.WAITING, Action.NONE)


def test_10時を過ぎたら本人に再通知():
    assert next_step(State.WAITING, time(10, 5), S) == (State.REMINDED, Action.REMIND_SELF)


def test_11時を過ぎたら家族に通知():
    assert next_step(State.REMINDED, time(11, 0), S) == (State.FAMILY1, Action.NOTIFY_FAMILY1)


def test_げんきを押した日は通知しない():
    assert next_step(State.GENKI, time(15, 0), S) == (State.GENKI, Action.NONE)


def test_お休みの日は通知しない():
    assert next_step(State.WAITING, time(12, 0), S, on_holiday=True) == (State.WAITING, Action.NONE)


# ---- ここから追加 ----

def test_ちょうど10時に再通知():
    assert next_step(State.WAITING, time(10, 0), S) == (State.REMINDED, Action.REMIND_SELF)


def test_再通知のあと家族通知時刻の前は待つ():
    assert next_step(State.REMINDED, time(10, 59), S) == (State.REMINDED, Action.NONE)


def test_13時を過ぎたら第2連絡先():
    assert next_step(State.FAMILY1, time(13, 0), S) == (State.FAMILY2, Action.NOTIFY_FAMILY2)


def test_第2連絡先のあとは何もしない():
    assert next_step(State.FAMILY2, time(23, 0), S) == (State.FAMILY2, Action.NONE)


def test_家族が確認したあとは何もしない():
    assert next_step(State.CONFIRMED, time(13, 30), S) == (State.CONFIRMED, Action.NONE)


def test_サーバー停止明けでも1回に1段階しか進まない():
    # 14時に初めて確認しても、いきなり家族ではなく、まず本人に再通知
    assert next_step(State.WAITING, time(14, 0), S) == (State.REMINDED, Action.REMIND_SELF)


def test_時刻は本人ごとに設定できる():
    early = Schedule(time(8, 0), time(9, 0), time(10, 0))
    assert next_step(State.WAITING, time(8, 30), early) == (State.REMINDED, Action.REMIND_SELF)
    assert next_step(State.WAITING, time(8, 30), S) == (State.WAITING, Action.NONE)


def test_時刻の順番チェック():
    assert Schedule().is_valid()
    assert not Schedule(time(11, 0), time(10, 0), time(13, 0)).is_valid()


def test_家族通知のあとにげんき_家族に知らせる():
    assert on_genki(State.FAMILY1) == (State.GENKI, Action.TELL_FAMILY_GENKI)
    assert on_genki(State.FAMILY2) == (State.GENKI, Action.TELL_FAMILY_GENKI)


def test_ふつうのげんき_家族には知らせない():
    assert on_genki(State.WAITING) == (State.GENKI, Action.NONE)
    assert on_genki(State.REMINDED) == (State.GENKI, Action.NONE)


def test_家族の確認は通知のあとだけ():
    assert on_family_confirm(State.FAMILY1) == State.CONFIRMED
    assert on_family_confirm(State.WAITING) == State.WAITING
    assert on_family_confirm(State.GENKI) == State.GENKI

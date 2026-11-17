"""見守りの状態遷移（設計書 3章・4-5）。

LINE やデータベースから切り離した「純粋な関数」だけを置く。
時刻と状態だけで次の動きが決まるので、pytest で全パターンを確かめられる。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from enum import Enum


class State(Enum):
    WAITING = "待機中"
    GENKI = "げんき"
    REMINDED = "再通知済み"
    FAMILY1 = "家族に通知済み"
    CONFIRMED = "確認済み"
    FAMILY2 = "第2連絡先に通知済み"


class Action(Enum):
    NONE = "何もしない"
    REMIND_SELF = "本人に再通知"
    NOTIFY_FAMILY1 = "第1連絡先に通知"
    NOTIFY_FAMILY2 = "第2連絡先に通知"
    TELL_FAMILY_GENKI = "家族に『げんきが押された』と知らせる"


@dataclass(frozen=True)
class Schedule:
    remind: time = time(10, 0)
    family1: time = time(11, 0)
    family2: time = time(13, 0)

    def is_valid(self) -> bool:
        return self.remind < self.family1 < self.family2


# これ以上は自動で進まない「終わりの状態」
FINAL_STATES = (State.GENKI, State.CONFIRMED, State.FAMILY2)


def next_step(state: State, now: time, s: Schedule, on_holiday: bool = False) -> tuple[State, Action]:
    """5分ごとに呼ばれ、次の状態と送るべき通知を返す。

    1回の呼び出しで進むのは1段階だけ。サーバーが止まっていて時刻を
    大きく過ぎていても、本人への再通知を飛ばして家族に通知することはない
    （再通知 → 次の確認で家族へ、の順番を必ず守る）。
    """
    if on_holiday or state in FINAL_STATES:
        return state, Action.NONE
    if state == State.WAITING and now >= s.remind:
        return State.REMINDED, Action.REMIND_SELF
    if state == State.REMINDED and now >= s.family1:
        return State.FAMILY1, Action.NOTIFY_FAMILY1
    if state == State.FAMILY1 and now >= s.family2:
        return State.FAMILY2, Action.NOTIFY_FAMILY2
    return state, Action.NONE


def on_genki(state: State) -> tuple[State, Action]:
    """本人が「げんき」を押したとき。

    家族に通知したあと（まだ家族が確認していない）で押された場合は、
    家族を安心させるために知らせる。家族が確認済みなら知らせない（通数の節約）。
    """
    if state in (State.FAMILY1, State.FAMILY2):
        return State.GENKI, Action.TELL_FAMILY_GENKI
    return State.GENKI, Action.NONE


def on_family_confirm(state: State) -> State:
    """家族が「確認できた」を押したとき。通知後だけ意味を持つ。"""
    if state in (State.FAMILY1, State.FAMILY2):
        return State.CONFIRMED
    return state

from datetime import date, datetime

from ascenso.game import Game
from ascenso.storage import Store


class Clock:
    def __init__(self, d):
        self.d = d

    def __call__(self):
        return self.d


def make(tmp_path, d=date(2026, 11, 18), diff="normal"):
    events = []
    clock = Clock(d)
    g = Game(Store(tmp_path / "p.json"), lambda k, data: events.append((k, data)), today=clock)
    g.register("Nico", diff)
    return g, clock, events


def titles(events):
    return [d["title"] for k, d in events if k == "modal"]


def test_complete_quest(tmp_path):
    g, _, ev = make(tmp_path)
    for k, t in g.quest["targets"].items():
        g.add_reps(k, t)
    assert g.quest["completed"]
    assert g.s["streak"] == 1
    assert "MISIÓN COMPLETADA" in titles(ev)
    assert g.player["level"] >= 2


def test_penalty_after_missed_days(tmp_path):
    g, clock, ev = make(tmp_path)
    g.player["xp"] = 50
    g.s["streak"] = 4
    normal = dict(g.quest["targets"])
    clock.d = date(2026, 11, 20)
    g.rollover()
    assert g.quest["penalty"]
    assert g.s["streak"] == 0
    assert g.player["xp"] < 50
    assert g.quest["targets"]["pushup"] > normal["pushup"]
    assert g.s["history"]["2026-11-19"]["completed"] is False
    assert "PENALIZACIÓN" in titles(ev)


def test_no_penalty_when_completed(tmp_path):
    g, clock, _ = make(tmp_path)
    for k, t in g.quest["targets"].items():
        g.add_reps(k, t)
    clock.d = date(2026, 11, 19)
    g.rollover()
    assert not g.quest["penalty"]
    assert g.s["streak"] == 1


def test_persistence(tmp_path):
    g, clock, _ = make(tmp_path)
    g.add_reps("pushup", 7)
    g2 = Game(Store(tmp_path / "p.json"), today=clock)
    assert g2.quest["progress"]["pushup"] == 7
    assert g2.player["name"] == "Nico"


def test_guardian_rules(tmp_path):
    g, _, _ = make(tmp_path)
    g.nag_settings()["startHour"] = 18
    assert not g.should_nag(datetime(2026, 11, 18, 10))
    assert g.should_nag(datetime(2026, 11, 18, 19))
    left = g.snoozes_left()
    g.snooze()
    assert g.snoozes_left() == left - 1
    g.surrender()
    assert not g.should_nag(datetime(2026, 11, 18, 19))


def test_manual_gives_less_xp(tmp_path):
    g, _, _ = make(tmp_path)
    assert g.add_reps("squat", 10, manual=True) < g.add_reps("squat", 10)

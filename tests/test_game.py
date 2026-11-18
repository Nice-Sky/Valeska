from datetime import date, datetime

from arise.game import Game
from arise.storage import Store


class Clock:
    def __init__(self, d):
        self.d = d

    def __call__(self):
        return self.d


def make(tmp_path, d=date(2026, 11, 18), plan="intermedio"):
    events = []
    clock = Clock(d)
    g = Game(Store(tmp_path / "p.json"), lambda k, data: events.append((k, data)), today=clock)
    g.register("Nico", plan)
    return g, clock, events


def titles(events):
    return [d["title"] for k, d in events if k == "modal"]


def test_complete_quest(tmp_path):
    g, _, ev = make(tmp_path)
    for k, t in g.quest["targets"].items():
        g.add_reps(k, t)
    assert g.quest["completed"]
    assert g.s["streak"] == 1
    assert "OBJETIVO CUMPLIDO" in titles(ev)
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


def test_rest_day_no_penalty(tmp_path):
    g, clock, ev = make(tmp_path, d=date(2026, 11, 21))  # sábado
    for k, t in g.quest["targets"].items():
        g.add_reps(k, t)
    clock.d = date(2026, 11, 22)  # domingo = descanso
    g.rollover()
    assert g.quest["rest"] and g.quest["completed"]
    assert not g.should_nag(datetime(2026, 11, 22, 20))
    clock.d = date(2026, 11, 23)  # lunes
    g.rollover()
    assert not g.quest["penalty"]
    assert g.s["streak"] == 1
    assert "PENALIZACIÓN" not in titles(ev)


def test_skipped_rest_day_in_gap_not_counted(tmp_path):
    g, clock, _ = make(tmp_path, d=date(2026, 11, 21))  # sábado
    for k, t in g.quest["targets"].items():
        g.add_reps(k, t)
    clock.d = date(2026, 11, 23)  # lunes: el domingo (descanso) no se cuenta como fallado
    g.rollover()
    assert not g.quest["penalty"]


def test_records(tmp_path):
    g, _, _ = make(tmp_path)
    assert not g.finish_set("pushup", 12, 0, 36)   # primera serie: marca inicial, no "récord"
    assert g.s["records"]["pushup"] == 12
    assert g.finish_set("pushup", 15, 1, 45)
    assert not g.finish_set("pushup", 10, 0, 30)
    assert g.s["records"]["pushup"] == 15


def test_progression(tmp_path):
    g, clock, _ = make(tmp_path, d=date(2026, 11, 16))  # lunes
    base = g.quest["targets"]["pushup"]
    day = date(2026, 11, 16)
    for i in range(8):  # 7 días de entrenamiento + el domingo de descanso
        clock.d = date.fromordinal(day.toordinal() + i)
        g.rollover()
        for k, t in g.quest["targets"].items():
            g.add_reps(k, t)
    assert g.s["progression"] == 1.05
    clock.d = date(2026, 11, 24)
    g.rollover()
    assert g.quest["targets"]["pushup"] > base


def test_adherence(tmp_path):
    g, clock, _ = make(tmp_path, d=date(2026, 11, 16))
    g.player["createdAt"] = 0
    for k, t in g.quest["targets"].items():
        g.add_reps(k, t)
    clock.d = date(2026, 11, 18)  # el 17 se falló
    g.rollover()
    assert g.adherence() == 50


def test_migrates_old_save(tmp_path):
    import json
    old = {"player": {"name": "Nico", "level": 3, "xp": 10, "freePoints": 2, "alloc": {"FUE": 1}},
           "settings": {"difficulty": "dificil"},
           "quest": {"date": "2026-11-18", "difficulty": "dificil", "penalty": False, "targets": {"pushup": 50},
                     "progress": {}, "completed": False}}
    (tmp_path / "p.json").write_text(json.dumps(old))
    g = Game(Store(tmp_path / "p.json"), today=Clock(date(2026, 11, 18)))
    assert g.settings["plan"] == "avanzado"
    assert "freePoints" not in g.player
    assert g.player["level"] == 3

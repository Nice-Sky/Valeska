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


def _do_session(g, rpe=2, quality=1.0, short=0):
    for it in g.session_items():
        sets = [{"good": it["reps"] - short, "bad": 0, "quality": quality, "slowdown": 1.0} for _ in range(it["sets"])]
        g.record_exercise(it["ex"], sets, rpe)
        g.add_reps(it["ex"], it["sets"] * it["reps"])


def test_smart_progression_goes_up_when_easy(tmp_path):
    g, clock, _ = make(tmp_path, d=date(2026, 11, 16))  # lunes
    first = {it["ex"]: (it["sets"], it["reps"]) for it in g.session_items()}
    _do_session(g, rpe=2)
    for ex, (sets, reps) in first.items():
        p = g.s["prog"][ex]
        assert p["sets"] * p["reps"] > sets * reps, ex


def test_progression_holds_when_hard_and_drops_after_failing(tmp_path):
    g, clock, _ = make(tmp_path, d=date(2026, 11, 16))
    it = g.session_items()[0]
    ex, reps = it["ex"], it["reps"]
    g.record_exercise(ex, [{"good": reps, "quality": 1.0}] * it["sets"], 3)
    assert g.s["prog"][ex]["reps"] == reps
    bad = [{"good": reps - 3, "quality": 1.0}] * it["sets"]
    g.record_exercise(ex, bad, 4)
    assert g.s["prog"][ex]["reps"] < reps


def test_bad_technique_does_not_progress(tmp_path):
    g, clock, _ = make(tmp_path, d=date(2026, 11, 16))
    it = g.session_items()[0]
    g.record_exercise(it["ex"], [{"good": it["reps"], "bad": 6, "quality": 0.5}] * it["sets"], 2)
    assert g.s["prog"][it["ex"]]["reps"] == it["reps"]


def test_tired_adapts_session_without_counting_as_failure(tmp_path):
    g, clock, _ = make(tmp_path, d=date(2026, 11, 16))
    full = [it["sets"] for it in g.session_items()]
    why = g.set_readiness("cansado")
    assert why
    assert all(it["sets"] <= s for it, s in zip(g.session_items(), full))
    it = g.session_items()[0]
    g.record_exercise(it["ex"], [{"good": it["reps"], "quality": 1.0}] * it["sets"], 3)
    assert g.s["prog"][it["ex"]]["fails"] == 0


def test_recovery_session_once_a_week(tmp_path):
    g, clock, _ = make(tmp_path, d=date(2026, 11, 16))
    g.set_readiness("dolorido")
    assert all(it.get("recovery") for it in g.session_items())
    _do_session(g)
    assert g.quest["completed"]
    clock.d = date(2026, 11, 17)
    g.rollover()
    g.set_readiness("dolorido")  # segunda vez en la semana: solo sesión "cansado"
    assert not any(it.get("recovery") for it in g.session_items())


def test_scheduled_rest_after_many_days(tmp_path):
    g, clock, _ = make(tmp_path, d=date(2026, 11, 16), plan="principiante")
    g.set_rest_days([])
    for i in range(3):
        clock.d = date(2026, 11, 16 + i)
        g.rollover()
        _do_session(g)
    clock.d = date(2026, 11, 19)
    g.rollover()
    assert g.quest["rest"] and g.quest["restReason"]


def test_new_exercises_unlock_with_sessions(tmp_path):
    g, clock, ev = make(tmp_path, d=date(2026, 11, 16), plan="principiante")
    g.set_rest_days([])
    start = set(g.pool())
    for i in range(6):
        clock.d = date.fromordinal(date(2026, 11, 16).toordinal() + i * 2)
        g.rollover()
        _do_session(g)
    assert set(g.pool()) > start


def test_equipment_adds_exercises(tmp_path):
    g, clock, _ = make(tmp_path)
    assert "pullup" not in g.pool()
    g.settings["equipment"] = ["bar", "dumbbell"]
    assert {"pullup", "curl", "press"} <= set(g.pool())


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
    assert g.quest["session"]  # el objetivo viejo se pasa a series
    assert "freePoints" not in g.player
    assert g.player["level"] == 3


def test_weights_and_checkins(tmp_path):
    g, clock, _ = make(tmp_path, d=date(2026, 11, 16))  # lunes
    assert g.checkin_due()
    for i, kg in enumerate((80, 80.4, 79.8, 80.2, 80.0, 79.6, 79.9, 79.5)):
        clock.d = date.fromordinal(date(2026, 11, 9).toordinal() + i)
        g.log_weight(kg)
    clock.d = date(2026, 11, 16)
    st = g.weight_stats()
    assert st["count"] == 8 and st["last"] == 79.5
    assert st["avg7"] is not None and st["week_change"] is not None
    g.add_checkin(79.5, {}, {"waist_cm": 84, "reliable": True}, [])
    assert not g.checkin_due()
    assert g.next_checkin().startswith("lunes")
    clock.d = date(2026, 11, 23)
    assert g.checkin_due()
    assert "checkin1" in g.s["achievements"]

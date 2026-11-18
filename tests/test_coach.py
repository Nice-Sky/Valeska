from arise import coach


def test_initial_scales_with_plan():
    a = coach.initial("pushup", "principiante")
    b = coach.initial("pushup", "avanzado")
    assert b["sets"] * b["reps"] > a["sets"] * a["reps"]


def test_bodyweight_adds_set_when_reps_high():
    p = {"sets": 3, "reps": 25, "kg": 0, "fails": 0, "hist": []}
    new, kind, _ = coach.progress(p, "squat", [{"good": 25, "quality": 1}] * 3, 2)
    assert kind == "up" and new["sets"] == 4 and new["reps"] < 25


def test_loaded_adds_weight_at_top_of_range():
    p = {"sets": 3, "reps": 12, "kg": 8, "fails": 0, "hist": []}
    new, kind, txt = coach.progress(p, "curl", [{"good": 12, "quality": 1}] * 3, 2)
    assert kind == "up" and new["kg"] == 10 and new["reps"] == coach.LOADED_RANGE[0]


def test_fixed_dumbbells_add_sets_instead():
    p = {"sets": 3, "reps": 12, "kg": 8, "fails": 0, "hist": []}
    new, kind, _ = coach.progress(p, "curl", [{"good": 12, "quality": 1}] * 3, 2, adjustable_kg=False)
    assert new["kg"] == 8 and new["sets"] == 4


def test_inferred_effort_from_slowdown():
    assert coach.infer_rpe([{"good": 10, "slowdown": 1.0}] * 3, 10) == 2
    assert coach.infer_rpe([{"good": 10, "slowdown": 1.8}] * 3, 10) == 3
    assert coach.infer_rpe([{"good": 6}] * 3, 10) == 4


def test_pick_covers_groups_and_rotates():
    pool = coach.unlocked(30, "intermedio", ["bar", "dumbbell"])
    a = coach.pick_exercises(pool, "intermedio", 30, 100)
    b = coach.pick_exercises(pool, "intermedio", 30, 101)
    from arise.exercises import EXERCISES
    groups = {EXERCISES[k].group for k in a}
    assert {"legs", "push", "core"} <= groups
    assert a != b


def test_fatigue_adapts():
    s = [{"ex": "pushup", "sets": 4, "reps": 10, "rest": 60}]
    out, why = coach.adapt(s, "", 0.7)
    assert out[0]["sets"] == 3 and why
    out, why = coach.adapt(s, "normal", 0.1)
    assert out[0]["sets"] == 4 and not why

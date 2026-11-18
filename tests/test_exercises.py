"""Simula ejercicios con un esqueleto 3D visto de frente, de costado y en diagonal, con el ruido y la profundidad
"aplastada" típicos de MediaPipe, y verifica el conteo y los chequeos de técnica."""
import pytest

import skeleton as S
from arise.exercises import EXERCISES, RepCounter

VIEWS = {"front": 0, "diag": 45, "side": 90}
NOISE = dict(zk=0.45, noise=0.008)


def cycle(hi, lo, n=18, hold=6):
    down = [hi - (hi - lo) * i / n for i in range(n)]
    up = [lo + (hi - lo) * i / n for i in range(n)]
    return down + [lo] * 3 + up + [hi] * hold


def run(ex, values, gen, yaw, start=0.0, fps=30, **kw):
    c = RepCounter(EXERCISES[ex])
    events, last = [], None
    for i, v in enumerate(values):
        pts = gen(v, **kw) if not callable(v) else v()
        lm, w = S.to_landmarks(pts, yaw, seed=i, **NOISE)
        r = c.update(lm, w, S.ASPECT, start + i / fps)
        last = r
        if r.event:
            events.append(r.event)
    return c, events, last


@pytest.mark.parametrize("view", VIEWS)
def test_squats_any_view(view):
    vals = [178] * 10 + sum((cycle(178, 85) for _ in range(5)), []) + cycle(178, 122)
    c, ev, _ = run("squat", vals, S.standing_squat, VIEWS[view])
    assert c.reps == 5, (view, ev)
    assert ev[-1] == "partial"


@pytest.mark.parametrize("view", VIEWS)
def test_pushups_any_view(view):
    vals = [172] * 10 + sum((cycle(172, 70) for _ in range(4)), [])
    c, ev, _ = run("pushup", vals, S.pushup, VIEWS[view])
    assert c.reps == 4, (view, ev)


@pytest.mark.parametrize("view", ["diag", "side"])
def test_pushups_with_hip_sag_do_not_count(view):
    vals = [172] * 10 + sum((cycle(172, 70) for _ in range(3)), [])
    c, ev, _ = run("pushup", vals, S.pushup, VIEWS[view], sag=0.18)
    assert c.reps == 0 and c.bad == 3, (view, ev)


def test_knee_pushups_do_not_count():
    vals = [172] * 10 + sum((cycle(172, 70) for _ in range(3)), [])
    c, _, _ = run("pushup", vals, S.pushup, 45, knees_down=True)
    assert c.reps == 0 and c.bad == 3


def test_pushups_from_front_flag_unverified_hips():
    vals = [172] * 10 + sum((cycle(172, 70) for _ in range(2)), [])
    c, _, _ = run("pushup", vals, S.pushup, 0)
    assert c.reps == 2
    assert not any(r["verified"] for r in c.log)  # de frente no se pudo revisar la cadera


def test_standing_is_not_a_pushup():
    c, _, last = run("pushup", [178] * 20 + sum((cycle(178, 90) for _ in range(3)), []), S.standing_squat, 0)
    assert c.reps == 0 and last.status == "hint"


@pytest.mark.parametrize("view", VIEWS)
def test_crunches_and_situps(view):
    vals = [0] * 15 + sum((cycle(0, 28) for _ in range(5)), []) + sum((cycle(0, 70) for _ in range(3)), [])
    c, ev, _ = run("situp", vals, S.situp, VIEWS[view])
    assert c.reps == 8, (view, ev)


def test_tiny_situp_movements_do_not_count():
    c, _, _ = run("situp", [0] * 15 + sum((cycle(0, 6) for _ in range(5)), []), S.situp, 90)
    assert c.reps == 0


@pytest.mark.parametrize("view", ["front", "diag"])
def test_jumping_jacks(view):
    c, ev, _ = run("jack", [0] * 6 + sum((cycle(0, 1, 8, 3) for _ in range(6)), []), S.jack, VIEWS[view])
    assert c.reps == 6, ev


@pytest.mark.parametrize("view", VIEWS)
def test_lunges(view):
    c, ev, _ = run("lunge", [0] * 8 + sum((cycle(0, 0.92) for _ in range(4)), []), S.lunge, VIEWS[view])
    assert c.reps == 4, (view, ev)


def test_hidden_body():
    lm, w = S.to_landmarks(S.standing_squat(178), 0)
    for p in lm:
        p.visibility = 0.1
    r = RepCounter(EXERCISES["squat"]).update(lm, w, S.ASPECT, 0)
    assert r.status == "hidden" and "piernas" in r.msg


def test_squat_knees_caving_from_front():
    vals = [178] * 10 + sum((cycle(178, 85) for _ in range(3)), [])
    c, ev, _ = run("squat", vals, S.standing_squat, 0, valgus=0.13)
    assert c.reps == 0 and c.bad == 3


# ---------------------------------------------------------------- plancha
def plank_seconds(yaw, seconds=4, **kw):
    c = RepCounter(EXERCISES["plank"])
    last = None
    for i in range(int(seconds * 30)):
        lm, w = S.to_landmarks(S.plank(**kw), yaw, seed=i, **NOISE)
        last = c.update(lm, w, S.ASPECT, i / 30)
    return c, last


@pytest.mark.parametrize("view", ["diag", "side"])
def test_plank_counts_when_straight(view):
    c, last = plank_seconds(VIEWS[view])
    assert c.seconds > 3.5 and last.status == "ok"


@pytest.mark.parametrize("view", ["diag", "side"])
def test_plank_hip_sag_and_pike(view):
    for sag, word in ((0.16, "Subí"), (-0.16, "Bajá")):
        c, last = plank_seconds(VIEWS[view], sag=sag)
        assert c.seconds < 0.7, (view, sag)
        assert last.status == "bad" and word in last.msg


@pytest.mark.parametrize("view", VIEWS)
def test_plank_knees_down(view):
    c, last = plank_seconds(VIEWS[view], knees_down=True)
    assert c.seconds < 0.7 and "rodillas" in last.msg


def test_plank_small_wobble_is_tolerated():
    c, _ = plank_seconds(90, sag=0.05)
    assert c.seconds > 3.5


def test_plank_from_front_warns_unverified():
    c, last = plank_seconds(0)
    assert c.seconds > 3.5
    assert last.status == "warn"
    assert any(ch.state == "unknown" for ch in last.checks)


def test_plank_hidden_legs_does_not_count():
    c = RepCounter(EXERCISES["plank"])
    last = None
    for i in range(90):
        lm, w = S.to_landmarks(S.plank(), 90, seed=i, **NOISE)
        for k in (25, 26, 27, 28):
            lm[k].visibility = 0.1
        last = c.update(lm, w, S.ASPECT, i / 30)
    assert c.seconds == 0 and last.status == "unknown"


# ---------------------------------------------------------------- barra y mancuernas
@pytest.mark.parametrize("view", VIEWS)
def test_pullups(view):
    c, ev, _ = run("pullup", [175] * 8 + sum((cycle(175, 55, 24) for _ in range(3)), []), S.pullup, VIEWS[view])
    assert c.reps == 3, (view, ev)


def test_pullups_half_reps_are_reported():
    # sube bien pero no vuelve a estirar los brazos entre repeticiones
    vals = [175] * 8 + cycle(175, 55, 24, 0)[:-12] + [128, 136, 138] + cycle(138, 55, 18, 0) + [175] * 10
    c, ev, _ = run("pullup", vals, S.pullup, 0)
    assert "partial" in ev


@pytest.mark.parametrize("view", VIEWS)
def test_curls(view):
    c, ev, _ = run("curl", [175] * 8 + sum((cycle(175, 45, 24) for _ in range(4)), []), S.curl, VIEWS[view])
    assert c.reps == 4, (view, ev)


def test_curl_elbow_forward_is_flagged():
    c, _, _ = run("curl", [175] * 8 + sum((cycle(175, 45, 24) for _ in range(2)), []), S.curl, 90, elbow_forward=55)
    assert c.reps == 0 and c.bad == 2


@pytest.mark.parametrize("view", VIEWS)
def test_shoulder_press(view):
    c, ev, _ = run("press", [75] * 8 + sum((cycle(75, 172, 24) for _ in range(3)), []), S.press, VIEWS[view])
    assert c.reps == 3, (view, ev)


@pytest.mark.parametrize("view", VIEWS)
def test_lateral_raises(view):
    c, ev, _ = run("lateral", [10] * 8 + sum((cycle(10, 88, 24) for _ in range(3)), []), S.lateral, VIEWS[view])
    assert c.reps == 3, (view, ev)


@pytest.mark.parametrize("view", VIEWS)
def test_rows(view):
    c, ev, _ = run("row", [170] * 8 + sum((cycle(170, 82, 24) for _ in range(3)), []), S.row, VIEWS[view])
    assert c.reps == 3, (view, ev)


@pytest.mark.parametrize("view", VIEWS)
def test_romanian_deadlift(view):
    c, ev, _ = run("rdl", [175] * 8 + sum((cycle(175, 95, 24) for _ in range(3)), []), S.rdl, VIEWS[view])
    assert c.reps == 3, (view, ev)


@pytest.mark.parametrize("view", VIEWS)
def test_glute_bridge(view):
    c, ev, _ = run("bridge", [0] * 10 + sum((cycle(0, 1) for _ in range(4)), []), S.bridge, VIEWS[view])
    assert c.reps == 4, (view, ev)


@pytest.mark.parametrize("view", ["diag", "side"])
def test_mountain_climbers_count_each_leg(view):
    vals = [0] * 6
    seq = []
    for i in range(6):
        leg = i % 2
        seq += [(d, leg) for d in (0.25, 0.5, 0.75, 1.0, 1.0, 0.75, 0.5, 0.25, 0.0, 0.0)]
    c = RepCounter(EXERCISES["climber"])
    for i, (d, leg) in enumerate([(0, 0)] * 6 + seq):
        lm, w = S.to_landmarks(S.climber(d, leg), VIEWS[view], seed=i, **NOISE)
        c.update(lm, w, S.ASPECT, i / 30)
    assert c.reps == 6


def test_summary_detects_slowdown():
    vals = [172] * 10
    for i in range(9):
        vals += cycle(172, 70, 10 + i * 4, 4)
    c, _, _ = run("pushup", vals, S.pushup, 90)
    s = c.summary()
    assert s["good"] == 9 and s["slowdown"] > 1.5 and s["quality"] == 1.0

"""Simula movimientos con poses sintéticas y verifica el conteo."""
import math
from types import SimpleNamespace as P

from ascenso.exercises import EXERCISES, RepCounter


def blank():
    return [P(x=0.5, y=0.5, z=0.0, visibility=0.99) for _ in range(33)], [P(x=0.0, y=0.0, z=0.0, visibility=0.99) for _ in range(33)]


def squat(theta):
    lm, w = blank()
    r = math.radians(theta)
    for h, k, a, s in ((23, 25, 27, 11), (24, 26, 28, 12)):
        w[k] = P(x=0, y=0, z=0)
        w[a] = P(x=0, y=0.45, z=0)
        w[h] = P(x=-0.45 * math.sin(math.pi - r), y=-0.45 * math.cos(math.pi - r), z=0)
        w[s] = P(x=w[h].x + 0.05, y=w[h].y - 0.5, z=0)
    return lm, w


def pushup(theta):
    lm, w = blank()
    r = math.radians(theta)
    lm[11], lm[23], lm[27] = P(x=.3, y=.5, visibility=.99), P(x=.55, y=.52, visibility=.99), P(x=.8, y=.55, visibility=.99)
    lm[13], lm[15] = P(x=.3, y=.6, visibility=.99), P(x=.3, y=.7, visibility=.99)
    for i in (12, 14, 16):
        lm[i].visibility = 0.1
    w[11], w[23], w[27] = P(x=0, y=0, z=0), P(x=.5, y=0, z=0), P(x=1.0, y=.02, z=0)
    w[13] = P(x=0, y=.3, z=0)
    w[15] = P(x=.3 * math.sin(r), y=.3 - .3 * math.cos(r), z=0)
    return lm, w


def jack(s):
    lm, w = blank()
    v = lambda x, y: P(x=x, y=y, z=0, visibility=.99)
    lm[11], lm[12], lm[23], lm[24] = v(.45, .3), v(.55, .3), v(.46, .55), v(.54, .55)
    wy = .5 - s * .35
    lm[15], lm[16] = v(.4 - s * .05, wy), v(.6 + s * .05, wy)
    half = .035 + s * .1
    lm[27], lm[28] = v(.5 - half, .9), v(.5 + half, .9)
    return lm, w


def cycle(hi, lo, n=20):
    return [hi - (hi - lo) * i / n for i in range(n)] + [lo + (hi - lo) * i / n for i in range(n)] + [hi] * 8


def run(ex, frames, gen):
    c = RepCounter(EXERCISES[ex])
    events = []
    for i, f in enumerate(frames):
        lm, w = gen(f)
        r = c.update(lm, w, 16 / 9, i / 30)
        if r.event:
            events.append(r.event)
    return c, events


def test_squats_count_and_partial():
    frames = sum((cycle(175, 80) for _ in range(5)), []) + cycle(175, 120)
    c, ev = run("squat", frames, squat)
    assert c.reps == 5
    assert ev[-1] == "partial"


def test_pushups():
    c, _ = run("pushup", sum((cycle(170, 70) for _ in range(4)), []), pushup)
    assert c.reps == 4


def test_pushups_need_horizontal_body():
    def standing(theta):
        lm, w = pushup(theta)
        lm[27] = P(x=.32, y=.95, visibility=.99)  # parado: tobillo debajo del hombro
        return lm, w
    c, _ = run("pushup", sum((cycle(170, 70) for _ in range(3)), []), standing)
    assert c.reps == 0


def test_jumping_jacks():
    c, _ = run("jack", sum((cycle(0, 1, 10) for _ in range(6)), []), jack)
    assert c.reps == 6


def test_hidden_body():
    lm, w = blank()
    for p in lm:
        p.visibility = 0.1
    r = RepCounter(EXERCISES["squat"]).update(lm, w, 1.7, 0)
    assert r.status == "hidden"

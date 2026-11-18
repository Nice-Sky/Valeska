// =============================================================
//  Ejercicios: cómo se mide cada uno a partir de la pose
//  Índices de MediaPipe Pose:
//   0 nariz | 11/12 hombros | 13/14 codos | 15/16 muñecas
//   23/24 caderas | 25/26 rodillas | 27/28 tobillos
// =============================================================

const VIS = 0.55; // visibilidad mínima de un punto para confiar en él

function angle3(a, b, c) {
  // ángulo ABC en grados usando coordenadas 3D (worldLandmarks, en metros)
  const ab = [a.x - b.x, a.y - b.y, (a.z || 0) - (b.z || 0)];
  const cb = [c.x - b.x, c.y - b.y, (c.z || 0) - (b.z || 0)];
  const dot = ab[0] * cb[0] + ab[1] * cb[1] + ab[2] * cb[2];
  const m = Math.hypot(...ab) * Math.hypot(...cb);
  if (!m) return 180;
  return (Math.acos(Math.max(-1, Math.min(1, dot / m))) * 180) / Math.PI;
}

const minVis = (lm, idx) => Math.min(...idx.map((i) => (lm[i] ? lm[i].visibility ?? 1 : 0)));
const clamp01 = (v) => Math.max(0, Math.min(1, v));
const avg = (arr) => arr.reduce((a, b) => a + b, 0) / arr.length;

// Elige el lado del cuerpo que la cámara ve mejor
function bestSide(lm, left, right) {
  const l = minVis(lm, left), r = minVis(lm, right);
  if (Math.max(l, r) < VIS) return null;
  return l >= r ? left : right;
}

// ¿El cuerpo está horizontal? (para flexiones / plancha)
function isHorizontal(lm, a, b, aspect) {
  const dx = Math.abs(lm[a].x - lm[b].x) * aspect;
  const dy = Math.abs(lm[a].y - lm[b].y);
  return dx > dy * 1.2;
}

export const EXERCISES = {
  pushup: {
    id: 'pushup',
    name: 'Flexiones',
    icon: '💪',
    unit: 'reps',
    xp: 3,
    stat: 'FUE',
    tip: 'Poné la cámara de costado, a la altura del piso, que se vea todo tu cuerpo.',
    dir: 'lower', rest: 150, mid: 125, active: 95,
    partialMsg: 'Bajá más el pecho',
    measure(lm, w, aspect) {
      const arm = bestSide(lm, [11, 13, 15], [12, 14, 16]);
      if (!arm) return { visible: false };
      const s = arm[0];
      const hip = s === 11 ? 23 : 24;
      const foot = minVis(lm, [s === 11 ? 27 : 28]) > VIS ? (s === 11 ? 27 : 28) : (s === 11 ? 25 : 26);
      if (minVis(lm, [hip]) < VIS) return { visible: false };
      if (!isHorizontal(lm, s, foot, aspect)) return { visible: true, value: null, hint: 'Ponete en posición de flexión' };
      const elbow = angle3(w[arm[0]], w[arm[1]], w[arm[2]]);
      const line = angle3(w[s], w[hip], w[foot]);
      let issue = null;
      if (line < 145) issue = 'Mantené la cadera alineada';
      return { visible: true, value: elbow, issue };
    },
  },

  squat: {
    id: 'squat',
    name: 'Sentadillas',
    icon: '🦵',
    unit: 'reps',
    xp: 2,
    stat: 'FUE',
    tip: 'Ponete de costado (o en diagonal) a la cámara, con piernas y torso a la vista.',
    dir: 'lower', rest: 155, mid: 130, active: 100,
    partialMsg: 'Bajá más, muslos paralelos al piso',
    measure(lm, w) {
      const sides = [[23, 25, 27], [24, 26, 28]].filter((s) => minVis(lm, s) > VIS);
      if (!sides.length) return { visible: false };
      const knee = avg(sides.map((s) => angle3(w[s[0]], w[s[1]], w[s[2]])));
      let issue = null;
      const sh = sides[0][0] === 23 ? 11 : 12;
      if (minVis(lm, [sh]) > VIS) {
        const torso = angle3(w[sh], w[sides[0][0]], w[sides[0][1]]);
        if (knee < 120 && torso < 45) issue = 'Pecho arriba, no te inclines tanto';
      }
      return { visible: true, value: knee, issue };
    },
  },

  situp: {
    id: 'situp',
    name: 'Abdominales',
    icon: '🔥',
    unit: 'reps',
    xp: 2,
    stat: 'RES',
    tip: 'Acostate de costado a la cámara, rodillas flexionadas. Subí el torso hacia las rodillas.',
    dir: 'lower', rest: 105, mid: 88, active: 72,
    partialMsg: 'Subí más el torso',
    measure(lm, w) {
      const side = bestSide(lm, [11, 23, 25], [12, 24, 26]);
      if (!side) return { visible: false };
      const hip = angle3(w[side[0]], w[side[1]], w[side[2]]);
      return { visible: true, value: hip };
    },
  },

  jack: {
    id: 'jack',
    name: 'Jumping Jacks',
    icon: '⚡',
    unit: 'reps',
    xp: 1,
    stat: 'AGI',
    tip: 'Ponete de frente a la cámara, cuerpo entero a la vista.',
    dir: 'higher', rest: 0.22, mid: 0.45, active: 0.72,
    partialMsg: 'Brazos bien arriba y piernas abiertas',
    measure(lm) {
      if (minVis(lm, [11, 12, 15, 16, 23, 24, 27, 28]) < VIS * 0.8) return { visible: false };
      const shY = (lm[11].y + lm[12].y) / 2;
      const hipY = (lm[23].y + lm[24].y) / 2;
      const torso = Math.max(0.05, hipY - shY);
      const arm = avg([15, 16].map((i) => clamp01((shY - lm[i].y) / (torso * 0.55))));
      const shW = Math.max(0.03, Math.abs(lm[11].x - lm[12].x));
      const ratio = Math.abs(lm[27].x - lm[28].x) / shW;
      const leg = clamp01((ratio - 1.0) / 0.6);
      return { visible: true, value: (arm + leg) / 2 };
    },
  },

  lunge: {
    id: 'lunge',
    name: 'Zancadas',
    icon: '🏃',
    unit: 'reps',
    xp: 2,
    stat: 'AGI',
    tip: 'Ponete de costado a la cámara. Alterná piernas; cada bajada cuenta.',
    dir: 'lower', rest: 155, mid: 132, active: 105,
    partialMsg: 'Bajá más la rodilla de atrás',
    measure(lm, w) {
      const sides = [[23, 25, 27], [24, 26, 28]].filter((s) => minVis(lm, s) > VIS * 0.85);
      if (!sides.length) return { visible: false };
      const knee = Math.min(...sides.map((s) => angle3(w[s[0]], w[s[1]], w[s[2]])));
      return { visible: true, value: knee };
    },
  },

  plank: {
    id: 'plank',
    name: 'Plancha',
    icon: '🧱',
    unit: 'seg',
    xp: 0.5,
    stat: 'RES',
    timed: true,
    tip: 'Cámara de costado al piso. Solo cuenta el tiempo con el cuerpo recto.',
    measure(lm, w, aspect) {
      const side = bestSide(lm, [11, 23, 27], [12, 24, 28]) || bestSide(lm, [11, 23, 25], [12, 24, 26]);
      if (!side) return { visible: false };
      if (!isHorizontal(lm, side[0], side[2], aspect)) return { visible: true, ok: false, hint: 'Ponete en posición de plancha' };
      const line = angle3(w[side[0]], w[side[1]], w[side[2]]);
      if (line < 155) {
        const hipAbove = lm[side[1]].y < (lm[side[0]].y + lm[side[2]].y) / 2;
        return { visible: true, ok: false, hint: hipAbove ? 'Bajá la cadera' : 'Subí la cadera, no la dejes caer' };
      }
      return { visible: true, ok: true };
    },
  },
};

export const EXERCISE_ORDER = ['pushup', 'squat', 'situp', 'jack', 'lunge', 'plank'];

// =============================================================
//  Contador de repeticiones: máquina de estados
//  reposo -> moviéndose -> activo -> reposo  = 1 rep
// =============================================================
export class RepCounter {
  constructor(ex) {
    this.ex = ex;
    this.reps = 0;
    this.bad = 0;
    this.phase = 'rest';
    this.ema = null;
    this.issues = new Set();
    this.lastRepAt = 0;
    this.seconds = 0;
    this.lastT = null;
  }

  // Devuelve { event: 'rep'|'bad'|'partial'|'second'|null, msg, value, progress, status }
  update(lm, w, aspect, now = performance.now()) {
    const ex = this.ex;
    const m = ex.measure(lm, w, aspect);
    if (!m.visible) { this.lastT = null; return { status: 'hidden', msg: 'No te veo completo: alejate un poco de la cámara' }; }

    if (ex.timed) {
      const dt = this.lastT == null ? 0 : (now - this.lastT) / 1000;
      this.lastT = now;
      if (!m.ok) return { status: 'bad', msg: m.hint };
      const before = Math.floor(this.seconds);
      this.seconds += Math.min(dt, 0.25);
      const after = Math.floor(this.seconds);
      return { status: 'ok', msg: '¡Bien! Mantené', event: after > before ? 'second' : null, count: after - before };
    }

    if (m.value == null) return { status: 'hint', msg: m.hint };

    this.ema = this.ema == null ? m.value : this.ema * 0.45 + m.value * 0.55;
    const v = this.ema;
    const lower = ex.dir === 'lower';
    const isActive = lower ? v < ex.active : v > ex.active;
    const isRest = lower ? v > ex.rest : v < ex.rest;
    const pastMid = lower ? v < ex.mid : v > ex.mid;
    const span = ex.rest - ex.active;
    const progress = clamp01((ex.rest - v) / span);

    let event = null, msg = null;
    if (this.phase === 'rest' && pastMid) this.phase = 'moving';
    if (this.phase !== 'rest' && m.issue) this.issues.add(m.issue);

    if (this.phase === 'moving') {
      if (isActive) this.phase = 'active';
      else if (isRest) { event = 'partial'; msg = ex.partialMsg; this.reset(); }
    } else if (this.phase === 'active' && isRest) {
      if (now - this.lastRepAt < 350) { this.reset(); }
      else if (this.issues.size === 0) { this.reps++; event = 'rep'; msg = '¡Perfecta!'; this.lastRepAt = now; this.reset(); }
      else { this.bad++; event = 'bad'; msg = [...this.issues][0] + ' (no cuenta)'; this.lastRepAt = now; this.reset(); }
    }
    return { status: m.issue ? 'warn' : 'ok', msg: msg || m.issue || null, event, value: v, progress };
  }

  reset() { this.phase = 'rest'; this.issues.clear(); }
}

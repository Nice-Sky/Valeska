import { EXERCISES, EXERCISE_ORDER, RepCounter } from './exercises.js';
import { PoseCamera } from './pose.js';

// =============================================================
//  Utilidades
// =============================================================
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const pad = (n) => String(n).padStart(2, '0');
const dateKey = (d = new Date()) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const parseKey = (k) => { const [y, m, d] = k.split('-').map(Number); return new Date(y, m - 1, d); };
const daysBetween = (a, b) => Math.round((parseKey(b) - parseKey(a)) / 86400000);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = (n) => Math.floor(n).toLocaleString('es-AR');

// =============================================================
//  Reglas del juego
// =============================================================
const DIFFICULTY = {
  facil:   { label: 'Fácil',   targets: { pushup: 10, squat: 15, situp: 10, jack: 20 }, reward: 100 },
  normal:  { label: 'Normal',  targets: { pushup: 20, squat: 30, situp: 20, jack: 40, plank: 30 }, reward: 200 },
  dificil: { label: 'Difícil', targets: { pushup: 50, squat: 60, situp: 50, jack: 80, plank: 60 }, reward: 350 },
  extremo: { label: 'Extremo', targets: { pushup: 100, squat: 100, situp: 100, plank: 120 }, reward: 600 },
};

const RANKS = [
  { min: 75, r: 'S' }, { min: 50, r: 'A' }, { min: 35, r: 'B' },
  { min: 20, r: 'C' }, { min: 10, r: 'D' }, { min: 1, r: 'E' },
];
const rankOf = (lvl) => RANKS.find((x) => lvl >= x.min).r;
const xpNeeded = (lvl) => Math.round(80 * Math.pow(lvl, 1.4) + 20);

const STATS = {
  FUE: { name: 'Fuerza', from: (t) => Math.floor(t.pushup / 15) + Math.floor(t.squat / 30) },
  AGI: { name: 'Agilidad', from: (t) => Math.floor(t.jack / 40) + Math.floor(t.lunge / 20) },
  RES: { name: 'Resistencia', from: (t) => Math.floor(t.situp / 20) + Math.floor(t.plank / 60) + Math.floor(t.squat / 30) },
  DIS: { name: 'Disciplina', from: (t, s) => s.questsDone + Math.floor(s.bestStreak / 3) },
};

const ACHIEVEMENTS = [
  { id: 'first', title: 'El Despertar', desc: 'Completá tu primera repetición', test: (s) => totalReps(s) >= 1 },
  { id: 'quest1', title: 'Jugador', desc: 'Completá tu primera misión diaria', test: (s) => s.questsDone >= 1 },
  { id: 'streak3', title: 'Constante', desc: 'Racha de 3 días', test: (s) => s.bestStreak >= 3 },
  { id: 'streak7', title: 'Imparable', desc: 'Racha de 7 días', test: (s) => s.bestStreak >= 7 },
  { id: 'streak30', title: 'Voluntad de Hierro', desc: 'Racha de 30 días', test: (s) => s.bestStreak >= 30 },
  { id: 'push100', title: 'Brazos de Acero', desc: '100 flexiones en total', test: (s) => s.totals.pushup >= 100 },
  { id: 'push1000', title: 'Rompe Pisos', desc: '1.000 flexiones en total', test: (s) => s.totals.pushup >= 1000 },
  { id: 'squat1000', title: 'Piernas de Titán', desc: '1.000 sentadillas en total', test: (s) => s.totals.squat >= 1000 },
  { id: 'plank600', title: 'Muralla', desc: '10 minutos de plancha en total', test: (s) => s.totals.plank >= 600 },
  { id: 'reps5000', title: 'Máquina', desc: '5.000 repeticiones en total', test: (s) => totalReps(s) >= 5000 },
  { id: 'lvl10', title: 'Cazador Rango D', desc: 'Llegá al nivel 10', test: (s) => s.player.level >= 10 },
  { id: 'lvl20', title: 'Cazador Rango C', desc: 'Llegá al nivel 20', test: (s) => s.player.level >= 20 },
  { id: 'lvl50', title: 'Élite', desc: 'Llegá al nivel 50', test: (s) => s.player.level >= 50 },
  { id: 'extremo', title: 'Monarca del Esfuerzo', desc: 'Completá una misión en dificultad Extremo', test: (s) => s.extremeDone >= 1 },
  { id: 'redemption', title: 'Redención', desc: 'Completá una misión de penalización', test: (s) => s.penaltiesCleared >= 1 },
];

const totalReps = (s) => EXERCISE_ORDER.filter((e) => e !== 'plank').reduce((a, e) => a + (s.totals[e] || 0), 0);

function newState() {
  return {
    version: 1,
    updatedAt: 0,
    player: { name: '', level: 1, xp: 0, freePoints: 0, alloc: { FUE: 0, AGI: 0, RES: 0, DIS: 0 }, createdAt: Date.now() },
    settings: {
      difficulty: 'facil', voice: true, sound: true, model: 'lite',
      nag: { enabled: true, startHour: 18, intervalMin: 20, snoozesPerDay: 2, hard: false },
    },
    quest: null,
    streak: 0, bestStreak: 0, questsDone: 0, extremeDone: 0, penaltiesCleared: 0,
    totals: Object.fromEntries(EXERCISE_ORDER.map((e) => [e, 0])),
    history: {},
    achievements: [],
    log: [],
  };
}

// =============================================================
//  Guardado: servidor local (si existe) + localStorage
// =============================================================
const LS_KEY = 'ascenso_state_v1';
const Store = {
  server: false,
  timer: null,
  async load() {
    let local = null, remote = null;
    try { local = JSON.parse(localStorage.getItem(LS_KEY)); } catch {}
    try {
      const r = await fetch('api/state', { cache: 'no-store' });
      if (r.ok && (r.headers.get('content-type') || '').includes('json')) { this.server = true; remote = await r.json(); }
    } catch {}
    const ok = (s) => s && s.player;
    if (ok(remote) && ok(local)) return (remote.updatedAt || 0) >= (local.updatedAt || 0) ? remote : local;
    return ok(remote) ? remote : ok(local) ? local : null;
  },
  save(s) {
    s.updatedAt = Date.now();
    try { localStorage.setItem(LS_KEY, JSON.stringify(s)); } catch {}
    if (!this.server) return;
    clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      fetch('api/state', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(s) }).catch(() => {});
    }, 400);
  },
  heartbeat(training) {
    if (this.server) fetch('api/heartbeat', { method: 'POST', body: JSON.stringify({ training }) }).catch(() => {});
  },
};

let S = newState();
const save = () => Store.save(S);

function merge(base, extra) {
  for (const k of Object.keys(extra || {})) {
    if (extra[k] && typeof extra[k] === 'object' && !Array.isArray(extra[k]) && base[k] && typeof base[k] === 'object') merge(base[k], extra[k]);
    else base[k] = extra[k];
  }
  return base;
}

// =============================================================
//  Sonido y voz
// =============================================================
let actx = null;
function beep(notes, type = 'square', vol = 0.06) {
  if (!S.settings.sound) return;
  try {
    actx = actx || new (window.AudioContext || window.webkitAudioContext)();
    let t = actx.currentTime;
    for (const [f, d] of notes) {
      const o = actx.createOscillator(), g = actx.createGain();
      o.type = type; o.frequency.value = f;
      g.gain.setValueAtTime(vol, t); g.gain.exponentialRampToValueAtTime(0.0001, t + d);
      o.connect(g).connect(actx.destination); o.start(t); o.stop(t + d);
      t += d * 0.8;
    }
  } catch {}
}
const SFX = {
  rep: () => beep([[880, 0.08], [1320, 0.1]]),
  bad: () => beep([[220, 0.18]], 'sawtooth'),
  open: () => beep([[660, 0.07], [990, 0.07], [1320, 0.12]], 'triangle', 0.08),
  level: () => beep([[523, 0.12], [659, 0.12], [784, 0.12], [1047, 0.3]], 'triangle', 0.1),
  alarm: () => beep([[440, 0.2], [330, 0.2], [440, 0.2], [330, 0.3]], 'sawtooth', 0.07),
};
let lastSpeak = 0;
function say(text, force = false) {
  if (!S.settings.voice || !('speechSynthesis' in window)) return;
  const now = Date.now();
  if (!force && now - lastSpeak < 1800) return;
  lastSpeak = now;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = 'es-AR'; u.rate = 1.1;
  const v = speechSynthesis.getVoices().find((v) => v.lang.startsWith('es'));
  if (v) u.voice = v;
  speechSynthesis.cancel();
  speechSynthesis.speak(u);
}

// =============================================================
//  Ventanas del Sistema (modales) y notificaciones
// =============================================================
const modalQueue = [];
let modalOpen = false;
function sysModal({ title = 'NOTIFICACIÓN', html, buttons = [{ text: 'Aceptar', primary: true }], color = '', sound = 'open' }) {
  return new Promise((resolve) => { modalQueue.push({ title, html, buttons, color, sound, resolve }); nextModal(); });
}
function nextModal() {
  if (modalOpen || !modalQueue.length) return;
  modalOpen = true;
  const m = modalQueue.shift();
  $('#modal').className = 'modal ' + m.color;
  $('#modalTitle').textContent = m.title;
  $('#modalBody').innerHTML = m.html;
  const acts = $('#modalActions');
  acts.innerHTML = '';
  m.buttons.forEach((b, i) => {
    const el = document.createElement('button');
    el.className = 'btn ' + (b.primary ? 'primary' : b.danger ? 'danger' : '');
    el.textContent = b.text;
    el.onclick = () => {
      const input = $('#modalBody input');
      $('#modalBack').classList.add('hidden');
      modalOpen = false;
      m.resolve({ index: i, value: input ? input.value : null });
      setTimeout(nextModal, 150);
    };
    acts.appendChild(el);
  });
  $('#modalBack').classList.remove('hidden');
  SFX[m.sound]?.();
}
function toast(text, cls = '') {
  const el = document.createElement('div');
  el.className = 'toast ' + cls;
  el.textContent = text;
  $('#toasts').appendChild(el);
  setTimeout(() => el.remove(), 3100);
}
function log(msg) {
  S.log.unshift({ t: Date.now(), msg });
  S.log = S.log.slice(0, 150);
}

// =============================================================
//  Lógica: XP, niveles, misión, penalizaciones
// =============================================================
function gainXP(amount, reason) {
  const p = S.player;
  p.xp += amount;
  let leveled = 0;
  while (p.xp >= xpNeeded(p.level)) {
    p.xp -= xpNeeded(p.level);
    const oldRank = rankOf(p.level);
    p.level++;
    p.freePoints += 3;
    leveled++;
    log(`¡Subiste al nivel ${p.level}!`);
    if (rankOf(p.level) !== oldRank) {
      log(`Rango ascendido: ${oldRank} → ${rankOf(p.level)}`);
      sysModal({ title: 'ASCENSO DE RANGO', color: 'gold', sound: 'level', html: `Tu rango cambió de <span class="em">${oldRank}</span> a <span class="reward">${rankOf(p.level)}</span><br>El Sistema reconoce tu esfuerzo.` });
    }
  }
  if (leveled) {
    SFX.level();
    say(`Subiste de nivel. Nivel ${p.level}`, true);
    sysModal({ title: '¡SUBISTE DE NIVEL!', color: 'gold', sound: 'level', html: `NIVEL <span class="reward" style="font-size:32px">${p.level}</span><br>+${3 * leveled} puntos de estadística para asignar.<br><small>Andá a <b>Estado</b> para repartirlos.</small>` });
  }
  if (reason) toast(`+${fmt(amount)} XP · ${reason}`);
}

function buildTargets(penalty) {
  const d = DIFFICULTY[S.settings.difficulty] || DIFFICULTY.facil;
  const scale = Math.min(2, 1 + Math.floor((S.player.level - 1) / 5) * 0.1) * (penalty ? 1.5 : 1);
  const t = {};
  for (const [k, v] of Object.entries(d.targets)) t[k] = Math.ceil((v * scale) / 5) * 5;
  return t;
}

function newQuest(date, penalty) {
  S.quest = {
    date, penalty, difficulty: S.settings.difficulty,
    targets: buildTargets(penalty),
    progress: {},
    completed: false,
  };
}

function rollover() {
  const today = dateKey();
  if (!S.quest) { newQuest(today, false); save(); return; }
  if (S.quest.date === today) return;

  const q = S.quest;
  S.history[q.date] = { completed: q.completed, penalty: q.penalty, progress: q.progress, targets: q.targets };
  const gap = daysBetween(q.date, today);
  const missed = (q.completed ? 0 : 1) + Math.max(0, gap - 1);
  for (let i = 1; i < gap; i++) {
    const d = new Date(parseKey(q.date)); d.setDate(d.getDate() + i);
    S.history[dateKey(d)] = { completed: false, progress: {}, targets: q.targets };
  }

  if (missed > 0) {
    const lost = Math.min(S.player.xp, Math.round(xpNeeded(S.player.level) * 0.15 * Math.min(missed, 5)));
    S.player.xp -= lost;
    const prevStreak = S.streak;
    S.streak = 0;
    log(`PENALIZACIÓN: ${missed} día(s) sin cumplir. -${lost} XP. Racha perdida (${prevStreak}).`);
    newQuest(today, true);
    sysModal({
      title: 'PENALIZACIÓN', color: 'red', sound: 'alarm',
      html: `No completaste la misión diaria${missed > 1 ? ` durante <b>${missed} días</b>` : ''}.<br><br>
        <span class="em" style="color:var(--red)">-${fmt(lost)} XP</span> · Racha perdida: ${prevStreak} días<br><br>
        Hoy te toca la <b>MISIÓN DE PENALIZACIÓN</b> (+50% de volumen).<br>Si la cumplís, recuperás el honor.`,
      buttons: [{ text: 'Entendido', danger: true }],
    });
  } else {
    newQuest(today, false);
  }
  save();
}

function questRemaining() {
  const q = S.quest;
  return Object.entries(q.targets).filter(([k, v]) => (q.progress[k] || 0) < v);
}

function checkQuestComplete() {
  const q = S.quest;
  if (q.completed || questRemaining().length) return;
  q.completed = true;
  S.streak++;
  S.bestStreak = Math.max(S.bestStreak, S.streak);
  S.questsDone++;
  if (q.difficulty === 'extremo') S.extremeDone++;
  if (q.penalty) S.penaltiesCleared++;
  const base = (DIFFICULTY[q.difficulty] || DIFFICULTY.facil).reward;
  const bonus = Math.min(200, S.streak * 10);
  const total = Math.round(base * (q.penalty ? 1.5 : 1) + bonus);
  log(`Misión diaria completada. +${total} XP. Racha: ${S.streak}`);
  say('Misión diaria completada', true);
  sysModal({
    title: 'MISIÓN COMPLETADA', color: 'gold', sound: 'level',
    html: `Completaste la ${q.penalty ? 'misión de penalización' : 'misión diaria'}.<br><br>
      <div class="reward">+${fmt(total)} XP</div>
      <div>Racha: <b>${S.streak}</b> día${S.streak === 1 ? '' : 's'} (+${bonus} bonus)</div>
      <div>Disciplina +1</div><br><small>Hoy el Sistema te deja en paz. Mañana, más.</small>`,
  });
  gainXP(total);
}

function addReps(ex, n, source = 'cam') {
  if (n <= 0) return;
  rollover();
  S.totals[ex] = (S.totals[ex] || 0) + n;
  const q = S.quest;
  if (q.targets[ex] != null) {
    const before = q.progress[ex] || 0;
    q.progress[ex] = before + n;
    if (before < q.targets[ex] && q.progress[ex] >= q.targets[ex]) {
      toast(`✔ ${EXERCISES[ex].name}: objetivo cumplido`, 'gold');
      say(`Objetivo de ${EXERCISES[ex].name} cumplido`, true);
    }
  }
  const xp = n * EXERCISES[ex].xp * (source === 'manual' ? 0.7 : 1);
  gainXP(xp);
  session.xp += xp;
  checkQuestComplete();
  checkAchievements();
  save();
  render();
}

function checkAchievements() {
  for (const a of ACHIEVEMENTS) {
    if (!S.achievements.includes(a.id) && a.test(S)) {
      S.achievements.push(a.id);
      log(`Logro desbloqueado: ${a.title}`);
      sysModal({ title: 'LOGRO DESBLOQUEADO', color: 'gold', html: `Título obtenido:<br><div class="reward">«${esc(a.title)}»</div><small>${esc(a.desc)}</small>` });
    }
  }
}

const currentTitle = () => {
  const last = [...ACHIEVEMENTS].reverse().find((a) => S.achievements.includes(a.id));
  return last ? last.title : 'Ninguno';
};
const statValue = (k) => 10 + (S.player.alloc[k] || 0) + STATS[k].from(S.totals, S);

// =============================================================
//  Render
// =============================================================
function render() {
  const p = S.player, rank = rankOf(p.level);
  $('#topPlayer').innerHTML = `<b>${esc(p.name || '—')}</b><br>NV ${p.level} · RANGO ${rank}`;
  $('#rankBadge').textContent = rank;
  $('#rankBadge').className = 'rank-badge ' + rank;
  $('#stName').textContent = p.name;
  $('#stLevel').textContent = p.level;
  $('#stTitle').textContent = currentTitle();
  $('#stStreak').textContent = `${S.streak} día${S.streak === 1 ? '' : 's'} (máx ${S.bestStreak})`;
  const need = xpNeeded(p.level);
  $('#xpFill').style.width = `${(p.xp / need) * 100}%`;
  $('#xpText').textContent = `XP ${fmt(p.xp)} / ${fmt(need)}`;

  $('#stats').innerHTML = Object.entries(STATS).map(([k, st]) => `
    <div class="stat">
      <div class="name">${k}<small>${st.name}</small></div>
      <div style="display:flex;gap:10px;align-items:center">
        <div class="val">${statValue(k)}</div>
        ${p.freePoints > 0 ? `<button class="btn plus" data-stat="${k}">+</button>` : ''}
      </div>
    </div>`).join('');
  $('#freePoints').textContent = p.freePoints > 0 ? `Puntos disponibles: ${p.freePoints}` : '';

  renderQuest();
  renderLog();
  if (!session.ex) renderExGrid();
}

function questItemsHTML(withButtons) {
  const q = S.quest;
  return Object.entries(q.targets).map(([k, t]) => {
    const ex = EXERCISES[k], v = Math.min(q.progress[k] || 0, t), done = v >= t;
    return `<div class="q-item ${done ? 'done' : ''}">
      <div class="q-name">${ex.icon} ${ex.name}</div>
      <div class="q-actions">
        <span class="q-num">[${fmt(v)}/${t}]${ex.unit === 'seg' ? ' s' : ''}</span>
        ${withButtons && !done ? `<button class="btn small" data-train="${k}">Ir</button>` : ''}
      </div>
      <div class="q-bar"><div style="width:${(v / t) * 100}%"></div></div>
    </div>`;
  }).join('');
}

function renderQuest() {
  const q = S.quest;
  if (!q) return;
  $('#questPanel').classList.toggle('penalty', !!q.penalty);
  $('#questTitle').textContent = q.penalty ? 'MISIÓN DE PENALIZACIÓN' : 'MISIÓN DIARIA';
  $('#questSub').textContent = `Dificultad: ${(DIFFICULTY[q.difficulty] || DIFFICULTY.facil).label}${q.penalty ? ' · +50% por fallar' : ''}`;
  $('#questList').innerHTML = questItemsHTML(true);
  $('#questMini').innerHTML = questItemsHTML(false);
  const w = $('#questWarning');
  if (q.completed) { w.className = 'quest-warning ok'; w.textContent = '✔ MISIÓN COMPLETADA. Descansá, cazador.'; }
  else { w.className = 'quest-warning'; w.textContent = '⚠ ADVERTENCIA: si no completás la misión antes de medianoche recibirás una penalización.'; }
  renderCountdown();
}

function renderCountdown() {
  const el = $('#questCountdown');
  if (!S.quest || S.quest.completed) { el.textContent = ''; return; }
  const now = new Date(), end = new Date(now); end.setHours(24, 0, 0, 0);
  const s = Math.floor((end - now) / 1000);
  el.textContent = `TIEMPO RESTANTE ${pad(Math.floor(s / 3600))}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`;
}

function renderLog() {
  $('#syslog').innerHTML = S.log.slice(0, 60).map((l) => {
    const d = new Date(l.t);
    return `<div><time>${pad(d.getDate())}/${pad(d.getMonth() + 1)} ${pad(d.getHours())}:${pad(d.getMinutes())}</time>${esc(l.msg)}</div>`;
  }).join('') || '<div class="hint">Sin mensajes todavía.</div>';
}

function renderRegistro() {
  const today = dateKey();
  let html = '';
  for (let i = 27; i >= 0; i--) {
    const d = new Date(); d.setDate(d.getDate() - i);
    const k = dateKey(d);
    const h = k === today ? { completed: S.quest?.completed } : S.history[k];
    const cls = h ? (h.completed ? 'ok' : k === today ? '' : 'fail') : '';
    html += `<div class="${cls} ${k === today ? 'today' : ''}" title="${k}">${d.getDate()}</div>`;
  }
  $('#heat').innerHTML = html;
  $('#totals').innerHTML = EXERCISE_ORDER.map((e) => `<div><b>${fmt(S.totals[e] || 0)}</b>${EXERCISES[e].icon} ${EXERCISES[e].name}${EXERCISES[e].unit === 'seg' ? ' (seg)' : ''}</div>`).join('')
    + `<div><b>${S.questsDone}</b>🏆 Misiones</div>`;
  $('#achievements').innerHTML = ACHIEVEMENTS.map((a) => `<div class="ach ${S.achievements.includes(a.id) ? 'on' : ''}"><b>${S.achievements.includes(a.id) ? '★' : '☆'} ${esc(a.title)}</b><span>${esc(a.desc)}</span></div>`).join('');
  renderLog();
}

function renderAjustes() {
  const st = S.settings;
  $('#setName').value = S.player.name;
  $('#setDiff').value = st.difficulty;
  $('#setVoice').checked = st.voice;
  $('#setSound').checked = st.sound;
  $('#setModel').value = st.model;
  $('#setNag').checked = st.nag.enabled;
  $('#setNagHour').value = st.nag.startHour;
  $('#setNagEvery').value = st.nag.intervalMin;
  $('#setNagSnooze').value = st.nag.snoozesPerDay;
  $('#setNagHard').checked = st.nag.hard;
  $('#guardianStatus').innerHTML = Store.server
    ? '🟢 El Guardián está <b>conectado</b>. Si no entrenás, te va a aparecer una alerta en la compu hasta que cumplas.'
    : '🔴 El Guardián <b>no está corriendo</b>. Para que te persiga en la compu abrí la app con <code>iniciar.bat</code> (Windows) o <code>python3 servidor.py</code>. Igual te avisa con notificaciones mientras esta pestaña esté abierta.';
}

function showTab(name) {
  $$('.tabs button').forEach((b) => b.classList.toggle('active', b.dataset.tab === name));
  $$('.tab').forEach((t) => t.classList.toggle('active', t.id === 'tab-' + name));
  if (name === 'registro') renderRegistro();
  if (name === 'ajustes') renderAjustes();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// =============================================================
//  Entrenamiento con cámara
// =============================================================
const cam = new PoseCamera($('#video'), $('#overlay'));
const session = { ex: null, counter: null, xp: 0, good: 0, bad: 0, state: 'idle', countdownEnd: 0, visibleSince: 0, lastMsg: '' };

function renderExGrid() {
  $('#exGrid').innerHTML = EXERCISE_ORDER.map((k) => {
    const ex = EXERCISES[k], t = S.quest?.targets[k];
    const prog = t != null ? `Misión: ${Math.min(S.quest.progress[k] || 0, t)}/${t}` : 'Libre';
    return `<button class="ex-card" data-train="${k}"><div class="ico">${ex.icon}</div><div class="nm">${ex.name}</div><div class="sub">${prog} · ${ex.stat}</div></button>`;
  }).join('');
}

function openTraining(k) {
  showTab('entrenar');
  const ex = EXERCISES[k];
  session.ex = ex; session.counter = new RepCounter(ex);
  session.xp = 0; session.good = 0; session.bad = 0; session.state = 'idle';
  $('#exercisePicker').classList.add('hidden');
  $('#trainPanel').classList.remove('hidden');
  $('#trainTitle').textContent = `${ex.icon} ${ex.name.toUpperCase()}`;
  $('#trainTip').textContent = ex.tip;
  $('#repCount').textContent = '0';
  $$('[data-add]').forEach((b) => (b.textContent = `+${b.dataset.add}${ex.timed ? 's' : ''}`));
  updateTrainHUD();
  setFeedback(cam.running ? 'Ponete en posición' : 'Encendé la cámara para empezar');
  if (cam.running) startCountdownWhenVisible();
}

function updateTrainHUD() {
  const ex = session.ex; if (!ex) return;
  const t = S.quest?.targets[ex.id];
  const done = S.quest?.progress[ex.id] || 0;
  $('#repTarget').textContent = t != null ? `misión ${Math.min(done, t)}/${t}` : '';
  $('#sessionStats').innerHTML = `
    <div><b>${session.good}</b><span>${ex.timed ? 'segundos' : 'buenas'}</span></div>
    <div><b>${session.bad}</b><span>${ex.timed ? '—' : 'mal hechas'}</span></div>
    <div><b>${fmt(session.xp)}</b><span>XP ganada</span></div>`;
}

function setFeedback(msg, cls = '') {
  const el = $('#feedback');
  el.textContent = msg; el.className = 'feedback ' + cls;
}

function startCountdownWhenVisible() { session.state = 'waiting'; session.visibleSince = 0; }

cam.onFrame = (lm, w, aspect) => {
  if (!session.ex) return null;
  const now = performance.now();
  if (!lm) {
    if (session.state === 'waiting' || session.state === 'countdown') { session.state = 'waiting'; $('#camCenter').innerHTML = '<small>Buscando tu cuerpo…</small>'; }
    setFeedback('No te detecto. Alejate y que se vea todo tu cuerpo', 'bad');
    return null;
  }
  if (session.state === 'waiting') {
    session.visibleSince = session.visibleSince || now;
    $('#camCenter').innerHTML = '<small>Te veo. Quedate en posición…</small>';
    if (now - session.visibleSince > 800) { session.state = 'countdown'; session.countdownEnd = now + 3000; }
    return '#4de1ff';
  }
  if (session.state === 'countdown') {
    const left = Math.ceil((session.countdownEnd - now) / 1000);
    const txt = left > 0 ? String(left) : '¡YA!';
    if ($('#camCenter').dataset.t !== txt) { $('#camCenter').dataset.t = txt; $('#camCenter').textContent = txt; beep([[left > 0 ? 600 : 1200, 0.12]]); }
    if (now >= session.countdownEnd) { session.state = 'running'; setTimeout(() => ($('#camCenter').textContent = ''), 500); say('Empezá'); }
    return '#4de1ff';
  }
  if (session.state !== 'running') return '#4de1ff';

  const r = session.counter.update(lm, w, aspect, now);
  const ex = session.ex;
  if (ex.timed) {
    if (r.event === 'second') {
      session.good += r.count;
      $('#repCount').textContent = Math.floor(session.counter.seconds);
      addReps(ex.id, r.count);
      updateTrainHUD();
      const s = Math.floor(session.counter.seconds);
      if (s % 10 === 0) say(`${s} segundos`);
    }
    setFeedback(r.msg || '', r.status === 'ok' ? 'good' : 'bad');
    if (r.status !== 'ok' && r.msg) say(r.msg);
    $('#depthFill').style.height = r.status === 'ok' ? '100%' : '0%';
    return r.status === 'ok' ? '#3dffa8' : '#ff3b5c';
  }

  if (r.progress != null) $('#depthFill').style.height = `${r.progress * 100}%`;
  if (r.event === 'rep') {
    session.good++;
    const el = $('#repCount');
    el.textContent = session.counter.reps;
    el.classList.remove('pop'); void el.offsetWidth; el.classList.add('pop');
    SFX.rep();
    say(String(session.counter.reps), true);
    addReps(ex.id, 1);
    updateTrainHUD();
    setFeedback(r.msg, 'good');
  } else if (r.event === 'bad' || r.event === 'partial') {
    if (r.event === 'bad') session.bad++;
    SFX.bad();
    say(r.msg.replace(' (no cuenta)', ''));
    setFeedback(r.msg, 'bad');
    updateTrainHUD();
  } else if (r.msg && r.status !== 'ok') {
    setFeedback(r.msg, r.status === 'warn' ? 'warn' : 'bad');
  } else if (r.status === 'ok' && !r.event && $('#feedback').classList.contains('bad') === false && !$('#feedback').classList.contains('good')) {
    setFeedback('Seguí así', '');
  }
  return r.status === 'warn' ? '#ffd166' : r.status === 'ok' ? '#4de1ff' : '#ff3b5c';
};

async function startCamera() {
  const btn = $('#btnCam');
  btn.disabled = true;
  btn.textContent = 'Cargando IA…';
  $('#camCenter').innerHTML = '<small>Cargando el modelo de visión (la primera vez tarda un poco)…</small>';
  try {
    await cam.start({ deviceId: $('#camSelect').value || undefined, model: S.settings.model });
    await fillCameras();
    btn.hidden = true;
    $('#btnStopCam').hidden = false;
    $('#camCenter').innerHTML = '';
    startCountdownWhenVisible();
    setFeedback('Ponete en posición', '');
  } catch (e) {
    console.error(e);
    $('#camCenter').innerHTML = '';
    const msg = e.name === 'NotAllowedError' ? 'Bloqueaste el permiso de la cámara. Habilitalo en el candado de la barra de direcciones.'
      : e.name === 'NotFoundError' ? 'No se encontró ninguna cámara.'
      : (e.message || String(e));
    sysModal({ title: 'ERROR', color: 'red', html: `No pude iniciar la cámara.<br><small>${esc(msg)}</small><br><br>Podés usar los botones <b>+1 / +5 / +10</b> mientras tanto.` });
  } finally {
    btn.disabled = false;
    btn.textContent = '📷 Encender cámara';
  }
}

function stopCamera() {
  cam.stop();
  $('#btnCam').hidden = false;
  $('#btnStopCam').hidden = true;
  session.state = 'idle';
  setFeedback('Cámara apagada');
}

async function fillCameras() {
  const sel = $('#camSelect');
  const cams = await PoseCamera.listCameras();
  const cur = sel.value;
  sel.innerHTML = cams.length ? cams.map((c, i) => `<option value="${c.deviceId}">${esc(c.label || 'Cámara ' + (i + 1))}</option>`).join('') : '<option value="">Cámara predeterminada</option>';
  if (cur) sel.value = cur;
}

function finishTraining() {
  const ex = session.ex;
  if (ex && (session.good || session.bad)) {
    log(`Serie de ${ex.name}: ${session.good}${ex.timed ? ' seg' : ' reps'}${session.bad ? `, ${session.bad} mal hechas` : ''}. +${fmt(session.xp)} XP`);
    sysModal({
      title: 'SERIE TERMINADA',
      html: `${ex.icon} <b>${ex.name}</b><br><br>
        ${ex.timed ? `Tiempo válido: <span class="em">${session.good} s</span>` : `Repeticiones válidas: <span class="em">${session.good}</span><br>Mal hechas: ${session.bad}`}<br>
        <div class="reward">+${fmt(session.xp)} XP</div>
        ${questRemaining().length && !S.quest.completed ? `<small>Te falta: ${questRemaining().map(([k, v]) => `${EXERCISES[k].name} ${v - (S.quest.progress[k] || 0)}`).join(', ')}</small>` : ''}`,
    });
  }
  session.ex = null;
  session.state = cam.running ? 'idle' : 'idle';
  $('#trainPanel').classList.add('hidden');
  $('#exercisePicker').classList.remove('hidden');
  renderExGrid();
  save();
}

// =============================================================
//  Recordatorios dentro del navegador
// =============================================================
function browserNag() {
  rollover();
  renderCountdown();
  const n = S.settings.nag;
  if (!n.enabled || S.quest.completed || Store.server) return;
  const now = new Date();
  if (now.getHours() < n.startHour) return;
  const last = Number(sessionStorage.getItem('lastNag') || 0);
  if (Date.now() - last < n.intervalMin * 60000) return;
  if (session.state === 'running') return;
  sessionStorage.setItem('lastNag', Date.now());
  const txt = 'Misión diaria incompleta. Andá a entrenar o recibirás una penalización.';
  if ('Notification' in window && Notification.permission === 'granted') new Notification('⚠ ALERTA DEL SISTEMA', { body: txt });
  SFX.alarm();
  sysModal({ title: 'ALERTA', color: 'red', sound: 'alarm', html: txt, buttons: [{ text: 'Entrenar ahora', primary: true }] }).then(() => showTab('mision'));
}

// =============================================================
//  Primer inicio
// =============================================================
async function onboarding() {
  await sysModal({
    title: 'NOTIFICACIÓN',
    html: 'Cumpliste los requisitos para convertirte en <span class="em">Jugador</span>.<br><br>El Sistema te va a asignar misiones diarias. Si las cumplís, vas a subir de nivel. Si no… habrá consecuencias.',
    buttons: [{ text: 'Aceptar', primary: true }],
  });
  let name = '';
  while (!name.trim()) {
    const r = await sysModal({ title: 'REGISTRO', html: '¿Cómo te llamás, Jugador?<input id="nameInput" maxlength="24" placeholder="Tu nombre" autofocus>', buttons: [{ text: 'Confirmar', primary: true }] });
    name = r.value || '';
  }
  S.player.name = name.trim();
  const r = await sysModal({
    title: 'NIVEL INICIAL',
    html: 'Elegí la dificultad de tus misiones diarias.<br><small>Podés cambiarla después en Ajustes.</small>',
    buttons: [{ text: 'Fácil' }, { text: 'Normal', primary: true }, { text: 'Difícil' }, { text: 'Extremo', danger: true }],
  });
  S.settings.difficulty = ['facil', 'normal', 'dificil', 'extremo'][r.index];
  newQuest(dateKey(), false);
  log(`${S.player.name} despertó como Jugador.`);
  save();
  render();
  if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission().catch(() => {});
  await sysModal({ title: 'MISIÓN DIARIA', html: `Tu primera misión ya está disponible.<br><br>${questItemsHTML(false)}`, buttons: [{ text: 'Empezar', primary: true }] });
  showTab('mision');
}

// =============================================================
//  Eventos
// =============================================================
function bind() {
  $('#tabs').addEventListener('click', (e) => { const b = e.target.closest('button[data-tab]'); if (b) showTab(b.dataset.tab); });
  document.addEventListener('click', (e) => {
    const g = e.target.closest('[data-goto]'); if (g) showTab(g.dataset.goto);
    const t = e.target.closest('[data-train]'); if (t) openTraining(t.dataset.train);
    const s = e.target.closest('[data-stat]');
    if (s && S.player.freePoints > 0) { S.player.freePoints--; S.player.alloc[s.dataset.stat]++; SFX.rep(); save(); render(); }
    const a = e.target.closest('[data-add]');
    if (a && session.ex) {
      const n = Number(a.dataset.add);
      session.good += n;
      $('#repCount').textContent = session.good;
      addReps(session.ex.id, n, 'manual');
      updateTrainHUD();
    }
  });
  $('#btnCam').onclick = startCamera;
  $('#btnStopCam').onclick = stopCamera;
  $('#btnFinish').onclick = finishTraining;

  $('#setName').onchange = (e) => { S.player.name = e.target.value.trim() || S.player.name; save(); render(); };
  $('#setDiff').onchange = (e) => {
    S.settings.difficulty = e.target.value;
    const q = S.quest;
    if (q && !q.completed && Object.values(q.progress).every((v) => !v)) { q.difficulty = e.target.value; q.targets = buildTargets(q.penalty); toast('Misión de hoy actualizada'); }
    save(); render();
  };
  $('#setVoice').onchange = (e) => { S.settings.voice = e.target.checked; save(); };
  $('#setSound').onchange = (e) => { S.settings.sound = e.target.checked; save(); };
  $('#setModel').onchange = (e) => { S.settings.model = e.target.value; save(); toast('Se aplica la próxima vez que enciendas la cámara'); };
  const nagNum = (id, key, min, max) => ($(id).onchange = (e) => { S.settings.nag[key] = Math.max(min, Math.min(max, Number(e.target.value) || min)); e.target.value = S.settings.nag[key]; save(); });
  nagNum('#setNagHour', 'startHour', 0, 23);
  nagNum('#setNagEvery', 'intervalMin', 5, 120);
  nagNum('#setNagSnooze', 'snoozesPerDay', 0, 10);
  $('#setNag').onchange = (e) => { S.settings.nag.enabled = e.target.checked; save(); };
  $('#setNagHard').onchange = async (e) => {
    if (e.target.checked) {
      const r = await sysModal({ title: 'CONFIRMAR', color: 'red', html: 'En modo hardcore la alerta ocupa toda la pantalla y <b>no se puede cerrar</b> hasta que vayas a entrenar, uses una posposición o escribas la frase de rendición.<br><br>¿Aceptás?', buttons: [{ text: 'Acepto', danger: true }, { text: 'Mejor no' }] });
      if (r.index !== 0) { e.target.checked = false; return; }
    }
    S.settings.nag.hard = e.target.checked; save();
  };

  $('#btnExport').onclick = () => {
    const blob = new Blob([JSON.stringify(S, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = `ascenso-${dateKey()}.json`; a.click();
  };
  $('#fileImport').onchange = async (e) => {
    try {
      const data = JSON.parse(await e.target.files[0].text());
      if (!data.player) throw new Error('Archivo inválido');
      S = merge(newState(), data); save(); render(); toast('Progreso importado');
    } catch (err) { toast('No se pudo importar: ' + err.message); }
  };
  $('#btnReset').onclick = async () => {
    const r = await sysModal({ title: 'REINICIAR', color: 'red', html: 'Vas a borrar TODO tu progreso. Escribí <b>BORRAR</b> para confirmar.<input>', buttons: [{ text: 'Borrar todo', danger: true }, { text: 'Cancelar' }] });
    if (r.index === 0 && (r.value || '').trim().toUpperCase() === 'BORRAR') { S = newState(); save(); location.reload(); }
  };

  setInterval(browserNag, 30000);
  setInterval(renderCountdown, 1000);
  setInterval(() => Store.heartbeat(session.state === 'running'), 30000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) { rollover(); render(); } });
  if ('speechSynthesis' in window) speechSynthesis.getVoices();
}

// =============================================================
//  Inicio
// =============================================================
async function main() {
  const loaded = await Store.load();
  if (loaded) S = merge(newState(), loaded);
  bind();
  fillCameras();
  if (!S.player.name) { render(); await onboarding(); }
  rollover();
  checkAchievements();
  render();
  renderExGrid();
  Store.heartbeat(false);
  setTimeout(browserNag, 4000);
  const hash = location.hash.replace('#', '');
  if (['estado', 'mision', 'entrenar', 'registro', 'ajustes'].includes(hash)) showTab(hash);
}

main();

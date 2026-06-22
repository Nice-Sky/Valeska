/* ══ Altura real en mobile (fix iOS Safari + Chrome) ══ */
function fixHeight() {
  const h = (window.visualViewport ? window.visualViewport.height : window.innerHeight);
  document.getElementById('presentation').style.height = h + 'px';
}
fixHeight();
window.addEventListener('resize', fixHeight);
window.addEventListener('orientationchange', () => setTimeout(fixHeight, 300));
if (window.visualViewport) {
  window.visualViewport.addEventListener('resize', fixHeight);
}

/* ══ Partículas de fondo ══ */
(function () {
  const canvas = document.getElementById('particle-canvas');
  const ctx = canvas.getContext('2d');
  let W, H, particles = [];

  function resize() {
    W = canvas.width  = window.innerWidth;
    H = canvas.height = window.innerHeight;
  }

  function mkParticle() {
    const side = Math.random() < 0.5 ? 'red' : 'green';
    return {
      x: Math.random() * W,
      y: Math.random() * H,
      r: Math.random() * 1.2 + 0.3,
      vx: (Math.random() - 0.5) * 0.25,
      vy: (Math.random() - 0.5) * 0.25,
      alpha: Math.random() * 0.35 + 0.05,
      side,
    };
  }

  function init() {
    resize();
    particles = Array.from({ length: 45 }, mkParticle);
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);
    for (const p of particles) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = p.side === 'red'
        ? `rgba(231,76,60,${p.alpha})`
        : `rgba(46,204,113,${p.alpha})`;
      ctx.fill();
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < 0 || p.x > W || p.y < 0 || p.y > H) {
        Object.assign(p, mkParticle(), { x: Math.random() * W, y: Math.random() * H });
      }
    }
    requestAnimationFrame(draw);
  }

  window.addEventListener('resize', resize);
  init();
  draw();
})();


/* ══ Audio por slide ══ */
const SLIDE_AUDIO = [
  null,                    // 0  Portada
  'introduccion.mp3',      // 1  Introducción
  'Contexto.mp3',          // 2  Contexto
  'percepcion.mp3',        // 3  Percepción
  'atencion.mp3',          // 4  Atención
  'memoria.mp3',           // 5  Memoria
  'pensamiento.mp3',       // 6  Pensamiento
  'lenguaje.mp3',          // 7  Lenguaje
  'inteligencia.mp3',      // 8  Inteligencia
  'metacognicion.mp3',     // 9  Metacognición
  'creatividad.mp3',       // 10 Creatividad
  'entorno.mp3',           // 11 El entorno
  'conclusion.mp3',        // 12 Conclusión
  'comparacion.mp3',       // 12 Comparación
  'conclusion.mp3',        // 13 Conclusión
];

let currentAudio = null;

/* ══ Imágenes por slide ══ */
const SLIDE_IMAGES = [
  'slide-00.jpg',  // 0  Portada
  'slide-01.jpg',  // 1  Introducción
  'slide-02.jpg',  // 2  Contexto
  'slide-03.jpg',  // 3  Percepción
  'slide-04.jpg',  // 4  Atención
  'slide-05.jpg',  // 5  Memoria
  'slide-06.jpg',  // 6  Pensamiento
  'slide-07.jpg',  // 7  Lenguaje
  'slide-08.jpg',  // 8  Inteligencia
  'slide-09.jpg',  // 9  Metacognición
  'slide-10.jpg',  // 10 Creatividad
  'slide-11.jpg',  // 11 El entorno
  'slide-12.jpg',  // 12 Comparación
  null,            // 13 Conclusión
  null,            // 14 Gracias
];

function injectSlideImages() {
  document.querySelectorAll('.slide').forEach((slide, i) => {
    const src = SLIDE_IMAGES[i];
    if (!src) return;
    const wrap = document.createElement('div');
    Object.assign(wrap.style, {
      position: 'absolute',
      bottom: '3.5rem',
      right: '1.5rem',
      width: '160px',
      height: '110px',
      borderRadius: '6px',
      overflow: 'hidden',
      border: '1px solid rgba(255,255,255,0.08)',
      boxShadow: '0 4px 20px rgba(0,0,0,0.6)',
      zIndex: '3',
      flexShrink: '0',
    });
    const img = document.createElement('img');
    img.src = src;
    img.alt = '';
    Object.assign(img.style, {
      width: '100%',
      height: '100%',
      objectFit: 'cover',
      display: 'block',
      filter: 'brightness(0.85) contrast(1.05)',
    });
    img.onerror = () => { wrap.style.display = 'none'; };
    wrap.appendChild(img);
    slide.appendChild(wrap);
  });
}
injectSlideImages();

/* ── Crear barra de audio en JS ── */
const audioBar = document.createElement('div');
Object.assign(audioBar.style, {
  background: '#06060c',
  borderTop: '1px solid rgba(255,255,255,0.04)',
  padding: '8px 40px',
  flexShrink: '0',
  zIndex: '10',
  boxSizing: 'border-box',
  width: '100%',
  opacity: '0',
  transform: 'translateY(6px)',
  transition: 'opacity 0.4s ease, transform 0.4s ease',
  pointerEvents: 'none',
  maxHeight: '0',
  paddingTop: '0',
  paddingBottom: '0',
  overflow: 'hidden',
});

const audioInner = document.createElement('div');
Object.assign(audioInner.style, {
  display: 'flex',
  alignItems: 'center',
  gap: '10px',
  maxWidth: '1140px',
  margin: '0 auto',
  width: '100%',
});

audioInner.innerHTML = `
  <button id="audio-playpause" style="background:rgba(155,89,182,0.15);border:1px solid rgba(155,89,182,0.4);color:#9b59b6;border-radius:50%;width:24px;height:24px;min-width:24px;font-size:9px;cursor:pointer;display:flex;align-items:center;justify-content:center;padding:0;box-sizing:border-box;">▶</button>
  <span id="audio-cur" style="font-family:monospace;font-size:11px;color:#f0f0f0;min-width:32px;text-align:right;white-space:nowrap;">0:00</span>
  <div id="audio-track" style="flex:1;height:4px;background:#1a1a2e;border-radius:2px;cursor:pointer;position:relative;min-width:0;">
    <div id="audio-fill" style="height:100%;width:0%;background:linear-gradient(90deg,#5b2d8e,#d4a017);border-radius:2px;transition:width 0.25s linear;"></div>
  </div>
  <span id="audio-total" style="font-family:monospace;font-size:11px;color:#6a6a88;min-width:32px;white-space:nowrap;">0:00</span>`;

audioBar.appendChild(audioInner);
document.getElementById('controls').insertAdjacentElement('beforebegin', audioBar);

const audioFill    = audioInner.querySelector('#audio-fill');
const audioCur     = audioInner.querySelector('#audio-cur');
const audioTotalEl = audioInner.querySelector('#audio-total');
const audioBtn     = audioInner.querySelector('#audio-playpause');
const audioTrack   = audioInner.querySelector('#audio-track');

function fmtTime(s) {
  if (!s || isNaN(s)) return '0:00';
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return m + ':' + String(sec).padStart(2, '0');
}

function updateBtn() {
  if (!currentAudio) { audioBtn.textContent = '▶'; return; }
  audioBtn.textContent = currentAudio.paused ? '▶' : '⏸';
}

audioBtn.addEventListener('click', () => {
  if (!currentAudio) return;
  if (currentAudio.paused) {
    currentAudio.play();
  } else {
    currentAudio.pause();
  }
  updateBtn();
});

audioTrack.addEventListener('click', (e) => {
  if (!currentAudio || !currentAudio.duration) return;
  const rect = audioTrack.getBoundingClientRect();
  currentAudio.currentTime = ((e.clientX - rect.left) / rect.width) * currentAudio.duration;
});

function playSlideAudio(index) {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.currentTime = 0;
    currentAudio = null;
  }

  audioFill.style.width   = '0%';
  audioCur.textContent    = '0:00';
  audioTotalEl.textContent = '0:00';
  updateBtn();

  const src = SLIDE_AUDIO[index];
  if (src) {
    audioBar.style.maxHeight = '60px';
    audioBar.style.paddingTop = '8px';
    audioBar.style.paddingBottom = '8px';
    audioBar.style.opacity = '1';
    audioBar.style.transform = 'translateY(0)';
    audioBar.style.pointerEvents = 'all';
    currentAudio = new Audio(src);

    currentAudio.addEventListener('loadedmetadata', () => {
      audioTotalEl.textContent = fmtTime(currentAudio.duration);
    });

    currentAudio.addEventListener('timeupdate', () => {
      const pct = (currentAudio.currentTime / currentAudio.duration) * 100 || 0;
      audioFill.style.width = pct + '%';
      audioCur.textContent  = fmtTime(currentAudio.currentTime);
      updateBtn();
    });

    currentAudio.addEventListener('ended', () => {
      audioFill.style.width = '100%';
      audioBtn.textContent  = '▶';
    });

    currentAudio.play().catch(() => {});
    updateBtn();
  } else {
    audioBar.style.opacity = '0';
    audioBar.style.transform = 'translateY(6px)';
    audioBar.style.pointerEvents = 'none';
    audioBar.style.maxHeight = '0';
    audioBar.style.paddingTop = '0';
    audioBar.style.paddingBottom = '0';
  }
}

/* ══ Presentación ══ */
const slides     = document.querySelectorAll('.slide');
const fill       = document.getElementById('progress-fill');
const counter    = document.getElementById('slide-counter');
const titleBar   = document.getElementById('slide-title-bar');
const btnPrev    = document.getElementById('btn-prev');
const btnNext    = document.getElementById('btn-next');
const dotsWrap   = document.getElementById('ctrl-dots');
const keyHint    = document.getElementById('key-hint');

const TITLES = [
  'Portada', 'Introducción', 'Contexto', 'Percepción', 'Atención',
  'Memoria', 'Pensamiento', 'Lenguaje', 'Inteligencia',
  'Metacognición', 'Creatividad',
  'El entorno', 'Comparación', 'Conclusión', 'Gracias',
];

const TOTAL = slides.length;
let current = 0;

/* Dots de navegación */
TITLES.forEach((_, i) => {
  const d = document.createElement('button');
  d.className = 'ctrl-dot' + (i === 0 ? ' active' : '');
  d.setAttribute('aria-label', 'Ir a diapositiva ' + (i + 1));
  d.addEventListener('click', () => goTo(i));
  dotsWrap.appendChild(d);
});

function getDots() { return dotsWrap.querySelectorAll('.ctrl-dot'); }

function goTo(index) {
  if (index < 0 || index >= TOTAL || index === current) return;

  const prev = current;
  current    = index;

  slides[prev].classList.remove('active');
  slides[prev].classList.add('exit-left');
  setTimeout(() => slides[prev].classList.remove('exit-left'), 500);

  slides[current].classList.add('active');

  fill.style.width = ((current + 1) / TOTAL * 100) + '%';
  counter.textContent = (current + 1) + ' / ' + TOTAL;
  titleBar.textContent = TITLES[current] || '';

  playSlideAudio(current);

  getDots().forEach((d, i) => d.classList.toggle('active', i === current));

  btnPrev.disabled = current === 0;
  btnNext.disabled = current === TOTAL - 1;
}

btnPrev.addEventListener('click', () => goTo(current - 1));
btnNext.addEventListener('click', () => goTo(current + 1));

document.addEventListener('keydown', (e) => {
  if (e.key === 'ArrowRight' || e.key === ' ') { e.preventDefault(); goTo(current + 1); }
  else if (e.key === 'ArrowLeft')               { e.preventDefault(); goTo(current - 1); }
  else if (e.key === 'Escape' && document.fullscreenElement) document.exitFullscreen();
  else if (e.key === 'f' || e.key === 'F') {
    document.fullscreenElement
      ? document.exitFullscreen()
      : document.documentElement.requestFullscreen().catch(() => {});
  }
});

/* Ocultar hint de teclado tras primer uso */
let hintHidden = false;
document.addEventListener('keydown', () => {
  if (!hintHidden) { keyHint.classList.add('hidden'); hintHidden = true; }
}, { once: true });

/* ══ Zonas táctiles ══ */
function addTap(id, fn) {
  const el = document.getElementById(id);
  let tapped = false;
  el.addEventListener('touchstart', (e) => { tapped = true; }, { passive: true });
  el.addEventListener('touchend', (e) => {
    if (tapped) { e.preventDefault(); fn(); tapped = false; }
  });
  el.addEventListener('click', fn);
}
addTap('tap-prev', () => goTo(current - 1));
addTap('tap-next', () => goTo(current + 1));

/* ══ Swipe táctil ══ */
let touchStartX = 0;
let touchStartY = 0;

document.addEventListener('touchstart', (e) => {
  touchStartX = e.touches[0].clientX;
  touchStartY = e.touches[0].clientY;
}, { passive: true });

document.addEventListener('touchend', (e) => {
  const dx = e.changedTouches[0].clientX - touchStartX;
  const dy = e.changedTouches[0].clientY - touchStartY;
  if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 40) {
    if (dx < 0) goTo(current + 1);
    else        goTo(current - 1);
  }
}, { passive: true });

/* Init */
goTo(0);
slides[0].classList.add('active');

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
  'comparacion.mp3',       // 13 Comparación
];

let currentAudio = null;

function playSlideAudio(index) {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.currentTime = 0;
    currentAudio = null;
  }
  const src = SLIDE_AUDIO[index];
  console.log('Audio slide', index, '→', src);
  if (src) {
    currentAudio = new Audio(src);
    currentAudio.play().then(() => {
      console.log('✅ Reproduciendo:', src);
    }).catch((e) => {
      console.error('❌ Error al reproducir:', src, e);
    });
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
  'El entorno', 'Conclusión', 'Comparación',
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

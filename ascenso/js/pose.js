// =============================================================
//  Cámara + detección de pose (MediaPipe Pose Landmarker)
// =============================================================
const MP_VER = '0.10.14';
// Primero se usan los archivos locales (carpeta vendor/), después CDNs públicos.
const SOURCES = [
  { lib: new URL('../vendor/vision_bundle.mjs', import.meta.url).href, wasm: new URL('../vendor/wasm', import.meta.url).href },
  { lib: `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${MP_VER}/vision_bundle.mjs`, wasm: `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${MP_VER}/wasm` },
  { lib: `https://unpkg.com/@mediapipe/tasks-vision@${MP_VER}/vision_bundle.mjs`, wasm: `https://unpkg.com/@mediapipe/tasks-vision@${MP_VER}/wasm` },
];
const GCS = 'https://storage.googleapis.com/mediapipe-models/pose_landmarker';
const MODELS = {
  lite: [new URL('../vendor/models/pose_landmarker_lite.task', import.meta.url).href, `${GCS}/pose_landmarker_lite/float16/1/pose_landmarker_lite.task`],
  full: [`${GCS}/pose_landmarker_full/float16/1/pose_landmarker_full.task`],
};

const CONNECTIONS = [
  [11, 12], [11, 13], [13, 15], [12, 14], [14, 16],
  [11, 23], [12, 24], [23, 24],
  [23, 25], [25, 27], [24, 26], [26, 28],
  [27, 31], [28, 32], [27, 29], [28, 30],
];

let landmarker = null;
let loadedModel = null;

async function tryEach(items, fn) {
  let last;
  for (const it of items) {
    try { return await fn(it); } catch (e) { last = e; console.warn('Falló', it, e); }
  }
  throw last;
}

async function getLandmarker(model = 'lite') {
  if (landmarker && loadedModel === model) return landmarker;
  const { vision, fileset } = await tryEach(SOURCES, async (src) => {
    const vision = await import(src.lib);
    const fileset = await vision.FilesetResolver.forVisionTasks(src.wasm);
    return { vision, fileset };
  });
  const opts = (path, delegate) => ({
    baseOptions: { modelAssetPath: path, delegate },
    runningMode: 'VIDEO',
    numPoses: 1,
    minPoseDetectionConfidence: 0.5,
    minPosePresenceConfidence: 0.5,
    minTrackingConfidence: 0.5,
  });
  landmarker = await tryEach(MODELS[model] || MODELS.lite, async (path) => {
    try {
      return await vision.PoseLandmarker.createFromOptions(fileset, opts(path, 'GPU'));
    } catch (e) {
      console.warn('GPU no disponible, usando CPU', e);
      return await vision.PoseLandmarker.createFromOptions(fileset, opts(path, 'CPU'));
    }
  });
  loadedModel = model;
  return landmarker;
}

export class PoseCamera {
  constructor(video, canvas) {
    this.video = video;
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.stream = null;
    this.running = false;
    this.onFrame = null; // (landmarks, worldLandmarks, aspect) => {color}
    this.lastVideoTime = -1;
    this.color = '#4de1ff';
  }

  async start({ deviceId, model } = {}) {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('Este navegador no permite usar la cámara. Abrí la app desde http://localhost o https.');
    }
    const lmP = getLandmarker(model);
    const video = deviceId
      ? { deviceId: { exact: deviceId }, width: { ideal: 1280 }, height: { ideal: 720 } }
      : { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } };
    lmP.catch(() => {});
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({ video, audio: false });
      this.video.srcObject = this.stream;
      await this.video.play();
      await lmP;
    } catch (e) {
      this.stop();
      throw e;
    }
    this.running = true;
    this.loop();
  }

  stop() {
    this.running = false;
    if (this.stream) this.stream.getTracks().forEach((t) => t.stop());
    this.stream = null;
    this.video.srcObject = null;
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
  }

  static async listCameras() {
    try {
      const devs = await navigator.mediaDevices.enumerateDevices();
      return devs.filter((d) => d.kind === 'videoinput');
    } catch { return []; }
  }

  loop() {
    if (!this.running) return;
    const v = this.video;
    if (v.readyState >= 2 && v.currentTime !== this.lastVideoTime) {
      this.lastVideoTime = v.currentTime;
      if (this.canvas.width !== v.videoWidth) {
        this.canvas.width = v.videoWidth;
        this.canvas.height = v.videoHeight;
      }
      const res = landmarker.detectForVideo(v, performance.now());
      const lm = res.landmarks?.[0];
      const w = res.worldLandmarks?.[0];
      this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
      if (lm && w) {
        const color = this.onFrame?.(lm, w, v.videoWidth / v.videoHeight) || this.color;
        this.draw(lm, color);
      } else {
        this.onFrame?.(null, null, 1);
      }
    }
    requestAnimationFrame(() => this.loop());
  }

  draw(lm, color) {
    const { ctx, canvas } = this;
    const W = canvas.width, H = canvas.height;
    ctx.lineWidth = Math.max(3, W / 250);
    ctx.strokeStyle = color;
    ctx.shadowColor = color;
    ctx.shadowBlur = 12;
    for (const [a, b] of CONNECTIONS) {
      if ((lm[a].visibility ?? 1) < 0.4 || (lm[b].visibility ?? 1) < 0.4) continue;
      ctx.beginPath();
      ctx.moveTo(lm[a].x * W, lm[a].y * H);
      ctx.lineTo(lm[b].x * W, lm[b].y * H);
      ctx.stroke();
    }
    ctx.fillStyle = '#ffffff';
    for (let i = 11; i < 33; i++) {
      if ((lm[i].visibility ?? 1) < 0.4) continue;
      ctx.beginPath();
      ctx.arc(lm[i].x * W, lm[i].y * H, Math.max(4, W / 200), 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.shadowBlur = 0;
  }
}

# ⚔ ASCENSO — Sistema de entrenamiento

Programa de Windows para entrenar como en un RPG: tenés **nivel, rango (E → S), XP, estadísticas,
misiones diarias, rachas, logros y penalizaciones**. La **cámara analiza cómo hacés cada ejercicio**
con IA, cuenta solo las repeticiones bien hechas y te corrige en voz alta. Y **el Guardián** vive en
la bandeja del sistema y te persigue con alertas encima de todo hasta que cumplas la misión del día.

## Instalar

1. Andá a **[Releases](../../releases/latest)** y descargá **`Ascenso-Instalador.exe`**.
2. Ejecutalo. Si Windows dice *"Windows protegió tu PC"*: **Más información → Ejecutar de todas formas**
   (aparece porque el programa no está firmado digitalmente).
3. Abrí Ascenso, registrate y elegí la dificultad. Te va a preguntar si querés que arranque solo con
   Windows: decí que sí para que el Guardián no te deje escapar.

No hace falta instalar Python ni nada más. Todo corre en tu compu: ningún video sale de ahí.

## Usar el iPhone como cámara

Si tu compu no tiene webcam (o querés ponerla en el piso para las flexiones), usá el iPhone como
cámara inalámbrica con alguna de estas apps (instalala en el iPhone y en Windows):

- **Camo** (Reincubate)
- **iVCam**
- **EpocCam**

Después elegí esa cámara en el selector de la pantalla **Entrenar**.

## Ejercicios con cámara

| Ejercicio | Dónde poner la cámara | Qué corrige |
|---|---|---|
| 💪 Flexiones | De costado, a la altura del piso | Profundidad, cadera caída, que estés en posición |
| 🦵 Sentadillas | De costado o en diagonal | Profundidad, inclinación del torso |
| 🔥 Abdominales | De costado, acostado | Que subas lo suficiente |
| ⚡ Jumping Jacks | De frente | Brazos arriba + piernas abiertas |
| 🏃 Zancadas | De costado | Profundidad |
| 🧱 Plancha | De costado, al piso | Solo cuenta el tiempo con el cuerpo recto |

- Antes de empezar hay una cuenta regresiva de 3 segundos cuando te detecta.
- Las repeticiones mal hechas **no cuentan** y te dice por qué.
- Sin cámara podés sumar con +1 / +5 / +10 ("modo honor": da el 70% de la XP).

## Las reglas del Sistema

- **Misión diaria** según la dificultad: Fácil, Normal, Difícil o Extremo (100 flexiones,
  100 abdominales, 100 sentadillas + 2 minutos de plancha). Crece un 10% cada 5 niveles.
- Completarla da XP grande, suma racha y Disciplina.
- **Si no la completás antes de medianoche**: perdés XP, perdés la racha y al día siguiente te toca
  la **Misión de Penalización** (+50% de volumen).
- Cada nivel da **3 puntos** para repartir en FUE / AGI / RES / DIS. Además las estadísticas suben
  solas según lo que entrenes.

## El Guardián

Se configura en **Ajustes**:

- Desde qué hora empieza a molestar (18 hs por defecto) y cada cuántos minutos repite.
- Cuántas veces por día podés posponer.
- **Modo hardcore**: la alerta cubre **todas tus pantallas** y no se cierra hasta que vayas a
  entrenar, uses una posposición o escribas `ME RINDO` (te deja en paz ese día, pero igual te comés
  la penalización).
- Mientras estás entrenando con la cámara no te interrumpe.
- Cerrar la ventana no cierra el programa: queda en la bandeja (al lado del reloj).

Tus datos se guardan en `%APPDATA%\Ascenso\progreso.json`. Podés exportarlos e importarlos desde Ajustes.

---

## Para desarrolladores

```bat
ejecutar.bat          :: corre desde el código (instala dependencias la primera vez, requiere Python 3.12)
build.bat             :: compila dist\Ascenso\Ascenso.exe
python -m pytest      :: tests
```

Cada push compila el instalador automáticamente con GitHub Actions (`.github/workflows/build.yml`)
y lo publica en Releases.

Estructura:

- `ascenso/exercises.py`: medición de cada ejercicio y contador de repeticiones
- `ascenso/game.py`: reglas (XP, niveles, misiones, penalizaciones, logros)
- `ascenso/camera.py`: cámara + MediaPipe Pose en un hilo aparte
- `ascenso/guardian.py`: alertas
- `ascenso/ui/`: interfaz (PySide6 / Qt)

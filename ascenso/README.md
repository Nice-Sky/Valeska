# ⚔ ASCENSO — Sistema de entrenamiento

App de entrenamiento personal estilo "sistema de RPG": tenés **nivel, rango (E → S), XP, estadísticas,
misiones diarias, rachas, logros y penalizaciones**. La **cámara analiza cómo hacés cada ejercicio**,
cuenta las repeticiones bien hechas y te corrige en voz alta. Y el **Guardián** te persigue en la compu
con alertas encima de todo hasta que completes la misión del día.

## Cómo arrancar

1. Instalá Python 3 (https://www.python.org/downloads/ — en Windows marcá **"Add Python to PATH"**).
2. **Windows:** doble clic en `iniciar.bat`.
   **Mac / Linux:** `./iniciar.sh` (o `python3 servidor.py`).
3. Se abre el navegador en `http://localhost:8765`. Registrate, elegí dificultad y a entrenar.

> Para que el Guardián arranque solo cada vez que prendés la compu (Windows): doble clic en
> `instalar_inicio_windows.bat`. Para sacarlo, borrá `ascenso_guardian.bat` de la carpeta Inicio
> (Win+R → `shell:startup`).

## Ejercicios con cámara

| Ejercicio | Dónde poner la cámara | Qué corrige |
|---|---|---|
| 💪 Flexiones | De costado, a la altura del piso | Profundidad, cadera caída |
| 🦵 Sentadillas | De costado o en diagonal | Profundidad, inclinación del torso |
| 🔥 Abdominales | De costado, acostado | Que subas lo suficiente |
| ⚡ Jumping Jacks | De frente | Brazos arriba + piernas abiertas |
| 🏃 Zancadas | De costado | Profundidad |
| 🧱 Plancha | De costado, al piso | Solo cuenta el tiempo con el cuerpo recto |

- Las reps mal hechas **no cuentan** (te dice por qué).
- Sin cámara podés sumar con los botones +1/+5/+10 ("modo honor", da 70% de la XP).
- La detección corre 100% en tu compu (MediaPipe). No se sube ningún video a ningún lado.
- Si va lento, en Ajustes dejá "Precisión: Rápida". Si tenés buena compu, probá "Precisa".

## Las reglas del Sistema

- **Misión diaria**: según la dificultad (Fácil / Normal / Difícil / Extremo = 100 flexiones,
  100 abdominales, 100 sentadillas + plancha). Crece un 10% cada 5 niveles.
- Completarla: XP grande + racha + Disciplina.
- **No completarla antes de medianoche**: perdés XP, perdés la racha y al día siguiente te toca la
  **Misión de Penalización** (+50% de volumen).
- Cada nivel da **3 puntos** para repartir en FUE / AGI / RES / DIS. Además las estadísticas suben
  solas según lo que entrenes.

## El Guardián (modo molesto)

Configurable en **Ajustes**:
- Desde qué hora empieza a molestar (por defecto 18 hs) y cada cuántos minutos.
- Cuántas veces por día podés posponer.
- **Modo hardcore**: alerta en pantalla completa que no se cierra hasta que vayas a entrenar,
  uses una posposición, o escribas `ME RINDO` (te deja en paz ese día, pero igual te comés la penalización).
- Mientras estás entrenando con la cámara no te interrumpe.

## Datos

Tu progreso se guarda en `datos/progreso.json` (y en el navegador). Podés exportarlo/importarlo
desde Ajustes.

## Usar el celular como cámara

La cámara del navegador solo funciona en `localhost` o en `https`. La forma más fácil: abrí la app
en la compu y usá el celular como webcam (DroidCam, Iriun, o "Cámara de continuidad" en Mac) y elegilo
en el selector de cámara.

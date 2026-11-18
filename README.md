# ARISE TRAINER

Programa de Windows para entrenar todos los días y no aflojar. Tenés un **objetivo diario**, la
**cámara cuenta tus repeticiones** con IA (solo valen las bien hechas) y un **sistema de progreso**
con XP, niveles y rangos (E → S) que premia la constancia y penaliza los días que fallás. Si no
entrenaste, el programa te lo recuerda con alertas encima de todo hasta que lo hagas.

## Instalar

1. Andá a **[Releases](../../releases/latest)** y descargá **`AriseTrainer-Instalador.exe`**.
2. Ejecutalo. Si Windows dice *"Windows protegió tu PC"*: **Más información → Ejecutar de todas formas**
   (aparece porque el programa no está firmado digitalmente).
3. Abrilo, poné tu nombre y elegí el plan. Te pregunta si querés que arranque con Windows: decí que sí.

No hace falta instalar nada más. Todo corre en tu compu: ningún video sale de ahí.

> ¿Tenías instalada la versión anterior ("Ascenso")? Tu progreso se pasa solo. Después desinstalá
> "Ascenso" desde *Configuración → Aplicaciones*.

## Cómo funciona

**Objetivo diario.** Según el plan (Principiante, Intermedio, Avanzado o Extremo), cada día tenés
que cumplir una cantidad de flexiones, sentadillas, abdominales, jumping jacks y segundos de plancha.

- **Progresión automática:** cada 7 días cumplidos los objetivos suben un 5% (se puede desactivar).
- **Días de descanso:** elegís qué días de la semana descansás (por defecto, el domingo). Esos días
  no hay objetivo ni penalización y la racha no se corta.
- **Si fallás un día:** perdés XP, la racha vuelve a cero y al día siguiente el objetivo es +30%.

**Entrenamiento por series.** Elegís el ejercicio, encendés la cámara y arranca una cuenta de 3 segundos
cuando te detecta. Al terminar la serie elegís descansar 60 o 90 segundos (con cuenta regresiva) o
terminar el ejercicio. Cada serie queda registrada y si superás tu mejor marca es **récord personal**.

**Progreso real.**
- Constancia: % de días cumplidos en los últimos 30.
- Volumen diario (gráfico de 30 días) y comparación con la semana anterior.
- Récords personales por ejercicio.
- Racha actual y mejor racha.

**XP, niveles y rangos.** Cada repetición válida suma XP; cumplir el objetivo del día suma un bonus que
crece con la racha. Rangos: E (nivel 1), D (10), C (20), B (35), A (50), S (75). Los atributos
(Fuerza, Resistencia, Agilidad) se calculan con tus récords y volumen. Disciplina es tu % de constancia.

## Ejercicios con cámara

| Ejercicio | Dónde poner la cámara | Qué corrige |
|---|---|---|
| Flexiones | De costado, a la altura del piso | Profundidad, cadera caída, que estés en posición |
| Sentadillas | De costado o en diagonal | Profundidad, inclinación del torso |
| Abdominales | De costado, acostado | Que subas lo suficiente |
| Jumping Jacks | De frente | Brazos arriba + piernas abiertas |
| Zancadas | De costado | Profundidad |
| Plancha | De costado, al piso | Solo cuenta el tiempo con el cuerpo recto |

Sin cámara podés sumar con +1 / +5 / +10 (da el 70% de la XP).

### Usar el iPhone como cámara

Instalá **Camo**, **iVCam** o **EpocCam** en el iPhone y en Windows, y elegí esa cámara en la
pantalla Entrenar. Sirve para apoyar el teléfono en el piso en las flexiones.

## Recordatorios

En **Ajustes → Recordatorios**: desde qué hora molesta (18 hs), cada cuántos minutos, cuántas veces
podés posponer, y el **modo estricto** (la alerta cubre todas las pantallas y no se cierra hasta que
vayas a entrenar, pospongas, o escribas `ME RINDO` para saltear el día con penalización).
Cerrar la ventana no cierra el programa: queda al lado del reloj.

Datos: `%APPDATA%\AriseTrainer\progreso.json` (exportables desde Ajustes).

---

## Para desarrolladores

```bat
ejecutar.bat          :: corre desde el código (requiere Python 3.12)
build.bat             :: compila dist\AriseTrainer\AriseTrainer.exe
python -m pytest      :: tests
```

Cada push compila, prueba y publica el instalador con GitHub Actions (`.github/workflows/build.yml`).

- `arise/exercises.py`: medición de cada ejercicio y contador de repeticiones
- `arise/game.py`: reglas (XP, niveles, objetivo, progresión, descanso, récords, penalizaciones)
- `arise/camera.py`: cámara + MediaPipe Pose en un hilo aparte
- `arise/guardian.py`: recordatorios
- `arise/ui/`: interfaz (PySide6 / Qt)

Íconos: [Lucide](https://lucide.dev) (licencia ISC, ver `assets/icons/LICENSE-lucide.txt`).

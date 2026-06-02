# 🎮 Neon Dodge: Level Overdrive

> **A gesture-controlled arcade survival game — dodge neon hazards using only your hand.**

Built with Python, Pygame, OpenCV, and MediaPipe. Control your player in real-time by pointing your index finger at the camera. No keyboard, no mouse — just your hand.

---

## 📸 Preview

> *(Add gameplay screenshots or a GIF here)*

---

## 🕹️ Gameplay

You are a glowing cyan orb on a neon grid. Hazards spawn from all directions. Your only goal: **survive for 60 seconds per level.**

Point your index finger at the webcam — the player follows wherever you point. Survive all three levels to see the credits.

---

## ✨ Features

### 🖐️ Hand Tracking Controls
- Powered by **MediaPipe Hands** running on a background thread for zero-lag input
- Index fingertip position is mapped to the full game screen with edge-margin compensation, so you can reach the corners without your hand leaving the camera frame
- Position is smoothed via lerp (55% per frame) to filter out camera noise while still feeling instant
- A live webcam preview with skeleton overlay is shown in the bottom-left corner during play

### 🌊 3-Level Campaign

| Level | Name | Theme | Key Hazards |
|---|---|---|---|
| 1 | **The Awakening** | Deep blue — calm neon | Exploders, lasers (slow) |
| 2 | **Pulse Overdrive** | Purple — intensifying | Rapid lasers, Sun Orbs (paired) |
| 3 | **Chaos Protocol** | Dark red — full chaos | Sun Orbs, Black Hole, dense exploders |

Each level has its own music track, color-shifted background grid, and cinematic intro card.

### 💥 Hazard Types

- **Exploders** — Timed orbs that detonate into a burst of mini-shrapnel particles. Explosion triggers screen shake and zoom.
- **Lasers** — Targeted beams fired directly at the player. Single-shot mode in Level 1, rapid-fire in Level 2+.
- **Sun Orbs** — Giant white orbs that grow from a pinpoint to full size while shaking the screen and ejecting flame particles. Always spawn in guaranteed-separation pairs.
- **Black Hole** (Level 3 only) — A mega-orb that grows to an enormous radius, distorts the screen, and triggers an intense vignette and sustained shake for the full 5-second active window.
- **Mini Circles** — Shrapnel fragments scattered outward from exploder detonations.

### ⚡ Power-Up System
One power-up spawns at a time. Collect it by touching it with your player orb.

| Power-Up | Effect | Duration |
|---|---|---|
| 🟢 **+HP** | +2 temporary hit points with orbiting green particle aura | 10 s or 2 hits |
| 🔵 **Shield** | Absorbs all damage; orbiting energy nodes with motion trails and connecting arc lines | 10 s |
| 💙 **Slow** | All hazards move at 60% speed; blue screen tint + ripple ring aura | 10 s |

- First power-up spawns within 10 seconds of level start
- Vanishes if not collected after 5 seconds
- 15-second cooldown between pickups

### 🎨 Visual Effects

- **Chromatic aberration** — RGB channel split on player hit
- **Screen shake + zoom** — Dynamic intensity based on hazard proximity and hit severity
- **Near-miss sparks** — Tiny cyan particles burst when a laser passes within 36px without hitting
- **Player trail** — 15-frame motion trail behind the player
- **Vignette** — Subtle edge darkening that intensifies during the Black Hole event
- **Animated grid background** — Beat-synced, per-level color-shifted neon grid
- **CRT scanlines** — Subtle overlay on transition screens
- **Glitch effect** — Horizontal pixel-band shifts on the stage-cleared screen
- **Power-up screen ripple** — 4-layer expanding shockwave on pickup

### 🎬 Cinematic Transitions

- **Level intro** — 2-second animated title card with scale-pulse and glow, per-level accent color
- **Stage-cleared screen** — Full cinematic sequence: glitch-in title → warning cascade → blinking prompt → 3-2-1 countdown with scale + ring animation → white flash
- **Death sequence** — 3-second fade to black with death music, then automatic level restart
- **Screen fade in/out** — Used on level start and after death

### 🔊 Audio
- Per-level looping music tracks
- Dedicated mixer channels for each SFX type (no audio cutoff from overlapping sounds)
- Separate stage-cleared music track that fades out cleanly before next level starts
- SFX: hit, death, laser fire, Sun Orb spawn, exploder detonation, slow-motion, shield pickup, extra HP

---

## 🗂️ Project Structure

```
neon-dodge/
├── dodge.py          # Main game loop, all classes, rendering, transitions
├── tracking.py       # HandTracker — MediaPipe on a background thread
├── powerups.py       # Power-up system, visual effects, HUD
├── levels.py         # Level configuration data (spawn rates, speeds, flags)
└── assets/
    ├── img/
    │   └── icon.png
    ├── sfx/
    │   ├── hit.mp3
    │   ├── death.mp3
    │   ├── laser.mp3
    │   ├── sunorb.mp3
    │   ├── expolosionorb.mp3
    │   ├── slowmo.mp3
    │   ├── shield.mp3
    │   └── extrahp.mp3
    ├── menu_music/
    │   ├── bgmusic.mp3
    │   └── stagemusic.mp3
    └── levels/
        ├── the_awakening.mp3
        ├── pulse_overdrive.mp3
        └── chaos-protocol.mp3
```

---

## ⚙️ Requirements

- Python 3.8+
- A webcam

### Dependencies

```
pygame
opencv-python
mediapipe
numpy
```

Install all at once:

```bash
pip install pygame opencv-python mediapipe numpy
```

---

## 🚀 Getting Started

```bash
# Clone the repository
git clone https://github.com/edrean-supremo/neon-dodge.git
cd neon-dodge

# Install dependencies
pip install pygame opencv-python mediapipe numpy

# Run the game
python dodge.py
```

> The game launches in **fullscreen** automatically. Press `ESC` at any time to quit.

---

## 🖐️ Controls

| Action | Input |
|---|---|
| Move player | Point your index finger at the webcam |
| Continue to next level | Press `C` on the stage-cleared screen |
| Quit | Press `Q` or `ESC` |

**Gesture controls** (on the stage-cleared screen):
- **All 4 fingers up** → Continue
- **Index + middle up only** → Quit

---

## 💡 Tips

- You don't need your whole hand visible — the tracker works even when the hand is partially off-screen
- Stay near the center during Black Hole events in Level 3 — the kill radius is large
- The Shield power-up absorbs hits but you still hear a sound — it's working
- Near-miss sparks on lasers are your reward for threading the needle — aim for them

---

## 🛠️ Built With

- **[Pygame](https://www.pygame.org/)** — Game loop, rendering, audio
- **[OpenCV](https://opencv.org/)** — Webcam capture
- **[MediaPipe](https://mediapipe.dev/)** — Real-time hand landmark detection
- **[NumPy](https://numpy.org/)** — Coordinate interpolation and frame processing

---

## 👤 Author

**Edrean Supremo**
Computer Engineering Student | Full-Stack Developer | Embedded Systems Engineer

- Portfolio: *(your portfolio URL)*
- GitHub: [@edrean-supremo](https://github.com/edrean-supremo)
- Email: edrean.supremo@gmail.com

---

## 📄 License

This project is open source and available under the [MIT License](LICENSE).

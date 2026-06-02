import pygame
import random
import math
from pygame.math import Vector2
from levels import LEVELS
from tracking import HandTracker
from powerups import (
    PowerUpManager,
    apply_powerup_state_to_player,
    update_powerup_timers,
    draw_powerup_effects,
    draw_powerup_hud,
    draw_slowmo_tint,
    get_slow_factor,
    player_hit_with_powerups,
    update_draw_ripples,
)

# =====================
# SETTINGS & AUDIO
# =====================
pygame.init()
# Init mixer with explicit settings: 44100 Hz, 16-bit signed, stereo, small buffer
# pre_init must be called BEFORE pygame.init() — we reinit here to be safe
pygame.mixer.quit()
pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
pygame.mixer.set_num_channels(16)   # enough channels for overlapping SFX
pygame.mixer.set_reserved(1)         # reserve ch 0 so music never clobbers SFX

# Logical game resolution — all game logic runs at this size
WIDTH, HEIGHT = 900, 600
virtual_screen = pygame.Surface((WIDTH, HEIGHT))

# Detect monitor resolution and go fullscreen
_tmp_screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
SCREEN_W, SCREEN_H = _tmp_screen.get_size()
screen = _tmp_screen
pygame.display.set_caption("Neon Dodge: Level Overdrive")

# Letterbox scale: largest 900x600 box that fits the monitor
_scale  = min(SCREEN_W / WIDTH, SCREEN_H / HEIGHT)
RENDER_W = int(WIDTH  * _scale)
RENDER_H = int(HEIGHT * _scale)
RENDER_X = (SCREEN_W - RENDER_W) // 2
RENDER_Y = (SCREEN_H - RENDER_H) // 2
clock = pygame.time.Clock()

try:
    icon = pygame.image.load(_asset("img/icon.png"))
    pygame.display.set_icon(icon)
except:
    pass

SURVIVAL_TIME = 3600  # 60 seconds at 60 FPS

# =====================
# COLORS
# =====================
BG = (5, 5, 15)
WHITE = (255, 255, 255)
CYAN = (0, 255, 255)
RED = (255, 50, 50)
NEON_LIME = (50, 255, 50)
NEON_PINK = (255, 50, 200)
NEON_ORANGE = (255, 140, 0)

# =====================
# SCREEN EFFECTS STATE
# =====================
shake_amount = 0
zoom_scale = 1.0
flash_timer = 0
FLASH_DURATION = 30

# Level 3 intensity flash
_l3_flash_timer  = 0
_l3_flash_cd     = 0
_L3_FLASH_MIN_CD = 80
_L3_FLASH_MAX_CD = 200

# =====================
# BLACK HOLE STATE
# =====================
# BlackHole constants (mega version — see BlackHole class)
BLACK_HOLE_GROW_TIME  = 180
BLACK_HOLE_MAX_RADIUS = 220
BLACK_HOLE_KILL_RADIUS = 200
BLACK_HOLE_DURATION   = 300
black_hole = None
black_hole_triggered = False
black_hole_active = False

# =====================
# AUDIO
# =====================
# ── Robust asset-path resolution ──────────────────────────────────────────────
import os as _os
BASE_DIR   = _os.path.dirname(_os.path.abspath(__file__))
ASSETS_DIR = _os.path.join(BASE_DIR, "assets")

def _asset(rel_path):
    """Return absolute path to an asset file, regardless of working directory.
    Accepts subdirectory paths like 'sfx/hit.mp3' or 'levels/the_awakening.mp3'.
    """
    return _os.path.join(ASSETS_DIR, rel_path)

def _load_sound(rel_path, volume=1.0):
    """
    Load a sound effect using absolute asset paths so the game works no matter
    where it is launched from (VSCode, terminal, double-click, etc.).
    Accepts subdirectory paths like 'sfx/hit.mp3'.
    Tries the given path first, then a .wav sibling as fallback.
    """
    abs_path = _asset(rel_path)

    candidates = [abs_path]
    wav_path = _os.path.splitext(abs_path)[0] + ".wav"
    if wav_path != abs_path:
        candidates.append(wav_path)

    for p in candidates:
        if not _os.path.exists(p):
            print(f"[audio] MISSING file: {p}")
            continue
        try:
            s = pygame.mixer.Sound(p)
            s.set_volume(volume)
            print(f"[audio] loaded OK: {p}  (vol={volume})")
            return s
        except Exception as e:
            print(f"[audio] FAILED to decode {p}: {e}")
    return None

print("[audio] mixer info:", pygame.mixer.get_init())

# big_orb and explosion_orb are loaded at 1.0; the dedicated channels further
# boost them to the pygame ceiling (see _play / _BOOSTED_CHANNELS below).
hit_sound           = _load_sound("sfx/hit.mp3",            0.6)
death_sound         = _load_sound("sfx/death.mp3",          1.0)
laser_sound         = _load_sound("sfx/laser.mp3",          1.0)
big_orb_sound       = _load_sound("sfx/sunorb.mp3",         1.0)
explosion_orb_sound = _load_sound("sfx/expolosionorb.mp3",  1.0)
slowmo_sound        = _load_sound("sfx/slowmo.mp3",         1.0)
shield_sound        = _load_sound("sfx/shield.mp3",         1.0)
extra_sound         = _load_sound("sfx/extrahp.mp3",        1.0)

# ── Stage-clear music (played during transition screens) ──────────────────────
_STAGE_MUSIC_FILE   = _asset("menu_music/stagemusic.mp3")
_STAGE_MUSIC_VOLUME = 0.75
_stage_music_playing = False

def _start_stage_music():
    """Load and loop stage_music.mp3 — called at the start of each stage-clear screen."""
    global _stage_music_playing, _bg_music_playing, _bg_music_fading
    try:
        _bg_music_playing = False
        _bg_music_fading  = False
        pygame.mixer.music.load(_STAGE_MUSIC_FILE)
        pygame.mixer.music.set_volume(_STAGE_MUSIC_VOLUME)
        pygame.mixer.music.play(-1)
        _stage_music_playing = True
        print(f"[audio] stage music playing: {_STAGE_MUSIC_FILE}")
    except Exception as e:
        print(f"[audio] stage music FAILED: {e}")

def _fade_out_stage_music(duration_ms=800):
    """Smoothly fade out stage_music.mp3 over duration_ms milliseconds."""
    global _stage_music_playing
    if _stage_music_playing:
        pygame.mixer.music.fadeout(duration_ms)
        _stage_music_playing = False

# Dedicate channels so SFX never steal the music channel
_SFX_CHANNEL = {
    "hit":      pygame.mixer.Channel(1),
    "death":    pygame.mixer.Channel(2),
    "laser":    pygame.mixer.Channel(3),
    "big_orb":  pygame.mixer.Channel(4),
    "explode":  pygame.mixer.Channel(5),
    "powerup":  pygame.mixer.Channel(6),
}

# Channels that receive maximum volume boost (big orb + explosions at 250% intent)
_BOOSTED_CHANNELS = {"big_orb", "explode"}

def _play(sound, channel_key=None):
    """
    Play a Sound on a dedicated channel (prevents cutoff from overlapping calls).
    big_orb and explode channels play at max volume (250% intent; pygame clamps to 1.0).
    Falls back to sound.play() if no channel key given.
    """
    if not sound:
        return
    if channel_key and channel_key in _SFX_CHANNEL:
        ch = _SFX_CHANNEL[channel_key]
        if channel_key in _BOOSTED_CHANNELS:
            # Maximise both the Sound object and the channel — pygame's hard ceiling is 1.0
            sound.set_volume(1.0)
            ch.set_volume(1.0)
        else:
            ch.set_volume(1.0)
        ch.play(sound)
    else:
        sound.play()

# =====================
# BACKGROUND MUSIC STATE
# =====================
_bg_music_playing = False
_bg_music_fading  = False
_BG_MUSIC_FILE    = _asset("menu_music/bgmusic.mp3")
_BG_MUSIC_VOLUME  = 0.70

def _start_bg_music():
    """Load and loop bgmusic.mp3 — called once at game start."""
    global _bg_music_playing
    try:
        pygame.mixer.music.load(_BG_MUSIC_FILE)
        pygame.mixer.music.set_volume(_BG_MUSIC_VOLUME)
        pygame.mixer.music.play(-1)
        _bg_music_playing = True
        print(f"[audio] bg music playing: {_BG_MUSIC_FILE}")
    except Exception as e:
        print(f"[audio] bg music FAILED: {e}")

def _fade_out_bg_music(duration_ms=800):
    """Smoothly fade out bgmusic.mp3 over duration_ms milliseconds."""
    global _bg_music_fading
    if _bg_music_playing and not _bg_music_fading:
        _bg_music_fading = True
        pygame.mixer.music.fadeout(duration_ms)


# =====================
# BACKGROUND GRID
# =====================
grid_offset = 0.0

# Per-level background base colors: (fill_color, grid_color_base)
_LEVEL_BG = [
    ((5,  5,  20),  (0,  40,  80)),    # Level 1 — deep blue / calm neon
    ((12, 5,  22),  (60,  0, 100)),    # Level 2 — purple
    ((20, 5,   5),  (80,  0,  20)),    # Level 3 — dark red / chaos
]

def get_level_bg(level_index):
    idx = min(level_index, len(_LEVEL_BG) - 1)
    return _LEVEL_BG[idx]

def draw_background_grid(surf, pulse_intensity=0.0, level_index=0):
    """Animated scrolling neon grid — color shifts per level, beat-synced pulse."""
    global grid_offset
    grid_offset = (grid_offset + 0.4) % 40

    _, grid_base = get_level_bg(level_index)
    br, bg_, bb = grid_base

    # Simulate beat at ~120bpm via sin — no real beat detection needed
    beat_t = pygame.time.get_ticks() / 1000.0
    beat   = 0.5 + 0.5 * abs(math.sin(beat_t * math.pi * 2.0))
    boost  = beat * 0.4 + pulse_intensity * 0.6

    r = min(255, int(br + boost * 80))
    g = min(255, int(bg_ + boost * 60))
    b = min(255, int(bb + boost * 100))
    grid_col = (r, g, b)

    for x in range(-40, WIDTH + 40, 40):
        gx = int(x + grid_offset) % (WIDTH + 40) - 40
        pygame.draw.line(surf, grid_col, (gx, 0), (gx, HEIGHT), 1)
    for y in range(0, HEIGHT + 40, 40):
        gy = int(y + grid_offset) % (HEIGHT + 40)
        pygame.draw.line(surf, grid_col, (0, gy), (WIDTH, gy), 1)


def _make_vignette(intensity):
    v = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    alpha = int(intensity * 160)
    for i in range(60):
        fade = int(alpha * (i / 60))
        pygame.draw.rect(v, (0, 0, 0, fade), (i, i, WIDTH - i * 2, HEIGHT - i * 2), 1)
    return v

_VIGNETTE_NORMAL  = _make_vignette(0.3)
_VIGNETTE_INTENSE = _make_vignette(0.8)

def draw_vignette(surf, intense=False):
    """Blit a pre-baked vignette — zero per-frame allocation."""
    surf.blit(_VIGNETTE_INTENSE if intense else _VIGNETTE_NORMAL, (0, 0))


# =====================
# PROGRESS BAR
# =====================
def draw_progress_bar(surf, time_left):
    bar_width = 500
    bar_height = 18
    x = WIDTH // 2 - bar_width // 2
    y = 25

    progress = 1 - (time_left / SURVIVAL_TIME)
    progress_width = int(bar_width * progress)

    pygame.draw.rect(surf, (40, 40, 60), (x, y, bar_width, bar_height), border_radius=10)
    pygame.draw.rect(surf, CYAN, (x, y, progress_width, bar_height), border_radius=10)
    pygame.draw.rect(surf, WHITE, (x, y, bar_width, bar_height), 2, border_radius=10)

    orb_x = x + progress_width
    orb_y = y + bar_height // 2

    for i in range(6):
        alpha = 150 - i * 25
        tail_surface = pygame.Surface((20, 20), pygame.SRCALPHA)
        pygame.draw.circle(tail_surface, (0, 255, 255, alpha), (10, 10), max(2, 6 - i))
        surf.blit(tail_surface, (orb_x - 10 - i * 6, orb_y - 10))

    pygame.draw.circle(surf, WHITE, (orb_x, orb_y), 8)


def draw_survive_timer(surf, time_left):
    """Show seconds survived in top-left."""
    seconds_survived = int((SURVIVAL_TIME - time_left) / 60)
    f = pygame.font.SysFont("Courier New", 18, bold=True)
    t = f.render(f"SURVIVED: {seconds_survived}s", True, (0, 200, 200))
    surf.blit(t, (12, 8))


def draw_hp(surf, hp):
    """Draw 3 heart/orb HP pips in the top-right corner."""
    f = pygame.font.SysFont("Courier New", 16, bold=True)
    label = f.render("HP", True, (180, 180, 180))
    surf.blit(label, (WIDTH - 110, 10))
    for i in range(3):
        cx = WIDTH - 80 + i * 26
        cy = 20
        if i < hp:
            # filled pip — bright cyan circle
            gs = pygame.Surface((20, 20), pygame.SRCALPHA)
            pygame.draw.circle(gs, (0, 255, 255, 80), (10, 10), 10)
            surf.blit(gs, (cx - 10, cy - 10))
            pygame.draw.circle(surf, CYAN, (cx, cy), 8)
        else:
            # empty pip — dim outline
            pygame.draw.circle(surf, (60, 60, 80), (cx, cy), 8, 2)


# =====================
# SCREEN FADE
# =====================
def screen_fade(direction="out"):
    fade_surface = pygame.Surface((SCREEN_W, SCREEN_H))
    fade_surface.fill((0, 0, 0))
    for alpha in range(0, 256, 4):
        actual_alpha = alpha if direction == "out" else 255 - alpha
        fade_surface.set_alpha(actual_alpha)
        screen.fill((0, 0, 0))
        screen.blit(pygame.transform.smoothscale(virtual_screen, (RENDER_W, RENDER_H)), (RENDER_X, RENDER_Y))
        screen.blit(fade_surface, (0, 0))
        if direction == "out":
            pygame.mixer.music.set_volume(max(0.0, 1.0 - (alpha / 255.0)))
        pygame.display.flip()
        clock.tick(60)


# =====================
# LEVEL INTRO ANIMATION
# =====================
_INTRO_COLORS = [
    (0,   200, 255),   # Level 1 — cyan
    (180,  80, 255),   # Level 2 — purple
    (255,  60,  60),   # Level 3 — red
]

def show_level_intro(level_index):
    """2-second cinematic title card before each level.
    Fades in, holds with a scale/glow pulse, then fades out.
    The game background (virtual_screen) is dimmed underneath — state untouched.
    """
    data      = LEVELS[level_index]
    title     = data["name"]
    sub_label = f"LEVEL  {data['id']}"
    accent    = _INTRO_COLORS[min(level_index, len(_INTRO_COLORS) - 1)]

    f_title = pygame.font.SysFont("Courier New", 52, bold=True)
    f_sub   = pygame.font.SysFont("Courier New", 22, bold=True)

    DURATION    = 120   # 2 s @ 60 fps
    FADE_FRAMES = 30

    t_title = f_title.render(title, True, accent)
    t_sub   = f_sub.render(sub_label, True, (180, 180, 180))

    # Capture current game frame as dimmed background
    bg_snap = pygame.transform.smoothscale(virtual_screen, (SCREEN_W, SCREEN_H))
    dim = pygame.Surface((SCREEN_W, SCREEN_H))
    dim.fill((0, 0, 0))
    dim.set_alpha(140)

    r_acc, g_acc, b_acc = accent

    for frame in range(DURATION):
        # Alpha envelope: fade-in / hold / fade-out
        if frame < FADE_FRAMES:
            alpha = int(255 * frame / FADE_FRAMES)
        elif frame > DURATION - FADE_FRAMES:
            alpha = int(255 * (DURATION - frame) / FADE_FRAMES)
        else:
            alpha = 255

        # Subtle scale pulse during hold
        hold_t = (frame - FADE_FRAMES) / max(1, DURATION - FADE_FRAMES * 2)
        scale  = 1.0 + 0.022 * abs(math.sin(hold_t * math.pi))
        glow_alpha = int(alpha * 0.38 * (0.7 + 0.3 * abs(math.sin(frame * 0.18))))

        screen.blit(bg_snap, (0, 0))
        screen.blit(dim, (0, 0))

        # Separator line
        line_surf = pygame.Surface((400, 2), pygame.SRCALPHA)
        line_surf.fill((r_acc, g_acc, b_acc, alpha))
        screen.blit(line_surf, (SCREEN_W // 2 - 200, SCREEN_H // 2 - 16))

        # Title scaled + glow layer
        tw, th = t_title.get_size()
        scaled_title = pygame.transform.smoothscale(t_title, (int(tw * scale), int(th * scale)))
        glow_surf = pygame.transform.smoothscale(scaled_title, (int(tw * scale * 1.07), int(th * scale * 1.07)))
        glow_surf.set_alpha(glow_alpha)
        screen.blit(glow_surf,
                    (SCREEN_W // 2 - glow_surf.get_width() // 2,
                     SCREEN_H // 2 - glow_surf.get_height() // 2 - 10))
        scaled_title.set_alpha(alpha)
        screen.blit(scaled_title,
                    (SCREEN_W // 2 - scaled_title.get_width() // 2,
                     SCREEN_H // 2 - scaled_title.get_height() // 2 - 10))

        # Sub-label
        t_sub.set_alpha(alpha)
        screen.blit(t_sub,
                    (SCREEN_W // 2 - t_sub.get_width() // 2,
                     SCREEN_H // 2 + scaled_title.get_height() // 2 + 8))

        pygame.display.flip()
        clock.tick(60)

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                tracker.release()
                pygame.quit()
                exit()
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                tracker.release()
                pygame.quit()
                exit()


# =====================
# CINEMATIC STAGE-CLEARED TRANSITION
# =====================

# Per-level destruction messages shown after stage is cleared
_DESTRUCTION_MSGS = [
    # After Stage 1
    {
        "cleared":  "STAGE 1: THE AWAKENING  CLEARED",
        "warning":  "⚠  SYSTEM INSTABILITY DETECTED  ⚠",
        "lines": [
            "Enemy patterns evolving",
            "Speed parameters increased",
            "Stay alert...",
        ],
    },
    # After Stage 2
    {
        "cleared":  "STAGE 2: PULSE OVERDRIVE  CLEARED",
        "warning":  "⚠  CORE SYSTEM FAILURE  ⚠",
        "lines": [
            "Hazard density critical",
            "Reaction window collapsing",
            "Brace for impact...",
        ],
    },
]

# Timing constants (frames @ 60 fps)
_FPS            = 60
_T_CLEARED      = int(1.2 * _FPS)   # 72  — "STAGE X CLEARED" hold
_T_WARN         = int(1.5 * _FPS)   # 90  — warning + body lines hold
_T_PAUSE        = int(0.5 * _FPS)   # 30  — brief pause before countdown
_T_DIGIT        = int(0.6 * _FPS)   # 36  — each countdown digit
_FADE_F         = 20                 # fade-in/out frames for most elements
_FADE_FAST      = 12                 # faster fade for countdown digits


def _pump():
    """Drain the event queue; quit cleanly on QUIT or ESC."""
    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            tracker.release()
            pygame.quit()
            exit()
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            tracker.release()
            pygame.quit()
            exit()


def _draw_scanlines(surf, alpha=18):
    """Subtle CRT scanline overlay — cheap cinematic texture."""
    sl = pygame.Surface((SCREEN_W, 1), pygame.SRCALPHA)
    sl.fill((0, 0, 0, alpha))
    for y in range(0, SCREEN_H, 3):
        surf.blit(sl, (0, y))


def _glitch_surface(surf, intensity=4):
    """
    Cheap horizontal-slice glitch: shifts a random band of pixels sideways.
    Called once per frame during glitch moments; mutates surf in-place.
    """
    if intensity <= 0:
        return
    for _ in range(random.randint(1, 3)):
        gy = random.randint(0, SCREEN_H - 8)
        gh = random.randint(2, 8)
        shift = random.randint(-intensity, intensity)
        band = surf.subsurface((0, gy, SCREEN_W, gh)).copy()
        surf.blit(band, (shift, gy))


def _render_text_centered(surf, text, font, color, cy, alpha=255, glow=False, glow_col=None):
    """Render text centred on cy with optional glow halo. Returns rendered surface."""
    base = font.render(text, True, color)
    base.set_alpha(alpha)
    if glow and glow_col and alpha > 20:
        g = pygame.transform.smoothscale(
            base,
            (int(base.get_width() * 1.06), int(base.get_height() * 1.06))
        )
        g.set_alpha(int(alpha * 0.35))
        r2, g2, b2 = glow_col
        gm = pygame.Surface(g.get_size(), pygame.SRCALPHA)
        gm.fill((r2, g2, b2, int(alpha * 0.35)))
        g.blit(gm, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surf.blit(g, (SCREEN_W // 2 - g.get_width() // 2, cy - g.get_height() // 2))
    surf.blit(base, (SCREEN_W // 2 - base.get_width() // 2, cy - base.get_height() // 2))
    return base


def show_stage_cleared_transition(cleared_level_index):
    """
    Cinematic destruction-style transition shown when a stage is cleared.
    - cleared_level_index: 0-based index of the level just finished.
    - For the final stage (index 2) this function does nothing — credits
      are shown by show_credits() in the main loop instead.

    Music flow:
      1. Gameplay music is faded out by the caller before this function runs.
      2. We start stage_music.mp3 at the top of Phase 1.
      3. After the player presses C and the countdown finishes, we fade out
         stage_music.mp3 before returning so the next level's music starts clean.
    """
    if cleared_level_index >= len(_DESTRUCTION_MSGS):
        return   # final stage: skip, let main loop call show_credits()

    msg   = _DESTRUCTION_MSGS[cleared_level_index]
    # Accent colours per stage
    accents = [(0, 220, 255), (180, 80, 255), (255, 60, 60)]
    accent  = accents[min(cleared_level_index, 2)]
    ra, ga, ba = accent
    warn_col = (255, 60, 60)

    # Pre-bake fonts
    f_cleared = pygame.font.SysFont("Courier New", 46, bold=True)
    f_warn    = pygame.font.SysFont("Courier New", 28, bold=True)
    f_body    = pygame.font.SysFont("Courier New", 22, bold=False)
    f_prompt  = pygame.font.SysFont("Courier New", 26, bold=True)
    f_count   = pygame.font.SysFont("Courier New", 140, bold=True)

    # ── Helper: draw the persistent black bg + scanlines ──────────────────
    def _bg():
        screen.fill((0, 0, 0))
        _draw_scanlines(screen)

    # ── Helper: draw the full destruction text block (cleared + warn + lines) ──
    def _draw_full_text(frame_for_pulse=0, body_alpha=255):
        pulse_a = int(210 + 45 * abs(math.sin(frame_for_pulse * 0.08)))
        _render_text_centered(screen, msg["cleared"], f_cleared, accent,
                              CLEARED_Y, pulse_a, glow=True, glow_col=accent)
        ls = pygame.Surface((min(SCREEN_W - 80, 700), 2), pygame.SRCALPHA)
        ls.fill((ra, ga, ba, pulse_a))
        screen.blit(ls, (SCREEN_W // 2 - ls.get_width() // 2, CLEARED_Y + 40))
        w_flicker = warn_col if (frame_for_pulse // 4) % 2 == 0 else (255, 120, 120)
        _render_text_centered(screen, msg["warning"], f_warn, w_flicker,
                              WARN_Y, body_alpha)
        for i, line in enumerate(msg["lines"]):
            _render_text_centered(screen, line, f_body, (200, 200, 200),
                                  BODY_START_Y + i * LINE_GAP, body_alpha)

    CLEARED_Y    = SCREEN_H // 2 - 100
    WARN_Y       = CLEARED_Y + 80
    BODY_START_Y = WARN_Y + 54
    LINE_GAP     = 36
    PROMPT_Y     = BODY_START_Y + len(msg["lines"]) * LINE_GAP + 50

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 1 — "STAGE X CLEARED" with glitch + fade-in
    #           🎵 Start stage_music.mp3 at the very beginning
    # ══════════════════════════════════════════════════════════════════════
    _start_stage_music()

    for frame in range(_T_CLEARED + _FADE_F):
        _pump()
        _bg()

        if frame < _FADE_F:
            alpha = int(255 * frame / _FADE_F)
        else:
            alpha = 255

        glitch_intensity = max(0, 6 - frame // 3) if frame < 18 else 0

        _render_text_centered(screen, msg["cleared"], f_cleared, accent,
                              CLEARED_Y, alpha, glow=True, glow_col=accent)

        if alpha > 60:
            line_a = min(255, alpha - 60)
            ls = pygame.Surface((min(SCREEN_W - 80, 700), 2), pygame.SRCALPHA)
            ls.fill((ra, ga, ba, line_a))
            screen.blit(ls, (SCREEN_W // 2 - ls.get_width() // 2, CLEARED_Y + 40))

        if glitch_intensity:
            _glitch_surface(screen, glitch_intensity)

        pygame.display.flip()
        clock.tick(_FPS)

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 2 — Warning line + body lines cascade in
    # ══════════════════════════════════════════════════════════════════════
    frames_per_line = max(10, (_T_WARN - _FADE_F) // (len(msg["lines"]) + 1))

    for frame in range(_T_WARN):
        _pump()
        _bg()

        pulse_a = int(210 + 45 * abs(math.sin(frame * 0.08)))
        _render_text_centered(screen, msg["cleared"], f_cleared, accent,
                              CLEARED_Y, pulse_a, glow=True, glow_col=accent)
        ls = pygame.Surface((min(SCREEN_W - 80, 700), 2), pygame.SRCALPHA)
        ls.fill((ra, ga, ba, pulse_a))
        screen.blit(ls, (SCREEN_W // 2 - ls.get_width() // 2, CLEARED_Y + 40))

        warn_alpha = min(255, int(255 * frame / _FADE_F)) if frame < _FADE_F else 255
        w_flicker = warn_col if (frame // 4) % 2 == 0 else (255, 120, 120)
        _render_text_centered(screen, msg["warning"], f_warn, w_flicker,
                              WARN_Y, warn_alpha)

        for i, line in enumerate(msg["lines"]):
            appear_frame = _FADE_F + frames_per_line * (i + 1)
            if frame >= appear_frame:
                line_frame = frame - appear_frame
                line_alpha = min(255, int(255 * line_frame / _FADE_F))
                _render_text_centered(screen, line, f_body, (200, 200, 200),
                                      BODY_START_Y + i * LINE_GAP, line_alpha)

        pygame.display.flip()
        clock.tick(_FPS)

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 3 — Wait for player input: C to continue / Q to quit
    #           stage_music.mp3 keeps playing here
    # ══════════════════════════════════════════════════════════════════════
    waiting     = True
    idle_frame  = 0
    c_pressed   = False

    while waiting:
        idle_frame += 1
        _bg()
        _draw_full_text(frame_for_pulse=idle_frame, body_alpha=255)

        # Blinking prompt lines
        prompt_alpha = int(180 + 75 * abs(math.sin(idle_frame * 0.06)))
        _render_text_centered(screen, "PRESS  C  TO  CONTINUE", f_prompt,
                              (0, 220, 255), PROMPT_Y, prompt_alpha)
        _render_text_centered(screen, "PRESS  Q  TO  QUIT", f_prompt,
                              (150, 150, 150), PROMPT_Y + 38, prompt_alpha)

        pygame.display.flip()
        clock.tick(_FPS)

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                tracker.release()
                pygame.quit()
                exit()
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_q or e.key == pygame.K_ESCAPE:
                    tracker.release()
                    pygame.quit()
                    exit()
                if e.key == pygame.K_c:
                    c_pressed = True
                    waiting   = False

    # ── C-button press animation: scale up + glow (~0.4 s = 24 frames) ───
    ANIM_FRAMES = 24
    for frame in range(ANIM_FRAMES):
        _bg()
        _draw_full_text(frame_for_pulse=idle_frame + frame, body_alpha=255)

        # Prompt dims away
        fade_out_a = int(255 * (1.0 - frame / ANIM_FRAMES))
        _render_text_centered(screen, "PRESS  Q  TO  QUIT", f_prompt,
                              (150, 150, 150), PROMPT_Y + 38, fade_out_a)

        # "C" letter scales up + glows
        t_anim = frame / ANIM_FRAMES
        c_scale = 1.0 + 0.9 * t_anim          # 1.0 → 1.9×
        glow_a  = int(220 * (1.0 - t_anim))    # glow fades to 0

        f_c_big  = pygame.font.SysFont("Courier New", int(26 * c_scale), bold=True)
        c_surf   = f_c_big.render("C", True, (0, 255, 255))
        c_surf.set_alpha(255)

        # Glow halo
        if glow_a > 10:
            glow_s = pygame.transform.smoothscale(
                c_surf,
                (int(c_surf.get_width() * 1.4), int(c_surf.get_height() * 1.4))
            )
            glow_s.set_alpha(glow_a)
            screen.blit(glow_s, (SCREEN_W // 2 - glow_s.get_width() // 2,
                                 PROMPT_Y - c_surf.get_height() // 2 - glow_s.get_height() // 2 + c_surf.get_height() // 2))

        # Render the scaled C centred
        full_prompt = f_prompt.render("PRESS  C  TO  CONTINUE", True, (0, 220, 255))
        full_prompt.set_alpha(max(0, fade_out_a))
        # Draw everything except the C, then overdraw C scaled
        screen.blit(full_prompt, (SCREEN_W // 2 - full_prompt.get_width() // 2,
                                  PROMPT_Y - full_prompt.get_height() // 2))
        screen.blit(c_surf, (SCREEN_W // 2 - c_surf.get_width() // 2,
                             PROMPT_Y - c_surf.get_height() // 2))

        pygame.display.flip()
        clock.tick(_FPS)

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 4 — Countdown: 3  2  1  (centred, scale-pulse animation)
    #           stage_music.mp3 still playing
    # ══════════════════════════════════════════════════════════════════════
    COUNT_Y = SCREEN_H // 2

    for digit in (3, 2, 1):
        digit_str = str(digit)
        d_colors = {3: (0, 220, 255), 2: (255, 160, 20), 1: (255, 40, 40)}
        d_col = d_colors[digit]
        dr, dg, db = d_col

        for frame in range(_T_DIGIT):
            _pump()
            _bg()

            t = frame / _T_DIGIT

            scale = 1.0 + 0.4 * max(0.0, 1.0 - t * 2.5)
            if frame < _FADE_FAST:
                alpha = int(255 * frame / _FADE_FAST)
            elif frame > _T_DIGIT - _FADE_FAST:
                alpha = int(255 * ((_T_DIGIT - frame) / _FADE_FAST))
            else:
                alpha = 255

            base = f_count.render(digit_str, True, d_col)
            if scale != 1.0:
                sw2 = max(1, int(base.get_width()  * scale))
                sh2 = max(1, int(base.get_height() * scale))
                base = pygame.transform.smoothscale(base, (sw2, sh2))
            base.set_alpha(alpha)

            if alpha > 30:
                glow = pygame.transform.smoothscale(
                    base,
                    (int(base.get_width() * 1.08), int(base.get_height() * 1.08))
                )
                glow.set_alpha(int(alpha * 0.28))
                screen.blit(glow, (SCREEN_W // 2 - glow.get_width() // 2,
                                   COUNT_Y - glow.get_height() // 2))

            screen.blit(base, (SCREEN_W // 2 - base.get_width() // 2,
                               COUNT_Y - base.get_height() // 2))

            if _FADE_FAST <= frame <= _T_DIGIT - _FADE_FAST:
                ring_r = int(60 + 20 * abs(math.sin(frame * 0.25)))
                ring_a = int(80 * (1.0 - t))
                rs = pygame.Surface((ring_r * 2, ring_r * 2), pygame.SRCALPHA)
                pygame.draw.circle(rs, (dr, dg, db, ring_a), (ring_r, ring_r), ring_r, 3)
                screen.blit(rs, (SCREEN_W // 2 - ring_r, COUNT_Y - ring_r))

            pygame.display.flip()
            clock.tick(_FPS)

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 5 — Fade out stage_music, white flash, fade to black
    # ══════════════════════════════════════════════════════════════════════
    _fade_out_stage_music(duration_ms=500)

    for frame in range(10):
        _pump()
        flash_a = int(255 * (1.0 - frame / 10))
        screen.fill((0, 0, 0))
        fl = pygame.Surface((SCREEN_W, SCREEN_H))
        fl.fill((255, 255, 255))
        fl.set_alpha(flash_a)
        screen.blit(fl, (0, 0))
        pygame.display.flip()
        clock.tick(_FPS)

    # Wait for music fade to complete before we hand off to the next level
    pygame.time.wait(550)

    screen.fill((0, 0, 0))
    pygame.display.flip()


# =====================
# WARNING SCREEN
# =====================
def show_warning():
    global _bg_music_playing, _bg_music_fading
    # Start background music as soon as the warning screen appears
    _start_bg_music()

    warning_text = [
        "WARNING:",
        "",
        "THIS GAME MAY POTENTIALLY TRIGGER",
        "SEIZURES FOR PEOPLE WITH PHOTOSENSITIVE EPILEPSY.",
        "",
        "VIEWER DISCRETION IS ADVISED.",
        "",
        "PRESS ANY KEY TO CONTINUE"
    ]

    waiting = True
    f = pygame.font.SysFont("Courier New", 24, bold=True)

    while waiting:
        screen.fill((0, 0, 0))
        for i, line in enumerate(warning_text):
            color = (200, 200, 200)
            if i == len(warning_text) - 1:
                alpha = int(abs(math.sin(pygame.time.get_ticks() * 0.005)) * 255)
                color = (alpha, alpha, alpha)
            t = f.render(line, True, color)
            screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, SCREEN_H // 2 - 140 + i * 40))
        pygame.display.flip()
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                tracker.release()
                pygame.quit()
                exit()
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    tracker.release()
                    pygame.quit()
                    exit()
                # Fade out bg music smoothly when player presses any key
                _fade_out_bg_music(duration_ms=900)
                waiting = False
        clock.tick(60)

    # Clean snapshot-based fade-out — no text ghosting
    pygame.event.clear()
    snapshot = screen.copy()
    fade_surf = pygame.Surface((SCREEN_W, SCREEN_H))
    fade_surf.fill((0, 0, 0))
    for alpha in range(0, 256, 5):
        screen.blit(snapshot, (0, 0))   # always redraw from clean snapshot
        fade_surf.set_alpha(alpha)
        screen.blit(fade_surf, (0, 0))
        pygame.display.flip()
        clock.tick(60)
    # Full black reset before any further rendering
    screen.fill((0, 0, 0))
    pygame.display.flip()


# =====================
# MUSIC
# =====================
def play_level_music(level_idx):
    """Load and play level music. Waits for bg music fade if still in progress."""
    global _bg_music_playing, _bg_music_fading
    try:
        # Give bg music fadeout time to complete (max ~1s / 60 frames)
        if _bg_music_fading:
            fade_wait = 0
            while pygame.mixer.music.get_busy() and fade_wait < 60:
                clock.tick(60)
                fade_wait += 1
        _bg_music_playing = False
        _bg_music_fading  = False

        # music field is now a relative subpath like "levels/the_awakening.mp3"
        _raw_music = LEVELS[level_idx].get("music", "levels/the_awakening.mp3")
        music_file = _asset(_raw_music)
        pygame.mixer.music.stop()
        pygame.mixer.music.load(music_file)
        pygame.mixer.music.set_volume(0.65)
        pygame.mixer.music.play(-1)
    except Exception as e:
        print(f"Music load error: {e}")


# =====================
# CLASSES
# =====================

class HitParticle:
    """Burst particle spawned when the player is hit."""
    def __init__(self, pos):
        self.pos = pos.copy()
        angle = random.uniform(0, 360)
        speed = random.uniform(3, 8)
        self.vel = Vector2(speed, 0).rotate(angle)
        self.life = random.randint(20, 35)
        self.max_life = self.life
        colors = [(255, 50, 50), (255, 140, 0), (255, 255, 255), (0, 255, 255)]
        self.color = random.choice(colors)

    def update(self):
        self.pos += self.vel
        self.vel *= 0.92
        self.life -= 1

    def draw(self, surf):
        if self.life <= 0:
            return
        alpha = int((self.life / self.max_life) * 220)
        r, g, b = self.color
        _tmp = pygame.Surface((8, 8), pygame.SRCALPHA)
        pygame.draw.circle(_tmp, (min(255, r), min(255, g), min(255, b), alpha), (4, 4), 4)
        surf.blit(_tmp, (int(self.pos.x) - 4, int(self.pos.y) - 4))

    @property
    def dead(self):
        return self.life <= 0


# =====================
# VISUAL EFFECTS STATE
# =====================
chroma_timer        = 0      # chromatic aberration frames remaining
CHROMA_FRAMES       = 14
near_miss_particles = []     # near-miss spark pool (global)
_near_miss_cooldown = 0      # global cooldown to avoid burst spam


class NearMissParticle:
    """Tiny cyan/white spark triggered when a laser nearly misses the player."""
    __slots__ = ("pos", "vel", "life", "max_life", "color")

    def __init__(self, pos):
        self.pos = Vector2(pos)
        angle = random.uniform(0, 360)
        speed = random.uniform(1.5, 4.5)
        self.vel = Vector2(speed, 0).rotate(angle)
        self.life = random.randint(12, 22)
        self.max_life = self.life
        self.color = random.choice([(0, 255, 255), (200, 255, 255), (255, 255, 255)])

    def update(self):
        self.pos += self.vel
        self.vel *= 0.88
        self.life -= 1

    def draw(self, surf):
        alpha = int((self.life / self.max_life) * 200)
        r, g, b = self.color
        s = pygame.Surface((6, 6), pygame.SRCALPHA)
        pygame.draw.circle(s, (r, g, b, alpha), (3, 3), 3)
        surf.blit(s, (int(self.pos.x) - 3, int(self.pos.y) - 3))

    @property
    def dead(self):
        return self.life <= 0


def trigger_near_miss(player_pos):
    """Spawn a small near-miss burst (max 8 particles to stay lightweight)."""
    for _ in range(8):
        near_miss_particles.append(NearMissParticle(player_pos))


def update_near_miss_particles(surf):
    """Update + draw near-miss particles and prune dead ones."""
    for p in near_miss_particles[:]:
        p.update()
        p.draw(surf)
        if p.dead:
            near_miss_particles.remove(p)


def apply_chromatic_aberration(surf):
    """Cheap RGB-split effect when player is hit: offsets red/blue channels."""
    if chroma_timer <= 0:
        return
    offset = max(1, int(chroma_timer * 0.5))

    # Red channel — shifted right
    r_surf = surf.copy()
    red_mask = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    red_mask.fill((255, 0, 0, 80))
    r_surf.blit(red_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    r_surf.set_alpha(100)
    surf.blit(r_surf, (-offset, 0))

    # Blue channel — shifted left
    b_surf = surf.copy()
    blue_mask = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    blue_mask.fill((0, 0, 255, 80))
    b_surf.blit(blue_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    b_surf.set_alpha(100)
    surf.blit(b_surf, (offset, 0))


class Player:
    def __init__(self):
        self.reset()

    def reset(self):
        self.pos = Vector2(WIDTH // 2, HEIGHT // 2)
        self.vel = Vector2(0, 0)
        self.radius = 12
        self.trail = []
        self.hp = 3
        self.hit_timer = 0
        self.is_dead = False
        self.pulse = 0.0
        self.hit_particles = []
        apply_powerup_state_to_player(self)   # inits all shield/hp/slow fields

    def update(self, direction):
        if self.is_dead:
            return
        # Tick power-up timers first
        update_powerup_timers(self)
        if direction.length() > 0:
            direction = direction.normalize()
            self.vel += direction * 1.1
        self.vel *= 0.82
        self.pos += self.vel
        self.pos.x = max(20, min(WIDTH - 20, self.pos.x))
        self.pos.y = max(20, min(HEIGHT - 20, self.pos.y))
        self.trail.insert(0, self.pos.copy())
        if len(self.trail) > 15:
            self.trail.pop()
        if self.hit_timer > 0:
            self.hit_timer -= 1
        self.pulse += 0.08

        for p in self.hit_particles[:]:
            p.update()
            if p.dead:
                self.hit_particles.remove(p)

    def draw(self, surf):
        # Trail — SRCALPHA circles, no opaque BG fill
        for i, p in enumerate(self.trail):
            alpha = max(0, 150 - i * 10)
            r = max(2, 10 - i)
            d = r * 2
            ts = pygame.Surface((d, d), pygame.SRCALPHA)
            pygame.draw.circle(ts, (0, 255, 255, alpha), (r, r), r)
            surf.blit(ts, (int(p.x) - r, int(p.y) - r))

        # ── Power-up aura effects (drawn before main body) ────────────────────
        draw_powerup_effects(surf, self, BG)

        # Glow pulse — SRCALPHA, no opaque background
        glow_radius = self.radius + int(abs(math.sin(self.pulse)) * 6)
        gd = glow_radius * 4
        glow_col = (255, 80, 80) if self.hit_timer > 0 else (0, 200, 255)
        glow_surf = pygame.Surface((gd, gd), pygame.SRCALPHA)
        r_g, g_g, b_g = glow_col
        pygame.draw.circle(glow_surf, (r_g, g_g, b_g, 55), (glow_radius * 2, glow_radius * 2), glow_radius * 2)
        surf.blit(glow_surf, (int(self.pos.x) - glow_radius * 2, int(self.pos.y) - glow_radius * 2))

        color = (255, 100, 100) if self.hit_timer > 0 else CYAN
        pygame.draw.circle(surf, color, self.pos, self.radius)

        # Hit particles
        for p in self.hit_particles:
            p.draw(surf)

    def hit(self, invulnerable=False):
        global shake_amount, zoom_scale
        if invulnerable:
            return
        if self.hit_timer == 0:
            # Check shield / extra-hits absorption first
            absorbed = not player_hit_with_powerups(self, invulnerable)
            if absorbed:
                shake_amount += 10   # small shake even when absorbed
                zoom_scale = max(zoom_scale, 1.05)
                return
            # Real damage — play hit sound
            _play(hit_sound,           "hit")
            self.hp -= 1
            self.hit_timer = 40
            shake_amount += 25
            zoom_scale = 1.1
            global chroma_timer
            chroma_timer = CHROMA_FRAMES
            # Spawn hit particles
            for _ in range(14):
                self.hit_particles.append(HitParticle(self.pos))
            if self.hp <= 0:
                self.is_dead = True
                _play(death_sound,         "death")


class BigOrb:
    """
    Level 3 hazard: same visual as SunOrb — bright white growing orb
    with flame particles erupting from edges, shakes the screen while spawning.
    Larger radius than SunOrb and stays longer.
    """
    RADIUS_MIN  = 5
    RADIUS_MAX  = 68
    GROW_TIME   = 110
    ACTIVE_TIME = 200
    EXIT_TIME   = 50
    FLAME_RATE  = 2

    def __init__(self):
        self.pos        = Vector2(random.randint(180, WIDTH - 180), random.randint(130, HEIGHT - 130))
        self.shake_off  = Vector2(0, 0)
        self.timer      = 0
        self.state      = "growing"
        self.dead       = False
        self.pulse      = random.uniform(0, math.tau)
        self.alpha      = 160
        self.flames     = []
        self.cur_radius = float(self.RADIUS_MIN)

    def update(self):
        global shake_amount, zoom_scale
        self.timer += 1
        self.pulse += 0.11

        if self.state == "growing":
            grow_t = min(1.0, self.timer / self.GROW_TIME)
            ease = 1 - (1 - grow_t) ** 3
            self.cur_radius = self.RADIUS_MIN + ease * (self.RADIUS_MAX - self.RADIUS_MIN)
            self.alpha = int(160 + ease * 95)

            # Screen shake during growth
            global_shake = 5 + ease * 20
            shake_amount = max(shake_amount, global_shake)
            if grow_t > 0.4:
                zoom_scale = max(zoom_scale, 1.0 + ease * 0.035)

            orb_shake = 2 + ease * 9
            self.shake_off = Vector2(
                random.uniform(-orb_shake, orb_shake),
                random.uniform(-orb_shake, orb_shake),
            )
            if self.timer % self.FLAME_RATE == 0:
                count = 1 + int(ease * 3)
                for _ in range(count):
                    self.flames.append(_FlameParticle(self.pos + self.shake_off, self.cur_radius))
            for f in self.flames[:]:
                f.update()
                if f.dead:
                    self.flames.remove(f)
            if self.timer >= self.GROW_TIME:
                self.state = "active"
                self.timer = 0
                _play(big_orb_sound,       "big_orb")

        elif self.state == "active":
            shake_amount = max(shake_amount, 8)
            self.shake_off = Vector2(random.uniform(-5, 5), random.uniform(-5, 5))
            if self.timer % self.FLAME_RATE == 0:
                for _ in range(3):
                    self.flames.append(_FlameParticle(self.pos + self.shake_off, self.cur_radius))
            for f in self.flames[:]:
                f.update()
                if f.dead:
                    self.flames.remove(f)
            if self.timer >= self.ACTIVE_TIME:
                self.state = "exiting"
                self.timer = 0

        elif self.state == "exiting":
            self.alpha = max(0, int(255 * (1 - self.timer / self.EXIT_TIME)))
            self.shake_off = Vector2(0, 0)
            for f in self.flames[:]:
                f.update()
                if f.dead:
                    self.flames.remove(f)
            if self.timer >= self.EXIT_TIME:
                self.dead = True

    def draw(self, surf):
        if self.dead:
            return
        cx = int(self.pos.x + self.shake_off.x)
        cy = int(self.pos.y + self.shake_off.y)
        a  = self.alpha
        r  = int(self.cur_radius)
        if r <= 0:
            return

        # Flame particles behind body
        for f in self.flames:
            f.draw(surf, a)

        # Outer fire halos (SRCALPHA — no box border)
        for col, extra, a_frac in [
            ((200, 30,   0), 40, 0.10),
            ((255, 100,  10), 24, 0.18),
            ((255, 200,  80), 12, 0.28),
        ]:
            pulse_add = int(abs(math.sin(self.pulse)) * 10)
            gr = r + extra + pulse_add
            gs = pygame.Surface((gr * 2, gr * 2), pygame.SRCALPHA)
            rr, gg, bb = col
            pygame.draw.circle(gs, (rr, gg, bb, int(a * a_frac)), (gr, gr), gr)
            surf.blit(gs, (cx - gr, cy - gr))

        # Solid white body
        body_r = max(1, r - int(abs(math.sin(self.pulse)) * 3))
        pygame.draw.circle(surf, WHITE, (cx, cy), body_r)

        # White bloom glow (SRCALPHA)
        bloom_r = body_r + int(abs(math.sin(self.pulse + 0.5)) * 7) + 10
        bs = pygame.Surface((bloom_r * 2, bloom_r * 2), pygame.SRCALPHA)
        pygame.draw.circle(bs, (255, 255, 255, int(a * 0.28)), (bloom_r, bloom_r), bloom_r)
        surf.blit(bs, (cx - bloom_r, cy - bloom_r))

        # Blue-white hot core (SRCALPHA)
        core_r = max(2, body_r // 3)
        cs = pygame.Surface((core_r * 2, core_r * 2), pygame.SRCALPHA)
        pygame.draw.circle(cs, (210, 235, 255, int(a * 0.95)), (core_r, core_r), core_r)
        surf.blit(cs, (cx - core_r, cy - core_r))


MIN_ORBS_DIST = 220  # minimum pixels between two SunOrbs to prevent overlap


class _FlameParticle:
    """A single flame ember ejected from the edge of a SunOrb."""
    __slots__ = ("pos", "vel", "life", "max_life", "size", "hue_shift")

    def __init__(self, origin, orb_radius):
        # Spawn on the orb's circumference at a random angle
        angle = random.uniform(0, math.tau)
        spawn = origin + Vector2(math.cos(angle), math.sin(angle)) * orb_radius
        self.pos = spawn.copy()
        # Velocity: mostly outward, with turbulent wobble
        speed = random.uniform(0.8, 2.6)
        spread = random.uniform(-0.5, 0.5)
        self.vel = Vector2(
            math.cos(angle + spread) * speed,
            math.sin(angle + spread) * speed,
        )
        self.life     = random.randint(14, 32)
        self.max_life = self.life
        self.size     = random.randint(3, 7)
        # 0 = orange-red, 1 = yellow-white tip
        self.hue_shift = random.random()

    def update(self):
        # Flames decelerate and drift slightly upward (buoyancy feel)
        self.vel *= 0.91
        self.vel.y -= 0.04
        self.pos += self.vel
        self.life -= 1

    def draw(self, surf, master_alpha):
        if self.life <= 0:
            return
        t = self.life / self.max_life          # 1.0 → fresh, 0.0 → dying
        # Colour: white-yellow core → orange → deep red as it cools
        r = 255
        g = int(min(255, 60 + self.hue_shift * 160 + t * 80))
        b = int(t * t * 40)
        size = max(1, int(self.size * t))
        alpha = int(master_alpha * t * 0.85)
        d = size * 2
        fs = pygame.Surface((d, d), pygame.SRCALPHA)
        pygame.draw.circle(fs, (r, g, b, alpha), (size, size), size)
        surf.blit(fs, (int(self.pos.x) - size, int(self.pos.y) - size))

    @property
    def dead(self):
        return self.life <= 0


class SunOrb:
    """
    Level 2 hazard: bright white orb that grows from tiny to full size
    while shaking the entire screen. Flame/ember particles burst from
    its edges. Spawned in pairs with guaranteed separation.
    """
    RADIUS_MIN   = 4      # starts as a tiny dot
    RADIUS_MAX   = 55     # fully-grown radius
    GROW_TIME    = 100    # frames to reach full size (~1.7 s)
    SHAKE_TIME   = 200    # total active frames (includes growth)
    EXIT_TIME    = 60     # 1 s fade-out
    FLAME_RATE   = 2      # spawn flames every N frames

    def __init__(self, pos):
        self.pos         = Vector2(pos)
        self.shake_off   = Vector2(0, 0)
        self.timer       = 0
        self.state       = "growing"   # growing → active → exiting → dead
        self.dead        = False
        self.pulse       = random.uniform(0, math.tau)
        self.alpha       = 180         # fades in during grow
        self.flames      = []
        self.cur_radius  = float(self.RADIUS_MIN)

    # ------------------------------------------------------------------
    @staticmethod
    def find_safe_pos(existing):
        margin = SunOrb.RADIUS_MAX + 30
        for _ in range(60):
            x = random.randint(margin + 60, WIDTH  - margin - 60)
            y = random.randint(margin + 60, HEIGHT - margin - 60)
            candidate = Vector2(x, y)
            if all(candidate.distance_to(o.pos) >= MIN_ORBS_DIST for o in existing):
                return candidate
        side = random.randint(0, 1)
        x = random.randint(margin, WIDTH // 2 - margin) if side == 0 \
            else random.randint(WIDTH // 2 + margin, WIDTH - margin)
        y = random.randint(margin, HEIGHT - margin)
        return Vector2(x, y)

    # ------------------------------------------------------------------
    def update(self):
        global shake_amount, zoom_scale
        self.timer += 1
        self.pulse += 0.12

        if self.state == "growing":
            grow_t = min(1.0, self.timer / self.GROW_TIME)
            # ease-out cubic: fast start, smooth finish
            ease = 1 - (1 - grow_t) ** 3
            self.cur_radius = self.RADIUS_MIN + ease * (self.RADIUS_MAX - self.RADIUS_MIN)
            self.alpha = int(180 + ease * 75)  # 180 → 255 as it grows

            # Shake intensity ramps hard during growth — shakes the whole screen
            global_shake = 4 + ease * 18        # 4 → 22 px of screen shake
            shake_amount = max(shake_amount, global_shake)
            if grow_t > 0.5:
                zoom_scale = max(zoom_scale, 1.0 + ease * 0.04)

            # Orb itself also trembles
            orb_shake = 2 + ease * 8
            self.shake_off = Vector2(
                random.uniform(-orb_shake, orb_shake),
                random.uniform(-orb_shake, orb_shake),
            )

            # Spawn flames — more as orb grows
            if self.timer % self.FLAME_RATE == 0:
                count = 1 + int(ease * 3)
                for _ in range(count):
                    self.flames.append(
                        _FlameParticle(self.pos + self.shake_off, self.cur_radius)
                    )

            for f in self.flames[:]:
                f.update()
                if f.dead:
                    self.flames.remove(f)

            if self.timer >= self.GROW_TIME:
                self.state = "active"
                self.timer = 0
                _play(big_orb_sound,       "big_orb")

        elif self.state == "active":
            # Fully grown — still shakes screen and spawns flames
            shake_amount = max(shake_amount, 10)
            self.shake_off = Vector2(
                random.uniform(-6, 6),
                random.uniform(-6, 6),
            )
            if self.timer % self.FLAME_RATE == 0:
                for _ in range(3):
                    self.flames.append(
                        _FlameParticle(self.pos + self.shake_off, self.cur_radius)
                    )
            for f in self.flames[:]:
                f.update()
                if f.dead:
                    self.flames.remove(f)

            remain = self.SHAKE_TIME - self.GROW_TIME
            if self.timer >= remain:
                self.state = "exiting"
                self.timer = 0

        elif self.state == "exiting":
            self.alpha = max(0, int(255 * (1 - self.timer / self.EXIT_TIME)))
            self.shake_off = Vector2(0, 0)
            for f in self.flames[:]:
                f.update()
                if f.dead:
                    self.flames.remove(f)
            if self.timer >= self.EXIT_TIME:
                self.dead = True

    # ------------------------------------------------------------------
    def draw(self, surf):
        if self.dead:
            return

        cx = int(self.pos.x + self.shake_off.x)
        cy = int(self.pos.y + self.shake_off.y)
        a  = self.alpha
        r  = int(self.cur_radius)
        if r <= 0:
            return

        # --- flame/ember particles behind the orb body ---
        for f in self.flames:
            f.draw(surf, a)

        # --- outer fire halo (3 layers: red → orange → yellow-white) ---
        # Use SRCALPHA so glow circles have no visible square border
        for col, extra, a_frac in [
            ((200, 30,   0),  36, 0.10),   # deep red far halo
            ((255, 100,  10), 22, 0.18),   # orange mid halo
            ((255, 200,  80), 10, 0.28),   # yellow near halo
        ]:
            pulse_add = int(abs(math.sin(self.pulse)) * 9)
            gr = r + extra + pulse_add
            gd = gr * 2
            gs = pygame.Surface((gd, gd), pygame.SRCALPHA)
            r2, g2, b2 = col
            pygame.draw.circle(gs, (r2, g2, b2, int(a * a_frac)), (gr, gr), gr)
            surf.blit(gs, (cx - gr, cy - gr))

        # --- bright white orb body ---
        body_r = max(1, r - int(abs(math.sin(self.pulse)) * 2))
        pygame.draw.circle(surf, WHITE, (cx, cy), body_r)

        # --- intense white glow bloom on top (SRCALPHA, no box) ---
        bloom_r = body_r + int(abs(math.sin(self.pulse + 0.5)) * 6) + 8
        bs = pygame.Surface((bloom_r * 2, bloom_r * 2), pygame.SRCALPHA)
        pygame.draw.circle(bs, (255, 255, 255, int(a * 0.30)), (bloom_r, bloom_r), bloom_r)
        surf.blit(bs, (cx - bloom_r, cy - bloom_r))

        # --- hot white-blue pinpoint core (SRCALPHA, no box) ---
        core_r = max(2, body_r // 3)
        cs = pygame.Surface((core_r * 2, core_r * 2), pygame.SRCALPHA)
        pygame.draw.circle(cs, (220, 240, 255, int(a * 0.95)), (core_r, core_r), core_r)
        surf.blit(cs, (cx - core_r, cy - core_r))

    # ------------------------------------------------------------------
    def hits_player(self, player):
        if self.state == "exiting":
            return False
        return (self.pos + self.shake_off).distance_to(player.pos) < self.cur_radius + player.radius


class BlackHoleDebris:
    """Spiraling particle pulled into the black hole."""
    def __init__(self, center, orbit_radius=None):
        self.center        = center
        self.angle         = random.uniform(0, math.tau)
        self.radius        = orbit_radius if orbit_radius else random.randint(80, 380)
        self.angular_speed = random.uniform(0.03, 0.09) * random.choice([-1, 1])
        self.inward_speed  = random.uniform(0.8, 2.4)
        # visual variety: some are streaks, some are dots
        self.kind   = random.choice(["dot", "dot", "streak"])
        self.color  = random.choice([
            WHITE,
            (180, 160, 255),  # pale violet
            (120, 200, 255),  # ice blue
            (255, 200, 120),  # warm yellow
        ])
        self.size   = random.randint(1, 3)

    def update(self):
        self.angle  += self.angular_speed
        # accelerate as it gets closer (inverse square-ish)
        accel = self.inward_speed * (1 + max(0, (200 - self.radius) / 200))
        self.radius -= accel

    def draw(self, surf):
        if self.radius <= 0:
            return
        fade = min(1.0, self.radius / 120)   # fade out as it's swallowed
        cx = self.center.x + math.cos(self.angle) * self.radius
        cy = self.center.y + math.sin(self.angle) * self.radius
        r, g, b = self.color
        col = (int(r * fade), int(g * fade), int(b * fade))
        if self.kind == "streak":
            # draw a short line tangent to the orbit for motion blur feel
            prev_a = self.angle - self.angular_speed * 4
            px = self.center.x + math.cos(prev_a) * (self.radius + self.inward_speed * 4)
            py = self.center.y + math.sin(prev_a) * (self.radius + self.inward_speed * 4)
            if col != (0, 0, 0):
                pygame.draw.line(surf, col, (int(cx), int(cy)), (int(px), int(py)), self.size)
        else:
            size = max(1, int(self.size * fade))
            if col != (0, 0, 0):
                pygame.draw.circle(surf, col, (int(cx), int(cy)), size)


class BHDustCloud:
    """Wispy ambient dust far from the black hole that slowly drifts inward."""
    def __init__(self, center):
        self.center = center
        angle = random.uniform(0, math.tau)
        dist  = random.randint(180, 420)
        self.pos    = Vector2(
            center.x + math.cos(angle) * dist,
            center.y + math.sin(angle) * dist,
        )
        self.alpha  = random.randint(30, 90)
        self.size   = random.randint(6, 18)
        self.drift  = (center - self.pos).normalize() * random.uniform(0.3, 0.9)
        self.spin   = random.uniform(-0.02, 0.02)
        self.angle  = random.uniform(0, math.tau)
        self.color  = random.choice([(60, 0, 100), (80, 0, 60), (30, 20, 80)])
        self.life   = random.randint(80, 180)
        self.max_life = self.life

    def update(self):
        self.pos   += self.drift
        self.drift  *= 1.01          # accelerates as it falls in
        self.angle  += self.spin
        self.life  -= 1
        self.alpha  = int(self.alpha * (self.life / self.max_life))

    def draw(self, surf):
        if self.life <= 0 or self.alpha < 2:
            return
        ds = pygame.Surface((self.size * 2, self.size * 2), pygame.SRCALPHA)
        r, g, b = self.color
        pygame.draw.circle(ds, (r, g, b, self.alpha), (self.size, self.size), self.size)
        surf.blit(ds, (int(self.pos.x) - self.size, int(self.pos.y) - self.size))

    @property
    def dead(self):
        return self.life <= 0


class BlackHole:
    """
    Final-30s mega black hole for level 3.
    - Grows to 220px radius over 3 seconds
    - Lasts 5 seconds (300 frames) then collapses
    - Swallows all hazards (big_orbs, exploders, minis, lasers, sun_orbs)
    - Directional gravity: moving TOWARD hole = pulled harder,
      moving AWAY = pulled weakly (still dragged in, just slower)
    - Player instant-kills when touching event horizon
    """
    GROW_TIME    = 180   # 3 s to reach full size
    DURATION     = 300   # 5 s total lifetime
    MAX_RADIUS   = 220   # huge — swallows the arena
    KILL_RADIUS  = 200

    def __init__(self):
        self.pos        = Vector2(WIDTH // 2, HEIGHT // 2)
        self.radius     = 5
        self.dead       = False
        self.pulse      = 0.0
        self.age        = 0
        # 160 spiraling debris particles + 60 ambient dust clouds
        self.debris     = [BlackHoleDebris(self.pos) for _ in range(160)]
        self.dust       = [BHDustCloud(self.pos) for _ in range(60)]
        self._swallow_flash = 0
        self._spawn_cd  = 0   # cooldown for refreshing debris/dust

    def update(self, player, big_orbs, exploders, minis, lasers=None, sun_orbs=None):
        global shake_amount, zoom_scale, flash_timer
        self.age   += 1
        self.pulse += 0.15

        # ── radius / phase ──────────────────────────────────────────────
        if self.age < self.GROW_TIME:
            grow_t = self.age / self.GROW_TIME
            ease   = 1 - (1 - grow_t) ** 3
            self.radius    = 5 + ease * (self.MAX_RADIUS - 5)
            gravity_scale  = ease
        elif self.age > self.DURATION - 40:
            # collapse phase
            collapse_t     = (self.age - (self.DURATION - 40)) / 40
            self.radius    = max(0, self.MAX_RADIUS * (1 - collapse_t))
            gravity_scale  = 0.2
        else:
            self.radius    = self.MAX_RADIUS
            gravity_scale  = 1.0

        # ── screen shake scales with gravity ────────────────────────────
        shake_amount = max(shake_amount, 8 + gravity_scale * 22)
        if gravity_scale > 0.5:
            zoom_scale = max(zoom_scale, 1.0 + gravity_scale * 0.05)

        # ── directional gravity on player ───────────────────────────────
        dir_vec  = self.pos - player.pos
        dist     = max(dir_vec.length(), 1)
        pull_dir = dir_vec.normalize()
        # dot product: +1 = moving toward hole, -1 = moving away
        vel_len  = player.vel.length()
        if vel_len > 0.01:
            dot = player.vel.normalize().dot(pull_dir)
        else:
            dot = 0.0
        # facing hole → strong pull; facing away → weak pull (still pulled)
        direction_factor = 0.6 + 0.4 * ((dot + 1) / 2)   # range 0.6 – 1.0
        base_force = (0.04 + gravity_scale * 0.28) * direction_factor
        player.vel += pull_dir * base_force

        # ── player swallowed ────────────────────────────────────────────
        if self.radius > self.KILL_RADIUS:
            if dist < self.radius + player.radius:
                player.hp = 0
                player.is_dead = True

        # ── swallow helper ──────────────────────────────────────────────
        def _get_pos(obj):
            """Lasers use .head; everything else uses .pos."""
            return obj.head if hasattr(obj, 'head') else obj.pos

        def _set_pos(obj, new_pos):
            if hasattr(obj, 'head'):
                obj.head = new_pos
            else:
                obj.pos = new_pos

        def pull_and_swallow(lst, strength, swallow_dist=None):
            sd = swallow_dist or self.radius
            for obj in lst[:]:
                obj_pos = _get_pos(obj)
                d = self.pos - obj_pos
                dlen = d.length()
                if dlen > 1:
                    _set_pos(obj, obj_pos + d.normalize() * (strength * gravity_scale))
                if _get_pos(obj).distance_to(self.pos) < sd:
                    lst.remove(obj)
                    self._swallow_flash = 4
                    for _ in range(6):
                        self.debris.append(BlackHoleDebris(self.pos, random.randint(20, 80)))

        pull_and_swallow(big_orbs,  0.30)
        pull_and_swallow(exploders, 0.40)
        pull_and_swallow(minis,     1.20)
        if lasers is not None:
            pull_and_swallow(lasers, 0.50)
        if sun_orbs is not None:
            pull_and_swallow(sun_orbs, 0.35)

        # ── debris + dust update, replenish continuously ────────────────
        for d in self.debris[:]:
            d.update()
            if d.radius <= 0:
                self.debris.remove(d)
        for dc in self.dust[:]:
            dc.update()
            if dc.dead:
                self.dust.remove(dc)
        # Keep a dense field: top up debris and dust every few frames
        self._spawn_cd -= 1
        if self._spawn_cd <= 0:
            self._spawn_cd = 3
            if len(self.debris) < 200 * gravity_scale + 80:
                self.debris.append(BlackHoleDebris(self.pos))
            if len(self.dust) < 80 * gravity_scale + 30:
                self.dust.append(BHDustCloud(self.pos))

        if self.age >= self.DURATION:
            self.dead = True

    def draw(self, surf):
        r   = int(self.radius)
        cx  = int(self.pos.x)
        cy  = int(self.pos.y)
        glow = abs(math.sin(self.pulse)) * 22

        # ── 1. Outer dust clouds (drawn first, furthest back) ────────────
        for dc in self.dust:
            dc.draw(surf)

        # ── 2. Wide ambient glow halos (deep purple/blue, large radii) ───
        for i, (col, extra, alf) in enumerate([
            ((15,  0,  40), 200, 50),   # faint far halo
            ((30,  0,  70), 140, 60),
            ((60,  0, 110), 90,  70),
            ((90,  0, 160), 50,  80),
        ]):
            hr = r + extra + int(glow * 0.5)
            if hr <= 0: continue
            hs = pygame.Surface((hr * 2, hr * 2), pygame.SRCALPHA)
            rr, gg, bb = col
            pygame.draw.circle(hs, (rr, gg, bb, alf), (hr, hr), hr)
            surf.blit(hs, (cx - hr, cy - hr))

        # ── 3. Accretion disk rings (bright narrow rings close to horizon) ─
        for i in range(5):
            ring_r = r + 8 + int(glow) + i * 14
            if ring_r <= 0: continue
            # colour: innermost = hot blue-white, outermost = dim violet
            t = i / 4
            rc = (int(180 * (1-t)), int(100 * (1-t)), int(255))
            alpha = max(0, 130 - i * 25)
            rs = pygame.Surface((ring_r * 2, ring_r * 2), pygame.SRCALPHA)
            thickness = max(1, 4 - i)
            pygame.draw.circle(rs, (*rc, alpha), (ring_r, ring_r), ring_r, thickness)
            surf.blit(rs, (cx - ring_r, cy - ring_r))

        # ── 4. Spiraling debris particles ───────────────────────────────
        for d in self.debris:
            d.draw(surf)

        # ── 5. Event horizon — pure black core ──────────────────────────
        if r > 0:
            pygame.draw.circle(surf, (0, 0, 0), (cx, cy), r)

        # ── 6. Photon sphere / chromatic edge ring ───────────────────────
        if r > 0:
            # Blue fringe (slightly larger)
            es = pygame.Surface(((r+10)*2, (r+10)*2), pygame.SRCALPHA)
            pygame.draw.circle(es, (80, 80, 255, 120), (r+10, r+10), r + 10, 3)
            surf.blit(es, (cx - r - 10, cy - r - 10))
            # Violet core ring
            vs = pygame.Surface(((r+4)*2, (r+4)*2), pygame.SRCALPHA)
            pygame.draw.circle(vs, (200, 0, 255, 200), (r+4, r+4), r + 4, 4)
            surf.blit(vs, (cx - r - 4, cy - r - 4))

        # ── 7. Swallow flash ─────────────────────────────────────────────
        if self._swallow_flash > 0:
            fs = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            fs.fill((180, 100, 255, 25))
            surf.blit(fs, (0, 0))
            self._swallow_flash -= 1


class Exploder:
    def __init__(self):
        self.pos = Vector2(random.randint(100, WIDTH - 100), random.randint(100, HEIGHT - 100))
        self.timer = 90
        self.dead = False
        self.shake_offset = Vector2(0, 0)

    def update(self):
        self.timer -= 1
        sp = (90 - self.timer) // 8
        self.shake_offset = Vector2(random.uniform(-sp, sp), random.uniform(-sp, sp))
        if self.timer <= 0:
            self.dead = True

    def draw(self, surf):
        t = 1.0 - (self.timer / 90.0)
        r = int(t * 255)
        g = int(180 - t * 150)
        b = int(255 - t * 255)
        color = (min(255, r), max(0, g), max(0, b))

        radius = (25 + (90 - self.timer) // 6) if self.timer > 10 else max(2, self.timer)
        draw_pos = self.pos + self.shake_offset

        # Glow — SRCALPHA circle, no opaque background box
        gd = radius * 4
        glow_surf = pygame.Surface((gd, gd), pygame.SRCALPHA)
        r_c, g_c, b_c = color
        pygame.draw.circle(glow_surf, (r_c, g_c, b_c, 55), (gd // 2, gd // 2), radius * 2)
        surf.blit(glow_surf, (int(draw_pos.x) - gd // 2, int(draw_pos.y) - gd // 2))

        pygame.draw.circle(surf, color, draw_pos, radius)


class Laser:
    """
    Fast projectile laser: spawns off-screen, shoots across at high speed.
    Shows a dashed warning line first, then fires a white bolt that travels
    across the screen. The bolt has a bright white core + fading white trail.
    """
    SPEED = 22           # default; overridden per-instance via constructor
    WARN_FRAMES = 45     # warning line duration before firing
    TRAIL_LEN = 14       # how many past positions to draw as trail

    def __init__(self, speed=22):
        self.SPEED = speed
        side = random.randint(0, 3)
        # Choose an entry edge and a matching exit edge so the bolt travels straight across
        if side == 0:    # top → bottom
            x = random.randint(50, WIDTH - 50)
            self.origin = Vector2(x, -30)
            self.direction = Vector2(0, 1)
        elif side == 1:  # bottom → top
            x = random.randint(50, WIDTH - 50)
            self.origin = Vector2(x, HEIGHT + 30)
            self.direction = Vector2(0, -1)
        elif side == 2:  # left → right
            y = random.randint(50, HEIGHT - 50)
            self.origin = Vector2(-30, y)
            self.direction = Vector2(1, 0)
        else:            # right → left
            y = random.randint(50, HEIGHT - 50)
            self.origin = Vector2(WIDTH + 30, y)
            self.direction = Vector2(-1, 0)

        # Warning line: drawn across the full screen along the bolt's path
        big = 1200
        self.warn_start = self.origin - self.direction * big
        self.warn_end   = self.origin + self.direction * big

        self.timer = 0
        self.phase = "warning"

        # Projectile head position — starts at origin when "active"
        self.head = self.origin.copy()
        self.trail = []   # list of past head positions

    def update(self):
        self.timer += 1

        if self.phase == "warning":
            if self.timer >= self.WARN_FRAMES:
                self.phase = "active"
                self.timer = 0
                self.head = self.origin.copy()
                self.trail = []
                _play(laser_sound,         "laser")

        elif self.phase == "active":
            # Save trail
            self.trail.insert(0, self.head.copy())
            if len(self.trail) > self.TRAIL_LEN:
                self.trail.pop()

            # Move head
            self.head += self.direction * self.SPEED

            # Done when bolt has fully exited the screen
            if (self.head.x < -200 or self.head.x > WIDTH + 200 or
                    self.head.y < -200 or self.head.y > HEIGHT + 200):
                self.phase = "done"

    def draw(self, surf, level_index=0):
        if self.phase == "warning":
            if (pygame.time.get_ticks() // 25) % 2 == 0:
                pygame.draw.line(surf, (180, 180, 180), self.warn_start, self.warn_end, 1)

        elif self.phase == "active":
            # Level-dependent neon trail color
            _trail_colors = [
                (0,   220, 255),   # Level 1 — cyan
                (180,  80, 255),   # Level 2 — purple
                (255,  80,  20),   # Level 3 — orange-red
            ]
            trail_col = _trail_colors[min(level_index, 2)]
            tr, tg, tb = trail_col

            # Neon fading trail segments
            for i in range(len(self.trail) - 1):
                t = 1.0 - (i / max(len(self.trail), 1))
                width = max(1, int(t * 6))
                seg_col = (int(tr * t), int(tg * t), int(tb * t))
                pygame.draw.line(surf, seg_col, self.trail[i], self.trail[i + 1], width)

            # Head glow (neon-tinted) — SRCALPHA, no black box
            hx, hy = int(self.head.x), int(self.head.y)
            gs = 60
            glow = pygame.Surface((gs, gs), pygame.SRCALPHA)
            pygame.draw.circle(glow, (tr, tg, tb, 80), (gs // 2, gs // 2), gs // 2)
            surf.blit(glow, (hx - gs // 2, hy - gs // 2))

            # Core bright lines
            tail = self.head - self.direction * 30
            pygame.draw.line(surf, (220, 220, 255), self.head, tail, 5)
            pygame.draw.line(surf, WHITE, self.head, self.head - self.direction * 18, 3)
            pygame.draw.circle(surf, WHITE, self.head, 5)

    def hits_player(self, player):
        if self.phase != "active":
            return False
        # Collision: check if player is within hit radius of the bolt head
        return self.head.distance_to(player.pos) < player.radius + 10


class MiniCircle:
    """
    Burst fragment from an Exploder.
    Has a long neon trail behind it for a spark/comet effect.
    """
    TRAIL_MAX = 10

    def __init__(self, pos, speed):
        self.pos = pos.copy()
        self.vel = Vector2(speed, 0).rotate(random.uniform(0, 360))
        self.color = random.choice([CYAN, NEON_PINK, NEON_LIME, NEON_ORANGE])
        self.trail = []

    def update(self):
        self.trail.insert(0, self.pos.copy())
        if len(self.trail) > self.TRAIL_MAX:
            self.trail.pop()
        self.pos += self.vel

    def draw(self, surf):
        # Draw trail as connected line segments on a single reused strip surface
        # Instead of one full-screen surface per segment, use direct circle dots
        r, g, b = self.color
        for i in range(len(self.trail) - 1):
            t = 1.0 - (i / self.TRAIL_MAX)
            alpha = int(t * 200)
            width = max(1, int(t * 4))
            p0 = self.trail[i]
            p1 = self.trail[i + 1]
            # Blit a tiny 1-pixel surface as a colored dot — avoids full-screen alloc
            pygame.draw.line(surf, (
                int(r * t), int(g * t), int(b * t)
            ), p0, p1, width)

        # Main dot with a subtle glow circle — SRCALPHA, no opaque box
        gd = 16
        glow = pygame.Surface((gd, gd), pygame.SRCALPHA)
        pygame.draw.circle(glow, (r, g, b, 70), (gd // 2, gd // 2), gd // 2)
        surf.blit(glow, (int(self.pos.x) - gd // 2, int(self.pos.y) - gd // 2))
        pygame.draw.circle(surf, self.color, self.pos, 4)


# =====================
# LEVEL 3 INTENSITY FLASH
# =====================
def _update_l3_flash(surf, level_timer):
    """
    Intense 3-layer flash bursts for Level 3 — chaotic, high-energy.
    Layer 1: red wash.  Layer 2: white strobe (alternating frames).
    Layer 3: dark-red edge vignette pulse for a heavy, oppressive feel.
    Timer values > 8 (set by Big Orb spawns) produce noticeably stronger flashes.
    """
    global _l3_flash_timer, _l3_flash_cd
    if _l3_flash_cd > 0:
        _l3_flash_cd -= 1
        return
    if _l3_flash_timer <= 0:
        # Slightly higher spontaneous chance than before
        if random.random() < 0.022:
            _l3_flash_timer = random.randint(4, 9)
            _l3_flash_cd    = random.randint(_L3_FLASH_MIN_CD, _L3_FLASH_MAX_CD)
    else:
        t = _l3_flash_timer
        max_t = 10.0
        intensity = t / max_t   # 0.0 → 1.0

        # ── Layer 1: Red wash ──────────────────────────────────────────────
        red_alpha = int(35 + 60 * intensity)   # 35 → 95
        red_layer = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        red_layer.fill((255, 10, 10, red_alpha))
        surf.blit(red_layer, (0, 0))

        # ── Layer 2: White core strobe (every other frame) ─────────────────
        if t % 2 == 0:
            white_alpha = int(18 + 44 * intensity)   # 18 → 62
            white_layer = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
            white_layer.fill((255, 255, 255, white_alpha))
            surf.blit(white_layer, (0, 0))

        # ── Layer 3: Dark-red edge vignette pulse ──────────────────────────
        edge_alpha = int(70 * intensity)
        if edge_alpha > 4:
            edge_layer = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
            for i in range(0, 32, 4):
                ring_a = max(0, edge_alpha - i * 2)
                pygame.draw.rect(
                    edge_layer,
                    (180, 0, 0, ring_a),
                    (i, i, surf.get_width() - i * 2, surf.get_height() - i * 2),
                    4,
                )
            surf.blit(edge_layer, (0, 0))

        _l3_flash_timer -= 1


# =====================
# GAME COMPLETION CREDITS
# =====================
_CREDITS_LINES = [
    ("CONGRATULATIONS FOR COMPLETING",  (255, 255, 100), 40, True),
    ("",                                 (0,   0,   0),  18, False),
    ("Neon Dodge: Level Overdrive",      (0,  240, 255), 34, True),
    ("",                                 (0,   0,   0),  14, False),
    ("Created by",                       (160,160, 160), 18, False),
    ("Edrean Supremo",                   (255,255, 255), 26, True),
    ("",                                 (0,   0,   0),  12, False),
    ("Game Design",                      (120,120, 120), 16, False),
    ("Edrean Supremo",                   (200,200, 200), 20, False),
    ("Programming",                      (120,120, 120), 16, False),
    ("Edrean Supremo",                   (200,200, 200), 20, False),
    ("Gameplay Mechanics",               (120,120, 120), 16, False),
    ("Edrean Supremo",                   (200,200, 200), 20, False),
    ("Level Design",                     (120,120, 120), 16, False),
    ("Edrean Supremo",                   (200,200, 200), 20, False),
    ("User Interface",                   (120,120, 120), 16, False),
    ("Edrean Supremo",                   (200,200, 200), 20, False),
    ("",                                 (0,   0,   0),  12, False),
    ("Music",                            (120,120, 120), 16, False),
    ("Geometry Dash",                    (200,200, 200), 20, False),
    ("Sound Effects",                    (120,120, 120), 16, False),
    ("PixaBay",                          (200,200, 200), 20, False),
    ("",                                 (0,   0,   0),  12, False),
    ("Production Manager",               (120,120, 120), 16, False),
    ("Edrean Supremo",                   (200,200, 200), 20, False),
    ("Quality Assurance",                (120,120, 120), 16, False),
    ("Beta Testers & Friends",           (200,200, 200), 20, False),
    ("",                                 (0,   0,   0),  12, False),
    ("Special Thanks",                   (120,120, 120), 16, False),
    ("My Teachers",                      (200,200, 200), 18, False),
    ("My Classmates",                    (200,200, 200), 18, False),
    ("Open Source Community",            (200,200, 200), 18, False),
    ("Arduino & Python Developers",      (200,200, 200), 18, False),
    ("",                                 (0,   0,   0),  14, False),
    ("\u00a9 2026 Edrean Supremo",       (160,160, 160), 15, False),
    ("All Rights Reserved",              (140,140, 140), 14, False),
    ("Unauthorized duplication is prohibited.", (100,100,100), 13, False),
    ("Made for educational purposes.",   (100,100, 100), 13, False),
    ("",                                 (0,   0,   0),  20, False),
    ("=" * 45,                           (40,  40,  60), 14, False),
    ("",                                 (0,   0,   0),  10, False),
    ("THANK YOU FOR PLAYING",            (0,  255, 200), 36, True),
]


def show_credits():
    """
    Cinematic end-game credits screen.
    Fades to black, plays scrolling credits. ESC or key after scroll exits.
    """
    # Fade to black
    fade_surf = pygame.Surface((SCREEN_W, SCREEN_H))
    fade_surf.fill((0, 0, 0))
    for alpha in range(0, 256, 4):
        screen.blit(pygame.transform.smoothscale(virtual_screen, (RENDER_W, RENDER_H)), (RENDER_X, RENDER_Y))
        fade_surf.set_alpha(alpha)
        screen.blit(fade_surf, (0, 0))
        pygame.display.flip()
        clock.tick(60)

    pygame.mixer.music.fadeout(1500)

    # Pre-render all credit line surfaces
    rendered = []
    total_h  = 0
    for (text, color, size, bold) in _CREDITS_LINES:
        f    = pygame.font.SysFont("Courier New", size, bold=bold)
        surf = f.render(text, True, color)
        rendered.append((surf, size))
        total_h += size + 10

    scroll_y    = float(SCREEN_H)
    scroll_speed = 0.9
    done        = False
    min_y_seen  = scroll_y
    _star_rng   = random.Random(42)   # deterministic stars — no flicker

    while not done:
        clock.tick(60)
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                tracker.release()
                pygame.quit()
                exit()
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    tracker.release()
                    pygame.quit()
                    exit()
                if min_y_seen < SCREEN_H * 0.25:
                    done = True

        screen.fill((0, 0, 0))

        # Subtle static star field
        _t = pygame.time.get_ticks()
        for _ in range(80):
            sx = _star_rng.randint(0, SCREEN_W)
            sy = _star_rng.randint(0, SCREEN_H)
            sa = int(60 + 50 * abs(math.sin(_t * 0.001 + _star_rng.random() * 6)))
            ss = pygame.Surface((2, 2), pygame.SRCALPHA)
            pygame.draw.circle(ss, (200, 200, 255, sa), (1, 1), 1)
            screen.blit(ss, (sx, sy))

        # Draw scrolling lines
        y = scroll_y
        for (surf, size) in rendered:
            if -size < y < SCREEN_H + size:
                x = SCREEN_W // 2 - surf.get_width() // 2
                screen.blit(surf, (int(x), int(y)))
            y += size + 10

        min_y_seen = min(min_y_seen, scroll_y)

        # Top/bottom gradient masks
        for i in range(70):
            a = int(255 * (1 - i / 70))
            gm = pygame.Surface((SCREEN_W, 1), pygame.SRCALPHA)
            gm.fill((0, 0, 0, a))
            screen.blit(gm, (0, i))
            screen.blit(gm, (0, SCREEN_H - 1 - i))

        pygame.display.flip()
        scroll_y -= scroll_speed
        if scroll_y + total_h < 0:
            done = True

    # Brief hold then exit
    for _ in range(120):
        clock.tick(60)
        screen.fill((0, 0, 0))
        pygame.display.flip()
        for e in pygame.event.get():
            if e.type in (pygame.QUIT,):
                tracker.release()
                pygame.quit()
                exit()
            if e.type == pygame.KEYDOWN:
                tracker.release()
                pygame.quit()
                exit()


# =====================
# GAME STATE RESET
# =====================
def reset_game_state(idx):
    global black_hole, black_hole_active, black_hole_triggered
    global chroma_timer, near_miss_particles, _near_miss_cooldown
    play_level_music(idx)
    black_hole          = None
    black_hole_active   = False
    black_hole_triggered = False
    chroma_timer        = 0
    _near_miss_cooldown = 0
    near_miss_particles.clear()
    pu_manager = PowerUpManager(SURVIVAL_TIME)
    # returns: player, exploders, minis, lasers, level_timer, laser_cd, start_delay, big_orbs, sun_orbs, sun_orb_cd, pu_manager
    return Player(), [], [], [], SURVIVAL_TIME, 0, 120, [], [], 0, pu_manager


# =====================
# MAIN
# =====================
tracker = HandTracker(WIDTH, HEIGHT)
show_warning()

level_index = 0
player, exploders, minis, lasers, level_timer, laser_cd, start_delay, big_orbs, sun_orbs, sun_orb_cd, pu_manager = reset_game_state(level_index)
death_timer = 0

while level_index < len(LEVELS):
    data = LEVELS[level_index]
    # Seed virtual_screen for the intro animation background
    lvl_fill, _ = get_level_bg(level_index)
    virtual_screen.fill(lvl_fill)
    draw_background_grid(virtual_screen, level_index=level_index)
    show_level_intro(level_index)
    screen_fade("in")
    in_menu = False
    running = True

    while running:
        clock.tick(60)

        for e in pygame.event.get():
            if e.type == pygame.QUIT or tracker.gesture_quit:
                tracker.release()
                pygame.quit()
                exit()

            if e.type == pygame.KEYDOWN:
                # ── Global ESC: quit immediately from anywhere ──
                if e.key == pygame.K_ESCAPE:
                    tracker.release()
                    pygame.quit()
                    exit()

                # ── Level select: 1 / 2 / 3 ──
                if e.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                    target = {pygame.K_1: 0, pygame.K_2: 1, pygame.K_3: 2}[e.key]
                    if target < len(LEVELS):
                        screen_fade("out")
                        level_index = target
                        player, exploders, minis, lasers, level_timer, laser_cd, start_delay, big_orbs, sun_orbs, sun_orb_cd, pu_manager = reset_game_state(level_index)
                        lvl_fill, _ = get_level_bg(level_index)
                        virtual_screen.fill(lvl_fill)
                        draw_background_grid(virtual_screen, level_index=level_index)
                        show_level_intro(level_index)
                        screen_fade("in")
                        in_menu = False
                        running = True
                        death_timer = 0

            if in_menu:
                if e.type == pygame.KEYDOWN and e.key == pygame.K_q:
                    tracker.release()
                    pygame.quit()
                    exit()

        if not player.is_dead:
            move_dir = tracker.get_move_vec(player.pos)
            player.update(move_dir)

            if start_delay > 0:
                start_delay -= 1
            else:
                # --- SPAWN EXPLODERS ---
                if level_timer % data["exploder_rate"] == 0:
                    count = 5 if level_index == 2 else data.get("exploder_count", 3)
                    for _ in range(count):
                        exploders.append(Exploder())

                # --- SPAWN BIG ORBS (level 3 only) ---
                # 3 orbs every 5 seconds (300 frames), cap at 6 on screen.
                # Triggers a strong shake + immediate flash burst for dramatic weight.
                if data.get("has_big_orb") and level_index == 2:
                    if level_timer % 300 == 0 and len(big_orbs) < 6:
                        for _ in range(3):
                            big_orbs.append(BigOrb())
                        # Stronger than Level 2 SunOrb (shake was 22, zoom was 1.04)
                        shake_amount = max(shake_amount, 45)
                        zoom_scale   = max(zoom_scale, 1.12)
                        # Override L3 flash: fire immediately, hold for 10 frames
                        _l3_flash_timer = 10
                        _l3_flash_cd    = 0

                # --- SPAWN SUN ORBS (level 2 and level 3) ---
                if level_index in (1, 2):
                    if sun_orb_cd <= 0 and len(sun_orbs) < 2:
                        # Spawn both orbs together, guaranteed non-overlapping
                        pos1 = SunOrb.find_safe_pos(sun_orbs)
                        o1 = SunOrb(pos1)
                        sun_orbs.append(o1)
                        pos2 = SunOrb.find_safe_pos(sun_orbs)
                        o2 = SunOrb(pos2)
                        sun_orbs.append(o2)
                        sun_orb_cd = data.get("sun_orb_rate", 300)
                    elif sun_orb_cd > 0:
                        sun_orb_cd -= 1

                # --- LASER SPAWN ---
                if laser_cd <= 0:
                    if data.get("laser_grace", 0) > 0 and (SURVIVAL_TIME - level_timer) < data["laser_grace"]:
                        pass  # grace period: no lasers at the very start
                    elif level_index == 2 and len(lasers) == 0:
                        lasers.append(Laser(speed=data.get("laser_speed", 22)))
                    elif level_index != 2:
                        for _ in range(data["laser_count"]):
                            lasers.append(Laser(speed=data.get("laser_speed", 22)))
                    laser_cd = data["laser_rate"]
                else:
                    laser_cd -= 1

                # --- BLACK HOLE TRIGGER (Level 3 only, last 30 seconds) ---
                if level_index == 2 and not black_hole_triggered:
                    if level_timer <= 1800:
                        black_hole = BlackHole()
                        black_hole_active = True
                        black_hole_triggered = True
                        shake_amount = max(shake_amount, 40)

                # --- BLACK HOLE UPDATE ---
                if black_hole:
                    black_hole.update(player, big_orbs, exploders, minis, lasers, sun_orbs)
                    if black_hole.dead:
                        black_hole = None
                        black_hole_active = False

            # --- POWER-UP UPDATE ---
            _collected = pu_manager.update(player, level_timer, in_menu)
            if _collected == "slow":    _play(slowmo_sound,        "powerup")
            elif _collected == "shield": _play(shield_sound,        "powerup")
            elif _collected == "hp":     _play(extra_sound,         "powerup")

            # Slow-motion factor: 0.6 when active, else 1.0
            _sf = get_slow_factor(player)

            # --- COLLISIONS & UPDATES ---
            for o in big_orbs[:]:
                o.update()
                # Apply slow-motion by nudging position back slightly against velocity
                if player.slow_motion_active and hasattr(o, 'vel'):
                    o.vel *= _sf
                if o.state in ("growing", "active") and (o.pos + o.shake_off).distance_to(player.pos) < o.cur_radius + player.radius:
                    player.hit(invulnerable=in_menu)
                if o.dead:
                    big_orbs.remove(o)

            for so in sun_orbs[:]:
                so.update()
                if player.slow_motion_active and hasattr(so, 'vel'):
                    so.vel *= _sf
                if so.hits_player(player):
                    player.hit(invulnerable=in_menu)
                if so.dead:
                    sun_orbs.remove(so)
                    # Reset cooldown so next pair spawns after 5s
                    if len(sun_orbs) == 0:
                        sun_orb_cd = data.get("sun_orb_rate", 300)

            for exp in exploders[:]:
                exp.update()
                # Slow-mo: add back (1-sf) of the 1-frame decrement so fuse burns slower
                if player.slow_motion_active and not exp.dead:
                    exp.timer += (1.0 - _sf)
                if exp.dead:
                    exploders.remove(exp)
                    shake_amount += 18
                    zoom_scale = max(zoom_scale, 1.07)
                    _play(explosion_orb_sound,"explode")
                    for _ in range(data.get("mini_count", 6)):
                        minis.append(MiniCircle(exp.pos, data["particle_speed"]))

            for m in minis[:]:
                m.update()
                # Slow-mo: partially undo the movement by nudging pos back
                if player.slow_motion_active:
                    m.pos -= m.vel * (1.0 - _sf)
                if m.pos.distance_to(player.pos) < player.radius:
                    player.hit(invulnerable=in_menu)
                    minis.remove(m)

            for lz in lasers[:]:
                lz.update()
                # Slow lasers: nudge head back by the fraction we over-moved
                if player.slow_motion_active and lz.phase == "active":
                    lz.head -= lz.direction * lz.SPEED * (1.0 - _sf)
                if lz.hits_player(player):
                    player.hit(invulnerable=in_menu)
                if lz.phase == "done":
                    lasers.remove(lz)

            if not in_menu:
                level_timer -= 1
                if level_timer <= 0:
                    in_menu = True

        # =====================
        # DRAW
        # =====================
        lvl_fill, _ = get_level_bg(level_index)
        virtual_screen.fill(lvl_fill)

        pulse = (shake_amount / 30.0) if black_hole else 0.0
        draw_background_grid(virtual_screen, pulse_intensity=min(1.0, pulse), level_index=level_index)

        for o in big_orbs:
            o.draw(virtual_screen)
        for so in sun_orbs:
            so.draw(virtual_screen)
        for exp in exploders:
            exp.draw(virtual_screen)
        for m in minis:
            m.draw(virtual_screen)

        # ── Power-ups drawn after background hazards, before player ──────────
        pu_manager.draw(virtual_screen)

        for lz in lasers:
            lz.draw(virtual_screen, level_index)
        if black_hole:
            black_hole.draw(virtual_screen)

        player.draw(virtual_screen)
        tracker.draw_preview(virtual_screen)

        # Near-miss detection: lasers passing close but not hitting
        if _near_miss_cooldown > 0:
            _near_miss_cooldown -= 1
        for lz in lasers:
            if lz.phase == "active":
                dist = lz.head.distance_to(player.pos)
                if player.radius + 10 < dist < player.radius + 36:
                    if not getattr(lz, '_near_miss_triggered', False):
                        lz._near_miss_triggered = True
                        if _near_miss_cooldown <= 0:
                            trigger_near_miss(player.pos)
                            _near_miss_cooldown = 20   # prevent burst spam
                else:
                    lz._near_miss_triggered = False

        # Draw near-miss particles
        update_near_miss_particles(virtual_screen)

        # Screen ripple on power-up pickup (purely visual)
        update_draw_ripples(virtual_screen)

        # Tick chromatic aberration
        if chroma_timer > 0:
            chroma_timer -= 1

        if not in_menu:
            draw_progress_bar(virtual_screen, level_timer)
            draw_survive_timer(virtual_screen, level_timer)
            draw_hp(virtual_screen, player.hp)
            # Power-up HUD (timer bar above player + badge)
            draw_powerup_hud(virtual_screen, player, WIDTH)

        # Slow-motion blue screen tint
        draw_slowmo_tint(virtual_screen, player, SURVIVAL_TIME - level_timer)

        draw_vignette(virtual_screen, intense=black_hole_active)

        # Level 3 intensity flash — subtle red/white pulse
        if level_index == 2 and not in_menu:
            _update_l3_flash(virtual_screen, level_timer)

        # Chromatic aberration on hit
        if chroma_timer > 0:
            apply_chromatic_aberration(virtual_screen)

        if flash_timer > 0:
            flash_surface = pygame.Surface((WIDTH, HEIGHT))
            flash_surface.fill((255, 255, 255))
            flash_surface.set_alpha(180)
            virtual_screen.blit(flash_surface, (0, 0))
            flash_timer -= 1

        render_offset = Vector2(
            random.uniform(-shake_amount, shake_amount),
            random.uniform(-shake_amount, shake_amount)
        ) if shake_amount > 0 else Vector2(0, 0)
        shake_amount *= 0.85
        zoom_scale = max(1.0, zoom_scale * 0.98)

        sw = int(RENDER_W * zoom_scale)
        sh = int(RENDER_H * zoom_scale)
        scaled = pygame.transform.smoothscale(virtual_screen, (sw, sh))
        screen.fill((0, 0, 0))
        blit_x = RENDER_X + (RENDER_W - sw) // 2 + int(render_offset.x)
        blit_y = RENDER_Y + (RENDER_H - sh) // 2 + int(render_offset.y)
        screen.blit(scaled, (blit_x, blit_y))

        if in_menu:
            # ── Cinematic stage-cleared transition fires automatically ────
            # Fade gameplay music out first, then hand off to the transition
            # (which starts stage_music.mp3, waits for input, countdowns, and
            #  fades stage_music out before returning).
            pygame.mixer.music.fadeout(600)
            pygame.time.wait(620)   # let fadeout finish before transition

            # Run cinematic (no-op for final stage — credits shown below)
            show_stage_cleared_transition(level_index)

            # Advance to next level or credits
            level_index += 1
            running = False   # break inner loop → outer loop handles next level

        if player.is_dead:
            death_timer += 1

            # Frame 1: stop level music and start death music
            if death_timer == 1:
                pygame.mixer.music.stop()
                try:
                    pygame.mixer.music.load(_asset("sfx/death.mp3"))
                    pygame.mixer.music.set_volume(1.0)
                    pygame.mixer.music.play(0)   # play once
                except Exception as e:
                    print(f"[audio] death music FAILED: {e}")

            # At frame 60 (2 s before restart at frame 180): fade death music out over 2000 ms
            if death_timer == 60:
                pygame.mixer.music.fadeout(2000)

            # Overlay fades to black over the full 180 frames (3 s)
            fade_alpha = min(255, int((death_timer / 180) * 255))
            overlay = pygame.Surface((SCREEN_W, SCREEN_H))
            overlay.fill((0, 0, 0))
            overlay.set_alpha(fade_alpha)
            screen.blit(overlay, (0, 0))

            if death_timer >= 180:
                # Reset same level, show intro, fade back in
                player, exploders, minis, lasers, level_timer, laser_cd, start_delay, big_orbs, sun_orbs, sun_orb_cd, pu_manager = reset_game_state(level_index)
                death_timer = 0
                lvl_fill, _ = get_level_bg(level_index)
                virtual_screen.fill(lvl_fill)
                draw_background_grid(virtual_screen, level_index=level_index)
                show_level_intro(level_index)
                screen_fade("in")

        pygame.display.flip()

    # level_index was already incremented inside the in_menu block above.
    # If there are more levels, set up the next one and show its intro.
    if level_index < len(LEVELS):
        player, exploders, minis, lasers, level_timer, laser_cd, start_delay, big_orbs, sun_orbs, sun_orb_cd, pu_manager = reset_game_state(level_index)

# All levels completed — show credits
show_credits()

tracker.release()
pygame.quit()

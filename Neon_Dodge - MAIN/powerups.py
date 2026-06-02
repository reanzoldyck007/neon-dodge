# powerups.py
# =====================================================================
# POWER-UP SYSTEM — Neon Dodge: Level Overdrive
# =====================================================================
# Three types:
#   "hp"    — +2 temporary hits (10 s or 2 hits, whichever first)
#   "shield"— absorbs all damage (5 s)
#   "slow"  — hazards move at 60 % speed (7 s)
#
# Spawn rules:
#   • First spawn within 10 s of game start  (≤600 frames from level_timer start)
#   • Expires if uncollected after 5 s       (300 frames)
#   • After pickup, next spawn in 15 s       (900 frames)
#   • Only one power-up on screen at a time
# =====================================================================

import pygame
import random
import math
from pygame.math import Vector2

# ── Colour palette ────────────────────────────────────────────────────────────
_BG        = (5, 5, 15)
_CYAN      = (0, 255, 255)
_GREEN     = (50, 255, 100)
_BLUE      = (50, 150, 255)
_YELLOW    = (255, 220, 50)
_WHITE     = (255, 255, 255)
_ORANGE    = (255, 160, 30)

# Duration constants (frames at 60 fps)
POWERUP_EXPIRE_FRAMES = 300    # 5 s on ground before it vanishes
POWERUP_COOLDOWN      = 900    # 15 s between pickups
FIRST_SPAWN_WINDOW    = 600    # spawn within first 10 s
SURVIVAL_TIME         = 3600   # must match dodge.py

POWERUP_TYPES = ["hp", "shield", "slow"]

POWERUP_DURATIONS = {
    "hp":     600,   # 10 s
    "shield": 600,   # 10 s
    "slow":   600,   # 10 s
}

POWERUP_COLORS = {
    "hp":     _GREEN,
    "shield": _CYAN,
    "slow":   _BLUE,
}

POWERUP_LABELS = {
    "hp":     "+HP",
    "shield": "SHIELD",
    "slow":   "SLOW",
}

WIDTH  = 900
HEIGHT = 600


# ── Small orbit particle for +HP aura ─────────────────────────────────────────
class _OrbitParticle:
    __slots__ = ("angle", "speed", "dist", "size", "color")

    def __init__(self):
        self.angle = random.uniform(0, math.tau)
        self.speed = random.uniform(0.04, 0.09) * random.choice([-1, 1])
        self.dist  = random.uniform(18, 28)
        self.size  = random.randint(2, 4)
        self.color = random.choice([_GREEN, (180, 255, 180), _WHITE])

    def draw(self, surf, cx, cy, alpha):
        self.angle += self.speed
        x = cx + math.cos(self.angle) * self.dist
        y = cy + math.sin(self.angle) * self.dist
        s = pygame.Surface((self.size * 2, self.size * 2), pygame.SRCALPHA)
        r, g, b = self.color
        pygame.draw.circle(s, (r, g, b, alpha), (self.size, self.size), self.size)
        surf.blit(s, (int(x) - self.size, int(y) - self.size))


# ── Ripple ring for slow-motion aura ──────────────────────────────────────────
class _RippleRing:
    __slots__ = ("radius", "max_radius", "alpha")

    def __init__(self):
        self.radius     = 14
        self.max_radius = random.randint(32, 50)
        self.alpha      = 220

    @property
    def dead(self):
        return self.alpha <= 0

    def update(self):
        self.radius += 1.2
        self.alpha   = max(0, int(220 * (1 - self.radius / self.max_radius)))

    def draw(self, surf, cx, cy):
        if self.dead:
            return
        r = int(self.radius)
        s = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (50, 150, 255, self.alpha), (r + 1, r + 1), r, 2)
        surf.blit(s, (cx - r - 1, cy - r - 1))


# ── [NEW] Orbiting shield node ─────────────────────────────────────────────────
class _ShieldNode:
    """One energy node in the orbiting shield ring around the player."""
    __slots__ = ("angle", "orbit_r", "speed", "size", "pulse", "color", "trail")

    def __init__(self, angle, orbit_r, speed, color):
        self.angle   = angle
        self.orbit_r = orbit_r
        self.speed   = speed
        self.size    = random.randint(3, 5)
        self.pulse   = random.uniform(0, math.tau)
        self.color   = color
        self.trail   = []   # list of (x, y) positions for motion trail

    def update(self):
        self.angle += self.speed
        self.pulse += 0.12
        x = self.orbit_r * math.cos(self.angle)
        y = self.orbit_r * math.sin(self.angle)
        self.trail.insert(0, (x, y))
        if len(self.trail) > 8:
            self.trail.pop()

    def draw(self, surf, cx, cy, alpha):
        if not self.trail:
            return
        r, g, b = self.color
        # Draw fading trail
        for i, (tx, ty) in enumerate(self.trail):
            t = 1.0 - (i / len(self.trail))
            ta = int(alpha * t * 0.5)
            sz = max(1, int(self.size * t * 0.7))
            d = sz * 2
            s = pygame.Surface((d, d), pygame.SRCALPHA)
            pygame.draw.circle(s, (r, g, b, ta), (sz, sz), sz)
            surf.blit(s, (cx + int(tx) - sz, cy + int(ty) - sz))
        # Draw head with glow pulse
        hx, hy = self.trail[0]
        pulse_sz = self.size + int(abs(math.sin(self.pulse)) * 2)
        # Glow
        gd = pulse_sz * 4
        gs = pygame.Surface((gd, gd), pygame.SRCALPHA)
        pygame.draw.circle(gs, (r, g, b, int(alpha * 0.4)), (gd // 2, gd // 2), gd // 2)
        surf.blit(gs, (cx + int(hx) - gd // 2, cy + int(hy) - gd // 2))
        # Core dot
        d2 = pulse_sz * 2
        s2 = pygame.Surface((d2, d2), pygame.SRCALPHA)
        pygame.draw.circle(s2, (r, g, b, alpha), (pulse_sz, pulse_sz), pulse_sz)
        surf.blit(s2, (cx + int(hx) - pulse_sz, cy + int(hy) - pulse_sz))
        # White hot center
        ws = pygame.Surface((4, 4), pygame.SRCALPHA)
        pygame.draw.circle(ws, (255, 255, 255, int(alpha * 0.85)), (2, 2), 2)
        surf.blit(ws, (cx + int(hx) - 2, cy + int(hy) - 2))


# ── [ENHANCED] Screen ripple wave on power-up pickup ─────────────────────────
class ScreenRipple:
    """
    Multi-layer expanding ripple — 4 rings with glow halo + inner fill ghost.
    Each layer has a different speed, radius ceiling, alpha, colour, and thickness
    so they naturally separate and create a layered shockwave feel.
    """
    # (speed_mult, max_r_mult, alpha_base, colour_rgb, ring_thickness)
    _LAYERS = [
        (1.00, 1.00, 200, (180, 255, 255), 3),   # primary cyan ring
        (0.78, 0.82, 145, (255, 255, 255), 1),   # inner white shimmer
        (1.22, 1.18, 105, (100, 200, 255), 2),   # outer blue ghost
        (0.58, 0.68,  80, (255, 255, 255), 1),   # slow tight glow ring
    ]

    def __init__(self, pos, layer_idx=0):
        self.pos        = Vector2(pos)
        self._li        = layer_idx
        spec            = self._LAYERS[layer_idx]
        self._spd_mult, self._mr_mult, self._a_base, self._col, self._thick = spec
        self.radius     = 8 + layer_idx * 6   # staggered start
        self.max_r      = 340 * self._mr_mult
        self.alpha      = self._a_base
        self.speed      = 8.0 * self._spd_mult

    @property
    def dead(self):
        return self.alpha <= 4

    def update(self):
        self.radius += self.speed
        self.speed   = max(2.5, self.speed * 0.97)
        t            = self.radius / self.max_r
        # Quadratic fade: fast at start, lingers at edge
        self.alpha   = max(0, int(self._a_base * (1 - t) * (1 - t)))

    def draw(self, surf):
        if self.dead:
            return
        r   = int(self.radius)
        if r <= 0:
            return
        a   = self.alpha
        cr, cg, cb = self._col
        pad = self._thick + 3
        dim = r * 2 + pad * 2
        cx  = r + pad

        s = pygame.Surface((dim, dim), pygame.SRCALPHA)

        # ── Main ring ─────────────────────────────────────────────────────
        pygame.draw.circle(s, (cr, cg, cb, a), (cx, cx), r, self._thick)

        # ── Glow halo (wider, lower alpha — fake bloom) ───────────────────
        glow_a = int(a * 0.35)
        if glow_a > 3:
            pygame.draw.circle(s, (cr, cg, cb, glow_a), (cx, cx), r + 5, self._thick + 4)

        # ── Inner fill ghost (very faint) — distortion illusion ───────────
        fill_a = int(a * 0.08)
        if fill_a > 2 and r > 8:
            pygame.draw.circle(s, (cr, cg, cb, fill_a), (cx, cx), max(1, r - 3))

        surf.blit(s, (int(self.pos.x) - cx, int(self.pos.y) - cx))


# Global ripple pool — managed here so PowerUpManager can append to it
_screen_ripples = []

def spawn_pickup_ripple(pos):
    """
    Spawn all 4 ripple layers at once. They start at staggered radii
    and expand at different speeds, creating a multi-wave shockwave effect.
    """
    for li in range(len(ScreenRipple._LAYERS)):
        _screen_ripples.append(ScreenRipple(pos, layer_idx=li))

def update_draw_ripples(surf):
    """Update and draw all active screen ripples. Call once per frame in main draw."""
    for rp in _screen_ripples[:]:
        rp.update()
        rp.draw(surf)
        if rp.dead:
            _screen_ripples.remove(rp)


# ─────────────────────────────────────────────────────────────────────────────
# PowerUp — floating collectable
# ─────────────────────────────────────────────────────────────────────────────
class PowerUp:
    RADIUS = 14   # collision / draw radius

    def __init__(self):
        margin = 80
        self.pos      = Vector2(
            random.randint(margin, WIDTH  - margin),
            random.randint(margin, HEIGHT - margin),
        )
        self.type     = random.choice(POWERUP_TYPES)
        self.picked   = False
        self.expired  = False
        self._age     = 0          # frames alive on ground
        self._float   = random.uniform(0, math.tau)   # sin-wave phase
        self._rot     = 0.0        # icon rotation angle

    # ── Update ────────────────────────────────────────────────────────────────
    def update(self):
        if self.picked or self.expired:
            return
        self._age   += 1
        self._float += 0.07
        self._rot   += 2.5
        if self._age >= POWERUP_EXPIRE_FRAMES:
            self.expired = True

    # ── Collision ─────────────────────────────────────────────────────────────
    def check_collect(self, player):
        if self.picked or self.expired:
            return False
        return self.pos.distance_to(player.pos) < player.radius + self.RADIUS

    # ── Apply effect to player ────────────────────────────────────────────────
    def apply(self, player):
        self.picked = True
        dur = POWERUP_DURATIONS[self.type]
        if self.type == "hp":
            player.extra_hits       = 2
            player.extra_hits_timer = dur
        elif self.type == "shield":
            player.shield_active = True
            player.shield_timer  = dur
        elif self.type == "slow":
            player.slow_motion_active = True
            player.slow_motion_timer  = dur

    # ── Draw ──────────────────────────────────────────────────────────────────
    def draw(self, surf):
        if self.picked or self.expired:
            return

        cx = int(self.pos.x)
        cy = int(self.pos.y + math.sin(self._float) * 5)   # float bob

        col = POWERUP_COLORS[self.type]
        r, g, b = col

        # Blink during last 60 frames (1 s)
        blink_alpha = 255
        if self._age >= POWERUP_EXPIRE_FRAMES - 60:
            phase       = (self._age % 14) / 14
            blink_alpha = int(abs(math.sin(phase * math.pi)) * 200) + 55

        # ── Outer glow pulse ──────────────────────────────────────────────────
        pulse_r = self.RADIUS + 8 + int(abs(math.sin(self._float)) * 6)
        gd      = pulse_r * 2
        gs      = pygame.Surface((gd, gd), pygame.SRCALPHA)
        pygame.draw.circle(gs, (r, g, b, int(blink_alpha * 0.30)), (pulse_r, pulse_r), pulse_r)
        surf.blit(gs, (cx - pulse_r, cy - pulse_r))

        # ── Body circle ───────────────────────────────────────────────────────
        bs = pygame.Surface((self.RADIUS * 2, self.RADIUS * 2), pygame.SRCALPHA)
        pygame.draw.circle(bs, (r, g, b, blink_alpha), (self.RADIUS, self.RADIUS), self.RADIUS)
        surf.blit(bs, (cx - self.RADIUS, cy - self.RADIUS))

        # ── Inner bright core ─────────────────────────────────────────────────
        cr = self.RADIUS // 2
        cs = pygame.Surface((cr * 2, cr * 2), pygame.SRCALPHA)
        pygame.draw.circle(cs, (255, 255, 255, int(blink_alpha * 0.7)), (cr, cr), cr)
        surf.blit(cs, (cx - cr, cy - cr))

        # ── Rotating icon symbol ──────────────────────────────────────────────
        self._draw_icon(surf, cx, cy, blink_alpha)

        # ── Label text ────────────────────────────────────────────────────────
        f = pygame.font.SysFont("Courier New", 11, bold=True)
        lbl = f.render(POWERUP_LABELS[self.type], True, (255, 255, 255))
        lbl.set_alpha(blink_alpha)
        surf.blit(lbl, (cx - lbl.get_width() // 2, cy + self.RADIUS + 4))

    def _draw_icon(self, surf, cx, cy, alpha):
        """Draw a small rotated icon specific to the power-up type."""
        rad = math.radians(self._rot)
        if self.type == "hp":
            # Plus/cross shape
            arms = [(0, -8), (0, 8), (-8, 0), (8, 0)]
            for dx, dy in arms:
                nx = cx + math.cos(rad) * dx - math.sin(rad) * dy
                ny = cy + math.sin(rad) * dx + math.cos(rad) * dy
                s = pygame.Surface((4, 4), pygame.SRCALPHA)
                pygame.draw.circle(s, (255, 255, 255, alpha), (2, 2), 2)
                surf.blit(s, (int(nx) - 2, int(ny) - 2))
        elif self.type == "shield":
            # Hexagon outline
            pts = []
            for i in range(6):
                a = rad + math.tau * i / 6
                pts.append((cx + math.cos(a) * 8, cy + math.sin(a) * 8))
            if len(pts) >= 2:
                s = pygame.Surface((self.RADIUS * 4, self.RADIUS * 4), pygame.SRCALPHA)
                adjusted = [(int(p[0] - cx + self.RADIUS * 2), int(p[1] - cy + self.RADIUS * 2)) for p in pts]
                pygame.draw.polygon(s, (255, 255, 255, alpha), adjusted, 2)
                surf.blit(s, (cx - self.RADIUS * 2, cy - self.RADIUS * 2))
        elif self.type == "slow":
            # Stylised clock: circle + two hands
            for length, angle_off in [(7, rad), (5, rad + math.pi * 0.5)]:
                ex = cx + math.cos(angle_off) * length
                ey = cy + math.sin(angle_off) * length
                s  = pygame.Surface((4, 4), pygame.SRCALPHA)
                pygame.draw.circle(s, (255, 255, 255, alpha), (2, 2), 2)
                surf.blit(s, (int(ex) - 2, int(ey) - 2))


# ─────────────────────────────────────────────────────────────────────────────
# PowerUpManager — controls spawning, timing, collection
# ─────────────────────────────────────────────────────────────────────────────
class PowerUpManager:
    def __init__(self, survival_time=SURVIVAL_TIME):
        self.survival_time   = survival_time
        self.powerup         = None          # current active PowerUp on screen
        self._spawn_cd       = 0            # frames until next spawn (counts down)
        self._first_spawned  = False        # did we spawn the first one yet?
        # First spawn window: within first 10 s — pick a random moment in [0, 600]
        self._first_spawn_at = random.randint(0, FIRST_SPAWN_WINDOW)

    # ── Reset (call on level start or death) ──────────────────────────────────
    def reset(self, survival_time=None):
        if survival_time is not None:
            self.survival_time = survival_time
        self.powerup         = None
        self._first_spawned  = False
        self._first_spawn_at = random.randint(0, FIRST_SPAWN_WINDOW)
        self._spawn_cd       = 0

    # ── Main update — call once per frame in game loop ────────────────────────
    def update(self, player, level_timer, in_menu):
        """Returns the collected power-up type string ('hp','shield','slow') or None."""
        if in_menu:
            return None

        elapsed = self.survival_time - level_timer   # frames elapsed this level
        collected_type = None

        # ── Clean up expired / picked powerup ─────────────────────────────────
        if self.powerup is not None:
            self.powerup.update()
            if self.powerup.expired:
                self.powerup = None
                self._spawn_cd = POWERUP_COOLDOWN
            elif self.powerup.picked:
                self.powerup = None
                self._spawn_cd = POWERUP_COOLDOWN

        # ── Check collection ──────────────────────────────────────────────────
        if self.powerup is not None:
            if self.powerup.check_collect(player):
                collected_type = self.powerup.type   # capture before apply clears it
                self.powerup.apply(player)
                # [NEW] Trigger screen ripple at player position
                spawn_pickup_ripple(player.pos)
                # powerup.picked is True; cleared next frame above

        # ── Spawn logic ───────────────────────────────────────────────────────
        if self.powerup is None:
            if not self._first_spawned:
                # First spawn: trigger at the chosen moment in the first 10 s
                if elapsed >= self._first_spawn_at:
                    self.powerup        = PowerUp()
                    self._first_spawned = True
            else:
                if self._spawn_cd > 0:
                    self._spawn_cd -= 1
                else:
                    self.powerup = PowerUp()

        return collected_type

    # ── Draw the on-screen powerup ────────────────────────────────────────────
    def draw(self, surf):
        if self.powerup is not None:
            self.powerup.draw(surf)


# ─────────────────────────────────────────────────────────────────────────────
# Player power-up state mixin — add these attributes to Player.__init__
# ─────────────────────────────────────────────────────────────────────────────
# In Player.reset() add:
#   self.shield_active       = False
#   self.shield_timer        = 0
#   self.extra_hits          = 0
#   self.extra_hits_timer    = 0
#   self.slow_motion_active  = False
#   self.slow_motion_timer   = 0
#   self._orbit_particles    = [_OrbitParticle() for _ in range(6)]
#   self._ripple_rings       = []
#   self._ripple_cd          = 0
#   self._shield_hit_flash   = 0
#   self._shield_shrink      = 0.0   # 0 = full, +ve = slightly shrunken
#   self._shield_nodes       = [...]  # NEW orbiting shield nodes

def apply_powerup_state_to_player(player):
    """
    Patch power-up state onto an existing Player instance.
    Call this inside Player.reset() (or after construction).
    """
    player.shield_active      = False
    player.shield_timer       = 0
    player.extra_hits         = 0
    player.extra_hits_timer   = 0
    player.slow_motion_active = False
    player.slow_motion_timer  = 0
    player._orbit_particles   = [_OrbitParticle() for _ in range(6)]
    player._ripple_rings      = []
    player._ripple_cd         = 0
    player._shield_hit_flash  = 0
    player._shield_shrink     = 0.0
    # [NEW] Orbiting shield nodes — 5 nodes on two concentric rings
    player._shield_nodes      = _make_shield_nodes()
    player._shield_pulse      = 0.0   # global pulse phase for shield glow


def _make_shield_nodes():
    """Create 5 shield nodes in two orbits, alternating directions."""
    nodes = []
    # 3 nodes on inner ring — clockwise
    inner_r = 26
    for i in range(3):
        angle = math.tau * i / 3
        nodes.append(_ShieldNode(
            angle   = angle,
            orbit_r = inner_r,
            speed   = 0.06,
            color   = (0, 230, 255),
        ))
    # 2 nodes on outer ring — counter-clockwise, offset phase
    outer_r = 38
    for i in range(2):
        angle = math.tau * i / 2 + math.pi / 3
        nodes.append(_ShieldNode(
            angle   = angle,
            orbit_r = outer_r,
            speed   = -0.045,
            color   = (100, 255, 255),
        ))
    return nodes


def update_powerup_timers(player):
    """
    Tick all active power-up timers on the player.
    Call at the start of Player.update().
    """
    # +HP timer
    if player.extra_hits_timer > 0:
        player.extra_hits_timer -= 1
        if player.extra_hits_timer <= 0:
            player.extra_hits = 0

    # Shield timer
    if player.shield_active:
        player.shield_timer -= 1
        if player.shield_timer <= 0:
            player.shield_active = False

    # Slow motion timer
    if player.slow_motion_active:
        player.slow_motion_timer -= 1
        if player.slow_motion_timer <= 0:
            player.slow_motion_active = False

    # Shield shrink recovery
    if hasattr(player, '_shield_shrink'):
        if player._shield_shrink > 0:
            player._shield_shrink = max(0.0, player._shield_shrink - 0.06)

    # Shield pulse
    if hasattr(player, '_shield_pulse'):
        player._shield_pulse += 0.1

    # Update orbiting shield nodes
    if hasattr(player, '_shield_nodes'):
        for node in player._shield_nodes:
            node.update()

    # Ripple ring spawn
    if player.slow_motion_active:
        if hasattr(player, '_ripple_cd'):
            player._ripple_cd -= 1
            if player._ripple_cd <= 0:
                player._ripple_rings.append(_RippleRing())
                player._ripple_cd = 18   # new ring every 18 frames
    for ring in player._ripple_rings[:]:
        ring.update()
        if ring.dead:
            player._ripple_rings.remove(ring)


def player_hit_with_powerups(player, invulnerable=False):
    """
    Replacement / augmentation for Player.hit().
    Returns True if actual HP damage was dealt, False if absorbed.
    Insert this logic at the TOP of Player.hit() before the normal HP decrement.
    """
    # Shield absorbs hit entirely
    if player.shield_active:
        player._shield_hit_flash = 8
        player._shield_shrink    = 1.0
        return False   # damage absorbed — caller should NOT deduct HP

    # Extra HP absorbs hit first
    if player.extra_hits > 0:
        player.extra_hits -= 1
        player.hit_timer = 20   # brief red flash but no real HP loss
        if player.extra_hits <= 0:
            player.extra_hits_timer = 0
        return False   # absorbed

    return True   # damage passes through to real HP


# ─────────────────────────────────────────────────────────────────────────────
# Drawing helpers — call from Player.draw() AFTER the trail but BEFORE the
# main body circle.
# ─────────────────────────────────────────────────────────────────────────────
def draw_powerup_effects(surf, player, bg_color=(5, 5, 15)):
    cx = int(player.pos.x)
    cy = int(player.pos.y)

    # ── Slow motion: blue ripple rings + blue aura ───────────────────────────
    if player.slow_motion_active:
        for ring in player._ripple_rings:
            ring.draw(surf, cx, cy)

        aura_r = player.radius + 10 + int(abs(math.sin(player.pulse)) * 4)
        ad     = aura_r * 2
        aura_s = pygame.Surface((ad, ad), pygame.SRCALPHA)
        pulse_alpha = 60 + int(abs(math.sin(player.pulse * 1.5)) * 40)
        pygame.draw.circle(aura_s, (50, 150, 255, pulse_alpha), (aura_r, aura_r), aura_r)
        surf.blit(aura_s, (cx - aura_r, cy - aura_r))

    # ── +HP: green aura + orbit particles ────────────────────────────────────
    if player.extra_hits > 0:
        aura_r = player.radius + 8 + int(abs(math.sin(player.pulse)) * 5)
        ad     = aura_r * 2
        aura_s = pygame.Surface((ad, ad), pygame.SRCALPHA)
        g_alpha = 50 + int(abs(math.sin(player.pulse * 1.2)) * 50)
        pygame.draw.circle(aura_s, (50, 255, 100, g_alpha), (aura_r, aura_r), aura_r)
        surf.blit(aura_s, (cx - aura_r, cy - aura_r))

        for op in player._orbit_particles:
            op.draw(surf, cx, cy, 200)

    # ── [NEW] Shield: orbiting energy nodes system ────────────────────────────
    if player.shield_active:
        fade = min(1.0, player.shield_timer / 60.0)
        alpha = int(fade * 220)
        pulse_phase = getattr(player, '_shield_pulse', 0.0)

        # ── Soft outer glow that breathes ─────────────────────────────────────
        outer_r = 48 + int(abs(math.sin(pulse_phase * 0.7)) * 8)
        gs = pygame.Surface((outer_r * 2, outer_r * 2), pygame.SRCALPHA)
        glow_alpha = int(fade * 35 + abs(math.sin(pulse_phase * 0.7)) * 20)
        pygame.draw.circle(gs, (0, 200, 255, glow_alpha), (outer_r, outer_r), outer_r)
        surf.blit(gs, (cx - outer_r, cy - outer_r))

        # ── Rotating inner bubble shell ───────────────────────────────────────
        bubble_r = player.radius + 14 - int(getattr(player, '_shield_shrink', 0) * 4)
        if bubble_r > player.radius:
            bs = pygame.Surface((bubble_r * 2, bubble_r * 2), pygame.SRCALPHA)
            body_alpha = int(fade * 30)
            pygame.draw.circle(bs, (120, 220, 255, body_alpha), (bubble_r, bubble_r), bubble_r)
            surf.blit(bs, (cx - bubble_r, cy - bubble_r))

            rs = pygame.Surface((bubble_r * 2, bubble_r * 2), pygame.SRCALPHA)
            ring_alpha = int(fade * 100)
            pygame.draw.circle(rs, (0, 255, 255, ring_alpha), (bubble_r, bubble_r), bubble_r, 2)
            surf.blit(rs, (cx - bubble_r, cy - bubble_r))

        # ── Orbiting energy nodes ─────────────────────────────────────────────
        if hasattr(player, '_shield_nodes'):
            for node in player._shield_nodes:
                node.draw(surf, cx, cy, alpha)

        # ── Connecting arc lines between inner-ring nodes ─────────────────────
        if hasattr(player, '_shield_nodes'):
            inner_nodes = player._shield_nodes[:3]
            pts = []
            for node in inner_nodes:
                if node.trail:
                    tx, ty = node.trail[0]
                    pts.append((cx + int(tx), cy + int(ty)))
            if len(pts) == 3:
                arc_alpha = int(fade * 80)
                for i in range(3):
                    p1 = pts[i]
                    p2 = pts[(i + 1) % 3]
                    # Draw dashed arc line
                    arc_surf = pygame.Surface((surf.get_width(), surf.get_height()), pygame.SRCALPHA)
                    pygame.draw.line(arc_surf, (0, 220, 255, arc_alpha), p1, p2, 1)
                    surf.blit(arc_surf, (0, 0))

        # ── Global pulse ring (scales with hit flash) ─────────────────────────
        pulse_r = bubble_r + 6 + int(abs(math.sin(pulse_phase)) * 5) if bubble_r > player.radius else player.radius + 20
        ps = pygame.Surface((pulse_r * 2, pulse_r * 2), pygame.SRCALPHA)
        p_alpha = int(fade * 50 + abs(math.sin(pulse_phase * 1.3)) * 30)
        pygame.draw.circle(ps, (100, 255, 255, p_alpha), (pulse_r, pulse_r), pulse_r, 1)
        surf.blit(ps, (cx - pulse_r, cy - pulse_r))

        # ── Hit flash — spark burst ───────────────────────────────────────────
        if player._shield_hit_flash > 0:
            player._shield_hit_flash -= 1
            fr = (bubble_r if bubble_r > player.radius else player.radius + 14) + 6
            fs2 = pygame.Surface((fr * 2, fr * 2), pygame.SRCALPHA)
            pygame.draw.circle(fs2, (255, 255, 100, 220), (fr, fr), fr, 3)
            surf.blit(fs2, (cx - fr, cy - fr))
            # Spark particles
            for _ in range(6):
                sa = random.uniform(0, math.tau)
                sx = cx + math.cos(sa) * (fr + 4)
                sy = cy + math.sin(sa) * (fr + 4)
                sp = pygame.Surface((8, 8), pygame.SRCALPHA)
                pygame.draw.circle(sp, (255, 220, 50, 220), (4, 4), 4)
                surf.blit(sp, (int(sx) - 4, int(sy) - 4))
            # Also scatter the nodes
            if hasattr(player, '_shield_nodes'):
                for node in player._shield_nodes:
                    node.angle += random.uniform(-0.3, 0.3)


# ─────────────────────────────────────────────────────────────────────────────
# HUD drawing — call from draw_hp() area or separately in the main draw block
# ─────────────────────────────────────────────────────────────────────────────
def draw_powerup_hud(surf, player, width=900):
    """
    Draw power-up indicators:
     • Timer bar above the player
     • Icon badge next to HP readout
    """
    font = pygame.font.SysFont("Courier New", 12, bold=True)

    active_type   = None
    active_timer  = 0
    active_dur    = 0

    if player.shield_active:
        active_type  = "shield"
        active_timer = player.shield_timer
        active_dur   = POWERUP_DURATIONS["shield"]
    elif player.extra_hits > 0:
        active_type  = "hp"
        active_timer = player.extra_hits_timer
        active_dur   = POWERUP_DURATIONS["hp"]
    elif player.slow_motion_active:
        active_type  = "slow"
        active_timer = player.slow_motion_timer
        active_dur   = POWERUP_DURATIONS["slow"]

    if active_type is None:
        return

    col   = POWERUP_COLORS[active_type]
    r, g, b = col
    frac  = max(0.0, active_timer / active_dur)
    cx    = int(player.pos.x)
    cy    = int(player.pos.y)

    # ── Timer bar above player ────────────────────────────────────────────────
    bar_w = 44
    bar_h = 5
    bx    = cx - bar_w // 2
    by    = cy - player.radius - 22

    # background
    pygame.draw.rect(surf, (40, 40, 60), (bx, by, bar_w, bar_h), border_radius=2)
    # fill
    fill_w = max(1, int(bar_w * frac))
    fill_s = pygame.Surface((fill_w, bar_h), pygame.SRCALPHA)
    fill_s.fill((r, g, b, 200))
    surf.blit(fill_s, (bx, by))
    # border
    pygame.draw.rect(surf, (r, g, b), (bx, by, bar_w, bar_h), 1, border_radius=2)

    # Label above the bar
    lbl = font.render(POWERUP_LABELS[active_type], True, (r, g, b))
    surf.blit(lbl, (cx - lbl.get_width() // 2, by - 13))

    # ── HUD badge top-right (next to HP) ──────────────────────────────────────
    hud_x = width - 110
    hud_y = 35
    badge = font.render(f"[ {POWERUP_LABELS[active_type]} {int(frac * 100)}% ]", True, (r, g, b))
    surf.blit(badge, (hud_x, hud_y))

    # Extra hits remaining indicator
    if active_type == "hp":
        hits_font = pygame.font.SysFont("Courier New", 11, bold=True)
        hits_lbl  = hits_font.render(f"+{player.extra_hits} hits", True, _GREEN)
        surf.blit(hits_lbl, (hud_x, hud_y + 15))


# ─────────────────────────────────────────────────────────────────────────────
# Slow-motion screen tint — call once per frame in main draw block
# ─────────────────────────────────────────────────────────────────────────────
def draw_slowmo_tint(surf, player, frame_count):
    """Blue screen pulse tint when slow-motion is active."""
    if not player.slow_motion_active:
        return
    pulse = abs(math.sin(frame_count * 0.04))
    tint_alpha = int(pulse * 25)
    if tint_alpha < 2:
        return
    tint = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    tint.fill((20, 60, 180, tint_alpha))
    surf.blit(tint, (0, 0))


# ─────────────────────────────────────────────────────────────────────────────
# Velocity multiplier for hazards — multiply hazard vel by this each frame
# ─────────────────────────────────────────────────────────────────────────────
def get_slow_factor(player):
    """Returns 0.6 if slow-motion active, else 1.0."""
    return 0.6 if player.slow_motion_active else 1.0

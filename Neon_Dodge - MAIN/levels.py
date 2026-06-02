# levels.py

LEVELS = [
    {
        "id": 1,
        "name": "THE AWAKENING",
        "music": "levels/the_awakening.mp3",
        "exploder_rate": 240,       # spawn exploders every 4s
        "exploder_count": 2,
        "laser_rate": 120,          # 1 laser every 2s
        "laser_count": 1,
        "laser_speed": 22,          # base projectile speed
        "laser_mode": "single",
        "laser_grace": 120,         # 2s grace period at start
        "has_big_orb": False,
        "big_orb_freq": 0,
        "mini_count": 4,
        "particle_speed": 3,
        "sun_orb_rate": 0,          # no sun orbs on level 1
    },
    {
        "id": 2,
        "name": "PULSE OVERDRIVE",
        "music": "levels/pulse_overdrive.mp3",
        "exploder_rate": 140,
        "exploder_count": 3,
        "laser_rate": 60,           # 1 laser every second
        "laser_count": 1,
        "laser_speed": 34,          # noticeably faster than level 1
        "laser_mode": "rapid",
        "laser_grace": 0,
        "has_big_orb": False,       # sun orbs replace big orbs here
        "big_orb_freq": 0,
        "mini_count": 6,
        "particle_speed": 6,
        "sun_orb_rate": 300,        # spawn pair of sun orbs every 5s
    },
    {
        "id": 3,
        "name": "CHAOS PROTOCOL",
        "music": "levels/chaos-protocol.mp3",
        "exploder_rate": 120,
        "exploder_count": 5,
        "laser_rate": 30,
        "laser_count": 1,
        "laser_speed": 28,
        "laser_mode": "single",
        "laser_grace": 0,
        "has_big_orb": True,
        "big_orb_freq": 999999,     # black hole managed manually in dodge.py
        "mini_count": 6,
        "particle_speed": 15,
        "sun_orb_rate": 240,        # spawn pair of sun orbs every 4s (faster than L2's 5s)
    }
]

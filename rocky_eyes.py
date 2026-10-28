#!/usr/bin/env python3
"""
Rocky's eyes - emotion presets and renderer (pygame).

The preset table is ported from Casey Grothaus's desk-robot firmware
(github.com/cgro00/desk-robot, MIT): seven emotion presets, each a set of eye
shape numbers, with the live shape easing toward the target every frame so
emotions morph instead of cutting.

His units are for a 128x64 mono OLED; SCALE maps them to a colour canvas.

    python rocky_eyes.py --selftest shots/    # one PNG per emotion
"""
from __future__ import annotations

import argparse
import math
import os

import pygame

# --- palette -----------------------------------------------------------------
BG     = (5, 8, 14)       # Jarvis theme background
PANEL  = (16, 22, 32)       # Updated panel colors  
LINE   = (38, 54, 74)       # Updated line/border colors
EYE    = (230, 240, 250)    # Updated eye colors
DIM    = (126, 146, 176)    # Updated dim text color
INK    = (238, 246, 255)    # Updated main text color
WARN   = (255, 190, 100)    # Updated warning color
REC    = (255, 100, 100)    # Updated recording indicator
ACCENT = (70, 230, 255)     # Updated accent color
OK     = (120, 245, 180)     # Updated status color
PUPIL  = (5, 10, 20)        # Pupil stays the same
GLINT  = (255, 255, 255)    # Glint stays the same  
BROW   = (100, 120, 150)    # Brows stay the same

# Pupil size per emotion: surprise contracts, anger narrows, joy opens up.
PUPILS = {
    "neutral": 1.00, "happy": 1.05, "sad": 1.00, "angry": 0.90,
    "surprised": 0.70, "sleepy": 0.95, "thinking": 0.85,
}

SCALE = 1.9          # his 128x64 units -> our canvas
EYE_DX = 92          # horizontal distance from centre to each eye
EYE_Y = 122          # eye centre line

# From face.cpp -> Face::paramsFor(), verbatim.
#             eyeW eyeH radius browSlant lowerLid upperLid
PRESETS = {
    "neutral":   dict(w=34, h=34, r=12, brow=0,   lower=0,  upper=0),
    "happy":     dict(w=36, h=36, r=12, brow=0,   lower=16, upper=0),
    "sad":       dict(w=32, h=26, r=10, brow=-9,  lower=0,  upper=4),
    "angry":     dict(w=34, h=24, r=8,  brow=10,  lower=0,  upper=0),
    "surprised": dict(w=38, h=44, r=19, brow=0,   lower=0,  upper=0),
    "sleepy":    dict(w=34, h=26, r=10, brow=0,   lower=0,  upper=14),
    "thinking":  dict(w=30, h=30, r=11, brow=0,   lower=0,  upper=5),
}
EMOTIONS = tuple(PRESETS)

# Keyword -> emotion, so his replies pick his own face.
MOODS = {
    "happy": ("happy", "good", "great", "glad", "love", "nice", "wonderful", "yes",
              "friend", "thank", "haha", "fun", "excited", "amazing", "yay"),
    "sad": ("sad", "sorry", "lonely", "miss", "bad bad", "unhappy", "hurt", "cry"),
    "angry": ("angry", "mad", "hate", "stupid", "furious", "no no", "grr"),
    "surprised": ("wow", "what", "really", "whoa", "suddenly", "oh", "amaze", "question"),
    "sleepy": ("sleep", "tired", "sleepy", "bed", "rest", "yawn"),
    "thinking": ("think", "maybe", "hmm", "wonder", "perhaps", "guess", "calculate"),
}


def mood_for(text: str) -> str:
    """Cheapest possible sentiment: first keyword hit wins."""
    low = text.lower()
    for mood, words in MOODS.items():
        if any(w in low for w in words):
            return mood
    return "neutral"


def _lerp(cur: float, target: float, factor: float) -> float:
    """The firmware's `approach()`, but frame-rate independent."""
    return cur + (target - cur) * factor


class Eyes:
    """Two eyes that morph between emotion presets."""

    def __init__(self) -> None:
        self.emotion = "neutral"
        self.p = dict(PRESETS["neutral"])
        self.pupil = 1.0                # pupil scale, follows the emotion
        self.gaze = [0.0, 0.0]          # saccade offset
        self.glint = 1.0                # glint visibility
        self.flourish = 0.0             # per-emotion accent ("!" pop, shake)

    def set_emotion(self, name: str) -> None:
        if name in PRESETS and name != self.emotion:
            self.emotion = name
            self.flourish = 1.0
            if name == "surprised":
                self.glint = 1.0

    def update(self, dt: float, *, amp: float = 0.0, blink: bool = False,
               t: float = 0.0, gaze=None, asleep: bool = False) -> None:
        target = dict(PRESETS["sleepy" if asleep else self.emotion])
        # exponential easing, ~0.15/frame at 60fps like the firmware
        k = 1.0 - math.exp(-9.0 * dt)

        if amp:  # speaking: swell and vibrate around the preset
            target["h"] += amp * 16
            target["w"] -= amp * 5
        if blink or asleep:
            target["h"] = 3 if not asleep else 2
            target["w"] = 34

        for key in ("w", "h", "r", "brow", "lower", "upper"):
            self.p[key] = _lerp(self.p[key], target[key], k)
        self.pupil = _lerp(self.pupil, PUPILS.get(self.emotion, 1.0), k)

        self.flourish = max(0.0, self.flourish - dt * 1.6)
        if gaze is not None:
            self.gaze[0] = _lerp(self.gaze[0], gaze[0], k)
            self.gaze[1] = _lerp(self.gaze[1], gaze[1], k)
        else:
            self.gaze[0] = _lerp(self.gaze[0], 0.0, k * 0.5)
            self.gaze[1] = _lerp(self.gaze[1], 0.0, k * 0.5)

    # --- drawing -------------------------------------------------------------
    def _eye_surface(self, w: int, h: int, r: int, color):
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(s, color, (0, 0, w, h), border_radius=r)
        return s

    def _draw_one(self, surface, center, w, h, r, lower, upper, jitter_x=0.0, glow=0.5,
                  pupil: float = 1.0):
        w, h = max(2, int(w)), max(2, int(h))
        r = max(1, min(int(r), w // 2, h // 2))
        eye = self._eye_surface(w, h, r, EYE)

        # Lids punch *transparent* holes rather than painting background colour,
        # so the silhouette and the bloom both follow the visible eye.
        cut_top = min(h, int(upper)) if upper > 0 else 0
        cut_bot = min(h, int(lower)) if lower > 0 else 0
        vis_top, vis_h = cut_top, h - cut_top - cut_bot

        # Black pupil, painted into the sclera so the lids clip it as well. It
        # tracks the centre of the *visible* band, so a heavy lid looks like the
        # eye is looking down instead of like a blank slice.
        pr, pc_y = 0, h // 2
        if vis_h >= 10 and w >= 12:
            pr = max(3, int(min(w, vis_h) * 0.36 * pupil))
            pc_y = cut_top + vis_h // 2
            pygame.draw.circle(eye, PUPIL, (w // 2, pc_y), pr)

        if cut_top:
            eye.fill((0, 0, 0, 0), (0, 0, w, cut_top))
        if cut_bot:
            eye.fill((0, 0, 0, 0), (0, h - cut_bot, w, cut_bot))

        cx = center[0] + int(jitter_x)
        # bloom: scaled copies of the visible shape, so lids do not glow
        for scale, alpha in ((1.26, 16), (1.13, 30)):
            sw, sh = max(1, int(w * scale)), max(1, int(h * scale))
            halo = pygame.transform.smoothscale(eye, (sw, sh))
            halo.set_alpha(int(alpha * glow * 2))
            surface.blit(halo, (cx - sw // 2, center[1] - sh // 2))
        surface.blit(eye, (cx - w // 2, center[1] - h // 2))

        # Highlight sits on the pupil.
        if pr and self.glint > 0.05:
            gr = max(2, int(pr * 0.30))
            gx = cx - int(pr * 0.34)
            gy = center[1] - h // 2 + pc_y - int(pr * 0.40)
            if gy - gr >= center[1] - h // 2 + vis_top:
                dot = pygame.Surface((gr * 2, gr * 2), pygame.SRCALPHA)
                pygame.draw.circle(dot, (*GLINT, int(225 * self.glint)), (gr, gr), gr)
                surface.blit(dot, (gx - gr, gy - gr))

    def draw(self, surface, t: float = 0.0, glow: float = 0.5) -> None:
        p = self.p
        w, h, r = p["w"] * SCALE, p["h"] * SCALE, p["r"] * SCALE
        lower, upper = p["lower"] * SCALE, p["upper"] * SCALE
        cx = surface.get_width() // 2
        jitter = 0.0
        if self.emotion == "angry":
            jitter = math.sin(t * 42) * 1.6 * (0.4 + 0.6 * self.flourish)
        pop = 1.0 + (0.10 * self.flourish if self.emotion == "surprised" else 0.0)

        for side, dx in ((-1, -EYE_DX), (1, EYE_DX)):
            center = (cx + dx + int(self.gaze[0]), EYE_Y + int(self.gaze[1]))
            ew, eh = w * pop, h * pop
            self._draw_one(surface, center, ew, eh, r, lower, upper, jitter, glow,
                           self.pupil)

        # eyebrows, slanted by the preset
        brow = p["brow"] * SCALE
        if abs(brow) > 0.6:
            for dx in (-EYE_DX, EYE_DX):
                bar = pygame.Surface((int(w * 1.02), 11), pygame.SRCALPHA)
                pygame.draw.rect(bar, (*BROW, 240), bar.get_rect(), border_radius=5)
                # inner edge drops for angry, lifts for sad
                angle = brow if dx < 0 else -brow
                rot = pygame.transform.rotate(bar, -angle)
                rect = rot.get_rect(center=(cx + dx, int(EYE_Y - h * 0.68 - self.gaze[1])))
                surface.blit(rot, rect)


def selftest(outdir: str) -> None:
    """Render one frame per emotion, plus blink and speaking variants."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    W, H = 520, 300
    pygame.display.set_mode((W, H))
    screen = pygame.display.get_surface()
    font = pygame.font.SysFont("menlo,monospace", 13)
    os.makedirs(outdir, exist_ok=True)

    frames = []
    for name in EMOTIONS:
        e = Eyes()
        e.emotion = name
        e.p = dict(PRESETS[name])          # skip the morph for a crisp reference
        e.pupil = PUPILS[name]
        screen.fill(BG)
        e.draw(screen, 0.0, glow=0.5)
        screen.blit(font.render(name, True, DIM), (16, 16))
        path = os.path.join(outdir, f"emotion_{name}.png")
        pygame.image.save(screen, path)
        frames.append(path)

    # speaking + blink composites
    e = Eyes()
    e.set_emotion("happy")
    for label, kwargs in (("speaking", dict(amp=0.8)), ("blink", dict(blink=True))):
        screen.fill(BG)
        for _ in range(40):                 # let the morph settle
            e.update(1 / 60, t=0.4, **kwargs)
        e.draw(screen, 0.4, glow=0.9)
        screen.blit(font.render("happy/" + label, True, DIM), (16, 16))
        path = os.path.join(outdir, f"emotion_happy_{label}.png")
        pygame.image.save(screen, path)
        frames.append(path)

    # mood inference check
    print("[selftest] mood_for:", {s: mood_for(s) for s in
          ("I am very happy!", "This is bad bad bad", "What? question?", "I am tired")})
    print("[selftest] " + os.pathsep.join(frames))
    pygame.quit()


def main() -> None:
    ap = argparse.ArgumentParser(description="Rocky eyes")
    ap.add_argument("--selftest", metavar="DIR", help="render one PNG per emotion")
    args = ap.parse_args()
    if args.selftest:
        selftest(args.selftest)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()

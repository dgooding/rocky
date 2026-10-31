#!/usr/bin/env python3
"""Rocky's HUD — a JARVIS-style face for the desk companion.

Pure rendering. No audio, no brain, no threads: hand `draw()` a surface, a
HUDState and the frame clock, and it paints. `python rocky_hud.py` renders one
frame per phase into shots/hud/ for review.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field

import numpy as np
import pygame
import pygame.gfxdraw

# --- palette (docs/HUD.md) --------------------------------------------------
BG = (5, 8, 14)
PANEL = (13, 19, 29)
PANEL_EDGE = (38, 54, 74)
ACCENT = (70, 230, 255)
ACCENT_DIM = (24, 92, 112)
AMBER = (255, 194, 75)
WARN = (255, 190, 100)
REC = (255, 100, 100)
OK = (120, 245, 180)
INK = (238, 246, 255)
DIM = (126, 146, 176)

FONT = "menlo"
MICRO, BODY, LABEL, READOUT = 11, 13, 15, 28

PHASES = ("idle", "listening", "thinking", "speaking", "asleep")

PHASE_LABEL = {
    "idle": "STANDING BY",
    "listening": "LISTENING",
    "thinking": "PROCESSING",
    "speaking": "SPEAKING",
    "asleep": "ASLEEP",
}

PHASE_COLOR = {
    "idle": ACCENT_DIM,
    "listening": ACCENT,
    "thinking": AMBER,
    "speaking": ACCENT,
    "asleep": (40, 58, 82),
}


@dataclass
class HUDState:
    """Everything the HUD is allowed to draw. All fields optional."""

    phase: str = "idle"
    transcript: list = field(default_factory=list)   # [(who, text), ...] oldest first
    note: str = ""
    typed: str = ""
    amplitude: float = 0.0      # playback RMS 0..1 (Rocky speaking)
    mic_level: float = 0.0      # input RMS 0..1 (you speaking)
    telemetry: dict = field(default_factory=dict)    # cpu, mem, net: floats 0..1
    latency: dict = field(default_factory=dict)      # stt, brain, tts: seconds
    camera: bool = False
    watching: bool = False
    face: tuple | None = None                        # (x, y) in -1..1
    awake_left: float = 0.0                          # seconds of hands-free left
    reduced_motion: bool = False


def layout_for(size):
    """Panel rectangles for a canvas of `size`, scaled from the 1600x900 design."""
    w, h = size
    m = max(10, round(w * 0.025))
    header = max(20, round(h * 0.062))
    gap = max(8, round(h * 0.027))
    top = m + header
    cmd_h = max(40, round(h * 0.084))
    command = pygame.Rect(m, h - m - cmd_h, w - 2 * m, cmd_h)
    bottom = command.top - gap
    col_h = bottom - top

    left_w = round(w * 0.275)
    right_w = round(w * 0.2875)
    transcript = pygame.Rect(m, top, left_w, col_h)

    rx = w - m - right_w
    telemetry = pygame.Rect(rx, top, right_w, round(col_h * 0.38))
    status = pygame.Rect(rx, telemetry.bottom + gap, right_w, round(col_h * 0.26))
    latency = pygame.Rect(rx, status.bottom + gap, right_w,
                          bottom - status.bottom - gap)

    cx = (transcript.right + rx) // 2
    cy = (top + bottom) // 2
    radius = max(40, min(rx - transcript.right, col_h) // 2 - round(h * 0.045))
    return {
        "size": size, "margin": m, "core": (cx, cy), "radius": radius,
        "transcript": transcript, "telemetry": telemetry, "status": status,
        "latency": latency, "command": command,
    }


class HUD:
    """Draws one frame. Owns cached surfaces; holds only animation phase."""

    def __init__(self, size=(1600, 900)):
        self.size = size
        self.layout = layout_for(size)
        self.font_micro = pygame.font.SysFont(FONT, MICRO)
        self.font_body = pygame.font.SysFont(FONT, BODY)
        self.font_label = pygame.font.SysFont(FONT, LABEL)
        self.font_readout = pygame.font.SysFont(FONT, READOUT)
        self._chrome = None
        self._glow: dict = {}
        self._angle = 0.0            # accumulated rotation, degrees
        self._pulse = 0.0            # accumulated pulse phase, radians
        self._text_cache: dict = {}

    # -- caches ------------------------------------------------------------
    def _surface(self, size):
        surf = pygame.Surface(size, pygame.SRCALPHA)
        return surf.convert_alpha()

    def glow(self, colour, radius):
        """Pre-rendered radial falloff, blitted with BLEND_ADD. Cached."""
        key = (colour, radius)
        hit = self._glow.get(key)
        if hit is not None:
            return hit
        # an exact radial falloff; drawing concentric circles here accumulates
        # alpha and turns the glow into a flat disc
        # BLEND_ADD ignores per-pixel alpha on an opaque target, so the falloff
        # has to live in the RGB itself; black adds nothing.
        size = radius * 2
        yy, xx = np.mgrid[0:size, 0:size]
        d = np.sqrt((xx - radius) ** 2 + (yy - radius) ** 2) / max(1, radius)
        falloff = np.clip(1.0 - d, 0.0, 1.0) ** 2.4
        buf = np.zeros((size, size, 4), dtype=np.uint8)
        for i in range(3):
            buf[..., i] = (colour[i] * falloff).astype(np.uint8)
        buf[..., 3] = 255
        surf = pygame.image.frombuffer(buf.tobytes(), (size, size), "RGBA").convert_alpha()
        self._glow[key] = surf
        return surf

    def text(self, font, string, colour):
        key = (id(font), string, colour)
        hit = self._text_cache.get(key)
        if hit is None:
            hit = font.render(string, True, colour)
            if len(self._text_cache) > 512:
                self._text_cache.clear()
            self._text_cache[key] = hit
        return hit

    # -- static chrome -----------------------------------------------------
    def _build_chrome(self):
        w, h = self.size
        surf = pygame.Surface((w, h)).convert()
        surf.fill(BG)

        grid = self._surface((w, h))
        step = max(16, round(w / 64))
        for x in range(0, w, step):
            pygame.draw.line(grid, (*PANEL_EDGE, 26), (x, 0), (x, h))
        for y in range(0, h, step):
            pygame.draw.line(grid, (*PANEL_EDGE, 26), (0, y), (w, y))
        surf.blit(grid, (0, 0))

        L = self.layout
        for name in ("transcript", "telemetry", "status", "latency", "command"):
            rect = L[name]
            panel = self._surface(rect.size)
            panel.fill((*PANEL, 210))
            pygame.draw.rect(panel, PANEL_EDGE, panel.get_rect(), 1)
            surf.blit(panel, rect.topleft)
            # bracket on the panel's top-left, the HUD tell
            pygame.draw.line(surf, ACCENT, (rect.left, rect.top), (rect.left + 18, rect.top), 2)
            pygame.draw.line(surf, ACCENT, (rect.left, rect.top), (rect.left, rect.top + 18), 2)

        # outer frame corners
        m = L["margin"]
        span = max(20, m)
        for (x, y, dx, dy) in ((m, m, 1, 1), (w - m, m, -1, 1),
                               (m, h - m, 1, -1), (w - m, h - m, -1, -1)):
            pygame.draw.line(surf, ACCENT, (x, y), (x + dx * span, y), 2)
            pygame.draw.line(surf, ACCENT, (x, y), (x, y + dy * span), 2)

        # vignette-free scanlines, baked once
        scan = self._surface((w, h))
        for y in range(0, h, 3):
            pygame.draw.line(scan, (0, 0, 0, 26), (0, y), (w, y))
        surf.blit(scan, (0, 0))
        return surf

    # -- pieces ------------------------------------------------------------
    def _arc(self, surface, cx, cy, r_in, r_out, a0, a1, colour, steps=None):
        """Thick antialiased ring segment. pygame.draw.arc is not antialiased."""
        if a1 - a0 < 0.6:
            return
        steps = steps or max(3, int(abs(a1 - a0) / 4))
        pts = []
        for i in range(steps + 1):
            a = math.radians(a0 + (a1 - a0) * i / steps)
            pts.append((cx + r_out * math.cos(a), cy + r_out * math.sin(a)))
        for i in range(steps, -1, -1):
            a = math.radians(a0 + (a1 - a0) * i / steps)
            pts.append((cx + r_in * math.cos(a), cy + r_in * math.sin(a)))
        pts = [(int(x), int(y)) for x, y in pts]
        rgb = tone(colour)
        pygame.gfxdraw.filled_polygon(surface, pts, rgb)
        pygame.gfxdraw.aapolygon(surface, pts, rgb)

    def _ring(self, surface, cx, cy, radius, width, colour, angle, dashes, duty):
        seg = 360.0 / dashes
        for i in range(dashes):
            start = angle + i * seg
            self._arc(surface, cx, cy, radius, radius + width,
                      start, start + seg * duty, colour)

    def _ticks(self, surface, cx, cy, radius, colour, count=60, length=6, angle=0.0):
        for i in range(count):
            a = math.radians(angle + i * 360.0 / count)
            x0, y0 = cx + radius * math.cos(a), cy + radius * math.sin(a)
            x1, y1 = cx + (radius + length) * math.cos(a), cy + (radius + length) * math.sin(a)
            pygame.draw.line(surface, colour, (x0, y0), (x1, y1), 1)

    def _core(self, screen, t, dt, st):
        cx, cy = self.layout["core"]
        r = self.layout["radius"]
        phase = st.phase if st.phase in PHASE_COLOR else "idle"
        colour = PHASE_COLOR[phase]

        if not st.reduced_motion:
            self._angle = (self._angle + dt * 360.0 * (0.02 if phase == "asleep" else 0.09)) % 360.0
            self._pulse += dt

        amp = max(st.amplitude, st.mic_level if phase == "listening" else 0.0)
        breathe = 0.5 + 0.5 * math.sin(self._pulse * (1.1 if phase == "asleep" else 2.4))
        energy = amp if phase in ("listening", "speaking") else breathe * 0.35
        if st.reduced_motion:
            energy = 0.35

        # glow behind the core
        g = self.glow(colour, r)
        g.set_alpha(int(95 + 70 * energy))
        screen.blit(g, (cx - r, cy - r), special_flags=pygame.BLEND_ADD)

        # outer tick ring
        self._ticks(screen, cx, cy, r, (*colour, 90), count=72, length=5, angle=self._angle)
        self._ticks(screen, cx, cy, r - 14, (*PANEL_EDGE, 200), count=72, length=3, angle=-self._angle * 0.6)

        # three concentric dashed rings, counter-rotating
        self._ring(screen, cx, cy, r - 40, 2, colour, self._angle, 12, 0.55)
        self._ring(screen, cx, cy, r - 78, 6, colour, -self._angle * 1.7, 6, 0.35)
        self._ring(screen, cx, cy, r - 112, 2, (*colour, 150), self._angle * 2.3, 24, 0.25)

        # progress arc whose sweep is the live energy
        sweep = 40 + 260 * energy
        self._arc(screen, cx, cy, r - 150, r - 150 + 10, -90, -90 + sweep, colour)

        # inner aperture
        inner = max(18, r - 190)
        pygame.draw.circle(screen, (*color_mix(colour, BG, 0.82), 255), (cx, cy), inner)
        pygame.draw.circle(screen, colour, (cx, cy), inner, 1)
        pygame.draw.circle(screen, colour, (cx, cy), max(3, int(inner * 0.18 + inner * 0.22 * energy)))

        label = self.text(self.font_micro, PHASE_LABEL[phase], colour)
        screen.blit(label, (cx - label.get_width() // 2, cy + r - 34))

    def _panel_title(self, screen, rect, title):
        label = self.text(self.font_micro, title, DIM)
        screen.blit(label, (rect.left + 12, rect.top + 9))
        pygame.draw.line(screen, PANEL_EDGE, (rect.left + 8, rect.top + 26),
                         (rect.right - 8, rect.top + 26), 1)

    def _wrap(self, text, font, width):
        words, lines, cur = text.split(), [], ""
        for word in words:
            trial = f"{cur} {word}".strip()
            if font.size(trial)[0] <= width or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        return lines

    def _transcript(self, screen, st):
        rect = self.layout["transcript"]
        self._panel_title(screen, rect, "TRANSCRIPT")
        y = rect.top + 34
        limit = rect.bottom - 12
        rows = list(st.transcript)[-14:]
        if not rows:
            hint = self.text(self.font_body, "nothing said yet", (*DIM, 150))
            screen.blit(hint, (rect.left + 12, y))
            return
        for who, text in rows:
            colour = ACCENT if who == "rocky" else DIM
            tag = self.text(self.font_micro, "ROCKY" if who == "rocky" else "YOU", colour)
            screen.blit(tag, (rect.left + 12, y))
            y += 14
            for line in self._wrap(text, self.font_body, rect.width - 28):
                if y > limit - 14:
                    return
                screen.blit(self.text(self.font_body, line, INK if who == "rocky" else (*DIM, 255)),
                            (rect.left + 12, y))
                y += 17
            y += 8

    def _bars(self, screen, rect, rows):
        self._panel_title(screen, rect, "SYSTEM")
        y = rect.top + 34
        for name, value in rows:
            label = self.text(self.font_micro, name.upper(), DIM)
            screen.blit(label, (rect.left + 12, y))
            bar = pygame.Rect(rect.left + 12, y + 15, rect.width - 24, 6)
            pygame.draw.rect(screen, (*PANEL_EDGE, 255), bar, 1)
            fill = int((bar.width - 2) * max(0.0, min(1.0, value)))
            if fill > 0:
                colour = REC if value > 0.85 else (WARN if value > 0.65 else ACCENT)
                pygame.draw.rect(screen, colour, (bar.x + 1, bar.y + 1, fill, bar.height - 2))
            pct = self.text(self.font_micro, f"{value * 100:3.0f}%", INK)
            screen.blit(pct, (rect.right - 12 - pct.get_width(), y - 1))
            y += 40

    def _status(self, screen, st):
        rect = self.layout["status"]
        self._panel_title(screen, rect, "SENSES")
        y = rect.top + 34
        rows = [
            ("mic", st.phase == "listening", "on" if st.phase == "listening" else "off"),
            ("camera", st.camera, "on" if st.camera else "off"),
            ("tracking", st.watching, "on" if st.watching else "off"),
        ]
        for name, on, word in rows:
            dot = OK if on else PANEL_EDGE
            pygame.draw.circle(screen, dot, (rect.left + 18, y + 6), 4)
            screen.blit(self.text(self.font_body, name, INK), (rect.left + 30, y))
            value = self.text(self.font_micro, word.upper(), OK if on else DIM)
            screen.blit(value, (rect.right - 12 - value.get_width(), y + 1))
            y += 24
        if st.face is not None:
            box = pygame.Rect(rect.left + 12, rect.bottom - 44, rect.width - 24, 30)
            pygame.draw.rect(screen, (*PANEL_EDGE, 255), box, 1)
            for i in range(1, 4):
                x = box.left + box.width * i / 4
                pygame.draw.line(screen, (*PANEL_EDGE, 160), (x, box.top + 1), (x, box.bottom - 1), 1)
            px = box.centerx + int(max(-1.0, min(1.0, st.face[0])) * (box.width / 2 - 6))
            py = box.centery + int(max(-1.0, min(1.0, st.face[1])) * (box.height / 2 - 5))
            pygame.draw.circle(screen, ACCENT, (px, py), 4)

    def _latency(self, screen, st):
        rect = self.layout["latency"]
        self._panel_title(screen, rect, "LATENCY")
        y = rect.top + 34
        for name, value in (("STT", st.latency.get("stt")),
                            ("BRAIN", st.latency.get("brain")),
                            ("VOICE", st.latency.get("tts"))):
            screen.blit(self.text(self.font_micro, name, DIM), (rect.left + 12, y))
            shown = "—" if value is None else (f"{value * 1000:.0f} ms" if value < 10 else f"{value:.1f} s")
            reading = self.text(self.font_label, shown, INK if value is not None else DIM)
            screen.blit(reading, (rect.right - 12 - reading.get_width(), y - 3))
            y += 30

        if st.awake_left > 0:
            bar = pygame.Rect(rect.left + 12, y + 4, rect.width - 24, 4)
            pygame.draw.rect(screen, (*PANEL_EDGE, 255), bar, 1)
            frac = max(0.0, min(1.0, st.awake_left / 60.0))
            pygame.draw.rect(screen, ACCENT, (bar.x + 1, bar.y + 1, int((bar.width - 2) * frac), 2))
            caption = self.text(self.font_micro, f"AWAKE {st.awake_left:.0f}s", DIM)
            screen.blit(caption, (rect.left + 12, y + 12))

    def _command(self, screen, t, st):
        rect = self.layout["command"]
        caret_on = (t * 2) % 2 < 1.0
        x = rect.left + 14
        y = rect.top + 16
        prompt = self.text(self.font_body, ">", ACCENT)
        screen.blit(prompt, (x, y))
        x += 18
        line = st.typed or st.note or ""
        colour = INK if st.typed else DIM
        avail = rect.width - 40 - 340        # keep clear of the key legend
        full = line
        while line and self.font_body.size(line)[0] > avail:
            line = line[:-1]
        if line != full:
            line = line[:-3].rstrip() + "..."
        surface = self.text(self.font_body, line, colour)
        screen.blit(surface, (x, y))
        if st.phase == "listening" and caret_on:
            cw = surface.get_width() if st.typed else 0
            pygame.draw.line(screen, ACCENT, (x + cw + 2, y + 1), (x + cw + 2, y + 14), 1)

        legend = "F1 hold-talk   F2 talk   F3 look   F4 hands-free   F5 watch   ESC quit"
        hint = self.text(self.font_micro, legend, DIM)
        screen.blit(hint, (rect.right - 14 - hint.get_width(), rect.top + 20))

    def _header(self, screen, st):
        m = self.layout["margin"]
        title = self.text(self.font_label, "R O C K Y", INK)
        screen.blit(title, (m + 4, m + 2))
        sub = self.text(self.font_micro, "DESK COMPANION // LOCAL", DIM)
        screen.blit(sub, (m + 4, m + 24))
        phase = PHASE_LABEL.get(st.phase, "STANDING BY")
        chip = self.text(self.font_micro, phase, PHASE_COLOR.get(st.phase, ACCENT))
        box = pygame.Rect(0, 0, chip.get_width() + 20, 22)
        box.topright = (self.size[0] - m - 4, m + 6)
        pygame.draw.rect(screen, color_mix(PHASE_COLOR.get(st.phase, ACCENT), PANEL, 0.86), box, border_radius=3)
        pygame.draw.rect(screen, PHASE_COLOR.get(st.phase, ACCENT), box, 1, border_radius=3)
        screen.blit(chip, (box.x + 10, box.y + 5))

    # -- frame -------------------------------------------------------------
    def draw(self, screen, t, dt, st):
        if self._chrome is None:
            self._chrome = self._build_chrome()
        screen.blit(self._chrome, (0, 0))
        self._core(screen, t, dt, st)
        self._transcript(screen, st)
        self._bars(screen, self.layout["telemetry"], [
            ("cpu", st.telemetry.get("cpu", 0.0)),
            ("memory", st.telemetry.get("mem", 0.0)),
            ("network", st.telemetry.get("net", 0.0)),
        ])
        self._status(screen, st)
        self._latency(screen, st)
        self._command(screen, t, st)
        self._header(screen, st)


def color_mix(a, b, f):
    return tuple(int(a[i] * (1 - f) + b[i] * f) for i in range(3))


def tone(colour):
    """Flatten an RGBA colour onto the background — gfxdraw ignores alpha."""
    if len(colour) == 4:
        return color_mix(colour[:3], BG, 1.0 - colour[3] / 255.0)
    return tuple(colour[:3])


def render_phases(outdir="shots/hud"):
    os.makedirs(outdir, exist_ok=True)
    pygame.init()
    size = (1600, 900)
    screen = pygame.display.set_mode(size)
    hud = HUD(size)
    sample = [("you", "hey rocky, what am i holding?"),
              ("rocky", "A black coffee mug, still steaming."),
              ("you", "look left and tell me if the window is open.")]
    for phase in PHASES:
        st = HUDState(
            phase=phase,
            transcript=sample if phase != "idle" else [],
            note="" if phase != "asleep" else "say \"hey rocky\"",
            typed="what do you see" if phase == "listening" else "",
            amplitude=0.55 if phase == "speaking" else 0.0,
            mic_level=0.4 if phase == "listening" else 0.0,
            telemetry={"cpu": 0.31, "mem": 0.62, "net": 0.12},
            latency={"stt": 0.42, "brain": 1.8 if phase != "idle" else None, "tts": 0.35},
            camera=phase in ("listening", "speaking"),
            watching=phase == "speaking",
            face=(-0.2, 0.1) if phase in ("listening", "speaking") else None,
            awake_left=42.0 if phase != "asleep" else 0.0,
        )
        st.reduced_motion = False
        for i in range(12):          # settle animation so frames differ per phase
            st.phase = phase
            hud.draw(screen, i / 60.0, 1 / 60.0, st)
        path = os.path.join(outdir, f"{phase}.png")
        pygame.image.save(screen, path)
        print(f"[hud] {path}")
    pygame.quit()


if __name__ == "__main__":
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    render_phases()

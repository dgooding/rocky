# Rocky HUD

The desktop window is a JARVIS-style HUD drawn with pygame. `rocky_hud.py` owns
all drawing; `rocky_desktop_app.py` owns state and calls `rocky_hud.HUD.draw()`
once per frame. No GUI toolkit, no new dependencies.

    ./venv/bin/python rocky_hud.py      # five state frames -> shots/hud/

## Palette

| Name | Hex | Role |
|---|---|---|
| `BG` | `#05080E` | canvas |
| `PANEL` | `#0D131D` | panel fill |
| `PANEL_EDGE` | `#263648` | panel borders, grid |
| `ACCENT` | `#46E6FF` | listening, speaking, brackets, values |
| `ACCENT_DIM` | `#185C70` | idle state |
| `AMBER` | `#FFC24B` | thinking |
| `WARN` | `#FFBE64` | telemetry above 65% |
| `REC` | `#FF6464` | telemetry above 85% |
| `OK` | `#78F5B4` | sense "on" dots |
| `INK` | `#EEF6FF` | values, transcript |
| `DIM` | `#7E92B0` | labels, metadata |

Cyan on near-black. Green never means "speaking" — it means "ok".

## Type

Menlo via `pygame.font.SysFont`. Micro-labels are uppercase.

| px | Use |
|---|---|
| 11 | panel titles, axis labels, legend, phase chip |
| 13 | transcript body, sense rows |
| 15 | window title, latency readings |
| 28 | reserved for a future large readout |

## Layout (1600x900)

All rectangles are computed by `layout_for()` from the window size, not
hardcoded. Values below are for the design size.

| name | x | y | w | h |
|---|---|---|---|---|
| transcript | 40 | 96 | 440 | 664 |
| telemetry | 1100 | 96 | 460 | 252 |
| status | 1100 | 372 | 460 | 173 |
| latency | 1100 | 569 | 460 | 191 |
| command | 40 | 784 | 1520 | 76 |
| core | centre (790, 428) | | radius 270 | |

## Motion

| phase | colour | rotation | behaviour |
|---|---|---|---|
| idle | `ACCENT_DIM` | 0.09 turn/s | slow breathe |
| listening | `ACCENT` | 0.09 turn/s | mic RMS drives ring energy |
| thinking | `AMBER` | 0.09 turn/s | same, amber |
| speaking | `ACCENT` | 0.09 turn/s | playback RMS drives ring energy |
| asleep | deep blue | 0.02 turn/s | dim, 1.1 Hz breathe |

Counter-rotating dashed rings at fixed radii; a progress arc sweeps 40°-300°
with energy; a 1 Hz-safe radar needle rotates once per 3.1 turns.
`--reduce-motion` freezes rotation, sweeps and pulses for photosensitive
users. Nothing flashes faster than 3 Hz.

## Rendering rules

- Static chrome (background, grid, panel frames, brackets, scanlines, panel
  titles) is baked once into a `Surface` by `_build_chrome()`. Never redraw it.
- Glow is one pre-rendered radial falloff per (colour, radius), blitted with
  `BLEND_ADD`. The falloff lives in RGB, not alpha: `BLEND_ADD` ignores
  per-pixel alpha on an opaque target, which turns an alpha glow into a square.
- Thick arcs are ring-segment polygons through `gfxdraw.aapolygon` +
  `filled_polygon`. `pygame.draw.arc(width=)` is not antialiased, and
  `gfxdraw.filled_arc` does not exist.
- Measured drawing cost at 1600x900: **0.7 ms/frame** (1400 fps headless), so
  the frame budget is spent on `display.flip()`, not on the HUD.

## Data

Every panel reads real state from `rocky_desktop_app.py` globals; a missing
value renders as `—`, never as a plausible-looking fake.

| panel | source |
|---|---|
| transcript | `transcript` deque, appended by `remember()` |
| system | `telemetry`, sampled at 1 Hz by `_telemetry_loop()` |
| senses | phase, `Watcher.enabled`, `face_pos` |
| latency | `latency["stt" | "brain" | "tts"]`, plus `awake_until` countdown |
| command | `note`, `typed`, `phase` |

# Notice and attribution

This repository is a derivative of
[`Kuberwastaken/rocky-tts`](https://github.com/Kuberwastaken/rocky-tts).

## Original work

- `rocky_say.py`, the Rocky grammar transform, the XTTS/RVC voice pipeline, and
  the original voice training assets were created by **Pedram Amini** and
  published through the upstream `rocky-tts` project.
- The upstream project is licensed under **Creative Commons
  Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)**. See
  [`LICENSE`](LICENSE).

## Rocky character and voice

Rocky is a character from *Project Hail Mary*. The character design and voice
are the intellectual property of the film production company. The voice
training audio and RVC model are provided for **personal, non-commercial use
only**. They are not included in this repository and must not be redistributed.

## Coqui XTTS v2

The voice path uses Coqui XTTS v2, which is licensed under the **Coqui Public
Model License (CPML)**. The CPML is non-commercial. Review it before any use
beyond personal experimentation.

## Eye presets

The eye presets are inspired by Casey Grothaus's desk robot
([`cgro00/desk-robot`](https://github.com/cgro00/desk-robot), MIT). The Python
renderer and app integration in this repository are local work.

## This repository

The desktop app, eye renderer, camera path, streaming brain integration, tests,
and documentation in this repository are provided under the same CC BY-NC 4.0
terms as the upstream work, to the extent permitted by the original license.

## No warranty

This software is provided "as is", without warranty of any kind. See the
LICENSE for the full text.

## Asset policy

Do **not** commit:

```text
assets/rocky_ref_15s.wav
assets/rocky_training_audio_scrubbed.wav
assets/rocky_voice.pth
assets/*.mp3
```

Restore them locally with `scripts/restore_assets.sh` from a private backup.

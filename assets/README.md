# Voice assets

This directory is intentionally empty in the public repository.

Place these files here from your private backup, or download them:

```text
assets/rocky_ref_15s.wav              # preferred 15 s voice reference
assets/rocky_training_audio_scrubbed.wav
assets/rocky_voice.pth                # RVC model (optional for the XTTS path)
```

Download (from the upstream author's published links, never from this repo):

```sh
./scripts/fetch_assets.sh
```

It confirms personal, non-commercial use, checks each file's type, makes
`rocky_ref_15s.wav` from the first 15 s of speech if you do not already have
one, and never overwrites existing files.

Restore from your own backup instead:

```sh
./scripts/restore_assets.sh /path/to/your/rocky-assets
# or, if you have the original archive:
./scripts/restore_assets.sh ../archives/rocky-tts-2026-10-21.tar.gz
```

The script copies the files, verifies they are non-empty, and prints a license
warning. It does not download anything; `fetch_assets.sh` does.

## Why these are not committed

- The upstream project is **CC BY-NC 4.0** (non-commercial).
- Rocky's voice design is the intellectual property of the *Project Hail Mary*
  film production.
- The training audio and RVC model are for personal, non-commercial use only.
- XTTS v2 / Coqui TTS is non-commercial under the CPML.

Do not commit these files, do not redistribute them, and do not use them
commercially. See [`../NOTICE.md`](../NOTICE.md) and [`../LICENSE`](../LICENSE).

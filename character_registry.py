"""Character Registry for Rocky: dynamic multi-character persona management.

Loads character manifests from characters/*.json with zero code edits.
Supports wake-word routing, custom persona prompts, speech styles, and voices.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class CharacterSpec:
    id: str
    order: int = 10
    name: str = "Rocky"
    title: str = "Rocky"
    wake_words: List[str] = field(default_factory=lambda: ["rocky", "hey rocky"])
    voice_engine: str = "kokoro"
    voice_name: str = "bf_emma"
    speed: float = 1.0
    speech_style: str = "eridian"
    system_prompt: str = ""
    wake_reply: str = "I am here, friend."
    sleep_reply: str = "Goodnight, friend."
    common_openers: List[str] = field(default_factory=list)


class CharacterRegistry:
    def __init__(self, characters_dir: str | None = None) -> None:
        if characters_dir is None:
            characters_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "characters")
        self.characters_dir = characters_dir
        self._characters: Dict[str, CharacterSpec] = {}
        self.default_id = "aura"
        self.load()

    def load(self) -> None:
        """Scan characters_dir and load all non-underscore .json files."""
        if not os.path.isdir(self.characters_dir):
            os.makedirs(self.characters_dir, exist_ok=True)

        loaded: Dict[str, CharacterSpec] = {}
        try:
            for fname in sorted(os.listdir(self.characters_dir)):
                if not fname.endswith(".json") or fname.startswith("_"):
                    continue
                fpath = os.path.join(self.characters_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    cid = data.get("id") or os.path.splitext(fname)[0]
                    v_info = data.get("voice", {})
                    p_info = data.get("persona", {})

                    spec = CharacterSpec(
                        id=cid,
                        order=data.get("order", 10),
                        name=data.get("name", cid.capitalize()),
                        title=data.get("title", cid.capitalize()),
                        wake_words=[w.lower().strip() for w in data.get("wake_words", [cid])],
                        voice_engine=v_info.get("engine", "kokoro"),
                        voice_name=v_info.get("name") or v_info.get("kokoro_voice", "bf_emma"),
                        speed=float(v_info.get("speed", 1.0)),
                        speech_style=p_info.get("speech_style", "clean"),
                        system_prompt=p_info.get("system_prompt", ""),
                        wake_reply=p_info.get("wake_reply") or "I am here, friend.",
                        sleep_reply=p_info.get("sleep_reply") or "Goodnight, friend.",
                        common_openers=p_info.get("common_openers", []),
                    )
                    loaded[cid] = spec
                except Exception as e:
                    print(f"[character_registry] failed to load {fname}: {e}")
        except OSError:
            pass

        self._characters = loaded
        if "aura" in self._characters:
            self.default_id = "aura"
        elif "rocky" in self._characters:
            self.default_id = "rocky"
        elif self._characters:
            self.default_id = next(iter(self._characters))

    def get(self, character_id: str) -> CharacterSpec | None:
        return self._characters.get(character_id)

    def default(self) -> CharacterSpec:
        if self.default_id in self._characters:
            return self._characters[self.default_id]
        return CharacterSpec(id="aura", name="Aura")

    def all_specs(self) -> List[CharacterSpec]:
        return sorted(self._characters.values(), key=lambda c: (c.order, c.id))

    def find_by_wake(self, text: str) -> Tuple[Optional[CharacterSpec], str]:
        """Check if utterance addresses any registered character.

        Returns (CharacterSpec, stripped_text) if matched, or (None, text).
        """
        clean_text = text.strip()
        lower_text = clean_text.lower()

        # Prioritize longest wake words first to avoid partial prefix collisions
        candidates = []
        for spec in self.all_specs():
            for w in spec.wake_words:
                candidates.append((len(w), w, spec))
        candidates.sort(reverse=True, key=lambda x: x[0])

        for _, wake, spec in candidates:
            # Pattern: start of sentence or after greeting e.g. "hey rocky", "rocky, ..."
            pattern = re.compile(
                rf"^(?:(?:hey|hi|hello|ok|okay)\s+)?{re.escape(wake)}\b[\s,.!?]*",
                re.IGNORECASE,
            )
            m = pattern.search(lower_text)
            if m:
                # Matched at start of text
                remainder = clean_text[m.end():].lstrip(" ,:;-")
                return spec, remainder

            # Mid-sentence address e.g. "... hey TARS, what time is it?"
            mid_pattern = re.compile(
                rf"\b(?:hey|hi|hello)\s+{re.escape(wake)}\b[\s,.!?]*",
                re.IGNORECASE,
            )
            m_mid = mid_pattern.search(lower_text)
            if m_mid:
                remainder = clean_text[m_mid.end():].lstrip(" ,:;-")
                return spec, remainder

        return None, text

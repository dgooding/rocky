"""Persona speech filters, emotion classification, and wake-phrase parsing.

Strips LLM artifacts (markdown asterisks, bullets, stage directions) and applies
character-specific nuances (e.g. Rocky's Eridian style, Marvin's deadpan, BMO).
"""
from __future__ import annotations

import re
from typing import Optional, Tuple
from character_registry import CharacterRegistry, CharacterSpec


def apply_character_filter(text: str, speech_style: str = "clean") -> str:
    """Clean LLM output of text artifacts and apply character speaking habits."""
    if not text:
        return ""

    # Strip markdown emphasis (**bold**, *italic*, stage directions *sighs*)
    cleaned = re.sub(r"\*+([^*]+)\*+", r"\1", text)
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)  # markdown links
    cleaned = re.sub(r"^#+\s*", "", cleaned, flags=re.MULTILINE)  # headers
    cleaned = re.sub(r"^\s*[-*•]\s+", "", cleaned, flags=re.MULTILINE)  # bullets
    cleaned = re.sub(r"#(\w+)", r"hashtag \1", cleaned)  # hashtags

    # Normalize whitespace
    cleaned = " ".join(cleaned.split()).strip()

    if speech_style == "eridian":
        # Andy Weir Eridian habits: questions end with ", question?"
        if cleaned.endswith("?") and not cleaned.endswith(", question?"):
            cleaned = cleaned[:-1].strip() + ", question?"
        # Clean filler words
        cleaned = re.sub(r"\b(as an ai|as an artificial intelligence)\b", "", cleaned, flags=re.IGNORECASE).strip()

    elif speech_style == "british_deadpan":
        # Marvin style: soften exclamation marks to dry periods
        cleaned = cleaned.replace("!", ".")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

    elif speech_style == "alluring":
        # Aura style: clean, silky speech, strip robotic phrases
        cleaned = re.sub(r"\b(as an ai|as an artificial intelligence|as a large language model)\b", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned


def detect_utterance_emotion(text: str, default_mood: str = "neutral") -> str:
    """Map sentence keywords and punctuation to emotion for eye/HUD states."""
    lower = text.lower()
    if any(w in lower for w in ("amaze", "wow", "incredible", "yay", "hooray", "awesome", "fantastic")):
        return "excited"
    if any(w in lower for w in ("happy", "good", "great", "friend", "pleasure", "glad", "delight")):
        return "happy"
    if any(w in lower for w in ("danger", "alert", "warning", "careful", "look out", "threat")):
        return "alarmed"
    if any(w in lower for w in ("sad", "terrible", "depressed", "depressing", "sorry", "miserable", "ghastly")):
        return "sad"
    if any(w in lower for w in ("boring", "bored", "trivial", "pointless", "sigh", "tedious")):
        return "bored"
    if any(w in lower for w in ("what", "how", "why", "where", "curious", "interesting")) or "?" in text:
        return "thinking"
    if "!" in text:
        return "surprised"
    return default_mood


def parse_wake_utterance(text: str, active_char: CharacterSpec,
                         registry: CharacterRegistry) -> Tuple[CharacterSpec, str, bool]:
    """Parse text for character wake words.

    Returns:
        (matched_character, stripped_text, is_wake_called)
    """
    matched, remainder = registry.find_by_wake(text)
    if matched is not None:
        return matched, remainder, True
    return active_char, text, False

"""Shared string normalisation.

Both the detector class names and the recipe ingredient strings get funnelled
through `normalize` before anything compares them, so "Bell Peppers", "bell
pepper" and "bell-peppers" all reduce to the same key.
"""

from __future__ import annotations

import re
import unicodedata

_PUNCT_RE = re.compile(r"[^a-z0-9\s]+")
_WS_RE = re.compile(r"\s+")

# Irregulars first; the suffix rules below are too blunt for these.
_IRREGULAR_PLURALS = {
    "leaves": "leaf",
    "loaves": "loaf",
    "halves": "half",
    "knives": "knife",
    "potatoes": "potato",
    "tomatoes": "tomato",
    "mangoes": "mango",
    "chilies": "chili",
    "chillies": "chilli",
    "berries": "berry",
    "cherries": "cherry",
    "peas": "pea",
    "molasses": "molasses",
    "greens": "greens",
    "grits": "grits",
    "oats": "oats",
    "beans": "bean",
    "lentils": "lentil",
    "noodles": "noodle",
    "scallions": "scallion",
    "capers": "caper",
    "sprouts": "sprout",
}

# Words that look plural but are not, or whose singular form would be wrong.
_NEVER_SINGULARIZE = {
    "asparagus",
    "couscous",
    "hummus",
    "swiss",
    "bass",
    "cress",
    "grass",
    "less",
    "miss",
    "brussels",
    "corns",  # "peppercorns" handled by suffix rule; bare "corns" is noise
}


def strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)
    )


def normalize(text: str) -> str:
    """Lowercase, de-accent, drop punctuation, collapse whitespace."""
    text = strip_accents(str(text)).lower()
    text = text.replace("-", " ").replace("/", " ")
    text = _PUNCT_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def singularize(word: str) -> str:
    """Crude English singulariser — enough for ingredient nouns."""
    if word in _IRREGULAR_PLURALS:
        return _IRREGULAR_PLURALS[word]
    if word in _NEVER_SINGULARIZE or len(word) <= 3:
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("ches", "shes", "sses", "xes", "zes")):
        return word[:-2]
    if word.endswith("oes") and len(word) > 4:
        return word[:-2]
    if word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def tokens(text: str) -> list[str]:
    """Normalised, singularised token list."""
    return [singularize(t) for t in normalize(text).split()]


def token_key(text: str) -> str:
    """Canonical whole-phrase key: normalised + singularised, space-joined."""
    return " ".join(tokens(text))


def find_phrase(haystack: list[str], needle: list[str]) -> int:
    """Index of the LAST whole-token occurrence of `needle`, or -1.

    Last rather than first because English compound nouns are head-final: in
    "cherry tomato" the head is "tomato", and callers use the position to prefer
    the head when several known ingredients appear in one string.
    """
    if not needle or len(needle) > len(haystack):
        return -1
    span = len(needle)
    for i in range(len(haystack) - span, -1, -1):
        if haystack[i : i + span] == needle:
            return i
    return -1


def contains_phrase(haystack: list[str], needle: list[str]) -> bool:
    """True when `needle` appears as a contiguous whole-token run in `haystack`."""
    return find_phrase(haystack, needle) >= 0

"""Maps detector classes and recipe ingredient strings into one shared key space.

The problem this solves: the detector emits 148 dataset-specific labels
("tomato", "palungo", "cornflakec") while recipes are written in free text
("cherry tomatoes", "extra-virgin olive oil", "unsalted butter"). Matching the
two by string equality finds almost nothing.

The fix is a canonical key per ingredient. A recipe ingredient canonicalises to
a detector class when it *mentions* that class (as a whole-token phrase, longest
class name wins); otherwise it keeps its own normalised form as its key. That
keeps the union term in the Jaccard score honest — ingredients the detector
could never see stay distinct instead of collapsing together.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .textutils import contains_phrase, find_phrase, normalize, token_key, tokens

_DATA_FILE = Path(__file__).parent / "data" / "ingredient_taxonomy.json"

VALID_CATEGORIES = ("protein", "vegetable", "dairy", "grain", "condiment", "fruit", "other")


@dataclass(frozen=True)
class ClassEntry:
    """One detector class and every phrase that should resolve to it."""

    key: str  # canonical key (normalised+singularised class name)
    raw_name: str  # class name exactly as the checkpoint spells it
    display: str  # what the UI shows
    category: str
    phrases: tuple[tuple[str, ...], ...]  # tokenised match phrases, longest first


class Taxonomy:
    def __init__(self, class_names: list[str]):
        spec = json.loads(_DATA_FILE.read_text())
        self._keyword_categories: dict[str, list[str]] = spec.get(
            "_categories_by_keyword", {}
        )

        self.entries: dict[str, ClassEntry] = {}
        self._by_raw_name: dict[str, ClassEntry] = {}

        # Pass 1: decide each class's key. A class may declare `canonical` to
        # merge with a synonym class ("palak" and "palungo" are both spinach);
        # otherwise it keys on its own name.
        class_key: dict[str, str] = {}
        own_name_keys: dict[tuple[str, ...], str] = {}
        for raw in class_names:
            cfg = spec.get(raw, {}) if isinstance(spec.get(raw), dict) else {}
            key = token_key(cfg.get("canonical") or raw)
            if not key:
                continue
            class_key[raw] = key
            own_name_keys[tuple(tokens(raw))] = key

        # Pass 2: collect phrases per key, merging classes that share one.
        phrases_by_key: dict[str, set[tuple[str, ...]]] = {}
        for raw, key in class_key.items():
            cfg = spec.get(raw, {}) if isinstance(spec.get(raw), dict) else {}
            for surface in [raw, cfg.get("canonical") or raw, *cfg.get("aliases", [])]:
                toks = tuple(tokens(surface)) if surface else ()
                if toks:
                    phrases_by_key.setdefault(key, set()).add(toks)

        for raw, key in class_key.items():
            cfg = spec.get(raw, {}) if isinstance(spec.get(raw), dict) else {}
            entry = ClassEntry(
                key=key,
                raw_name=raw,
                display=cfg.get("display") or _titlecase(raw),
                category=cfg.get("category") or self.infer_category(raw),
                phrases=tuple(sorted(phrases_by_key[key], key=len, reverse=True)),
            )
            self.entries.setdefault(key, entry)
            self._by_raw_name[raw] = entry

        # Build the match order. Two rules, in this priority:
        #
        #  1. A phrase that is some class's OWN name always resolves to that
        #     class. Without this, an alias silently steals a real class: the
        #     "citrus" class lists "lemon" as an alias, "lemon" is itself a
        #     class, and both phrases are one token — so the tiebreak handed
        #     every recipe lemon to "citrus" while a *detected* lemon stayed
        #     "lemon". The two could then never match, and "lemon" bound to 0
        #     of 13,502 recipes.
        #  2. Otherwise longest phrase wins, so "olive oil" beats "oil" and
        #     "sweet potato" beats "potato". Ties break alphabetically by key
        #     purely so the mapping is reproducible run to run.
        candidates: dict[tuple[str, ...], str] = {}
        for key, phrases in phrases_by_key.items():
            for phrase in phrases:
                owner = own_name_keys.get(phrase)
                if owner is not None and owner != key:
                    continue  # rule 1: this phrase belongs to another class
                if phrase in candidates and candidates[phrase] < key:
                    continue  # rule 2 tiebreak
                candidates[phrase] = key

        self._match_order: list[tuple[tuple[str, ...], str]] = sorted(
            candidates.items(), key=lambda pair: (-len(pair[0]), pair[1])
        )

        self._canonical_cache: dict[str, str] = {}

    # ── canonicalisation ──────────────────────────────────────────────────

    def canonical(self, ingredient: str) -> str:
        """Canonical key for a recipe ingredient string.

        Returns a detector class key when the string mentions one, else the
        ingredient's own normalised key.
        """
        cached = self._canonical_cache.get(ingredient)
        if cached is not None:
            return cached

        toks = tokens(ingredient)
        result = " ".join(toks)

        # Score every phrase that occurs, and take the best by:
        #   1. longest phrase   — "olive oil" beats "oil", "sweet potato" beats
        #                         "potato";
        #   2. rightmost match  — English compounds are head-final, so in
        #                         "cherry tomatoes" (where "cherry" and "tomato"
        #                         are both classes) the head "tomato" wins;
        #   3. key, alphabetically, only so the result is reproducible.
        best: tuple[int, int, str] | None = None
        for phrase, key in self._match_order:
            at = find_phrase(toks, list(phrase))
            if at < 0:
                continue
            score = (len(phrase), at, key)
            if best is None or score[:2] > best[:2] or (
                score[:2] == best[:2] and score[2] < best[2]
            ):
                best = score
        if best is not None:
            result = best[2]

        self._canonical_cache[ingredient] = result
        return result

    def canonical_for_class(self, raw_class_name: str) -> str | None:
        entry = self._by_raw_name.get(raw_class_name)
        return entry.key if entry else None

    def entry_for_key(self, key: str) -> ClassEntry | None:
        return self.entries.get(key)

    # ── presentation helpers ──────────────────────────────────────────────

    def display_name(self, key: str) -> str:
        entry = self.entries.get(key)
        return entry.display if entry else _titlecase(key)

    def category_for_key(self, key: str) -> str:
        entry = self.entries.get(key)
        return entry.category if entry else self.infer_category(key)

    def infer_category(self, text: str) -> str:
        """Keyword-based fallback for anything not in the taxonomy file."""
        norm = normalize(text)
        toks = tokens(text)
        best: tuple[int, str] = (0, "other")
        for category, keywords in self._keyword_categories.items():
            for kw in keywords:
                kw_toks = tokens(kw)
                if contains_phrase(toks, kw_toks) or kw in norm:
                    # Prefer the most specific (longest) keyword that hits.
                    if len(kw) > best[0]:
                        best = (len(kw), category)
        return best[1]


def _titlecase(text: str) -> str:
    text = str(text).strip()
    return text[:1].upper() + text[1:] if text else text

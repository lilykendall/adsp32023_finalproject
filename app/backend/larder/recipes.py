"""Ingredient -> recipe retrieval.

Jaccard set similarity, the method that won the notebook comparison on the
shared seed-42 test set (HitRate@1 0.932, MRR 0.954, coverage 0.987 — ahead of
the LoRA-tuned Qwen embedder at 0.906/0.930/0.977 and binary cosine at
0.791/0.839/0.899).

One deliberate difference from the notebook: the score is computed over
*canonical* keys rather than raw ingredient strings. The notebook's queries were
drawn from the corpus itself, so raw strings always matched exactly. Here the
query comes from a detector whose vocabulary is not the corpus's, so both sides
are canonicalised first (see taxonomy.py). Scoring is otherwise unchanged:

    score = |Q ∩ C_r| / |Q ∪ C_r|

with Q the detected key set and C_r the recipe's canonical key set.
"""

from __future__ import annotations

import hashlib
import pickle
from dataclasses import dataclass, field
from pathlib import Path

from . import presentation
from .parsing import parse_ingredients, parse_instructions
from .taxonomy import Taxonomy

CACHE_VERSION = 3


@dataclass
class RecipeRecord:
    dish_id: str
    dish_name: str
    photo_path: str | None
    ingredients: list[str]
    canon_keys: frozenset[str]
    # canonical key -> the raw ingredient strings that produced it
    key_to_ingredients: dict[str, list[str]]
    time_display: str
    time_estimated: bool
    difficulty: str
    description: str
    tags: list[str]
    n_steps: int


@dataclass
class RecipeMatch:
    record: RecipeRecord
    score: float
    matched_keys: list[str]
    missing_keys: list[str]
    matched_ingredients: list[str]
    missing_ingredients: list[str]
    coverage: float = 0.0


@dataclass
class IndexStats:
    n_recipes: int = 0
    n_unique_keys: int = 0
    n_keys_bound_to_classes: int = 0
    detectable_classes: list[str] = field(default_factory=list)


class RecipeIndex:
    """Forward + inverted index over canonical ingredient keys."""

    def __init__(self, records: list[RecipeRecord], taxonomy: Taxonomy):
        self.records = records
        self.taxonomy = taxonomy

        self.inverted: dict[str, list[int]] = {}
        for idx, rec in enumerate(records):
            for key in rec.canon_keys:
                self.inverted.setdefault(key, []).append(idx)

        class_keys = set(taxonomy.entries)
        bound = class_keys & set(self.inverted)
        self.stats = IndexStats(
            n_recipes=len(records),
            n_unique_keys=len(self.inverted),
            n_keys_bound_to_classes=len(bound),
            detectable_classes=sorted(bound),
        )

    # ── construction ──────────────────────────────────────────────────────

    @classmethod
    def from_dataframe(cls, df, taxonomy: Taxonomy) -> "RecipeIndex":
        records: list[RecipeRecord] = []

        for row in df.itertuples(index=False):
            raw_text = getattr(row, "recipe", None)
            ingredients = parse_ingredients(raw_text)
            if not ingredients:
                continue  # matches the notebook, which drops 0-ingredient recipes

            instructions = parse_instructions(raw_text)
            dish_name = str(getattr(row, "dish_name", "") or "Untitled")

            key_to_ingredients: dict[str, list[str]] = {}
            for ing in ingredients:
                key_to_ingredients.setdefault(taxonomy.canonical(ing), []).append(ing)

            time_display, time_estimated = presentation.cook_time(
                instructions, len(ingredients)
            )
            records.append(
                RecipeRecord(
                    dish_id=str(getattr(row, "dish_id", "") or f"R-{len(records):06d}"),
                    dish_name=dish_name,
                    photo_path=_opt_str(getattr(row, "photo_path", None)),
                    ingredients=ingredients,
                    canon_keys=frozenset(key_to_ingredients),
                    key_to_ingredients=key_to_ingredients,
                    time_display=time_display,
                    time_estimated=time_estimated,
                    difficulty=presentation.difficulty(len(ingredients), len(instructions)),
                    description=presentation.description(dish_name, instructions, ingredients),
                    tags=presentation.tags(
                        dish_name,
                        ingredients,
                        instructions,
                        presentation.minutes_from_display(time_display),
                    ),
                    n_steps=len(instructions),
                )
            )

        return cls(records, taxonomy)

    # ── retrieval ─────────────────────────────────────────────────────────

    def rank(
        self,
        query_keys: set[str],
        top_k: int = 12,
        min_matches: int = 2,
    ) -> list[RecipeMatch]:
        """Top-k recipes by Jaccard over canonical keys.

        `min_matches` is a product filter, not part of the score: without it a
        two-ingredient dressing that happens to use one detected item outranks a
        dinner that uses six, which is correct Jaccard and useless advice.
        """
        if not query_keys:
            return []

        candidates: set[int] = set()
        for key in query_keys:
            candidates.update(self.inverted.get(key, ()))
        if not candidates:
            return []

        scored: list[RecipeMatch] = []
        for idx in candidates:
            rec = self.records[idx]
            matched = query_keys & rec.canon_keys
            if len(matched) < min_matches:
                continue
            union = len(query_keys | rec.canon_keys)
            if union == 0:
                continue

            missing = rec.canon_keys - query_keys
            scored.append(
                RecipeMatch(
                    record=rec,
                    score=len(matched) / union,
                    matched_keys=sorted(matched),
                    missing_keys=sorted(missing),
                    matched_ingredients=_ingredient_names(rec, matched),
                    missing_ingredients=_ingredient_names(rec, missing, drop_staples=True),
                    coverage=len(matched) / len(query_keys),
                )
            )

        # Tie-break on absolute match count, then on shorter shopping lists —
        # among equally-similar recipes, the one needing fewest extra items wins.
        scored.sort(
            key=lambda m: (m.score, len(m.matched_keys), -len(m.missing_keys)),
            reverse=True,
        )
        if min_matches > 1 and not scored:
            return self.rank(query_keys, top_k=top_k, min_matches=1)
        return scored[:top_k]

    # ── cache ─────────────────────────────────────────────────────────────

    def save_cache(self, path: Path, fingerprint: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as fh:
            pickle.dump(
                {"version": CACHE_VERSION, "fingerprint": fingerprint, "records": self.records},
                fh,
                protocol=pickle.HIGHEST_PROTOCOL,
            )

    @classmethod
    def load_cache(
        cls, path: Path, fingerprint: str, taxonomy: Taxonomy
    ) -> "RecipeIndex | None":
        if not path.exists():
            return None
        try:
            with path.open("rb") as fh:
                blob = pickle.load(fh)
        except Exception:
            return None
        if blob.get("version") != CACHE_VERSION or blob.get("fingerprint") != fingerprint:
            return None
        return cls(blob["records"], taxonomy)


def fingerprint_for(source: Path, class_names: list[str]) -> str:
    """Cache key: the corpus file identity plus the class vocabulary.

    Both matter — new weights with a different taxonomy change every canonical
    key in the index, so a stale cache would silently serve the old mapping.
    """
    stat = source.stat()
    payload = "|".join(
        [str(source.resolve()), str(stat.st_size), str(int(stat.st_mtime)), *sorted(class_names)]
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


# Seasonings that survive the notebook's stopword list on a technicality and
# then show up on every shopping list. `parse_ingredients` drops "freshly ground
# black pepper", but it strips "freshly" as a prep verb *first*, so what reaches
# the stopword check is "ground black pepper" — which is not in it. The result is
# a phantom ingredient in 1,760 of the 13,502 recipes.
#
# Suppressed for DISPLAY ONLY. The index keeps them, so the Jaccard scores here
# are the same ones the notebook evaluated; this only stops the UI telling you to
# go buy pepper.
_PANTRY_STAPLES = {
    "ground black pepper", "black pepper", "ground pepper", "white pepper",
    "ground white pepper", "sea salt", "table salt", "coarse salt", "flaky salt",
    "salt pepper", "cold water", "warm water", "hot water", "ice water",
    "boiling water", "lukewarm water",
}


def _ingredient_names(
    rec: RecipeRecord,
    keys: set[str] | frozenset[str],
    drop_staples: bool = False,
) -> list[str]:
    """Human-readable ingredient strings for a set of canonical keys."""
    names: list[str] = []
    for key in sorted(keys):
        if drop_staples and key in _PANTRY_STAPLES:
            continue
        raws = rec.key_to_ingredients.get(key, [])
        names.append(_titlecase(raws[0]) if raws else _titlecase(key))
    return names


def _titlecase(text: str) -> str:
    text = str(text).strip()
    return text[:1].upper() + text[1:] if text else text


def _opt_str(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

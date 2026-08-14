"""Recipe ingredient parsing.

Ported verbatim in behaviour from `recipe_embedding/Recipe_Modeling.ipynb`
section 1. Keeping the parse identical matters: the retrieval scores quoted for
this app (HitRate@1 0.932, MRR 0.954) were measured over the ingredient sets
this function produces, so any drift here invalidates them.
"""

from __future__ import annotations

import ast
import re

_UNITS = {
    "cup", "cups", "tbsp", "tsp", "tablespoon", "tablespoons", "teaspoon", "teaspoons",
    "oz", "ounce", "ounces", "lb", "lbs", "pound", "pounds", "quart", "quarts", "gallon",
    "gallons", "pint", "pints", "ml", "g", "kg", "liter", "liters", "inch", "inches",
    "clove", "cloves", "can", "cans", "stick", "sticks", "package", "packages", "pinch",
    "piece", "pieces", "slice", "slices", "sprig", "sprigs", "bunch", "bunches", "head",
    "heads", "small", "medium", "large", "whole", "half",
}

_PREP_VERBS = {
    "chopped", "diced", "minced", "sliced", "grated", "crushed", "peeled", "melted",
    "softened", "divided", "optional", "fresh", "freshly", "finely", "coarsely",
    "roughly", "thinly", "plus", "about", "to", "taste", "for", "garnish", "more",
    "room", "temperature", "extra", "additional",
}

_STOPWORDS = {
    "", "salt", "pepper", "water", "kosher salt", "salt and", "and pepper",
    "freshly ground pepper", "freshly ground black pepper",
    "kosher salt freshly ground pepper", "black pepper",
}

_NUM_RE = re.compile(
    r"^[\d¼½¾⅓⅔⅛⅜⅝⅞/.\-–—]+$"
)


def clean_ingredient(raw: str) -> str:
    raw = re.sub(r"\(.*?\)", "", raw)
    raw = re.sub(r"[,;].*", "", raw)
    parts = [t.strip("'\"") for t in raw.lower().split()]
    parts = [t for t in parts if not _NUM_RE.match(t)]
    parts = [t for t in parts if t not in _UNITS and t not in _PREP_VERBS]
    name = " ".join(parts).strip(" -–—•")
    return name if name else raw.lower().strip()


def parse_ingredients(recipe_text: str | None) -> list[str]:
    """Extract cleaned ingredient names from a recipe's raw text blob."""
    if not recipe_text or not isinstance(recipe_text, str):
        return []

    if "Instructions:" in recipe_text:
        block = recipe_text.split("Instructions:")[0]
    else:
        block = recipe_text
    block = block.replace("Ingredients:", "").strip()

    if block.startswith("["):
        try:
            raw_items = ast.literal_eval(block)
        except Exception:
            raw_items = [s.strip(" '\"") for s in block.strip("[]").split("',")]
    else:
        raw_items = [
            line.lstrip("- ").strip()
            for line in block.splitlines()
            if line.strip().startswith("-")
        ]

    if not isinstance(raw_items, (list, tuple)):
        return []

    cleaned = [clean_ingredient(str(i)) for i in raw_items if str(i).strip()]
    return [c for c in cleaned if c not in _STOPWORDS]


def parse_instructions(recipe_text: str | None) -> list[str]:
    """Instruction steps, for the derived time/difficulty/description fields."""
    if not recipe_text or not isinstance(recipe_text, str):
        return []
    if "Instructions:" not in recipe_text:
        return []
    block = recipe_text.split("Instructions:", 1)[1].strip()

    if block.startswith("["):
        try:
            items = ast.literal_eval(block)
            if isinstance(items, (list, tuple)):
                return [str(s).strip() for s in items if str(s).strip()]
        except Exception:
            pass

    steps = [s.strip().lstrip("-• ").strip() for s in block.split("\n")]
    return [s for s in steps if s]

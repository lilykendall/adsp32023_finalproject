"""Derived recipe card fields.

The recipe corpus has four columns — dish_id, dish_name, recipe, photo_path —
but the UI card wants a cook time, a difficulty, a blurb and tags. None of those
are in the data, so they are *derived* here and flagged as such in the API
response (`derived: true`) rather than presented as ground truth.

Time is read out of the instruction text when the text states one, and only
estimated from step/ingredient count when it does not.
"""

from __future__ import annotations

import re

_TIME_RE = re.compile(
    r"(\d+(?:\s*(?:to|-|–|or)\s*\d+)?)\s*(hour|hr|minute|min)s?\b", re.IGNORECASE
)
_LEADING_NUM_RE = re.compile(r"^\s*\d+\s*[.):]\s*")

_VEGAN_EXCLUSIONS = {
    "meat", "chicken", "beef", "pork", "lamb", "mutton", "fish", "shrimp", "prawn",
    "crab", "bacon", "sausage", "ham", "turkey", "duck", "anchovy", "gelatin",
    "milk", "cheese", "butter", "cream", "yogurt", "yoghurt", "egg", "honey",
    "ghee", "custard", "mayonnaise", "paneer", "curd",
}
_VEGETARIAN_EXCLUSIONS = {
    "meat", "chicken", "beef", "pork", "lamb", "mutton", "fish", "shrimp", "prawn",
    "crab", "bacon", "sausage", "ham", "turkey", "duck", "anchovy", "gelatin",
}

def cook_time(instructions: list[str], n_ingredients: int) -> tuple[str, bool]:
    """(display string, estimated?) — estimated=True when nothing was stated."""
    total = 0
    for step in instructions:
        for amount, unit in _TIME_RE.findall(step):
            # "20 to 25 minutes" -> take the upper bound, the honest planning number
            numbers = [int(n) for n in re.findall(r"\d+", amount)]
            if not numbers:
                continue
            value = max(numbers)
            total += value * 60 if unit.lower().startswith(("hour", "hr")) else value

    if total <= 0:
        # Nothing stated: ~4 min of handling per step, floored by ingredient prep.
        total = max(10, len(instructions) * 4 + n_ingredients)
        estimated = True
    else:
        estimated = False
        total = max(5, total)

    if total >= 60:
        hours, minutes = divmod(total, 60)
        return (f"{hours} hr" if minutes < 8 else f"{hours} hr {minutes} min"), estimated
    return f"{int(round(total / 5.0) * 5)} min", estimated


def difficulty(n_ingredients: int, n_steps: int) -> str:
    """Proxy for effort: how much there is to buy and how much there is to do."""
    score = n_ingredients + 1.5 * n_steps
    if score <= 14:
        return "Easy"
    if score <= 26:
        return "Medium"
    return "Challenging"


def description(dish_name: str, instructions: list[str], ingredients: list[str]) -> str:
    """First instruction sentence, or an ingredient-led fallback."""
    for step in instructions:
        text = _LEADING_NUM_RE.sub("", step).strip()
        if len(text) < 25:
            continue
        sentences = re.split(r"(?<=[.!?])\s+", text)
        blurb = sentences[0].strip()
        if len(blurb) < 25 and len(sentences) > 1:
            blurb = f"{blurb} {sentences[1].strip()}"
        if len(blurb) > 180:
            blurb = blurb[:177].rsplit(" ", 1)[0] + "…"
        return blurb

    if ingredients:
        lead = ", ".join(ingredients[:4])
        return f"{dish_name} — built around {lead}."
    return dish_name


def tags(dish_name: str, ingredients: list[str], instructions: list[str],
         time_minutes: int | None = None) -> list[str]:
    found: list[str] = []

    joined_ingredients = " ".join(ingredients).lower()
    if not any(x in joined_ingredients for x in _VEGAN_EXCLUSIONS):
        found.append("Vegan")
    elif not any(x in joined_ingredients for x in _VEGETARIAN_EXCLUSIONS):
        found.append("Vegetarian")

    if len(instructions) <= 3:
        found.append("Few Steps")
    if time_minutes is not None and time_minutes <= 20:
        found.append("Quick")

    # Cap the list — the card only renders the first two anyway.
    return found[:4]


def minutes_from_display(display: str) -> int | None:
    hours = re.search(r"(\d+)\s*hr", display)
    mins = re.search(r"(\d+)\s*min", display)
    total = 0
    if hours:
        total += int(hours.group(1)) * 60
    if mins:
        total += int(mins.group(1))
    return total or None

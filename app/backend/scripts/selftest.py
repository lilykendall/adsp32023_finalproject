#!/usr/bin/env python3
"""Self-test for the ingredient/recipe layer — runs without the real artifacts.

Covers the parts that are easy to get quietly wrong: the ingredient parser, the
detector-class-to-recipe-vocabulary bridge, and the Jaccard ranking. Uses a
hand-written corpus so the expected answers are checkable by eye.

    python scripts/selftest.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from fridgefest import presentation
from fridgefest.parsing import parse_ingredients, parse_instructions
from fridgefest.recipes import RecipeIndex
from fridgefest.taxonomy import Taxonomy

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}" + (f"  ({detail})" if detail else ""))
        FAILURES.append(label)


# A slice of the real detector vocabulary, including the awkward ones.
CLASS_NAMES = [
    "tomato", "onion", "garlic", "egg", "potato", "sweet potato", "chicken",
    "bell pepper", "palungo", "cornflakec", "olive oil", "milk", "lemon",
    "zucchini", "mushroom", "minced meat", "rice", "carrot", "butter", "cheese",
]


def recipe_text(ingredients: list[str], steps: list[str]) -> str:
    return f"Ingredients:\n{ingredients!r}\nInstructions:\n{steps!r}"


CORPUS = pd.DataFrame(
    [
        {
            "dish_id": "T-001",
            "dish_name": "Garlic Tomato Frittata",
            "photo_path": "photos/T-001.jpg",
            "recipe": recipe_text(
                ["6 large eggs", "2 cloves garlic, minced", "1 cup cherry tomatoes",
                 "1/2 cup grated cheddar cheese", "2 tbsp extra-virgin olive oil",
                 "1 medium onion, diced", "salt", "freshly ground black pepper"],
                ["Heat the olive oil in an ovenproof skillet over medium heat.",
                 "Add the onion and garlic and cook for 5 minutes until soft.",
                 "Pour in the beaten eggs and bake for 12 minutes until set."],
            ),
        },
        {
            "dish_id": "T-002",
            "dish_name": "Roast Chicken with Potatoes",
            "photo_path": "photos/T-002.jpg",
            "recipe": recipe_text(
                ["1 whole chicken", "4 large potatoes, peeled", "3 cloves garlic",
                 "2 tbsp olive oil", "1 lemon", "fresh rosemary"],
                ["Preheat the oven to 200C.",
                 "Rub the chicken with olive oil and roast for 1 hour 20 minutes."],
            ),
        },
        {
            "dish_id": "T-003",
            "dish_name": "Simple Vinaigrette",
            "photo_path": None,
            "recipe": recipe_text(
                ["3 tbsp olive oil", "1 tbsp red wine vinegar"],
                ["Whisk together and season."],
            ),
        },
        {
            "dish_id": "T-004",
            "dish_name": "Creamed Spinach",
            "photo_path": "photos/T-004.jpg",
            "recipe": recipe_text(
                ["1 pound spinach", "2 tbsp unsalted butter", "1 cup whole milk",
                 "1 clove garlic", "pinch of nutmeg"],
                ["Wilt the spinach in butter for about 3 minutes.",
                 "Stir in the milk and simmer 10 minutes."],
            ),
        },
        {
            "dish_id": "T-005",
            "dish_name": "Cornflake Crusted Chicken",
            "photo_path": None,
            "recipe": recipe_text(
                ["2 cups cornflakes, crushed", "4 chicken thighs", "2 eggs", "1/2 cup milk"],
                ["Dip the chicken in egg, coat in cornflakes.",
                 "Bake for 35 minutes."],
            ),
        },
    ]
)


def main() -> int:
    print("\n1. Ingredient parsing")
    parsed = parse_ingredients(CORPUS.iloc[0]["recipe"])
    check("quantities and units stripped", "eggs" in parsed, str(parsed))
    check("prep verbs stripped", "cherry tomatoes" in parsed, str(parsed))
    check("parenthetical/comma tail dropped", "garlic" in parsed, str(parsed))
    check("salt and pepper dropped as stopwords",
          "salt" not in parsed and "black pepper" not in parsed, str(parsed))
    steps = parse_instructions(CORPUS.iloc[0]["recipe"])
    check("instructions parsed", len(steps) == 3, str(steps))

    print("\n2. Detector class -> recipe vocabulary")
    tax = Taxonomy(CLASS_NAMES)
    cases = [
        ("cherry tomatoes", "tomato"),
        ("extra-virgin olive oil", "olive oil"),
        ("grated cheddar cheese", "cheese"),
        ("unsalted butter", "butter"),
        ("whole milk", "milk"),
        ("chicken thighs", "chicken"),
        ("cornflakes", "cornflakec"),   # via alias on the misspelled class
        ("spinach", "spinach"),          # "palungo" declares canonical "spinach"
        ("4 potatoes", "potato"),
        ("cherry tomatoes", "tomato"),   # head-final: a tomato, not a cherry
    ]
    for raw, expected in cases:
        got = tax.canonical(raw)
        check(f"{raw!r} -> {expected!r}", got == expected, f"got {got!r}")

    # The longest-phrase rule: "sweet potato" must not be swallowed by "potato".
    check("'sweet potatoes' -> 'sweet potato' (longest phrase wins)",
          tax.canonical("sweet potatoes") == "sweet potato",
          tax.canonical("sweet potatoes"))
    # Ingredients the detector cannot see keep their own identity.
    check("'red wine vinegar' stays itself",
          tax.canonical("red wine vinegar") == "red wine vinegar",
          tax.canonical("red wine vinegar"))

    print("\n3. Categories")
    check("egg -> protein", tax.category_for_key("egg") == "protein", tax.category_for_key("egg"))
    check("milk -> dairy", tax.category_for_key("milk") == "dairy", tax.category_for_key("milk"))
    check("tomato -> vegetable", tax.category_for_key("tomato") == "vegetable", tax.category_for_key("tomato"))
    check("olive oil -> condiment", tax.category_for_key("olive oil") == "condiment", tax.category_for_key("olive oil"))
    check("cornflakec -> grain", tax.category_for_key("cornflakec") == "grain", tax.category_for_key("cornflakec"))
    check("lemon -> fruit", tax.category_for_key("lemon") == "fruit", tax.category_for_key("lemon"))

    print("\n4. Index + Jaccard ranking")
    index = RecipeIndex.from_dataframe(CORPUS, tax)
    check("all 5 recipes indexed", index.stats.n_recipes == 5, str(index.stats.n_recipes))

    detected = {"egg", "tomato", "garlic", "onion", "cheese", "olive oil"}
    ranked = index.rank(detected, top_k=5, min_matches=2)
    check("ranking returns results", len(ranked) > 0)
    if ranked:
        top = ranked[0]
        check("frittata ranks first", top.record.dish_id == "T-001", top.record.dish_name)
        check("matched ingredients are real strings",
              "Cherry tomatoes" in top.matched_ingredients, str(top.matched_ingredients))
        check("no salt/pepper leaks into the shopping list",
              all("pepper" not in m.lower() for m in top.missing_ingredients),
              str(top.missing_ingredients))
        check("score is a proper fraction", 0 < top.score <= 1, str(top.score))
        # Query has 6 keys; the recipe canonicalises to 7 — the 6 detected ones
        # plus "ground black pepper", which the notebook's parser lets through.
        # 6 matched / 7 union = 0.857. The pepper is hidden from the shopping
        # list but still counts in the score, exactly as it did when the 0.932
        # HitRate@1 was measured.
        check("score = matched/union including the un-detectable seasoning",
              abs(top.score - 6 / 7) < 1e-9, str(top.score))

    print("\n5. min_matches filter")
    # The vinaigrette shares only olive oil; it must not outrank real dishes.
    loose = index.rank({"olive oil", "chicken", "potato"}, top_k=5, min_matches=2)
    ids = [m.record.dish_id for m in loose]
    check("2-ingredient dressing filtered out of a 3-ingredient query",
          "T-003" not in ids, str(ids))
    check("roast chicken surfaces instead", ids and ids[0] == "T-002", str(ids))

    # With a single detected ingredient, min_matches=2 can eliminate everything;
    # rank() must fall back rather than return nothing.
    fallback = index.rank({"olive oil"}, top_k=5, min_matches=2)
    check("single-ingredient query falls back to min_matches=1", len(fallback) > 0, str(len(fallback)))

    print("\n6. Alias reach (the point of the taxonomy file)")
    spinach_hits = index.rank({tax.canonical_for_class("palungo"), "milk", "butter"}, top_k=3, min_matches=2)
    check("romanised class 'palungo' finds the spinach recipe",
          any(m.record.dish_id == "T-004" for m in spinach_hits),
          str([m.record.dish_id for m in spinach_hits]))
    corn_hits = index.rank({"cornflakec", "chicken", "egg"}, top_k=3, min_matches=2)
    check("misspelled class 'cornflakec' finds the cornflake recipe",
          any(m.record.dish_id == "T-005" for m in corn_hits),
          str([m.record.dish_id for m in corn_hits]))

    print("\n7. Derived card fields")
    frittata = next(r for r in index.records if r.dish_id == "T-001")
    check("time read from the steps, not estimated", not frittata.time_estimated, frittata.time_display)
    check("time is 5+12=17 -> rounded", frittata.time_display == "15 min" or frittata.time_display == "20 min",
          frittata.time_display)
    roast = next(r for r in index.records if r.dish_id == "T-002")
    check("1 hr 20 min parsed into hours", "hr" in roast.time_display, roast.time_display)
    check("description comes from the first real step",
          roast.description.startswith("Preheat"), roast.description)
    check("vegetarian tag on the frittata", "Vegetarian" in frittata.tags, str(frittata.tags))
    check("vinaigrette tagged vegan",
          "Vegan" in next(r for r in index.records if r.dish_id == "T-003").tags)
    check("difficulty is one of the three bands",
          all(r.difficulty in ("Easy", "Medium", "Challenging") for r in index.records))

    print("\n8. Time helpers")
    check("range takes the upper bound",
          presentation.cook_time(["Simmer 20 to 25 minutes."], 3)[0] == "25 min",
          presentation.cook_time(["Simmer 20 to 25 minutes."], 3)[0])
    check("no stated time -> estimated flag set",
          presentation.cook_time(["Mix everything."], 4)[1] is True)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) failed:")
        for name in FAILURES:
            print(f"  - {name}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

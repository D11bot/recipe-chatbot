"""Generate a tiny *synthetic* recipe dataset for an offline API demonstration.

This is not the 13,480-recipe evaluation dataset. The demo rows are illustrative
and are deliberately small, so reviewers can exercise the FastAPI endpoints
without downloading third-party recipe content.

From the repository root:
    python recipe-service/scripts/make_demo_data.py

The script refuses to overwrite existing data unless --overwrite is supplied.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

SERVICE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = SERVICE_DIR / "data" / "processed"

# Short original demonstration recipes; not intended as culinary instructions.
DEMO_RECIPES: list[tuple[str, str, list[str]]] = [
    ("Tomato Pasta", "Cook pasta and toss with warmed tomato, garlic, olive oil and basil.",
     ["pasta", "tomato", "garlic", "olive oil", "basil"]),
    ("Simple Omelette", "Whisk eggs and cook gently with butter, onion and seasoning.",
     ["egg", "butter", "onion", "milk", "salt", "pepper"]),
    ("Tomato and Egg Stir-Fry", "Cook eggs, soften the onion and tomato, then combine.",
     ["tomato", "egg", "onion", "garlic", "olive oil", "salt"]),
    ("Greek-Style Salad", "Combine vegetables, feta and olive oil; season to taste.",
     ["tomato", "cucumber", "feta", "olive oil", "onion", "oregano"]),
    ("Basic Pancakes", "Mix dry and wet ingredients and cook small pancakes on a pan.",
     ["flour", "egg", "milk", "baking powder", "sugar", "butter"]),
    ("Chickpea Curry", "Simmer chickpeas and vegetables with spices and coconut milk.",
     ["chickpea", "onion", "tomato", "garlic", "curry powder", "coconut milk"]),
    ("Potato Soup", "Simmer potato and onion in broth until tender.",
     ["potato", "onion", "vegetable broth", "garlic", "salt"]),
    ("Vegetable Fried Rice", "Cook the vegetables and toss with rice and soy sauce.",
     ["rice", "egg", "peas", "carrot", "soy sauce", "olive oil"]),
]

AMOUNT_COLUMNS = [
    "amount_row_id", "ingredient_row_id", "quantity", "quantity_max", "unit",
    "amount_text", "approximate", "range", "singular", "prepared_ingredient",
]


def generate(output: Path, overwrite: bool = False) -> None:
    """Write recipe and ingredient tables in the production service's schema."""
    names = ("recipes.csv", "recipe_ingredients.csv", "ingredient_amounts.csv")
    existing = [path for name in names if (path := output / name).exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "Existing recipe data found. Refusing to overwrite it: "
            + ", ".join(str(path) for path in existing)
            + ". Use --overwrite only when the target directory is disposable."
        )

    output.mkdir(parents=True, exist_ok=True)
    recipes: list[dict] = []
    ingredients: list[dict] = []

    for recipe_id, (title, instructions, names_in_recipe) in enumerate(DEMO_RECIPES):
        recipes.append({
            "recipe_id": recipe_id,
            "title": title,
            "instructions": instructions,
            "image_name": None,
        })
        for name in names_in_recipe:
            ingredients.append({
                "ingredient_row_id": len(ingredients),
                "recipe_id": recipe_id,
                "raw_text": name,
                "parser_input": name,
                "fallback_input": None,
                "name": name,
                "size": None,
                "preparation": None,
                "comment": None,
                "status": "ok",
                "used_fallback": False,
                "needs_quantity_review": False,
                "primary_error": None,
                "fallback_error": None,
            })

    pd.DataFrame(recipes).to_csv(output / names[0], index=False)
    pd.DataFrame(ingredients).to_csv(output / names[1], index=False)
    # Amounts are intentionally absent: these are API demonstration entries.
    pd.DataFrame(columns=AMOUNT_COLUMNS).to_csv(output / names[2], index=False)
    print(f"Generated {len(recipes)} synthetic recipes in {output}")
    print("These are NOT the source dataset and must NOT be used to reproduce evaluation metrics.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    generate(args.output, args.overwrite)


if __name__ == "__main__":
    main()

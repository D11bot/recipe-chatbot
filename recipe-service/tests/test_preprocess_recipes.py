"""Fast, dependency-light tests of the recipe data preparation helpers.

These tests use a fake ingredient parser, not a trained NLP model. They check
our own list repair, table linking and QA behavior deterministically.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "preprocess_recipes.py"
SPEC = importlib.util.spec_from_file_location("preprocess_recipes", SCRIPT)
assert SPEC and SPEC.loader
pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline)


def fake_parser(text: str):
    """Return a small ParsedIngredient-like object for predictable unit tests."""
    return SimpleNamespace(
        name=[SimpleNamespace(text="tomato")],
        size=None,
        preparation=None,
        comment=None,
        amount=[SimpleNamespace(
            quantity=2, quantity_max=2, unit="tablespoons", text="2 tablespoons",
            APPROXIMATE=False, RANGE=False, SINGULAR=False, PREPARED_INGREDIENT=False,
        )],
    )


def test_ingredient_list_repair_keeps_normal_commas():
    lines = pipeline.parse_ingredient_list('[\'"1 cup flour", 1 teaspoon salt\', \'1 onion, finely chopped\']')
    assert pipeline.repair_ingredient_list(lines) == [
        "1 cup flour", "1 teaspoon salt", "1 onion, finely chopped"
    ]


def test_drops_incomplete_and_duplicate_recipes():
    df = pd.DataFrame([
        {"Title": "Soup", "Cleaned_Ingredients": "['2 tomatoes']", "Instructions": "Cook", "Image_Name": "soup.jpg"},
        {"Title": "Soup", "Cleaned_Ingredients": "['2 tomatoes']", "Instructions": "Cook", "Image_Name": "soup.jpg"},
        {"Title": None, "Cleaned_Ingredients": "['1 carrot']", "Instructions": "Cook", "Image_Name": "carrot.jpg"},
    ])
    clean = pipeline.clean_recipes(df)
    assert len(clean) == 1
    assert clean.iloc[0]["ingredient_lines"] == ["2 tomatoes"]


def test_outputs_keep_recipe_ingredient_amount_links(tmp_path):
    raw = pd.DataFrame([{
        "Title": "Soup", "Cleaned_Ingredients": "['2 tomatoes']",
        "Instructions": "Cook", "Image_Name": "soup.jpg",
    }])
    with patch.object(pipeline, "parse_ingredient", fake_parser):
        rec, ing, amt = pipeline.build_tables(pipeline.clean_recipes(raw))
    assert len(rec) == len(ing) == len(amt) == 1
    assert int(ing.iloc[0]["recipe_id"]) == int(rec.iloc[0]["recipe_id"])
    assert int(amt.iloc[0]["ingredient_row_id"]) == int(ing.iloc[0]["ingredient_row_id"])
    assert amt.iloc[0]["unit"] == "tbsp"
    pipeline.write_outputs(tmp_path, rec, ing, amt)
    assert (tmp_path / "review_unparsed.csv").exists()
    assert (tmp_path / "recipes.csv").exists()

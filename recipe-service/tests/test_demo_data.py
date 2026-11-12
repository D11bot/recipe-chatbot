"""Verify the synthetic demo produces a valid, nonempty ingredient dataset."""

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "make_demo_data.py"
SPEC = importlib.util.spec_from_file_location("make_demo_data", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_generates_expected_csvs_without_overwriting(tmp_path):
    module.generate(tmp_path)
    recipe_rows = pd.read_csv(tmp_path / "recipes.csv")
    ingredients = pd.read_csv(tmp_path / "recipe_ingredients.csv")
    amounts = pd.read_csv(tmp_path / "ingredient_amounts.csv")
    assert len(recipe_rows) == 8
    assert len(ingredients) >= 32
    assert set(ingredients["status"]) == {"ok"}
    assert len(amounts) == 0
    assert ingredients["recipe_id"].isin(recipe_rows["recipe_id"]).all()
    with pytest.raises(FileExistsError):
        module.generate(tmp_path)

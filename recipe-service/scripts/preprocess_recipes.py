"""Build normalized recipe tables from the original Kaggle recipe CSV.

Original pipeline implemented for the Recipe Assistant's recipe engine by Dan Zhang.
This portfolio version consolidates the earlier cleaning/validation steps and
fixes an ingredient-list repair bug found in a saved development draft.

Run from the repository root:
    python recipe-service/scripts/preprocess_recipes.py

Input (not committed):
    recipe-service/data/raw/13k-recipes.csv

Outputs:
    recipe-service/data/processed/recipes.csv
    recipe-service/data/processed/recipe_ingredients.csv
    recipe-service/data/processed/ingredient_amounts.csv
    recipe-service/data/processed/review_*.csv

The output row counts depend on the source CSV and NLP parser version.
"""

from __future__ import annotations

import argparse
import ast
import csv
import re
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

try:
    from ingredient_parser import parse_ingredient
except ModuleNotFoundError:
    parse_ingredient = None

SERVICE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = SERVICE_DIR / "data" / "raw" / "13k-recipes.csv"
DEFAULT_OUTPUT = SERVICE_DIR / "data" / "processed"

RENAME_COLUMNS = {
    "Title": "title",
    "Ingredients": "ingredients_raw",
    "Instructions": "instructions",
    "Image_Name": "image_name",
    "Cleaned_Ingredients": "ingredients",
}
REQUIRED_COLUMNS = {"title", "ingredients", "instructions"}

UNIT_ALIASES = {
    "tbsp": "tbsp", "tbsps": "tbsp", "tablespoon": "tbsp", "tablespoons": "tbsp",
    "tsp": "tsp", "tsps": "tsp", "teaspoon": "tsp", "teaspoons": "tsp",
    "cup": "cup", "cups": "cup",
    "fl oz": "fl_oz", "fluid ounce": "fl_oz", "fluid ounces": "fl_oz",
    "oz": "oz", "ounce": "oz", "ounces": "oz",
    "lb": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb",
    "g": "g", "gram": "g", "grams": "g",
    "kg": "kg", "kilogram": "kg", "kilograms": "kg",
    "ml": "ml", "milliliter": "ml", "milliliters": "ml",
    "millilitre": "ml", "millilitres": "ml",
    "l": "l", "liter": "l", "liters": "l", "litre": "l", "litres": "l",
    "clove": "clove", "cloves": "clove",
    "pinch": "pinch", "pinches": "pinch",
    "piece": "piece", "pieces": "piece",
    "can": "can", "cans": "can",
}

RECIPE_COLS = ["recipe_id", "title", "instructions", "image_name"]
INGREDIENT_COLS = [
    "ingredient_row_id", "recipe_id", "raw_text", "parser_input", "fallback_input",
    "name", "size", "preparation", "comment", "status", "used_fallback",
    "needs_quantity_review", "primary_error", "fallback_error",
]
AMOUNT_COLS = [
    "amount_row_id", "ingredient_row_id", "quantity", "quantity_max", "unit",
    "amount_text", "approximate", "range", "singular", "prepared_ingredient",
]


def parse_ingredient_list(cell: Any) -> list[str]:
    """Decode stringified Python lists without executing arbitrary code."""
    if isinstance(cell, list):
        return [str(x) for x in cell if x is not None]
    if pd.isna(cell):
        return []
    try:
        decoded = ast.literal_eval(str(cell))
    except (ValueError, SyntaxError):
        return []
    return [str(x) for x in decoded if x is not None] if isinstance(decoded, list) else []


def repair_ingredient_line(line: str) -> list[str]:
    """Split clearly malformed merged entries but retain normal comma descriptions.

    For example, '"1 cup flour", 1 tsp salt' contains two entries, while
    '1 onion, finely chopped' is one ingredient and should stay intact.
    """
    text = str(line).strip()
    if text.lower() in {"", "nan", "none", "null"}:
        return []
    if not text.startswith('"'):
        return [text]
    try:
        parts = next(csv.reader([text], skipinitialspace=True))
    except (csv.Error, StopIteration):
        return [text]
    return [x.strip() for x in parts if x.strip()] or [text]


def repair_ingredient_list(lines: list[str]) -> list[str]:
    """Apply line-level repair *inside* each ingredient list.

    A saved early draft accidentally passed an entire list to
    repair_ingredient_line(). Keeping the per-list wrapper avoids collapsing
    all ingredients into one malformed string.
    """
    repaired: list[str] = []
    for line in lines:
        repaired.extend(repair_ingredient_line(line))
    return repaired


def normalize_unit(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return UNIT_ALIASES.get(text, text) if text else None


def safe_number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def text_value(value: Any) -> str | None:
    """Handle both single IngredientText values and lists returned by the parser."""
    if not value:
        return None
    if isinstance(value, list):
        value = value[0] if value else None
    if value is None:
        return None
    return str(getattr(value, "text", value)).strip() or None


def normalize_parser_input(text: str) -> str:
    """Change only syntax likely to confuse the parser; preserve raw_text."""
    return re.sub(r'(?<=\d)"', " inch", text)


def without_parentheses(text: str) -> str:
    """A conservative second attempt when an embedded size confuses parsing."""
    return re.sub(r"\s+", " ", re.sub(r"\([^)]*\)", " ", text)).strip()


def is_fragment(raw: str) -> bool:
    """Detect instructions/comments masquerading as ingredient entries."""
    phrase = raw.strip().lower()
    return bool(re.match(
        r"^(?:for serving|for garnish|to garnish|for finishing|to serve|"
        r"cut into|finely sliced|coarsely grated|peeled$|sliced$|chopped$)",
        phrase,
    ))


def flatten_amounts(value: Any) -> Iterator[Any]:
    """Keep both pieces of composite amounts, such as '1 (3-4 lb) chicken'."""
    if hasattr(value, "amounts"):
        for subamount in value.amounts:
            yield from flatten_amounts(subamount)
    else:
        yield value


def amount_record(value: Any, ingredient_row_id: int, amount_row_id: int) -> dict[str, Any]:
    return {
        "amount_row_id": amount_row_id,
        "ingredient_row_id": ingredient_row_id,
        "quantity": safe_number(getattr(value, "quantity", None)),
        "quantity_max": safe_number(getattr(value, "quantity_max", None)),
        "unit": normalize_unit(getattr(value, "unit", None)),
        "amount_text": getattr(value, "text", None),
        "approximate": bool(getattr(value, "APPROXIMATE", False)),
        "range": bool(getattr(value, "RANGE", False)),
        "singular": bool(getattr(value, "SINGULAR", False)),
        "prepared_ingredient": bool(getattr(value, "PREPARED_INGREDIENT", False)),
    }


def parse_line(raw_line: str) -> dict[str, Any]:
    """Parse an ingredient with a fallback and annotate uncertain results.

    The raw sentence is never discarded: reviewers can trace the origin of any
    name, quantity or unit that the NLP model may have interpreted incorrectly.
    """
    if parse_ingredient is None:
        raise RuntimeError("Install the data dependencies: pip install -r recipe-service/requirements-data.txt")

    raw_text = str(raw_line)
    parser_input = normalize_parser_input(raw_text)
    fallback_input = None
    primary_error = None
    fallback_error = None
    used_fallback = False
    parsed = None

    try:
        parsed = parse_ingredient(parser_input)
    except Exception as exc:
        primary_error = str(exc)

    name = text_value(getattr(parsed, "name", None)) if parsed is not None else None
    size = text_value(getattr(parsed, "size", None)) if parsed is not None else None
    preparation = text_value(getattr(parsed, "preparation", None)) if parsed is not None else None
    comment = text_value(getattr(parsed, "comment", None)) if parsed is not None else None
    amounts = list(getattr(parsed, "amount", None) or []) if parsed is not None else []

    if not name:
        candidate = without_parentheses(parser_input)
        if candidate != parser_input:
            fallback_input = candidate
            try:
                fallback = parse_ingredient(candidate)
                recovered_name = text_value(getattr(fallback, "name", None))
                if recovered_name:
                    name = recovered_name
                    used_fallback = True
                size = size or text_value(getattr(fallback, "size", None))
                preparation = preparation or text_value(getattr(fallback, "preparation", None))
                comment = comment or text_value(getattr(fallback, "comment", None))
                amounts = amounts or list(getattr(fallback, "amount", None) or [])
            except Exception as exc:
                fallback_error = str(exc)

    status = "ok" if name else "fragment" if is_fragment(raw_text) or (not amounts and (preparation or comment)) else "unparsed"
    # 'plus 1 tbsp' hidden in a comment can make an extracted amount incomplete.
    extra_amount_in_comment = bool(comment and re.search(r"\bplus\s+(?:\d|[¼½¾⅓⅔⅛⅜⅝⅞])", comment, re.I))
    needs_quantity_review = bool(status == "ok" and (primary_error or used_fallback or extra_amount_in_comment))

    return {
        "raw_text": raw_text,
        "parser_input": parser_input,
        "fallback_input": fallback_input,
        "name": name,
        "size": size,
        "preparation": preparation,
        "comment": comment,
        "status": status,
        "amounts": amounts,
        "used_fallback": used_fallback,
        "needs_quantity_review": needs_quantity_review,
        "primary_error": primary_error,
        "fallback_error": fallback_error,
    }


def clean_recipes(source: pd.DataFrame) -> pd.DataFrame:
    """Validate, trim and deduplicate recipes before assigning stable IDs."""
    df = source.drop(columns=["Unnamed: 0"], errors="ignore").rename(columns=RENAME_COLUMNS).copy()
    missing = REQUIRED_COLUMNS.difference(df.columns)
    if missing:
        raise ValueError(f"Source CSV is missing required columns: {sorted(missing)}")

    df = df.dropna(subset=["title", "ingredients", "instructions"])
    for col in ("title", "ingredients", "instructions"):
        df[col] = df[col].astype(str).str.strip()
    df = df[(df["title"] != "") & (df["ingredients"] != "") & (df["instructions"] != "")]
    df = df.drop_duplicates(subset=["title", "ingredients", "instructions"]).reset_index(drop=True)
    df["image_name"] = df.get("image_name", pd.Series([None] * len(df), index=df.index))
    df["ingredient_lines"] = df["ingredients"].map(parse_ingredient_list).map(repair_ingredient_list)
    return df


def build_tables(cleaned: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Create one-to-many recipe -> ingredient -> amount tables."""
    recipe_rows: list[dict[str, Any]] = []
    ingredient_rows: list[dict[str, Any]] = []
    amount_rows: list[dict[str, Any]] = []

    for recipe_id, row in cleaned.iterrows():
        recipe_rows.append({
            "recipe_id": int(recipe_id), "title": row["title"],
            "instructions": row["instructions"], "image_name": row["image_name"],
        })
        for line in row["ingredient_lines"]:
            parsed = parse_line(line)
            ingredient_row_id = len(ingredient_rows)
            ingredient_rows.append({
                "ingredient_row_id": ingredient_row_id,
                "recipe_id": int(recipe_id),
                **{key: parsed.get(key) for key in INGREDIENT_COLS if key not in {"ingredient_row_id", "recipe_id"}},
            })
            for composite in parsed["amounts"]:
                for amount in flatten_amounts(composite):
                    amount_rows.append(amount_record(amount, ingredient_row_id, len(amount_rows)))

        if (recipe_id + 1) % 500 == 0:
            print(f"Processed {recipe_id + 1}/{len(cleaned)} recipes")

    return (
        pd.DataFrame(recipe_rows, columns=RECIPE_COLS),
        pd.DataFrame(ingredient_rows, columns=INGREDIENT_COLS),
        pd.DataFrame(amount_rows, columns=AMOUNT_COLS),
    )


def write_outputs(
    output_dir: Path,
    recipes: pd.DataFrame,
    ingredients: pd.DataFrame,
    amounts: pd.DataFrame,
) -> None:
    """Write application tables and separate audit queues for questionable parses."""
    output_dir.mkdir(parents=True, exist_ok=True)
    recipes.to_csv(output_dir / "recipes.csv", index=False)
    ingredients.to_csv(output_dir / "recipe_ingredients.csv", index=False)
    amounts.to_csv(output_dir / "ingredient_amounts.csv", index=False)

    reviews = {
        "review_unparsed.csv": ingredients[ingredients["status"] == "unparsed"],
        "review_fragments.csv": ingredients[ingredients["status"] == "fragment"],
        "review_quantity.csv": ingredients[ingredients["needs_quantity_review"].astype(bool)],
        "review_primary_errors.csv": ingredients[ingredients["primary_error"].notna()],
    }
    for filename, subset in reviews.items():
        subset.to_csv(output_dir / filename, index=False)

    total = len(ingredients)
    parsed_names = int((ingredients["status"] == "ok").sum())
    print(f"Recipes: {len(recipes):,}; ingredient lines: {total:,}; amount rows: {len(amounts):,}")
    print(f"Ingredient names parsed: {parsed_names:,}/{total:,} ({parsed_names / total:.2%})" if total else "No ingredient lines were produced")
    print(f"Outputs written to {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Source 13k-recipes.csv file")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Directory for generated CSVs")
    args = parser.parse_args()

    if not args.input.is_file():
        parser.error(f"Source file not found: {args.input}. Download it from the dataset source first.")
    if parse_ingredient is None:
        parser.error("Install dependencies: python -m pip install -r recipe-service/requirements-data.txt")

    recipes = clean_recipes(pd.read_csv(args.input, low_memory=False))
    recipe_table, ingredient_table, amount_table = build_tables(recipes)
    write_outputs(args.output, recipe_table, ingredient_table, amount_table)


if __name__ == "__main__":
    main()

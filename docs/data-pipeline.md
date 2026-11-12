# Recipe data pipeline

**Owner of this component:** Dan Zhang (portfolio fork of a three-person team application).

This page explains how the structured recipe tables are produced and why the preprocessing matters for the LLM recipe assistant.

## Source and purpose

The source is the **Food Ingredients and Recipe Dataset with Images** on [Kaggle](https://www.kaggle.com/datasets/pes12017000148/food-ingredients-and-recipe-dataset-with-images), originally sourced from Epicurious. It contains titles, instructions, photos and ingredient descriptions that were written for people, not for an ingredient matching engine.

An ingredient line may contain several fields in one string:

```text
2 tablespoons extra virgin olive oil, divided
```

The pipeline extracts a usable ingredient name, quantity, unit and preparation/comment fields while retaining the original text for auditing. It also handles input problems such as malformed ingredient lists, blank rows, duplicate recipes, ranges, multiple amounts and non-ingredient fragments.

## Pipeline

1. **Validate the input schema** and remove empty, duplicate or incomplete recipe records.
2. **Decode ingredient lists** from CSV string literals and repair accidentally merged ingredient entries.
3. **Parse each ingredient sentence** using `ingredient-parser-nlp`, preserving raw text for traceability.
4. **Normalize units** (for example, `tablespoons` -> `tbsp`, `pounds` -> `lb`).
5. **Fallback on difficult descriptions** by retrying without parenthetical details when the primary parser fails to identify the ingredient.
6. **Split the data into linked tables** with stable `recipe_id` and `ingredient_row_id` keys.
7. **Write QA outputs** listing unparsed lines, likely non-ingredient fragments and quantities needing review.

## Outputs

| File | Purpose | Historical export count |
|---|---|---:|
| `recipes.csv` | One recipe per row: title, instructions, photo reference | 13,480 |
| `recipe_ingredients.csv` | Original and parsed ingredient text, per recipe, with parse status | 148,854 |
| `ingredient_amounts.csv` | Numeric quantities and units, linked to ingredient rows | 151,011 |

From the historical export, 145,868 of 148,854 ingredient lines had parsed names (approximately **98.0%**). This is *not* equivalent to 98.0% guaranteed quantity accuracy; missing and suspicious amounts are tracked separately in QA outputs.

## Reproducing the data

```bash
python -m pip install -r recipe-service/requirements-data.txt
python recipe-service/scripts/preprocess_recipes.py \
  --input recipe-service/data/raw/13k-recipes.csv \
  --output recipe-service/data/processed
```

The source CSV must be downloaded separately and must include `Title`, `Ingredients`, `Instructions`, `Image_Name`, and `Cleaned_Ingredients`. Use the source dataset's applicable access and reuse terms. Results may change when the parsing model changes; compare output counts and review flagged rows before updating published metrics.

## Where the data is used

- `recipe-service/app/recipe_service.py` loads `recipes.csv` and `recipe_ingredients.csv` to build recipe-ingredient lookup tables.
- `/recommend` ranks recipes using ingredient coverage and usage.
- `/missing` computes which ingredients are still required for a selected recipe.
- The original amount records are available for further quantity-aware shopping calculations, but the core recommender currently operates primarily on ingredient names. Do not claim that every quantity is used directly by the ranking algorithm.

# NutriScore ML

Estimating the official 2023 Nutri-Score grade from incomplete packaged-food
label data, for front-of-pack nutrient profiling at database scale.

When a product's fruit, vegetable, and legume (FVL) percentage is missing, a
LightGBM model recovers it from the nutrient panel and ingredient text, and a
version-pinned 2023 Nutri-Score scorer then assigns the grade from the completed
input. The model is developed on Open Food Facts, with a preliminary
cross-database evaluation on USDA FoodData Central.

## Repository layout

```
scripts/
  nutriscore_2023.py        version-pinned official 2023 Nutri-Score scorer
  build_category_sets.py    build category-flag sets from the OFF taxonomy
  explore_off.py            nutrient and FVL completeness, selection-bias profiling
  provenance_split.py       separate declared, estimated, and category FVL provenance
  declared_viability.py     declared-set learnability and distribution shift
  extract_declared.py       build the declared-FVL modeling dataset
  pilot_baseline.py         baseline-beating grade-recovery pilot
  pilot_transport.py        France to non-France transportability
  bootstrap_ci.py           bootstrap 95% confidence intervals for the headline metrics
  make_figures.py           provenance, grade-recovery, and transportability figures
  make_interpretability.py  SHAP attribution and confusion-matrix figures
  usda_profile.py           USDA external-dataset profiling
  usda_external.py          GTIN dedup against OFF and the FVL=0 error quantification
  validate_live.py          scorer agreement against the OFF API
  validate_bulk.py          end-to-end scorer agreement against the OFF stored grade
  pubmed_verify.py          reference verification via PubMed E-utilities
  download_off.py           download the OFF parquet
  dl_parquet.sh             resumable, revision-pinned OFF parquet download
  build_docx.js             build the manuscript Word files from markdown
  build_tripod.js           build the TRIPOD+AI checklist (Table S1)
ref/
  VALIDATION.md             scorer validation record
  category_flags.json       category-flag sets used by the scorer
requirements.txt            Python dependencies
package.json                Node dependencies for the Word builders
```

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/download_off.py      # Open Food Facts parquet (~7.5 GB)
```

## Reproducing the analysis

```bash
source .venv/bin/activate
python scripts/build_category_sets.py     # ref/category_flags.json
python scripts/extract_declared.py        # declared-FVL modeling dataset
python scripts/pilot_baseline.py          # grade recovery vs deterministic baselines
python scripts/pilot_transport.py         # geographic transportability
python scripts/bootstrap_ci.py            # 95% confidence intervals
python scripts/make_figures.py
python scripts/make_interpretability.py
```

## Scorer validation

`nutriscore_2023.py` reproduces the official 2023 Nutri-Score on 260
matched-input OFF products (grade, score, and every component point), and reaches
96.4% end-to-end agreement with the OFF published grade (99.4% within one grade).
See `ref/VALIDATION.md`.

## Data sources

- Open Food Facts (development): Open Database License, bulk parquet via Hugging
  Face (`openfoodfacts/product-database`, `food` split), pinned to a single revision.
- USDA FoodData Central Branded (external evaluation): public domain.
- Chomp and Edamam were excluded because their terms prohibit a stored corpus.

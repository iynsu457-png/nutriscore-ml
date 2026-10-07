#!/usr/bin/env python3
"""
Version-pinned implementation of the official 2023 Nutri-Score algorithm.

Transcribed from the Open Food Facts reference implementation
(openfoodfacts-server/lib/ProductOpener/Nutriscore.pm and Food.pm, main branch,
fetched 2026-06-10). This is the same code path that produced the
`nutriscore_grade` labels in the OFF dataset, so a faithful port should agree
with those labels on complete-input general foods up to category-detection edge
cases (nuts / red-meat HS-code rules that require the OFF taxonomy).

Inputs are per 100 g (foods) or per 100 ml (beverages):
  energy        kJ
  sugars        g
  saturated_fat g
  fat           g   (only needed for fats/oils/nuts/seeds ratio)
  salt          g   (if only sodium known: salt = sodium_g * 2.5)
  fiber         g   (AOAC)
  proteins      g
  fvl           %   (fruits/vegetables/legumes, 0-100)
Flags: is_beverage, is_water, is_cheese, is_fat_oil_nuts_seeds,
       is_red_meat_product, has_non_nutritive_sweetener
"""
from __future__ import annotations
from dataclasses import dataclass

# --- exact 2023 thresholds (from Nutriscore.pm %points_thresholds_2023) -------
TH = {
    # negative
    "energy":                    [335, 670, 1005, 1340, 1675, 2010, 2345, 2680, 3015, 3350],
    "energy_beverages":          [30, 90, 150, 210, 240, 270, 300, 330, 360, 390],
    "sugars":                    [3.4, 6.8, 10, 14, 17, 20, 24, 27, 31, 34, 37, 41, 44, 48, 51],
    "sugars_beverages":          [0.5, 2, 3.5, 5, 6, 7, 8, 9, 10, 11],
    "saturated_fat":             [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    "salt":                      [0.2, 0.4, 0.6, 0.8, 1, 1.2, 1.4, 1.6, 1.8, 2,
                                  2.2, 2.4, 2.6, 2.8, 3, 3.2, 3.4, 3.6, 3.8, 4],
    # fats/oils/nuts/seeds replacements
    "energy_from_saturated_fat": [120, 240, 360, 480, 600, 720, 840, 960, 1080, 1200],
    "saturated_fat_ratio":       [10, 16, 22, 28, 34, 40, 46, 52, 58, 64],  # uses >=
    # positive
    "fruits_vegetables_legumes":           [40, 60, 80, 80, 80],
    "fruits_vegetables_legumes_beverages": [40, 40, 60, 60, 80, 80],
    "fiber":                     [3.0, 4.1, 5.2, 6.3, 7.4],
    "proteins":                  [2.4, 4.8, 7.2, 9.6, 12, 14, 17],
    "proteins_beverages":        [1.2, 1.5, 1.8, 2.1, 2.4, 2.7, 3.0],
}


def _points(value, thresholds, ge=False):
    """Count thresholds exceeded. Strict > except saturated_fat_ratio (>=)."""
    if value is None:
        return 0
    if ge:
        return sum(1 for t in thresholds if value >= t)
    return sum(1 for t in thresholds if value > t)


@dataclass
class NutriInput:
    energy: float | None = None          # kJ
    sugars: float | None = None
    saturated_fat: float | None = None
    fat: float | None = None
    salt: float | None = None
    fiber: float | None = None
    proteins: float | None = None
    fvl: float | None = None             # %
    is_beverage: bool = False
    is_water: bool = False
    is_cheese: bool = False
    is_fat_oil_nuts_seeds: bool = False
    is_red_meat_product: bool = False
    has_non_nutritive_sweetener: bool = False


def compute_score_2023(x: NutriInput) -> dict:
    bev = x.is_beverage

    def th(key):
        bk = key + "_beverages"
        if bev and bk in TH:
            return TH[bk]
        return TH[key]

    # energy / saturated-fat columns swap for fats/oils/nuts/seeds
    if x.is_fat_oil_nuts_seeds:
        energy_val = (x.saturated_fat * 37) if x.saturated_fat is not None else None
        energy_key = "energy_from_saturated_fat"
        satfat_val = ((x.saturated_fat / x.fat * 100)
                      if (x.saturated_fat is not None and x.fat) else None)
        satfat_key = "saturated_fat_ratio"
    else:
        energy_val, energy_key = x.energy, "energy"
        satfat_val, satfat_key = x.saturated_fat, "saturated_fat"

    energy_pts = _points(energy_val, th(energy_key))
    sugars_pts = _points(x.sugars, th("sugars"))
    satfat_pts = _points(satfat_val, TH[satfat_key], ge=(satfat_key == "saturated_fat_ratio"))
    salt_pts = _points(x.salt, TH["salt"])

    negative = energy_pts + sugars_pts + satfat_pts + salt_pts
    sweetener_pts = 0
    if bev:
        sweetener_pts = 4 if x.has_non_nutritive_sweetener else 0
        negative += sweetener_pts

    # positive
    fiber_pts = _points(x.fiber, TH["fiber"])
    fvl_pts = _points(x.fvl, th("fruits_vegetables_legumes"))
    prot_pts = _points(x.proteins, th("proteins"))
    if x.is_red_meat_product and prot_pts > 2:
        prot_pts = 2

    # whether proteins count
    if bev:
        count_proteins = True
    elif x.is_cheese:
        count_proteins = True
    elif x.is_fat_oil_nuts_seeds:
        count_proteins = negative < 7
    else:
        count_proteins = negative < 11

    positive = fiber_pts + fvl_pts + (prot_pts if count_proteins else 0)
    score = negative - positive
    return {
        "score": score, "negative": negative, "positive": positive,
        "energy_pts": energy_pts, "sugars_pts": sugars_pts, "satfat_pts": satfat_pts,
        "salt_pts": salt_pts, "sweetener_pts": sweetener_pts,
        "fiber_pts": fiber_pts, "fvl_pts": fvl_pts, "proteins_pts": prot_pts,
        "count_proteins": count_proteins,
    }


def compute_grade_2023(score, is_beverage=False, is_water=False,
                       is_fat_oil_nuts_seeds=False) -> str:
    if score is None:
        return ""
    if is_beverage:
        if is_water:
            return "a"
        return "b" if score <= 2 else "c" if score <= 6 else "d" if score <= 9 else "e"
    if is_fat_oil_nuts_seeds:
        return "a" if score <= -6 else "b" if score <= 2 else "c" if score <= 10 else "d" if score <= 18 else "e"
    # other foods
    return "a" if score <= 0 else "b" if score <= 2 else "c" if score <= 10 else "d" if score <= 18 else "e"


def compute(x: NutriInput) -> tuple[int, str]:
    s = compute_score_2023(x)
    g = compute_grade_2023(s["score"], x.is_beverage, x.is_water, x.is_fat_oil_nuts_seeds)
    return s["score"], g


# --- category flags from OFF categories_tags (Food.pm + Config_off.pm) --------
# All flags use OFF taxonomy CLOSURES built by build_category_sets.py
# (ref/category_flags.json), because categories_tags does not always include
# ancestor categories (e.g. a milk is tagged en:milks but not en:beverages).
# Falls back to a small hardcoded heuristic if the file is absent.
import os as _os, json as _json
_HERE = _os.path.dirname(_os.path.abspath(__file__))

# Search ref/category_flags.json in script dir, parent dir, and CWD so the module
# works whether placed at the project root or under scripts/.
_CF = None
for _cand in (_os.path.join(_HERE, "ref", "category_flags.json"),
              _os.path.join(_HERE, "..", "ref", "category_flags.json"),
              _os.path.join(_os.getcwd(), "ref", "category_flags.json")):
    try:
        _CF = {k: set(v) for k, v in _json.load(open(_cand)).items()}
        break
    except OSError:
        continue

def flags_from_categories(categories_tags, with_non_nutritive_sweeteners=0):
    tags = set(categories_tags) if categories_tags is not None else set()
    has = lambda t: t in tags

    if _CF is not None:
        hit = lambda key: bool(tags & _CF[key])
        is_beverage = (hit("bev_base") and not hit("bev_excl")) or hit("bev_add")
        is_water = hit("water") and not hit("water_excl")
        is_cheese = hit("cheese") and not hit("cheese_excl")
        # beverages take precedence (e.g. almond-milk is a beverage, not a "nut/seed/fat")
        is_fat_oil_nuts_seeds = (not has("en:chestnuts")) and hit("fat") and not is_beverage
        is_red_meat = hit("redmeat")
    else:  # fallback heuristic (less accurate)
        is_beverage = has("en:beverages") or has("en:beverage-preparations")
        is_water = (has("en:spring-waters")
                    and not (has("en:flavored-waters") or has("en:flavoured-waters")))
        is_cheese = has("en:cheeses") and not has("fr:fromages-blancs")
        is_fat_oil_nuts_seeds = (not has("en:chestnuts")) and (
            has("en:fats") or has("en:creams") or has("en:seeds") or has("en:nuts"))
        is_red_meat = any(has(t) for t in ("en:beef", "en:pork", "en:lamb", "en:red-meats"))

    return dict(
        is_beverage=is_beverage, is_water=is_water, is_cheese=is_cheese,
        is_fat_oil_nuts_seeds=is_fat_oil_nuts_seeds, is_red_meat_product=is_red_meat,
        has_non_nutritive_sweetener=bool(with_non_nutritive_sweeteners),
    )


if __name__ == "__main__":
    # quick self-checks (illustrative)
    # Plain water -> a
    print(compute(NutriInput(energy=0, sugars=0, saturated_fat=0, salt=0,
                             fiber=0, proteins=0, fvl=0,
                             is_beverage=True, is_water=True)))
    # Sugary soda (e.g. cola ~180 kJ, 10.6 g sugar /100ml) -> expect d/e
    print(compute(NutriInput(energy=180, sugars=10.6, saturated_fat=0, salt=0,
                             fiber=0, proteins=0, fvl=0, is_beverage=True)))
    # A lean food example
    print(compute(NutriInput(energy=1500, sugars=5, saturated_fat=1, salt=0.5,
                             fiber=3.5, proteins=8, fvl=50)))

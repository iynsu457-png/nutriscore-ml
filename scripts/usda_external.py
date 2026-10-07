#!/usr/bin/env python3
"""
GTIN dedup vs OFF plus FVL=0 systematic-error quantification. Treats products
as general foods (USDA lacks OFF category tags) to isolate the FVL effect.
"""
import re, numpy as np, duckdb
from nutriscore_2023 import NutriInput, compute_score_2023, compute_grade_2023

con = duckdb.connect(); con.execute("PRAGMA threads=4")

# --- GTIN overlap with OFF (independence / dedup) ----------------------------
print("## GTIN overlap with OFF (dedup for independence)")
con.execute("""CREATE TEMP VIEW off_codes AS
  SELECT DISTINCT ltrim(code,'0') AS c FROM read_parquet('data/food.parquet')
  WHERE code IS NOT NULL""")
con.execute("""CREATE TEMP VIEW usda_g AS
  SELECT DISTINCT ltrim(cast(gtin_upc AS VARCHAR),'0') AS c FROM read_parquet('data/usda/usda_products.parquet')
  WHERE gtin_upc IS NOT NULL""")
nu = con.execute("SELECT count(*) FROM usda_g").fetchone()[0]
ov = con.execute("SELECT count(*) FROM usda_g WHERE c IN (SELECT c FROM off_codes)").fetchone()[0]
print(f"  USDA distinct GTINs: {nu:,}")
print(f"  also in OFF:         {ov:,} ({100*ov/nu:.1f}%)  <- exclude these for an INDEPENDENT external set")
print(f"  independent USDA:    {nu-ov:,} ({100*(nu-ov)/nu:.1f}%)\n")

# --- FVL=0 vs FVL-estimate grade impact (sample of usable products) ----------
rows = con.execute("""
  SELECT energy_kj, sugars, satfat, fat, salt, fiber, protein, ingredients, branded_food_category
  FROM read_parquet('data/usda/usda_products.parquet')
  WHERE energy_kj IS NOT NULL AND sugars IS NOT NULL AND satfat IS NOT NULL
    AND salt IS NOT NULL AND fiber IS NOT NULL AND protein IS NOT NULL
    AND length(coalesce(ingredients,''))>3
  USING SAMPLE 120000 ROWS
""").fetchall()
cols = [d[0] for d in con.description]; I = {c: i for i, c in enumerate(cols)}
print(f"## FVL=0 vs FVL-estimate grade impact (sample n={len(rows):,}, treated as general foods)\n")

# crude ingredient FVL estimate: fraction of fruit/veg/legume keyword hits, scaled
KW = r"(fruit|vegetable|legume|tomato|apple|orange|carrot|potato|pea|bean|lentil|nut|almond|spinach|onion|pepper|corn|berry|mango|pineapple|broccoli|cabbage|garlic|olive|raisin|date|fig|cherry|peach|pumpkin|squash|cucumber|lettuce|kale|avocado)"
def fvl_est(t):
    t = (t or "").lower(); toks = re.findall(r"[a-z]+", t)
    if not toks: return 0.0
    hits = len(re.findall(KW, t))
    return min(100.0, 100.0 * hits / max(len(toks), 1) * 3)  # crude scale

def grade(nuts, fvl):
    x = NutriInput(energy=nuts[0], sugars=nuts[1], saturated_fat=nuts[2], fat=nuts[3],
                   salt=nuts[4], fiber=nuts[5], proteins=nuts[6], fvl=fvl)  # general food
    return compute_grade_2023(compute_score_2023(x)["score"])

GR = "abcde"; changed = 0; up = 0; n = 0
chg_hi = hi = 0
for r in rows:
    nuts = [r[I["energy_kj"]], r[I["sugars"]], r[I["satfat"]], r[I["fat"]], r[I["salt"]], r[I["fiber"]], r[I["protein"]]]
    fe = fvl_est(r[I["ingredients"]])
    g0 = grade(nuts, 0.0); ge = grade(nuts, fe)
    n += 1
    if g0 != ge:
        changed += 1
        if GR.index(ge) < GR.index(g0): up += 1  # estimate gives better (lower) grade
    if fe >= 40:  # ingredient-rich in fruit/veg
        hi += 1
        if g0 != ge: chg_hi += 1

print(f"  grade changes FVL=0 -> FVL-estimate: {changed:,}/{n:,} ({100*changed/n:.1f}%)")
print(f"    of which estimate improves grade:  {up:,} ({100*up/max(changed,1):.0f}% of changes)")
print(f"  products with high FVL-estimate (>=40): {hi:,} ({100*hi/n:.1f}%)")
print(f"    grade changed for: {chg_hi:,} ({100*chg_hi/max(hi,1):.1f}% of high-FVL products)")
print("\n  => FVL=0 forcing mis-grades a non-trivial, ingredient-identifiable slice;")
print("     an FVL-estimate arm (vs FVL=0 arm) is justified for USDA external validation.")

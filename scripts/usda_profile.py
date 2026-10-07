#!/usr/bin/env python3
"""
USDA FoodData Central Branded as an external-validation set.

Builds per-product Nutri-Score inputs (nutrients are already per-100g in FDC),
quantifies usability, GTIN overlap with OFF (dedup for independence), and the
FVL=0 vs FVL-estimate grade impact.
Writes data/usda/usda_products.parquet and prints a report.
"""
import duckdb
con = duckdb.connect(); con.execute("PRAGMA threads=4"); con.execute("PRAGMA memory_limit='6GB'")
D = "data/usda/FoodData_Central_branded_food_csv_2026-04-30"

# pivot food_nutrient to wide (key Nutri-Score nutrient ids), join branded_food
print("building per-product table (pivot 1.4GB food_nutrient)...", flush=True)
con.execute(f"""
CREATE OR REPLACE TABLE usda AS
WITH fn AS (
  SELECT fdc_id,
    max(CASE WHEN nutrient_id=1062 THEN amount END) AS energy_kj_d,
    max(CASE WHEN nutrient_id=1008 THEN amount END) AS energy_kcal,
    max(CASE WHEN nutrient_id=2000 THEN amount END) AS sugars_a,
    max(CASE WHEN nutrient_id=1063 THEN amount END) AS sugars_b,
    max(CASE WHEN nutrient_id=1258 THEN amount END) AS satfat,
    max(CASE WHEN nutrient_id=1004 THEN amount END) AS fat,
    max(CASE WHEN nutrient_id=2033 THEN amount END) AS fiber_a,
    max(CASE WHEN nutrient_id=1079 THEN amount END) AS fiber_b,
    max(CASE WHEN nutrient_id=1003 THEN amount END) AS protein,
    max(CASE WHEN nutrient_id=1093 THEN amount END) AS sodium_mg
  FROM read_csv_auto('{D}/food_nutrient.csv', sample_size=200)
  WHERE nutrient_id IN (1062,1008,2000,1063,1258,1004,2033,1079,1003,1093)
  GROUP BY fdc_id
)
SELECT b.fdc_id, b.gtin_upc, b.ingredients, b.branded_food_category, b.market_country,
  coalesce(fn.energy_kj_d, fn.energy_kcal*4.184) AS energy_kj,
  coalesce(fn.sugars_a, fn.sugars_b) AS sugars,
  fn.satfat, fn.fat,
  coalesce(fn.fiber_a, fn.fiber_b) AS fiber,
  fn.protein,
  fn.sodium_mg/1000.0*2.5 AS salt
FROM read_csv_auto('{D}/branded_food.csv', sample_size=200) b
JOIN fn USING (fdc_id)
""")
total = con.execute("SELECT count(*) FROM usda").fetchone()[0]
print(f"USDA branded products: {total:,}\n")

# completeness
print("## Completeness (per-100g nutrients)")
for col in ["energy_kj","sugars","satfat","salt","fiber","protein","ingredients"]:
    c = con.execute(f"SELECT count(*) FROM usda WHERE {col} IS NOT NULL").fetchone()[0]
    print(f"  {col:12} {c:>9,} ({100*c/total:.1f}%)")
complete = con.execute("""SELECT count(*) FROM usda WHERE energy_kj IS NOT NULL AND sugars IS NOT NULL
  AND satfat IS NOT NULL AND salt IS NOT NULL AND fiber IS NOT NULL AND protein IS NOT NULL""").fetchone()[0]
complete_ing = con.execute("""SELECT count(*) FROM usda WHERE energy_kj IS NOT NULL AND sugars IS NOT NULL
  AND satfat IS NOT NULL AND salt IS NOT NULL AND fiber IS NOT NULL AND protein IS NOT NULL
  AND length(coalesce(ingredients,''))>3""").fetchone()[0]
print(f"\n  all 6 core nutrients:        {complete:,} ({100*complete/total:.1f}%)")
print(f"  + ingredients text:          {complete_ing:,} ({100*complete_ing/total:.1f}%)  <- usable external set")

# market country
print("\n## market_country")
for c,n in con.execute("SELECT coalesce(market_country,'(null)'), count(*) c FROM usda GROUP BY 1 ORDER BY c DESC LIMIT 5").fetchall():
    print(f"  {c:20} {n:,}")

con.execute("COPY usda TO 'data/usda/usda_products.parquet' (FORMAT PARQUET)")
print("\n[written] data/usda/usda_products.parquet")

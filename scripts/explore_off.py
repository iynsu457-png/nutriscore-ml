#!/usr/bin/env python3
"""
OFF feasibility exploration: FVL & nutrient completeness, grade distribution,
and selection-bias check. Reads the HF OpenFoodFacts food.parquet via DuckDB.

Run:  python explore_off.py [path/to/food.parquet]
Outputs: prints a report and writes data/exploration_report.md
"""
import sys, textwrap
import duckdb

PARQUET = sys.argv[1] if len(sys.argv) > 1 else "data/food.parquet"

con = duckdb.connect()
con.execute("PRAGMA threads=4")

def q(sql):
    return con.execute(sql).fetchall()

def nut(name, field="100g"):
    """SQL expression: extract a nutriment's <field> (default per-100g) by name."""
    return (f"list_extract(list_transform("
            f"list_filter(nutriments, x -> x.name = '{name}'), "
            f"x -> x['{field}']), 1)")

REPORT = []
def out(line=""):
    print(line)
    REPORT.append(line)

src = f"read_parquet('{PARQUET}')"

# ---------------------------------------------------------------------------
out("# OFF feasibility exploration\n")

# 0) total rows ---------------------------------------------------------------
total = q(f"SELECT count(*) FROM {src}")[0][0]
non_obsolete = q(f"SELECT count(*) FROM {src} WHERE NOT coalesce(obsolete,false)")[0][0]
out(f"Total food rows:        {total:,}")
out(f"Non-obsolete rows:      {non_obsolete:,}")
out("")

# 1) nutrient name frequency (sample for speed) ------------------------------
out("## Most common nutriment names (sample 300k rows, with non-null 100g)\n")
names = q(f"""
    SELECT n.name AS name, count(*) AS cnt
    FROM (SELECT nutriments FROM {src} USING SAMPLE 300000 ROWS) ,
         UNNEST(nutriments) AS t(n)
    WHERE n['100g'] IS NOT NULL
    GROUP BY n.name
    ORDER BY cnt DESC
    LIMIT 70
""")
for name, cnt in names:
    out(f"  {name:48} {cnt:>9,}")
out("")

# Detect FVL-style field names present
fvl_candidates = [
    "fruits-vegetables-legumes-estimate-from-ingredients",
    "fruits-vegetables-nuts-estimate-from-ingredients",
    "fruits-vegetables-nuts-estimate",
    "fruits-vegetables-nuts",
    "fruits-vegetables-legumes",
]
present_names = {n for n, _ in names}
out("## FVL candidate fields seen in sample:")
for c in fvl_candidates:
    out(f"  {'PRESENT' if c in present_names else 'absent ':8} {c}")
out("")

# ---------------------------------------------------------------------------
# 2) full completeness pass (single scan, per-row extraction) ----------------
# Build a CTE that extracts the Nutri-Score-relevant nutrients per product.
base_cols = {
    "energy_kj":   nut("energy-kj"),
    "energy_kcal": nut("energy-kcal"),
    "satfat":      nut("saturated-fat"),
    "sugars":      nut("sugars"),
    "salt":        nut("salt"),
    "sodium":      nut("sodium"),
    "fiber":       nut("fiber"),
    "proteins":    nut("proteins"),
    "fvl_leg_ing": nut("fruits-vegetables-legumes-estimate-from-ingredients"),
    "fvl_nut_ing": nut("fruits-vegetables-nuts-estimate-from-ingredients"),
    "fvl_nut_est": nut("fruits-vegetables-nuts-estimate"),
    "fvl_nut":     nut("fruits-vegetables-nuts"),
}
select_exprs = ",\n        ".join(f"{expr} AS {alias}" for alias, expr in base_cols.items())

con.execute(f"""
CREATE OR REPLACE TEMP VIEW ext AS
SELECT
    code,
    nutriscore_grade,
    nutriscore_score,
    nova_group,
    coalesce(obsolete,false) AS obsolete,
    coalesce(no_nutrition_data,false) AS no_nutrition_data,
    coalesce(len(ingredients_text),0) > 0 AS has_ing_text,
    coalesce(len(categories_tags),0) > 0 AS has_category,
    {select_exprs}
FROM {src}
""")

# Energy present if either kj or kcal; salt present if salt or sodium
con.execute("""
CREATE OR REPLACE TEMP VIEW flags AS
SELECT *,
    (energy_kj IS NOT NULL OR energy_kcal IS NOT NULL) AS has_energy,
    (satfat IS NOT NULL) AS has_satfat,
    (sugars IS NOT NULL) AS has_sugars,
    (salt IS NOT NULL OR sodium IS NOT NULL) AS has_salt,
    (fiber IS NOT NULL) AS has_fiber,
    (proteins IS NOT NULL) AS has_proteins,
    (coalesce(fvl_leg_ing, fvl_nut_ing, fvl_nut_est, fvl_nut) IS NOT NULL) AS has_fvl_any,
    (fvl_leg_ing IS NOT NULL) AS has_fvl_leg_ing
FROM ext
WHERE NOT obsolete
""")

n = q("SELECT count(*) FROM flags")[0][0]
out(f"## Completeness over {n:,} non-obsolete food products\n")

def pct(c): return f"{c:,} ({100.0*c/n:.1f}%)"

stats = q("""
SELECT
  sum(has_energy::int), sum(has_satfat::int), sum(has_sugars::int),
  sum(has_salt::int), sum(has_fiber::int), sum(has_proteins::int),
  sum(has_ing_text::int), sum(has_category::int),
  sum(has_fvl_any::int), sum(has_fvl_leg_ing::int)
FROM flags
""")[0]
labels = ["energy","saturated fat","sugars","salt/sodium","fiber","proteins",
          "ingredients_text","category","FVL (any est.)","FVL legumes-from-ing"]
for lab, c in zip(labels, stats):
    out(f"  {lab:22} {pct(c)}")
out("")

# Core 6 nutrients all present (energy, satfat, sugars, salt, fiber, proteins)
core = q("""
SELECT count(*) FROM flags
WHERE has_energy AND has_satfat AND has_sugars AND has_salt AND has_fiber AND has_proteins
""")[0][0]
out(f"All 6 core nutrients present:                 {pct(core)}")

core_ing = q("""
SELECT count(*) FROM flags
WHERE has_energy AND has_satfat AND has_sugars AND has_salt AND has_fiber AND has_proteins
  AND has_ing_text
""")[0][0]
out(f"  + ingredients_text:                         {pct(core_ing)}")

core_fvl = q("""
SELECT count(*) FROM flags
WHERE has_energy AND has_satfat AND has_sugars AND has_salt AND has_fiber AND has_proteins
  AND has_fvl_any
""")[0][0]
out(f"  + FVL (any estimate)  [GROUND-TRUTH-able]:  {pct(core_fvl)}")

core_fvl_ing = q("""
SELECT count(*) FROM flags
WHERE has_energy AND has_satfat AND has_sugars AND has_salt AND has_fiber AND has_proteins
  AND has_fvl_leg_ing
""")[0][0]
out(f"  + FVL legumes-from-ingredients (2023):      {pct(core_fvl_ing)}")
out("")

# 3) existing nutriscore_grade label distribution ----------------------------
out("## Existing nutriscore_grade label distribution (non-obsolete)\n")
gd = q("""
SELECT coalesce(nutriscore_grade,'(null)') AS g, count(*) c
FROM flags GROUP BY g ORDER BY g
""")
for g, c in gd:
    out(f"  {g:10} {pct(c)}")
out("")

# 4) selection-bias check: included (core+FVL) vs excluded -------------------
out("## Selection-bias check: products WITH full inputs vs WITHOUT\n")
bias = q("""
WITH g AS (
  SELECT *,
    (has_energy AND has_satfat AND has_sugars AND has_salt AND has_fiber
       AND has_proteins AND has_fvl_any) AS included
  FROM flags
)
SELECT included,
       count(*) AS n,
       avg(nova_group) AS mean_nova,
       avg(has_ing_text::int) AS frac_ing,
       avg(has_category::int) AS frac_cat,
       avg(nutriscore_score) AS mean_score
FROM g GROUP BY included ORDER BY included
""")
out("  included |        n | mean_nova | frac_ing | frac_cat | mean_score")
for inc, nn, nova, fing, fcat, msc in bias:
    nova = f"{nova:.2f}" if nova is not None else "  n/a"
    msc = f"{msc:.2f}" if msc is not None else "  n/a"
    out(f"  {str(bool(inc)):8} | {nn:>8,} |   {nova}   |  {fing:.2f}   |  {fcat:.2f}   |  {msc}")
out("")

# nova distribution within included set
out("## NOVA group distribution (included = full-input products)\n")
nv = q("""
WITH g AS (
  SELECT *,
    (has_energy AND has_satfat AND has_sugars AND has_salt AND has_fiber
       AND has_proteins AND has_fvl_any) AS included
  FROM flags
)
SELECT coalesce(cast(nova_group as varchar),'(null)') ng, count(*) c
FROM g WHERE included GROUP BY ng ORDER BY ng
""")
inc_total = sum(c for _, c in nv) or 1
for ng, c in nv:
    out(f"  NOVA {ng:8} {c:,} ({100.0*c/inc_total:.1f}%)")
out("")

# write report
with open("data/exploration_report.md", "w") as f:
    f.write("\n".join(REPORT))
out("[written] data/exploration_report.md")

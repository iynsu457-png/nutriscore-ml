#!/usr/bin/env python3
"""
FVL provenance split: circularity and leakage check.

OFF assigns the Nutri-Score FVL input from one of several sources, recorded in
misc_tags. Only DECLARED FVL is leakage-free; estimate-from-ingredients is a
text-derived pseudo-label (predicting it from ingredient text is circular).

This script:
  1. classifies every product into a provenance bucket (priority order),
  2. counts each bucket overall and among complete-nutrient products,
  3. characterizes selection bias of declared vs estimate vs absent
     (grade, NOVA, top countries, top categories).

Run: python provenance_split.py [path] ; writes data/provenance_report.md
"""
import sys
import duckdb

PARQUET = sys.argv[1] if len(sys.argv) > 1 else "data/food.parquet"
con = duckdb.connect(); con.execute("PRAGMA threads=4")
src = f"read_parquet('{PARQUET}')"
REP = []
def out(s=""):
    print(s); REP.append(s)

def nut(name, field="100g"):
    return (f"list_extract(list_transform(list_filter(nutriments, x -> x.name = '{name}'), "
            f"x -> x['{field}']), 1)")

DECLARED = ("(list_contains(misc_tags,'en:nutrition-fruits-vegetables-nuts') OR "
            " list_contains(misc_tags,'en:nutrition-fruits-vegetables-legumes'))")
ESTIMATE = ("(list_contains(misc_tags,'en:nutrition-fruits-vegetables-legumes-estimate-from-ingredients') OR "
            " list_contains(misc_tags,'en:nutrition-fruits-vegetables-nuts-estimate-from-ingredients'))")
FROMCAT = ("(len(list_filter(misc_tags, x -> x LIKE 'en:nutrition-fruits-vegetables-%-from-category%')) > 0)")

# priority: declared > estimate > from_category > absent
PROV = f"""CASE
  WHEN {DECLARED} THEN 'declared'
  WHEN {ESTIMATE} THEN 'estimate_from_ingredients'
  WHEN {FROMCAT}  THEN 'from_category'
  ELSE 'absent'
END"""

# complete core nutrients flag
COMPLETE = f"""(
  ({nut('energy-kj')} IS NOT NULL OR {nut('energy-kcal')} IS NOT NULL OR {nut('energy')} IS NOT NULL)
  AND {nut('saturated-fat')} IS NOT NULL AND {nut('sugars')} IS NOT NULL
  AND ({nut('salt')} IS NOT NULL OR {nut('sodium')} IS NOT NULL)
  AND {nut('fiber')} IS NOT NULL AND {nut('proteins')} IS NOT NULL
)"""

con.execute(f"""
CREATE OR REPLACE TEMP VIEW v AS
SELECT
  code,
  {PROV} AS provenance,
  {COMPLETE} AS complete_core,
  nutriscore_grade AS grade,
  nova_group AS nova,
  coalesce(len(ingredients_text),0) > 0 AS has_ing,
  list_extract(countries_tags, 1) AS country1,
  list_extract(categories_tags, -1) AS cat_leaf
FROM {src}
WHERE NOT coalesce(obsolete,false)
""")

total = con.execute("SELECT count(*) FROM v").fetchone()[0]
out("# FVL provenance split\n")
out(f"Total non-obsolete products: {total:,}\n")

out("## Provenance distribution (all products)\n")
rows = con.execute("""
  SELECT provenance, count(*) n,
         sum(complete_core::int) n_complete,
         avg(has_ing::int) frac_ing
  FROM v GROUP BY provenance ORDER BY n DESC
""").fetchall()
out(f"  {'provenance':28} {'n':>12} {'%':>6}   {'complete-nutrient':>18} {'has_ing':>8}")
for prov, n, nc, fing in rows:
    out(f"  {prov:28} {n:>12,} {100*n/total:>5.1f}%   {nc:>18,} {fing:>7.2f}")
out("")

out("## ML-usable ground-truth set sizes (complete nutrients AND ingredient text)\n")
rows = con.execute("""
  SELECT provenance, count(*) n
  FROM v WHERE complete_core AND has_ing
  GROUP BY provenance ORDER BY n DESC
""").fetchall()
for prov, n in rows:
    out(f"  {prov:28} {n:>12,}")
out("")
out("  KEY: 'declared' = leakage-free clean set; 'estimate_from_ingredients' = circular (text-derived).")
out("")

# bias characterization for the two ML-relevant buckets + absent
for bucket in ["declared", "estimate_from_ingredients", "absent"]:
    out(f"## Selection-bias profile: provenance = {bucket} (complete-nutrient products)\n")
    base = f"FROM v WHERE complete_core AND provenance='{bucket}'"
    n = con.execute(f"SELECT count(*) {base}").fetchone()[0]
    out(f"  n = {n:,}")
    if n == 0:
        out(""); continue
    # grade dist
    gd = con.execute(f"SELECT coalesce(grade,'(null)') g, count(*) c {base} GROUP BY g ORDER BY g").fetchall()
    out("  grade: " + ", ".join(f"{g}={100*c/n:.1f}%" for g, c in gd))
    nova = con.execute(f"SELECT avg(nova) {base}").fetchone()[0]
    out(f"  mean NOVA: {nova:.2f}" if nova is not None else "  mean NOVA: n/a")
    # top countries
    cs = con.execute(f"SELECT coalesce(country1,'(null)') c, count(*) n {base} GROUP BY c ORDER BY n DESC LIMIT 8").fetchall()
    out("  top countries: " + ", ".join(f"{c.replace('en:','')}={100*x/n:.0f}%" for c, x in cs))
    # top category leaves
    cats = con.execute(f"SELECT coalesce(cat_leaf,'(null)') c, count(*) n {base} GROUP BY c ORDER BY n DESC LIMIT 8").fetchall()
    out("  top category leaves: " + ", ".join(f"{c.replace('en:','')}({100*x/n:.0f}%)" for c, x in cats))
    out("")

with open("data/provenance_report.md", "w") as f:
    f.write("\n".join(REP))
out("[written] data/provenance_report.md")

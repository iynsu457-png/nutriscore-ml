#!/usr/bin/env python3
"""
Is the leakage-free DECLARED-FVL set viable for modeling, and how big is the
train(declared) -> deploy(estimate) distribution shift?

Outputs per-grade and per-FVL-band coverage of the declared set, and PSI
(population stability index) of grade and FVL-band distributions declared vs
estimate. Writes data/declared_viability.md
"""
import sys, math
import duckdb

PARQUET = sys.argv[1] if len(sys.argv) > 1 else "data/food.parquet"
con = duckdb.connect(); con.execute("PRAGMA threads=4")
src = f"read_parquet('{PARQUET}')"
REP = []
def out(s=""):
    print(s); REP.append(s)

def nut(name):
    return (f"list_extract(list_transform(list_filter(nutriments, x -> x.name='{name}'), "
            f"x -> x['100g']),1)")

DECL = ("(list_contains(misc_tags,'en:nutrition-fruits-vegetables-nuts') OR "
        " list_contains(misc_tags,'en:nutrition-fruits-vegetables-legumes'))")
EST = ("(list_contains(misc_tags,'en:nutrition-fruits-vegetables-legumes-estimate-from-ingredients') OR "
       " list_contains(misc_tags,'en:nutrition-fruits-vegetables-nuts-estimate-from-ingredients'))")
FC = ("(len(list_filter(misc_tags, x -> x LIKE 'en:nutrition-fruits-vegetables-%-from-category%'))>0)")
COMPLETE = (f"({nut('saturated-fat')} IS NOT NULL AND {nut('sugars')} IS NOT NULL AND "
            f"{nut('proteins')} IS NOT NULL AND {nut('fiber')} IS NOT NULL AND "
            f"({nut('salt')} IS NOT NULL OR {nut('sodium')} IS NOT NULL) AND "
            f"({nut('energy-kj')} IS NOT NULL OR {nut('energy-kcal')} IS NOT NULL OR {nut('energy')} IS NOT NULL))")
# FVL value: prefer declared field, then legumes, then estimate
FVLVAL = (f"coalesce({nut('fruits-vegetables-nuts')}, {nut('fruits-vegetables-legumes')}, "
          f"{nut('fruits-vegetables-legumes-estimate-from-ingredients')}, "
          f"{nut('fruits-vegetables-nuts-estimate-from-ingredients')})")

con.execute(f"""
CREATE OR REPLACE TEMP VIEW v AS
SELECT
  CASE WHEN {DECL} THEN 'declared' WHEN {EST} THEN 'estimate' WHEN {FC} THEN 'from_category' ELSE 'absent' END AS prov,
  nutriscore_grade AS grade,
  {FVLVAL} AS fvl,
  list_extract(categories_tags, -1) AS cat_leaf,
  list_extract(countries_tags, 1) AS country1
FROM {src}
WHERE NOT coalesce(obsolete,false) AND {COMPLETE}
""")

out("# Declared-FVL set viability + train->deploy shift\n")

# FVL band expression
def band_sql(col):
    return (f"CASE WHEN {col} IS NULL THEN 'null' WHEN {col}<=0 THEN '0' "
            f"WHEN {col}<=40 THEN '(0,40]' WHEN {col}<=60 THEN '(40,60]' "
            f"WHEN {col}<=80 THEN '(60,80]' ELSE '(80,100]' END")

out("## Declared set: per-grade x per-FVL-band coverage (learnability)\n")
n_decl = con.execute("SELECT count(*) FROM v WHERE prov='declared'").fetchone()[0]
out(f"declared complete-nutrient n = {n_decl:,}\n")
rows = con.execute(f"""
  SELECT coalesce(grade,'(null)') g, {band_sql('fvl')} band, count(*) c
  FROM v WHERE prov='declared' GROUP BY g, band ORDER BY g, band
""").fetchall()
# pivot
from collections import defaultdict
grades = ['a','b','c','d','e']
bands = ['0','(0,40]','(40,60]','(60,80]','(80,100]','null']
tab = defaultdict(int)
for g, b, c in rows: tab[(g, b)] = c
out(f"  {'grade':6}" + "".join(f"{b:>10}" for b in bands) + f"{'total':>10}")
for g in grades:
    tot = sum(tab[(g, b)] for b in bands)
    out(f"  {g:6}" + "".join(f"{tab[(g,b)]:>10,}" for b in bands) + f"{tot:>10,}")
out("")

# PSI declared vs estimate on grade and FVL band
def dist(prov, expr):
    rows = con.execute(f"SELECT {expr} k, count(*) c FROM v WHERE prov='{prov}' GROUP BY k").fetchall()
    tot = sum(c for _, c in rows) or 1
    return {str(k): c/tot for k, c in rows}

def psi(a, b):
    keys = set(a) | set(b)
    s = 0.0
    for k in keys:
        pa = max(a.get(k, 0), 1e-6); pb = max(b.get(k, 0), 1e-6)
        s += (pa - pb) * math.log(pa / pb)
    return s

out("## Train(declared) -> Deploy(estimate) distribution shift\n")
for label, expr in [("grade", "coalesce(grade,'(null)')"), ("FVL band", band_sql('fvl'))]:
    da = dist('declared', expr); db = dist('estimate', expr)
    p = psi(da, db)
    sev = "SMALL" if p < 0.1 else "MODERATE" if p < 0.25 else "LARGE"
    out(f"  {label:10} PSI = {p:.3f}  ({sev} shift)")
    keys = sorted(set(da) | set(db))
    out("    " + "  ".join(f"{k}:{100*da.get(k,0):.0f}/{100*db.get(k,0):.0f}" for k in keys) + "   (declared%/estimate%)")
out("")

# FVL value distribution summary
out("## FVL value distribution (declared vs estimate), complete-nutrient\n")
for prov in ['declared', 'estimate']:
    r = con.execute(f"""SELECT
        count(*) n,
        avg(fvl) mean, median(fvl) med,
        sum((fvl<=0)::int) z, sum((fvl>=80)::int) hi
        FROM v WHERE prov='{prov}' AND fvl IS NOT NULL""").fetchone()
    n = r[0] or 1
    out(f"  {prov:10} n={r[0]:,}  mean={r[1]:.1f}  median={r[2]:.1f}  "
        f"FVL=0: {100*r[3]/n:.0f}%  FVL>=80: {100*r[4]/n:.0f}%")
out("")

# category overlap
out("## Category coverage: distinct category leaves\n")
for prov in ['declared', 'estimate']:
    d = con.execute(f"SELECT count(DISTINCT cat_leaf) FROM v WHERE prov='{prov}'").fetchone()[0]
    out(f"  {prov:10} distinct category leaves: {d:,}")
out("")

with open("data/declared_viability.md", "w") as f:
    f.write("\n".join(REP))
out("[written] data/declared_viability.md")

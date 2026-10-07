#!/usr/bin/env python3
"""
v2 end-to-end validation + diagnosis of the 91.8% gap.

Improvements over validate_bulk.py:
  1. FVL input = OFF's FINAL value field (fruits-vegetables-legumes / -nuts),
     which is what OFF's algorithm actually consumed (the earlier script used the
     estimate-from-ingredients field, which can differ from the value OFF used).
  2. Uses OFF's stored nutriscore_score to LOCALIZE each mismatch:
       - score matches but grade differs  -> category routing / grade-cutoff issue
       - score differs                     -> input derivation (FVL/energy/salt) or
                                              which-nutrients-count (category) issue
Run: python validate_bulk_v2.py [path] [sample_n]
"""
import sys
from collections import Counter
import duckdb
import nutriscore_2023 as nsmod
from nutriscore_2023 import NutriInput, flags_from_categories, compute_score_2023, compute_grade_2023

PARQUET = sys.argv[1] if len(sys.argv) > 1 else "data/food.parquet"
SAMPLE_N = int(sys.argv[2]) if len(sys.argv) > 2 else 150000
con = duckdb.connect(); con.execute("PRAGMA threads=4")

def nut(name):
    return (f"list_extract(list_transform(list_filter(nutriments, x -> x.name='{name}'), "
            f"x -> x['100g']),1)")

sql = f"""
SELECT
    code, nutriscore_grade, nutriscore_score, categories_tags,
    coalesce(with_non_nutritive_sweeteners,0) AS sweet,
    {nut('energy-kj')} AS energy_kj, {nut('energy-kcal')} AS energy_kcal, {nut('energy')} AS energy_any,
    {nut('sugars')} AS sugars, {nut('saturated-fat')} AS satfat, {nut('fat')} AS fat,
    {nut('salt')} AS salt, {nut('sodium')} AS sodium,
    {nut('fiber')} AS fiber, {nut('proteins')} AS proteins,
    {nut('fruits-vegetables-legumes')} AS fvl_leg_final,
    {nut('fruits-vegetables-nuts')} AS fvl_nut_final,
    {nut('fruits-vegetables-legumes-estimate-from-ingredients')} AS fvl_leg_est,
    {nut('fruits-vegetables-nuts-estimate-from-ingredients')} AS fvl_nut_est
FROM read_parquet('{PARQUET}')
WHERE NOT coalesce(obsolete,false)
  AND nutriscore_grade IN ('a','b','c','d','e')
  AND nutriscore_score IS NOT NULL
  AND {nut('sugars')} IS NOT NULL AND {nut('saturated-fat')} IS NOT NULL AND {nut('proteins')} IS NOT NULL
  AND ({nut('salt')} IS NOT NULL OR {nut('sodium')} IS NOT NULL)
  AND ({nut('energy-kj')} IS NOT NULL OR {nut('energy-kcal')} IS NOT NULL OR {nut('energy')} IS NOT NULL)
USING SAMPLE {SAMPLE_N} ROWS
"""
print(f"loading sample up to {SAMPLE_N:,} ...", flush=True)
rows = con.execute(sql).fetchall()
cols = [d[0] for d in con.description]; idx = {c: i for i, c in enumerate(cols)}
def g(r, c): return r[idx[c]]
print(f"got {len(rows):,} rows\n", flush=True)

GRADES = "abcde"
exact = adj = 0
score_match = 0
cause = Counter()          # mismatch cause buckets
cat_bucket = Counter()     # mismatch by category type
mismatch_examples = []

for r in rows:
    e = g(r, "energy_kj")
    if e is None: e = g(r, "energy_any")
    if e is None and g(r, "energy_kcal") is not None: e = g(r, "energy_kcal") * 4.184
    salt = g(r, "salt")
    if salt is None and g(r, "sodium") is not None: salt = g(r, "sodium") * 2.5
    # FVL: prefer OFF's FINAL value field, then estimate, then 0
    fvl = g(r, "fvl_leg_final")
    for k in ("fvl_nut_final", "fvl_leg_est", "fvl_nut_est"):
        if fvl is None: fvl = g(r, k)
    if fvl is None: fvl = 0.0

    flags = flags_from_categories(g(r, "categories_tags"), g(r, "sweet"))
    x = NutriInput(energy=e, sugars=g(r, "sugars"), saturated_fat=g(r, "satfat"),
                   fat=g(r, "fat"), salt=salt, fiber=g(r, "fiber"), proteins=g(r, "proteins"),
                   fvl=fvl, **flags)
    s = compute_score_2023(x)
    my_score = s["score"]
    my_grade = compute_grade_2023(my_score, flags["is_beverage"], flags["is_water"], flags["is_fat_oil_nuts_seeds"])
    off_grade = g(r, "nutriscore_grade"); off_score = g(r, "nutriscore_score")

    smatch = (my_score == off_score)
    if smatch: score_match += 1
    if my_grade == off_grade:
        exact += 1
        continue
    if abs(GRADES.index(my_grade) - GRADES.index(off_grade)) == 1:
        adj += 1

    # localize cause
    active = tuple(k.replace("is_", "") for k, v in flags.items()
                   if v and k != "has_non_nutritive_sweetener") or ("general",)
    cat_bucket["+".join(active)] += 1
    if smatch:
        cause["score_ok_grade_diff (category/cutoff)"] += 1
    else:
        dscore = my_score - off_score
        cause[f"score_diff (input derivation)"] += 1
    if len(mismatch_examples) < 30:
        mismatch_examples.append((g(r, "code"), off_grade, my_grade, off_score, my_score, active))

total = len(rows)
print(f"=== v2 end-to-end vs OFF (n={total:,}) ===")
print(f"exact grade match: {exact:,} ({100*exact/total:.2f}%)   [v1 was 91.84%]")
print(f"within +/-1:       {exact+adj:,} ({100*(exact+adj)/total:.2f}%)")
print(f"score exact match: {score_match:,} ({100*score_match/total:.2f}%)")
print(f"\nmismatch cause:")
for k, v in cause.most_common():
    print(f"  {k:42} {v}")
print(f"\nmismatch by category type:")
for k, v in cat_bucket.most_common(10):
    print(f"  {k:30} {v}")
print(f"\nsample mismatches (off->mine, score off/mine):")
for code, og, mg, os_, ms, act in mismatch_examples[:20]:
    print(f"  {code}  {og}->{mg}  score {os_}/{ms}  {list(act)}")

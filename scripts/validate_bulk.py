#!/usr/bin/env python3
"""
End-to-end validation of the 2023 Nutri-Score port on the OFF bulk parquet.

Computes OUR grade from raw nutriments + categories_tags (full pipeline:
category detection, unit handling, salt-from-sodium, FVL extraction) and
compares to OFF's stored `nutriscore_grade`, on a sample of products where OFF
itself computed a 2023 grade and the core inputs are present.

This validates the parts NOT covered by validate_live.py: category flags and
raw-input handling.

Run: python validate_bulk.py [path/to/food.parquet] [sample_n]
"""
import sys
from collections import Counter
import duckdb
import nutriscore_2023 as nsmod
from nutriscore_2023 import NutriInput, flags_from_categories, compute

PARQUET = sys.argv[1] if len(sys.argv) > 1 else "data/food.parquet"
SAMPLE_N = int(sys.argv[2]) if len(sys.argv) > 2 else 100000

con = duckdb.connect()
con.execute("PRAGMA threads=4")

def nut(name, field="100g"):
    return (f"list_extract(list_transform(list_filter(nutriments, x -> x.name = '{name}'), "
            f"x -> x['{field}']), 1)")

sql = f"""
SELECT
    code,
    nutriscore_grade,
    categories_tags,
    coalesce(with_non_nutritive_sweeteners, 0) AS sweet,
    {nut('energy-kj')}        AS energy_kj,
    {nut('energy-kcal')}      AS energy_kcal,
    {nut('energy')}           AS energy_any,
    {nut('sugars')}           AS sugars,
    {nut('saturated-fat')}    AS satfat,
    {nut('fat')}              AS fat,
    {nut('salt')}             AS salt,
    {nut('sodium')}           AS sodium,
    {nut('fiber')}            AS fiber,
    {nut('proteins')}         AS proteins,
    {nut('fruits-vegetables-legumes-estimate-from-ingredients')} AS fvl_leg,
    {nut('fruits-vegetables-nuts-estimate-from-ingredients')}    AS fvl_nut_ing,
    {nut('fruits-vegetables-nuts-estimate')}                     AS fvl_nut_est
FROM read_parquet('{PARQUET}')
WHERE NOT coalesce(obsolete, false)
  AND nutriscore_grade IN ('a','b','c','d','e')
  AND {nut('sugars')} IS NOT NULL
  AND {nut('saturated-fat')} IS NOT NULL
  AND {nut('proteins')} IS NOT NULL
  AND ({nut('salt')} IS NOT NULL OR {nut('sodium')} IS NOT NULL)
  AND ({nut('energy-kj')} IS NOT NULL OR {nut('energy-kcal')} IS NOT NULL OR {nut('energy')} IS NOT NULL)
USING SAMPLE {SAMPLE_N} ROWS
"""

print(f"loading sample (up to {SAMPLE_N:,}) ...", flush=True)
rows = con.execute(sql).fetchall()
cols = [d[0] for d in con.description]
print(f"got {len(rows):,} rows\n", flush=True)

idx = {c: i for i, c in enumerate(cols)}
def g(r, c): return r[idx[c]]

match = 0
total = 0
adjacent = 0
conf = Counter()       # (off, mine) pairs
GRADES = "abcde"
mismatches = []

for r in rows:
    # energy in kJ
    e = g(r, "energy_kj")
    if e is None:
        e = g(r, "energy_any")
    if e is None and g(r, "energy_kcal") is not None:
        e = g(r, "energy_kcal") * 4.184
    # salt
    salt = g(r, "salt")
    if salt is None and g(r, "sodium") is not None:
        salt = g(r, "sodium") * 2.5
    # FVL (default 0 if no estimate available — matches the "validly zero" assumption)
    fvl = g(r, "fvl_leg")
    if fvl is None: fvl = g(r, "fvl_nut_ing")
    if fvl is None: fvl = g(r, "fvl_nut_est")
    if fvl is None: fvl = 0.0

    flags = flags_from_categories(g(r, "categories_tags"), g(r, "sweet"))
    x = NutriInput(
        energy=e, sugars=g(r, "sugars"), saturated_fat=g(r, "satfat"),
        fat=g(r, "fat"), salt=salt, fiber=g(r, "fiber"), proteins=g(r, "proteins"),
        fvl=fvl, **flags,
    )
    _, mine = compute(x)
    off = g(r, "nutriscore_grade")
    total += 1
    conf[(off, mine)] += 1
    if mine == off:
        match += 1
    elif abs(GRADES.index(mine) - GRADES.index(off)) == 1:
        adjacent += 1
        if len(mismatches) < 40:
            mismatches.append((g(r, "code"), off, mine, flags))
    else:
        if len(mismatches) < 40:
            mismatches.append((g(r, "code"), off, mine, flags))

print(f"=== End-to-end vs OFF nutriscore_grade ({total:,} products) ===")
print(f"exact match:    {match:,}  ({100*match/max(total,1):.2f}%)")
print(f"adjacent (±1):  {adjacent:,}  ({100*adjacent/max(total,1):.2f}%)")
print(f"off by >1:      {total-match-adjacent:,}  ({100*(total-match-adjacent)/max(total,1):.2f}%)")

print("\nConfusion (OFF rows x our cols):")
print("      " + "  ".join(f"{c:>6}" for c in GRADES))
for off in GRADES:
    line = "  ".join(f"{conf.get((off,m),0):>6}" for m in GRADES)
    print(f"  {off}   {line}")

# mismatch breakdown by category flag
print("\nMismatch category-flag breakdown:")
flagc = Counter()
for _, off, mine, fl in mismatches:
    active = [k for k, v in fl.items() if v and k != "has_non_nutritive_sweetener"]
    flagc[tuple(active) or ("general",)] += 1
for k, v in flagc.most_common():
    print(f"  {('+'.join(k)):40} {v}")

print("\nSample mismatches:")
for code, off, mine, fl in mismatches[:20]:
    active = [k.replace('is_','') for k, v in fl.items() if v and k != 'has_non_nutritive_sweetener']
    print(f"  {code}  off={off} mine={mine}  {active}")

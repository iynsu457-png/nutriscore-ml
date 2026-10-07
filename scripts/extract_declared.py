#!/usr/bin/env python3
"""
Extract the leakage-free DECLARED-FVL modeling dataset to data/declared_dataset.parquet.
Declared FVL is manufacturer-provided (independent of ingredient text), so predicting
it from text is a legitimate, non-circular task.
"""
import duckdb

con = duckdb.connect(); con.execute("PRAGMA threads=4")
def nut(n):
    return (f"list_extract(list_transform(list_filter(nutriments, x -> x.name='{n}'), "
            f"x -> x['100g']),1)")

DECL = ("(list_contains(misc_tags,'en:nutrition-fruits-vegetables-nuts') OR "
        " list_contains(misc_tags,'en:nutrition-fruits-vegetables-legumes'))")

sql = f"""
COPY (
  SELECT
    code,
    nutriscore_grade AS grade_off,
    nutriscore_score AS score_off,
    coalesce({nut('fruits-vegetables-legumes')}, {nut('fruits-vegetables-nuts')}) AS fvl_declared,
    coalesce({nut('energy-kj')}, {nut('energy')},
             {nut('energy-kcal')} * 4.184) AS energy_kj,
    {nut('sugars')} AS sugars,
    {nut('saturated-fat')} AS satfat,
    {nut('fat')} AS fat,
    coalesce({nut('salt')}, {nut('sodium')} * 2.5) AS salt,
    {nut('fiber')} AS fiber,
    {nut('proteins')} AS proteins,
    list_aggregate(list_transform(coalesce(ingredients_text, []), x -> coalesce(x.text,'')), 'string_agg', ' ') AS ingredients_text,
    list_extract(categories_tags, -1) AS cat_leaf,
    list_extract(countries_tags, 1) AS country1,
    coalesce(with_non_nutritive_sweeteners,0) AS sweet,
    categories_tags
  FROM read_parquet('data/food.parquet')
  WHERE NOT coalesce(obsolete,false) AND {DECL}
    AND nutriscore_grade IN ('a','b','c','d','e')
    AND coalesce({nut('fruits-vegetables-legumes')}, {nut('fruits-vegetables-nuts')}) IS NOT NULL
    AND {nut('sugars')} IS NOT NULL AND {nut('saturated-fat')} IS NOT NULL
    AND {nut('proteins')} IS NOT NULL AND {nut('fiber')} IS NOT NULL
    AND (coalesce({nut('salt')}, {nut('sodium')})) IS NOT NULL
    AND (coalesce({nut('energy-kj')}, {nut('energy')}, {nut('energy-kcal')})) IS NOT NULL
    AND length(coalesce(list_aggregate(list_transform(coalesce(ingredients_text, []), x -> coalesce(x.text,'')), 'string_agg', ' '),'')) > 3
) TO 'data/declared_dataset.parquet' (FORMAT PARQUET)
"""
con.execute(sql)
n = con.execute("SELECT count(*) FROM read_parquet('data/declared_dataset.parquet')").fetchone()[0]
print(f"[written] data/declared_dataset.parquet  ({n:,} rows)")
# quick peek
g = con.execute("SELECT grade_off, count(*) c FROM read_parquet('data/declared_dataset.parquet') GROUP BY grade_off ORDER BY grade_off").fetchall()
print("grade dist:", {k: v for k, v in g})
fvl = con.execute("SELECT avg(fvl_declared), median(fvl_declared), sum((fvl_declared<=0)::int), sum((fvl_declared>=80)::int), count(*) FROM read_parquet('data/declared_dataset.parquet')").fetchone()
print(f"FVL: mean={fvl[0]:.1f} median={fvl[1]:.1f} zero={100*fvl[2]/fvl[4]:.0f}% high(>=80)={100*fvl[3]/fvl[4]:.0f}%")

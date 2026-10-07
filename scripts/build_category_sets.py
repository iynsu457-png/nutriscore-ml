#!/usr/bin/env python3
"""
Build category closure sets for the 2023 Nutri-Score category flags, replicating
OFF's is_beverage/is_water/is_cheese/is_fat_oil_nuts_seeds/is_red_meat logic
(Food.pm + Config_off.pm), expanding each seed category to all descendants in the
OFF categories taxonomy (since categories_tags does not always include ancestors).

Writes ref/category_flags.json.
"""
import json
from collections import deque

tax = json.load(open("ref/categories_taxonomy.json"))

children = {}
for cat, v in tax.items():
    if isinstance(v, dict):
        for p in (v.get("parents") or []):
            children.setdefault(p, []).append(cat)

def own_hs(cat, key):
    v = tax.get(cat)
    if isinstance(v, dict) and isinstance(v.get(key), dict):
        return v[key].get("en")
    return None

def descendants(seeds):
    out = set(seeds); dq = deque(seeds)
    while dq:
        c = dq.popleft()
        for ch in children.get(c, []):
            if ch not in out:
                out.add(ch); dq.append(ch)
    return out

# --- fat / oil / nuts / seeds (HS headings + direct) -------------------------
FAT_HEADINGS = {"08.01", "08.02", "12.02", "12.04", "12.06", "12.07"}
FAT_CODES = {"2008.11", "2008.19"}
REDMEAT_HEADINGS = {"02.01", "02.02", "02.03", "02.04", "02.05", "02.06"}

fat_seeds = {c for c in tax if isinstance(tax.get(c), dict)
             and (own_hs(c, "wco_hs_heading") in FAT_HEADINGS
                  or own_hs(c, "wco_hs_code") in FAT_CODES)} | {"en:fats", "en:creams", "en:seeds"}
redmeat_seeds = {c for c in tax if isinstance(tax.get(c), dict)
                 and own_hs(c, "wco_hs_heading") in REDMEAT_HEADINGS}

fat = descendants(fat_seeds) - descendants({"en:chestnuts"})
redmeat = descendants(redmeat_seeds)

# --- beverages (2023): base + additions, minus exclusions --------------------
bev_base = descendants({"en:beverages", "en:beverage-preparations"})
bev_add = descendants({
    "en:milks", "en:plant-based-milk-alternatives", "en:dairy-drinks",
    "en:plant-based-beverages", "en:tea-based-beverages", "en:iced-teas",
    "en:herbal-tea-beverages", "en:coffee-beverages", "en:coffee-drinks",
    "en:coffees", "en:herbal-teas", "en:teas",
})
bev_excl = descendants({"en:meal-replacement", "en:soups"})

# --- water / cheese ----------------------------------------------------------
water = descendants({"en:spring-waters"})
water_excl = descendants({"en:flavored-waters", "en:flavoured-waters"})
cheese = descendants({"en:cheeses"})
cheese_excl = descendants({"fr:fromages-blancs"})

sets = {
    "fat": sorted(fat), "redmeat": sorted(redmeat),
    "bev_base": sorted(bev_base), "bev_add": sorted(bev_add), "bev_excl": sorted(bev_excl),
    "water": sorted(water), "water_excl": sorted(water_excl),
    "cheese": sorted(cheese), "cheese_excl": sorted(cheese_excl),
}
json.dump(sets, open("ref/category_flags.json", "w"))
for k, v in sets.items():
    print(f"  {k:12} {len(v):>6,} categories")
print("[written] ref/category_flags.json")

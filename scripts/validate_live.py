#!/usr/bin/env python3
"""
Validate the local 2023 Nutri-Score port against Open Food Facts' own
computation, fetched live from the OFF API.

Strategy: OFF returns the full nutriscore.2023 breakdown (input flags + each
component's value and points). We recompute each component's points from its
value using OUR threshold tables, recompute the score and grade with OUR logic,
and compare to OFF. This validates the threshold tables, grade cutoffs, and the
count-proteins rule exactly (independent of category detection, since we use
OFF's flags as given).

Run: python validate_live.py
"""
import json, time, urllib.request, urllib.parse
from collections import Counter
import nutriscore_2023 as ns

UA = {"User-Agent": "NutriScoreML-research/0.1 (academic validation; contact research)"}

def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)

FIELDS = "code,product_name,categories_tags,nutriscore,nutriments,with_non_nutritive_sweeteners"

def search(tag=None, page_size=50, sort="unique_scans_n"):
    base = "https://world.openfoodfacts.org/api/v2/search"
    params = {"fields": FIELDS, "page_size": str(page_size), "sort_by": sort,
              "states_tags": "en:nutrition-facts-completed"}
    if tag:
        params["categories_tags_en"] = tag
    return get(base + "?" + urllib.parse.urlencode(params)).get("products", [])

# threshold table id per component
def table_for(comp_id, bev):
    m = {
        "energy": "energy", "energy_from_saturated_fat": "energy_from_saturated_fat",
        "sugars": "sugars", "saturated_fat": "saturated_fat",
        "saturated_fat_ratio": "saturated_fat_ratio", "salt": "salt",
        "proteins": "proteins", "fiber": "fiber",
        "fruits_vegetables_legumes": "fruits_vegetables_legumes",
    }
    key = m[comp_id]
    bk = key + "_beverages"
    if bev and bk in ns.TH:
        return ns.TH[bk], (comp_id == "saturated_fat_ratio")
    return ns.TH[key], (comp_id == "saturated_fat_ratio")

def my_points(comp_id, value, bev):
    if comp_id == "non_nutritive_sweeteners":
        return 4 if (value or 0) > 0 else 0
    tbl, ge = table_for(comp_id, bev)
    return ns._points(value, tbl, ge=ge)

def main():
    queries = [None, "en:beverages", "en:cheeses", "en:vegetable-oils",
               "en:nuts", "en:breakfast-cereals", "en:yogurts", "en:hams"]
    products = {}
    for tag in queries:
        try:
            for p in search(tag):
                if p.get("code"):
                    products[p["code"]] = p
            time.sleep(1.0)  # be polite to the API
        except Exception as e:
            print(f"  [warn] search {tag}: {e}")
    print(f"fetched {len(products)} unique products\n")

    checked = 0
    grade_match = score_match = cp_match = 0
    comp_pts_total = comp_pts_match = 0
    comp_mismatch = Counter()
    grade_mismatches = []

    for code, p in products.items():
        ns23 = (p.get("nutriscore") or {}).get("2023") or {}
        if not ns23.get("nutriscore_computed"):
            continue
        data = ns23.get("data") or {}
        comps = data.get("components") or {}
        neg = comps.get("negative") or []
        pos = comps.get("positive") or []
        if not neg:
            continue
        bev = bool(data.get("is_beverage"))
        flags = dict(is_beverage=bev, is_water=bool(data.get("is_water")),
                     is_fat_oil_nuts_seeds=bool(data.get("is_fat_oil_nuts_seeds")))

        # recompute each component's points with our tables
        my_neg = 0
        ok = True
        for c in neg:
            mp = my_points(c["id"], c.get("value"), bev)
            comp_pts_total += 1
            if mp == c["points"]:
                comp_pts_match += 1
            else:
                comp_mismatch[c["id"]] += 1
                ok = False
            my_neg += mp

        # positive: proteins / fiber / fvl. Determine count_proteins ourselves.
        pos_vals = {c["id"]: c.get("value") for c in pos}
        pos_pts_off = {c["id"]: c["points"] for c in pos}
        my_fiber = my_points("fiber", pos_vals.get("fiber"), bev)
        my_fvl = my_points("fruits_vegetables_legumes", pos_vals.get("fruits_vegetables_legumes"), bev)
        my_prot = my_points("proteins", pos_vals.get("proteins"), bev)
        # red-meat cap (use OFF flag)
        if data.get("is_red_meat_product") and my_prot > 2:
            my_prot = 2
        # count proteins
        if bev or data.get("is_cheese"):
            count_proteins = True
        elif data.get("is_fat_oil_nuts_seeds"):
            count_proteins = my_neg < 7
        else:
            count_proteins = my_neg < 11
        if bool(count_proteins) == bool(data.get("count_proteins")):
            cp_match += 1

        # validate listed positive component points
        for cid, mp in (("fiber", my_fiber), ("fruits_vegetables_legumes", my_fvl), ("proteins", my_prot)):
            if cid in pos_pts_off:
                comp_pts_total += 1
                if mp == pos_pts_off[cid]:
                    comp_pts_match += 1
                else:
                    comp_mismatch[cid] += 1

        my_pos = my_fiber + my_fvl + (my_prot if count_proteins else 0)
        my_score = my_neg - my_pos
        my_grade = ns.compute_grade_2023(my_score, **flags)

        checked += 1
        if my_score == ns23.get("score"):
            score_match += 1
        if my_grade == ns23.get("grade"):
            grade_match += 1
        else:
            grade_mismatches.append(
                (code, p.get("product_name"), my_score, ns23.get("score"),
                 my_grade, ns23.get("grade"),
                 [k for k in ("is_beverage","is_fat_oil_nuts_seeds","is_cheese","is_red_meat_product") if data.get(k)]))

    print(f"=== Validation over {checked} products with OFF 2023 computed ===")
    print(f"grade match:           {grade_match}/{checked}  ({100*grade_match/max(checked,1):.1f}%)")
    print(f"score match:           {score_match}/{checked}  ({100*score_match/max(checked,1):.1f}%)")
    print(f"count_proteins match:  {cp_match}/{checked}  ({100*cp_match/max(checked,1):.1f}%)")
    print(f"component-points match: {comp_pts_match}/{comp_pts_total}  ({100*comp_pts_match/max(comp_pts_total,1):.1f}%)")
    if comp_mismatch:
        print("component mismatches by id:", dict(comp_mismatch))
    if grade_mismatches:
        print(f"\n--- grade mismatches ({len(grade_mismatches)}) ---")
        for m in grade_mismatches[:25]:
            print(f"  {m[0]} {str(m[1])[:30]:30} my={m[4]}({m[2]}) off={m[5]}({m[3]}) flags={m[6]}")

if __name__ == "__main__":
    main()

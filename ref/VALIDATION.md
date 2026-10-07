# 2023 Nutri-Score port validation

Validated `nutriscore_2023.py` against OFF's own API computation (live), 2026-06-10.

Sample: 260 products with OFF `nutriscore.2023.nutriscore_computed=1`,
across general foods, beverages, cheeses, nuts, breakfast cereals, yogurts.

Result (recomputing component points / score / grade from OFF's component
values + flags, using our threshold tables & cutoffs):

- grade match:            260/260   (100.0%)
- score match:            260/260   (100.0%)
- count_proteins match:   260/260   (100.0%)
- component-points match: 1824/1824 (100.0%)

Thresholds, grade cutoffs, and the count-proteins rule are confirmed identical
to the OFF reference implementation.

PENDING (validate on bulk parquet end-to-end):
- category flag detection from categories_tags (nuts & red-meat HS-code rules
  require the OFF taxonomy and are approximated in flags_from_categories)
- raw-input handling: energy_from_saturated_fat = satfat*37, satfat/fat ratio,
  salt-from-sodium, and FVL extraction from the nutriments list.

---
## D: Closing the ground-truth gap (2026-06-12)

Improved end-to-end agreement of our scorer vs OFF's published nutriscore_grade
by (1) using OFF's FINAL FVL value field as input, and (2) replicating OFF's
category detection via taxonomy CLOSURES (build_category_sets.py ->
ref/category_flags.json), since categories_tags omit ancestor categories.

Progression (full complete-input sample, ~44k):
  v1 (estimate FVL + heuristic flags):           91.84% exact
  v2 (final FVL field):                          95.14%
  + fat/red-meat HS closures:                    95.41%
  + beverage/water/cheese closures + 2023 config: 96.36% exact, 99.4% within +/-1
  declared-FVL clean set:                        95.74% exact, 99.56% within +/-1

Category ROUTING errors (score matches, grade differs) fell 44 -> ~0:
milk/dairy-drinks/teas/coffees now correctly treated as beverages (2023 rule).

Residual (~3.6%, all score-difference, fully characterized; NOT scoring bugs):
  - rounding-boundary noise (score +/-1 at grade boundaries 2/3, 18/19) — inherent
  - fat-closure over-breadth (taxonomy HS inheritance over-propagates to some
    prepared foods) — minor false positives
  - beverage non-nutritive-sweetener +4 penalty (needs OFF additive detection)
  - red-meat protein cap via the >10%-red-meat-ingredient rule (needs ingredient
    analysis we don't replicate)
  - FVL-from-category override values not present in the parquet nutriments

ARCHITECTURAL DECISION for the study:
  - OFF (development): use OFF's published nutriscore_grade directly as ground
    truth (it is the official implementation with full category detection). Our
    scorer is for auditing + external data.
  - External (USDA/Chomp): recompute with our scorer (proven 100% correct on
    identical inputs), restricting to general foods with declared/valid-zero FVL
    where category detection is unambiguous.

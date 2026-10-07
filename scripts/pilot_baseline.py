#!/usr/bin/env python3
"""
Baseline-beating grade-recovery pilot.

Question: when FVL% is withheld, does an ML model recover the Nutri-Score grade
better than the deterministic baselines OFF/Yuka would use -- especially in the
FVL-SENSITIVE subgroup (where FVL actually changes the grade)?

Setup (leakage-free): train on DECLARED FVL (manufacturer-provided, independent
of ingredient text). Each method produces an FVL estimate; the grade is then
computed by our validated scorer using that FVL + the available nutrients. The
true grade uses the true declared FVL. Only FVL varies across methods.
"""
import re, numpy as np, pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import cohen_kappa_score, mean_absolute_error
import lightgbm as lgb
from nutriscore_2023 import NutriInput, flags_from_categories, compute_score_2023, compute_grade_2023

RNG = 42
GR = "abcde"; G2I = {g: i for i, g in enumerate(GR)}
df = pd.read_parquet("data/declared_dataset.parquet")
df = df[df["fvl_declared"].between(0, 100)].reset_index(drop=True)
print(f"rows: {len(df):,}")

# precompute per-row flags + a grade(fvl) closure
flags_list = [flags_from_categories(ct, sw) for ct, sw in zip(df["categories_tags"], df["sweet"])]
def grade_of(i, fvl):
    r = df.iloc[i]; fl = flags_list[i]
    x = NutriInput(energy=r.energy_kj, sugars=r.sugars, saturated_fat=r.satfat, fat=r.fat,
                   salt=r.salt, fiber=r.fiber, proteins=r.proteins, fvl=float(fvl), **fl)
    s = compute_score_2023(x)
    return compute_grade_2023(s["score"], fl["is_beverage"], fl["is_water"], fl["is_fat_oil_nuts_seeds"])

idx = np.arange(len(df))
true_grade = np.array([grade_of(i, df.fvl_declared[i]) for i in idx])
grade_fvl0 = np.array([grade_of(i, 0.0) for i in idx])
sensitive = true_grade != grade_fvl0
print(f"FVL-sensitive (grade changes vs FVL=0): {sensitive.sum():,} ({100*sensitive.mean():.1f}%)\n")

tr, te = train_test_split(idx, test_size=0.25, random_state=RNG, stratify=true_grade)

# ---- features ----
num_cols = ["energy_kj", "sugars", "satfat", "fat", "salt", "fiber", "proteins"]
Xnum = df[num_cols].fillna(-1).values
tfidf = TfidfVectorizer(min_df=5, max_features=4000, ngram_range=(1, 2), lowercase=True)
Xtxt_tr = tfidf.fit_transform(df.ingredients_text.iloc[tr])
Xtxt = tfidf.transform(df.ingredients_text)
# category frequency-mean FVL feature (train only)
cat_mean = df.iloc[tr].groupby("cat_leaf")["fvl_declared"].mean()
global_mean = df.fvl_declared.iloc[tr].mean()
cat_feat = df.cat_leaf.map(cat_mean).fillna(global_mean).values.reshape(-1, 1)

import scipy.sparse as sp
def build(rows):
    return sp.hstack([sp.csr_matrix(Xnum[rows]), Xtxt[rows], sp.csr_matrix(cat_feat[rows])]).tocsr()

# ---- FVL estimators ----
y_fvl = df.fvl_declared.values
def fit_lgb(Xtr, ytr):
    m = lgb.LGBMRegressor(n_estimators=400, learning_rate=0.05, num_leaves=63,
                          subsample=0.8, colsample_bytree=0.6, random_state=RNG, n_jobs=4, verbose=-1)
    m.fit(Xtr, ytr); return m

# ML-full: nutrients + text + category
ml = fit_lgb(build(tr), y_fvl[tr])
pred_ml = np.clip(ml.predict(build(te)), 0, 100)
# ML nutrients-only (no text) -> isolates text value
ml_no = fit_lgb(sp.csr_matrix(Xnum[tr]), y_fvl[tr])
pred_ml_no = np.clip(ml_no.predict(sp.csr_matrix(Xnum[te])), 0, 100)

# Baselines
pred_zero = np.zeros(len(te))
pred_catmean = df.cat_leaf.iloc[te].map(cat_mean).fillna(global_mean).values
# keyword rule: count fruit/veg/legume/nut mentions (en+fr), fit linear scale on train
KW = r"(fruit|vegetable|legume|tomato|apple|orange|carrot|potato|pea|bean|lentil|nut|almond|fraise|pomme|tomate|légume|fruits|carotte|haricot|noiset|amande|olive|pomme de terre|oignon|onion|spinach|épinard)"
def kw_density(t):
    t = (t or "").lower(); toks = re.findall(r"[a-zà-ÿ]+", t)
    if not toks: return 0.0
    hits = len(re.findall(KW, t))
    return hits / max(len(toks), 1)
kwd = np.array([kw_density(t) for t in df.ingredients_text])
# fit FVL ~ a*density on train (least squares through data, clipped)
a = np.clip(np.polyfit(kwd[tr], y_fvl[tr], 1), -1e6, 1e6)
pred_kw = np.clip(np.polyval(a, kwd[te]), 0, 100)

# ---- evaluate ----
def grades_from_fvl(rows, fvls):
    return np.array([grade_of(i, f) for i, f in zip(rows, fvls)])

def report(name, fvl_pred):
    g = grades_from_fvl(te, fvl_pred)
    tg = true_grade[te]
    gi = np.array([G2I[x] for x in g]); ti = np.array([G2I[x] for x in tg])
    fvl_mae = mean_absolute_error(y_fvl[te], fvl_pred)
    acc = (g == tg).mean(); qwk = cohen_kappa_score(ti, gi, weights="quadratic"); mae = np.abs(gi - ti).mean()
    # sensitive subset (within test)
    sm = sensitive[te]
    accs = (g[sm] == tg[sm]).mean() if sm.sum() else float("nan")
    qwks = cohen_kappa_score(ti[sm], gi[sm], weights="quadratic") if sm.sum() > 1 else float("nan")
    print(f"  {name:22} FVL_MAE={fvl_mae:5.1f} | ALL: acc={acc:.3f} QWK={qwk:.3f} gradeMAE={mae:.3f} "
          f"| SENSITIVE(n={sm.sum()}): acc={accs:.3f} QWK={qwks:.3f}")
    return dict(name=name, acc=acc, qwk=qwk, acc_sens=accs, qwk_sens=qwks, fvl_mae=fvl_mae)

print(f"test n={len(te):,}  (sensitive in test: {sensitive[te].sum():,})\n")
print("method                 FVL accuracy of recovered grade vs TRUE grade")
res = []
res.append(report("B1 FVL=0", pred_zero))
res.append(report("B2 category-mean", pred_catmean))
res.append(report("B3 keyword-rule", pred_kw))
res.append(report("ML nutrients-only", pred_ml_no))
res.append(report("ML full (txt+cat+nut)", pred_ml))

# headline: ML vs best baseline on sensitive subgroup
best_bl = max(res[:3], key=lambda d: d["acc_sens"])
ml_full = res[-1]
print(f"\nHEADLINE (FVL-sensitive subgroup): best baseline = {best_bl['name']} acc={best_bl['acc_sens']:.3f} "
      f"vs ML-full acc={ml_full['acc_sens']:.3f}  (delta={ml_full['acc_sens']-best_bl['acc_sens']:+.3f})")
print(f"           QWK: best baseline={best_bl['qwk_sens']:.3f} vs ML-full={ml_full['qwk_sens']:.3f}")

#!/usr/bin/env python3
"""
Transportability stress-test: train on France declared products, test on
non-France declared products, to check whether the ML advantage survives the
geographic distribution shift.
"""
import re, numpy as np, pandas as pd, scipy.sparse as sp
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import cohen_kappa_score, mean_absolute_error
import lightgbm as lgb
from nutriscore_2023 import NutriInput, flags_from_categories, compute_score_2023, compute_grade_2023

RNG = 42; GR = "abcde"; G2I = {g: i for i, g in enumerate(GR)}
df = pd.read_parquet("data/declared_dataset.parquet")
df = df[df.fvl_declared.between(0, 100)].reset_index(drop=True)
is_fr = df.country1.fillna("").str.contains("france")
tr = np.where(is_fr.values)[0]; te = np.where(~is_fr.values)[0]
print(f"train (France): {len(tr):,}   test (non-France): {len(te):,}")

flags_list = [flags_from_categories(ct, sw) for ct, sw in zip(df.categories_tags, df.sweet)]
def grade_of(i, fvl):
    r = df.iloc[i]; fl = flags_list[i]
    x = NutriInput(energy=r.energy_kj, sugars=r.sugars, saturated_fat=r.satfat, fat=r.fat,
                   salt=r.salt, fiber=r.fiber, proteins=r.proteins, fvl=float(fvl), **fl)
    return compute_grade_2023(compute_score_2023(x)["score"], fl["is_beverage"], fl["is_water"], fl["is_fat_oil_nuts_seeds"])

y_fvl = df.fvl_declared.values
true_grade = np.array([grade_of(i, y_fvl[i]) for i in range(len(df))])
grade0 = np.array([grade_of(i, 0.0) for i in range(len(df))])
sens = true_grade != grade0

num = df[["energy_kj","sugars","satfat","fat","salt","fiber","proteins"]].fillna(-1).values
tf = TfidfVectorizer(min_df=5, max_features=4000, ngram_range=(1,2))
tf.fit(df.ingredients_text.iloc[tr]); Xtxt = tf.transform(df.ingredients_text)
cat_mean = df.iloc[tr].groupby("cat_leaf").fvl_declared.mean(); gm = y_fvl[tr].mean()
catf = df.cat_leaf.map(cat_mean).fillna(gm).values.reshape(-1,1)
build = lambda rows: sp.hstack([sp.csr_matrix(num[rows]), Xtxt[rows], sp.csr_matrix(catf[rows])]).tocsr()

def fit(X, y):
    m = lgb.LGBMRegressor(n_estimators=400, learning_rate=0.05, num_leaves=63, subsample=0.8,
                          colsample_bytree=0.6, random_state=RNG, n_jobs=4, verbose=-1); m.fit(X, y); return m
ml = fit(build(tr), y_fvl[tr]); pred_ml = np.clip(ml.predict(build(te)), 0, 100)
pred_zero = np.zeros(len(te))
pred_cat = df.cat_leaf.iloc[te].map(cat_mean).fillna(gm).values

def report(name, fvl_pred):
    g = np.array([grade_of(i, f) for i, f in zip(te, fvl_pred)]); tg = true_grade[te]
    gi = np.array([G2I[x] for x in g]); ti = np.array([G2I[x] for x in tg]); sm = sens[te]
    acc = (g==tg).mean(); qwk = cohen_kappa_score(ti, gi, weights="quadratic")
    accs = (g[sm]==tg[sm]).mean() if sm.sum() else float("nan")
    qwks = cohen_kappa_score(ti[sm], gi[sm], weights="quadratic") if sm.sum()>1 else float("nan")
    print(f"  {name:20} ALL acc={acc:.3f} QWK={qwk:.3f} | SENSITIVE(n={sm.sum()}) acc={accs:.3f} QWK={qwks:.3f} | FVL_MAE={mean_absolute_error(y_fvl[te],fvl_pred):.1f}")
    return accs

print("\nTRANSPORT (France -> non-France):")
a0 = report("B1 FVL=0", pred_zero)
ac = report("B2 category-mean", pred_cat)
am = report("ML full", pred_ml)
print(f"\n  ML-full vs category-mean on sensitive subgroup: {am:.3f} vs {ac:.3f} (delta={am-ac:+.3f})")

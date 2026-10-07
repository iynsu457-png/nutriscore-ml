"""Bootstrap 95% CIs for the headline grade-recovery metrics. Product-level
bootstrap of the held-out test set, 2000 resamples (RNG=42; point estimates
match Table 3).
Run: source .venv/bin/activate && python scripts/bootstrap_ci.py
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
import numpy as np, pandas as pd, scipy.sparse as sp
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import cohen_kappa_score, mean_absolute_error
import lightgbm as lgb
from nutriscore_2023 import NutriInput, flags_from_categories, compute_score_2023, compute_grade_2023

RNG=42; B=2000; GR="abcde"; G2I={g:i for i,g in enumerate(GR)}
rng=np.random.RandomState(RNG)
df=pd.read_parquet("data/declared_dataset.parquet"); df=df[df["fvl_declared"].between(0,100)].reset_index(drop=True)
flags=[flags_from_categories(ct,sw) for ct,sw in zip(df["categories_tags"],df["sweet"])]
def grade_of(i,fvl):
    r=df.iloc[i]; fl=flags[i]
    x=NutriInput(energy=r.energy_kj,sugars=r.sugars,saturated_fat=r.satfat,fat=r.fat,salt=r.salt,
                 fiber=r.fiber,proteins=r.proteins,fvl=float(fvl),**fl)
    return compute_grade_2023(compute_score_2023(x)["score"],fl["is_beverage"],fl["is_water"],fl["is_fat_oil_nuts_seeds"])
idx=np.arange(len(df))
true_grade=np.array([grade_of(i,df.fvl_declared[i]) for i in idx])
grade0=np.array([grade_of(i,0.0) for i in idx]); sensitive=true_grade!=grade0
tr,te=train_test_split(idx,test_size=0.25,random_state=RNG,stratify=true_grade)

num=df[["energy_kj","sugars","satfat","fat","salt","fiber","proteins"]].fillna(-1).values
tf=TfidfVectorizer(min_df=5,max_features=4000,ngram_range=(1,2),lowercase=True); tf.fit(df.ingredients_text.iloc[tr])
Xtxt=tf.transform(df.ingredients_text)
cat_mean=df.iloc[tr].groupby("cat_leaf")["fvl_declared"].mean(); gm=df.fvl_declared.iloc[tr].mean()
catf=df.cat_leaf.map(cat_mean).fillna(gm).values.reshape(-1,1)
build=lambda rows: sp.hstack([sp.csr_matrix(num[rows]),Xtxt[rows],sp.csr_matrix(catf[rows])]).tocsr()
ml=lgb.LGBMRegressor(n_estimators=400,learning_rate=0.05,num_leaves=63,subsample=0.8,
                     colsample_bytree=0.6,random_state=RNG,n_jobs=4,verbose=-1).fit(build(tr),df.fvl_declared.values[tr])

y=df.fvl_declared.values
pred_full=np.clip(ml.predict(build(te)),0,100)
pred_cat=df.cat_leaf.iloc[te].map(cat_mean).fillna(gm).values
g_full=np.array([grade_of(i,f) for i,f in zip(te,pred_full)])
g_cat =np.array([grade_of(i,f) for i,f in zip(te,pred_cat)])
tg=true_grade[te]; sm=sensitive[te]
ti=np.array([G2I[x] for x in tg]); gif=np.array([G2I[x] for x in g_full]); gic=np.array([G2I[x] for x in g_cat])
ytrue=y[te]
def accqwk(t_codes, p_codes):
    acc=(p_codes==t_codes).mean()
    qwk=cohen_kappa_score(t_codes,p_codes,weights="quadratic") if len(set(t_codes))>1 and len(set(p_codes))>1 else np.nan
    return acc,qwk
def ci(vals):
    v=np.array(vals); v=v[~np.isnan(v)]; return np.percentile(v,2.5),np.percentile(v,97.5)

n=len(te); idxs=np.arange(n)
acc_f,qwk_f,acc_c,qwk_c,d_acc,d_qwk,maef=[],[],[],[],[],[],[]
for _ in range(B):
    bs=rng.choice(idxs,size=n,replace=True)
    s=bs[sm[bs]]                       # resampled rows that are FVL-sensitive
    if len(s)<2: continue
    af,qf=accqwk(ti[s],gif[s]); ac,qc=accqwk(ti[s],gic[s])
    acc_f.append(af); qwk_f.append(qf); acc_c.append(ac); qwk_c.append(qc)
    d_acc.append(af-ac); d_qwk.append(qf-qc)
    maef.append(mean_absolute_error(ytrue[bs],pred_full[bs]))
def fmt(name,point,vals):
    lo,hi=ci(vals); print(f"  {name:38} {point:.3f}  95% CI [{lo:.3f}, {hi:.3f}]")
print(f"Bootstrap {B} resamples; test n={n}, FVL-sensitive n={sm.sum()}\n")
print("FVL-sensitive subgroup:")
fmt("Full model accuracy", accqwk(ti[sm],gif[sm])[0], acc_f)
fmt("Full model QWK", accqwk(ti[sm],gif[sm])[1], qwk_f)
fmt("Category-mean accuracy", accqwk(ti[sm],gic[sm])[0], acc_c)
fmt("Category-mean QWK", accqwk(ti[sm],gic[sm])[1], qwk_c)
fmt("Delta accuracy (full - cat)", accqwk(ti[sm],gif[sm])[0]-accqwk(ti[sm],gic[sm])[0], d_acc)
fmt("Delta QWK (full - cat)", accqwk(ti[sm],gif[sm])[1]-accqwk(ti[sm],gic[sm])[1], d_qwk)
print("\nOverall:")
fmt("Full model FVL MAE", mean_absolute_error(ytrue,pred_full), maef)

"""Interpretability figures for the CDN manuscript, from the identical pilot pipeline:
  Figure 3 = LightGBM feature importance (gain) of the full FVL model
  Figure 4 = confusion matrix (true vs recovered grade) of the full model on the held-out test
Reuses scripts/pilot_baseline.py logic (RNG=42) so results match Table 3.
Run: source .venv/bin/activate && python scripts/make_interpretability.py
"""
import os, sys, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
import numpy as np, pandas as pd, scipy.sparse as sp
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
import lightgbm as lgb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from nutriscore_2023 import NutriInput, flags_from_categories, compute_score_2023, compute_grade_2023

OUT = "manuscript/figures"; DPI = 300
ACCENT="#1A6FB0"; WARM="#E07B39"; INK="#222831"; GRID="#E4E8EC"
plt.rcParams.update({"font.size":11,"font.family":"DejaVu Sans","axes.edgecolor":INK,
                     "axes.linewidth":0.8,"text.color":INK,"axes.labelcolor":INK,
                     "xtick.color":INK,"ytick.color":INK,"savefig.dpi":DPI,"figure.dpi":DPI})
def despine(ax,left=True,bottom=True):
    for s in ("top","right"): ax.spines[s].set_visible(False)
    if not left: ax.spines["left"].set_visible(False)
    if not bottom: ax.spines["bottom"].set_visible(False)
def save(fig,name):
    fig.savefig(f"{OUT}/{name}",format="jpg",dpi=DPI,bbox_inches="tight",pad_inches=0.06,facecolor="white"); plt.close(fig)

RNG=42; GR="abcde"; G2I={g:i for i,g in enumerate(GR)}
df = pd.read_parquet("data/declared_dataset.parquet")
df = df[df["fvl_declared"].between(0,100)].reset_index(drop=True)
flags_list=[flags_from_categories(ct,sw) for ct,sw in zip(df["categories_tags"],df["sweet"])]
def grade_of(i,fvl):
    r=df.iloc[i]; fl=flags_list[i]
    x=NutriInput(energy=r.energy_kj,sugars=r.sugars,saturated_fat=r.satfat,fat=r.fat,
                 salt=r.salt,fiber=r.fiber,proteins=r.proteins,fvl=float(fvl),**fl)
    return compute_grade_2023(compute_score_2023(x)["score"],fl["is_beverage"],fl["is_water"],fl["is_fat_oil_nuts_seeds"])
idx=np.arange(len(df))
true_grade=np.array([grade_of(i,df.fvl_declared[i]) for i in idx])
tr,te=train_test_split(idx,test_size=0.25,random_state=RNG,stratify=true_grade)

num_cols=["energy_kj","sugars","satfat","fat","salt","fiber","proteins"]
nice={"energy_kj":"energy","sugars":"sugars","satfat":"saturated fat","fat":"total fat",
      "salt":"salt","fiber":"fiber","proteins":"protein"}
Xnum=df[num_cols].fillna(-1).values
tfidf=TfidfVectorizer(min_df=5,max_features=4000,ngram_range=(1,2),lowercase=True)
Xtxt_tr=tfidf.fit_transform(df.ingredients_text.iloc[tr]); Xtxt=tfidf.transform(df.ingredients_text)
cat_mean=df.iloc[tr].groupby("cat_leaf")["fvl_declared"].mean(); global_mean=df.fvl_declared.iloc[tr].mean()
cat_feat=df.cat_leaf.map(cat_mean).fillna(global_mean).values.reshape(-1,1)
def build(rows): return sp.hstack([sp.csr_matrix(Xnum[rows]),Xtxt[rows],sp.csr_matrix(cat_feat[rows])]).tocsr()

ml=lgb.LGBMRegressor(n_estimators=400,learning_rate=0.05,num_leaves=63,subsample=0.8,
                     colsample_bytree=0.6,random_state=RNG,n_jobs=4,verbose=-1)
ml.fit(build(tr),df.fvl_declared.values[tr])

# ---- feature names + gain importance ----
feat_names=[nice[c] for c in num_cols]+["text: "+t for t in tfidf.get_feature_names_out()]+["category-mean FVL"]
gain=ml.booster_.feature_importance(importance_type="gain")
order=np.argsort(gain)[::-1][:15][::-1]   # top 15, ascending for barh
labels=[feat_names[i] for i in order]; vals=[gain[i] for i in order]
isnum=[not labels[k].startswith("text:") for k in range(len(labels))]
colors=[WARM if isnum[k] else ACCENT for k in range(len(labels))]

print("TOP FEATURES (gain):")
for l,v in list(zip(labels,vals))[::-1]: print(f"  {l:30} {v:,.0f}")

# ---- Figure 3: SHAP beeswarm summary (top 15 by mean |SHAP|) ----
import shap
expl = shap.TreeExplainer(ml)
rs = np.random.RandomState(RNG)
samp = rs.choice(te, size=min(1500, len(te)), replace=False)
Xs = build(samp).toarray()
sv = expl.shap_values(Xs)
disp_names = [f.replace("text: ", "“") + "”" if f.startswith("text: ") else f for f in feat_names]
plt.figure(figsize=(7.6, 5.4))
shap.summary_plot(sv, Xs, feature_names=disp_names, max_display=15, show=False,
                  color_bar_label="Feature value", plot_size=None)
fig = plt.gcf()
fig.axes[-1].set_ylabel("Feature value (red high, blue low)", fontsize=9)
for a in fig.axes:
    a.tick_params(labelsize=9)
fig.axes[0].set_xlabel("SHAP value (impact on predicted FVL)", fontsize=10)
fig.savefig(f"{OUT}/fig3_feature_importance.jpg", dpi=DPI, bbox_inches="tight",
            pad_inches=0.06, facecolor="white")
plt.close(fig)
print("SHAP beeswarm written for", len(samp), "test products")

# ---- confusion matrix: true vs recovered grade (full model, test) ----
pred_fvl=np.clip(ml.predict(build(te)),0,100)
pred_grade=np.array([grade_of(i,f) for i,f in zip(te,pred_fvl)])
tg=true_grade[te]
labels_g=list("ABCDE")
M=np.zeros((5,5),dtype=int)
for t_,p_ in zip(tg,pred_grade): M[G2I[t_],G2I[p_]]+=1
acc=(pred_grade==tg).mean()
print(f"\noverall exact accuracy (test n={len(te)}): {acc:.3f}")
print("confusion (rows=true, cols=pred) A-E:"); print(M)

blues=LinearSegmentedColormap.from_list("b",["#ffffff",ACCENT])
fig,ax=plt.subplots(figsize=(5.6,5.0))
Mn=M/M.sum(axis=1,keepdims=True).clip(min=1)
im=ax.imshow(Mn,cmap=blues,vmin=0,vmax=1)
ax.set_xticks(range(5)); ax.set_xticklabels(labels_g); ax.set_yticks(range(5)); ax.set_yticklabels(labels_g)
ax.set_xlabel("Recovered grade"); ax.set_ylabel("True grade")
for r in range(5):
    for c in range(5):
        ax.text(c,r,f"{M[r,c]:,}",ha="center",va="center",
                color="white" if Mn[r,c]>0.55 else INK,fontsize=10)
ax.set_xticks(np.arange(-.5,5,1),minor=True); ax.set_yticks(np.arange(-.5,5,1),minor=True)
ax.grid(which="minor",color="white",linewidth=1.2); ax.tick_params(which="minor",length=0)
cb=fig.colorbar(im,ax=ax,fraction=0.046,pad=0.04); cb.set_label("Row-normalized share",fontsize=9); cb.outline.set_visible(False)
save(fig,"fig4_confusion_matrix.jpg")
print("\nwritten: fig3_feature_importance.jpg, fig4_confusion_matrix.jpg")

"""Publication-quality figures for the Current Developments in Nutrition manuscript.

CDN (Elsevier/ASN) permits color and requires >=300 DPI; figure titles live in the
legend, not the image. Output: high-resolution color JPEGs (300 DPI, ~7 in wide).
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np

OUT = "manuscript/figures"
DPI = 300

# ---- cohesive palette ---------------------------------------------------------
ACCENT  = "#1A6FB0"   # primary (highlighted / full model / leakage-free)
ACCENT2 = "#9ECAE1"   # secondary series (light blue)
WARM    = "#E07B39"   # emphasis accent (the result that matters)
NEUTRAL = "#B9C2CC"   # muted bars (de-emphasized)
INK     = "#222831"   # text / edges
GRID    = "#E4E8EC"

plt.rcParams.update({
    "font.size": 11,
    "font.family": "DejaVu Sans",
    "axes.edgecolor": INK,
    "axes.linewidth": 0.8,
    "axes.titlesize": 12,
    "axes.labelcolor": INK,
    "text.color": INK,
    "xtick.color": INK,
    "ytick.color": INK,
    "figure.dpi": DPI,
    "savefig.dpi": DPI,
})

def despine(ax, left=True, bottom=True):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    if not left:
        ax.spines["left"].set_visible(False)
    if not bottom:
        ax.spines["bottom"].set_visible(False)

def save(fig, name):
    fig.savefig(f"{OUT}/{name}", format="jpg", dpi=DPI,
                bbox_inches="tight", pad_inches=0.06, facecolor="white")
    plt.close(fig)

# ============================================================ Figure 1: provenance
prov = ["Manufacturer-declared", "Estimated from ingredients",
        "Imputed from category", "Absent"]
cnt  = [14998, 1213640, 121831, 3178880]
pct  = [0.3, 26.8, 2.7, 70.2]
colors = [WARM, NEUTRAL, NEUTRAL, NEUTRAL]

fig, ax = plt.subplots(figsize=(7.0, 4.0))
y = np.arange(len(prov))[::-1]
ax.barh(y, cnt, color=colors, edgecolor=INK, linewidth=0.6, height=0.66, zorder=3)
ax.set_xscale("log")
ax.set_yticks(y)
ax.set_yticklabels(prov)
ax.set_xlabel("Number of products (log scale)")
ax.set_xlim(1e3, 2e7)
ax.xaxis.grid(True, color=GRID, linewidth=0.8, zorder=0)
ax.set_axisbelow(True)
for yi, c, p in zip(y, cnt, pct):
    lab = f"{c:,} ({p}%)"
    if yi == y[0]:
        lab += "  — leakage-free"
    ax.text(c * 1.3, yi, lab, va="center", ha="left", fontsize=9.5,
            color=(WARM if yi == y[0] else INK))
despine(ax, left=False)
ax.tick_params(left=False)
save(fig, "fig1_provenance.jpg")

# ===================================================== Figure 2: grade recovery
methods = ["Zero\nsubstitution", "Ingredient-\nkeyword rule",
           "Category-mean\nimputation", "Nutrients\nonly (ML)",
           "Full model\n(text + nutrients\n+ category)"]
acc = [0.00, 0.13, 0.61, 0.64, 0.76]
qwk = [0.51, 0.58, 0.78, 0.84, 0.88]
x = np.arange(len(methods))
w = 0.40
acc_colors = [WARM if m.startswith("Full") else ACCENT for m in methods]

fig, ax = plt.subplots(figsize=(7.4, 4.4))
ax.yaxis.grid(True, color=GRID, linewidth=0.8, zorder=0)
ax.set_axisbelow(True)
b1 = ax.bar(x - w / 2, acc, w, label="Exact-match accuracy",
            color=acc_colors, edgecolor=INK, linewidth=0.6, zorder=3)
b2 = ax.bar(x + w / 2, qwk, w, label="Quadratic weighted kappa",
            color=ACCENT2, edgecolor=INK, linewidth=0.6, zorder=3)
ax.set_xticks(x)
ax.set_xticklabels(methods, fontsize=8.8)
ax.set_ylabel("Score in the FVL-sensitive subgroup")
ax.set_ylim(0, 1.0)
for b in list(b1) + list(b2):
    h = b.get_height()
    ax.text(b.get_x() + b.get_width() / 2, h + 0.015, f"{h:.2f}",
            ha="center", fontsize=8.5, color=INK)
ax.legend(loc="upper left", frameon=False, fontsize=9.5)
despine(ax)
save(fig, "fig2_grade_recovery.jpg")

# ================================================ Figure 5: transportability
settings = ["Random product split", "France → non-French\n(geographic transport)"]
full_model = [0.76, 0.59]
baseline   = [0.61, 0.52]
x = np.arange(len(settings))
w = 0.34

fig, ax = plt.subplots(figsize=(6.4, 4.4))
ax.yaxis.grid(True, color=GRID, linewidth=0.8, zorder=0)
ax.set_axisbelow(True)
b1 = ax.bar(x - w / 2, full_model, w, label="Full ML model",
            color=WARM, edgecolor=INK, linewidth=0.6, zorder=3)
b2 = ax.bar(x + w / 2, baseline, w, label="Strongest deterministic baseline",
            color=NEUTRAL, edgecolor=INK, linewidth=0.6, zorder=3)
ax.set_xticks(x)
ax.set_xticklabels(settings, fontsize=9.5)
ax.set_ylabel("Accuracy in the FVL-sensitive subgroup")
ax.set_ylim(0, 1.0)
for b in list(b1) + list(b2):
    h = b.get_height()
    ax.text(b.get_x() + b.get_width() / 2, h + 0.015, f"{h:.2f}",
            ha="center", fontsize=9, color=INK)
# annotate the preserved margin
for xi, fm_, bl in zip(x, full_model, baseline):
    ax.annotate("", xy=(xi - w / 2, fm_), xytext=(xi - w / 2, bl),
                arrowprops=dict(arrowstyle="<->", color=INK, lw=0.8))
    ax.text(xi - w / 2 - 0.06, (fm_ + bl) / 2, f"+{fm_ - bl:.2f}",
            ha="right", va="center", fontsize=8.5, color=INK)
ax.legend(loc="upper right", frameon=False, fontsize=9.5)
despine(ax)
save(fig, "fig5_transportability.jpg")

print("figures written:", "fig1_provenance.jpg, fig2_grade_recovery.jpg, fig5_transportability.jpg")

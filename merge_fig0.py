"""Merge Fig0a (CTM12 map, panels A-B) and a new panel C (collector + taxa) into one Fig. 0."""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
FIG = r"c:\Users\roberto.navarro\Documents\paula\04_figuras"
plt.rcParams["font.family"] = "DejaVu Sans"

# ---- Panel C strip (same width ratio as the map: 12.5 in) ----
fig = plt.figure(figsize=(12.5, 2.4), dpi=300, facecolor="white")
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

ax.text(0.015, 0.93, "C", fontsize=16, fontweight="bold",
        bbox=dict(boxstyle="square,pad=0.25", fc="white", ec="black", lw=1.2), va="center")
ax.text(0.05, 0.93, "Experimental collector and focal taxa", fontsize=11, fontweight="bold", va="center")

ax.add_patch(FancyBboxPatch((0.015, 0.06), 0.43, 0.74, boxstyle="round,pad=0.01", fc="#ebf5fb", ec="#2980b9", lw=1.3))
ax.text(0.23, 0.70, "Artificial sampling collector", fontsize=10, fontweight="bold", color="#1b4f72", ha="center")
ax.text(0.23, 0.38,
        "\u2022 Volume: 4.0 dm\u00b3 (20 \u00d7 20 \u00d7 10 cm) plastic mesh basket\n"
        "\u2022 Substrate: dead coral rubble (Acropora cervicornis)\n"
        "\u2022 Depth: 1.0\u20131.5 m, shallow subtidal\n"
        "\u2022 Monthly retrieval/replacement (T = 12)\n"
        "\u2022 Total crabs measured: N = 2,446",
        fontsize=8.8, color="#2c3e50", ha="center", va="center", linespacing=1.5)

ax.add_patch(FancyBboxPatch((0.47, 0.06), 0.515, 0.74, boxstyle="round,pad=0.01", fc="#fef9e7", ec="#f39c12", lw=1.3))
ax.text(0.7275, 0.70, "Focal porcellanid morphotypes", fontsize=10, fontweight="bold", color="#7d6608", ha="center")
morphs = [
    ("P. galathinus 'Spots'", "#1565C0", "n = 471 (19.3%)  |  L\u221e = 10.62 mm"),
    ("P. galathinus 'Stripes'", "#2E7D32", "n = 581 (23.8%)  |  L\u221e = 12.32 mm"),
    ("P. galathinus 'White Teeth'", "#6A1B9A", "n = 726 (29.7%)  |  L\u221e = 10.69 mm"),
    ("P. coeruleus sp. nov.", "#00838F", "n = 668 (27.3%)  |  L\u221e = 11.63 mm"),
]
for i, (n, c, info) in enumerate(morphs):
    bx = 0.49 + (i % 2) * 0.250
    by = 0.33 - (i // 2) * 0.21
    ax.add_patch(FancyBboxPatch((bx, by), 0.235, 0.17, boxstyle="round,pad=0.006", fc=c, ec="none", alpha=0.15))
    ax.text(bx + 0.008, by + 0.115, n, fontsize=8.3, fontweight="bold", color=c)
    ax.text(bx + 0.008, by + 0.04, info, fontsize=7.6, color="#34495e")
strip = os.path.join(FIG, "_fig0_panelC.png")
fig.savefig(strip, dpi=300)
plt.close(fig)

# ---- Stack: map on top, panel C below ----
top = Image.open(os.path.join(FIG, "Fig0a_Colombia_CTM12_Map.png")).convert("RGB")
bot = Image.open(strip).convert("RGB")
bot = bot.resize((top.width, int(bot.height * top.width / bot.width)), Image.LANCZOS)
out = Image.new("RGB", (top.width, top.height + bot.height), "white")
out.paste(top, (0, 0)); out.paste(bot, (0, top.height))
out.save(os.path.join(FIG, "Fig0_Study_Area_Map.png"), dpi=(300, 300))
os.remove(strip)
print("Saved merged Fig0_Study_Area_Map.png", out.size)

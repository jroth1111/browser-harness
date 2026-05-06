#!/usr/bin/env python3
"""Generate a value chart for the Substack post: Memory vs Cost for AU buyers."""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

fig, ax = plt.subplots(figsize=(15, 9))
fig.patch.set_facecolor('#FFFFFF')
ax.set_facecolor('#FFFFFF')

# ── Data ──
systems = [
    ("RX 7900 XTX DIY",       24,  2514, 136, "gpu"),
    ("RTX 3090 DIY (used)",    24,  2615,  87, "gpu"),
    ("RTX 5090 DIY",           32,  4005, 117, "gpu"),
    ("HP Omen RTX 5090",       32,  4699, 117, "gpu_prebuilt"),
    ("Mac Studio M4 Max",      36,  3149, 122, "mac"),
    ("Bosgame M5 (direct)",    128, 3887,  46, "strix"),
    ("Bosgame M5 (AliExpress)",128, 4034,  46, "strix_alt"),
    ("DGX Spark (import)",     128, 6200,  32, "dgx"),
]

# ── Tier shading — more visible ──
ax.axvspan(0,  18, alpha=0.05, color='#FCA5A5', zorder=0)
ax.axvspan(18, 42, alpha=0.05, color='#FDE68A', zorder=0)
ax.axvspan(42, 150, alpha=0.06, color='#BBF7D0', zorder=0)

# Tier dividers
ax.axvline(x=18, color='#E5E7EB', linestyle=':', linewidth=0.8, zorder=1)
ax.axvline(x=42, color='#E5E7EB', linestyle=':', linewidth=0.8, zorder=1)

ax.text(9,  6200, "8B models",    ha='center', fontsize=10, color='#B0B0B0',
        style='italic', fontweight='bold')
ax.text(30, 6200, "36B models",   ha='center', fontsize=10, color='#B0B0B0',
        style='italic', fontweight='bold')
ax.text(90, 6200, "200B+ models", ha='center', fontsize=10, color='#B0B0B0',
        style='italic', fontweight='bold')

# ── Colors ──
colors = {
    "gpu":          "#2563EB",
    "gpu_prebuilt": "#60A5FA",
    "mac":          "#4B5563",
    "strix":        "#DC2626",
    "strix_alt":    "#F97316",
    "dgx":          "#7C3AED",
}

# ── Label positions — spread to avoid any overlap ──
label_positions = {
    "RX 7900 XTX DIY":        (50,  2050),
    "RTX 3090 DIY (used)":     (50,  2950),
    "Mac Studio M4 Max":       (64,  3700),
    "RTX 5090 DIY":            (64,  4700),
    "HP Omen RTX 5090":        (64,  5500),
    "Bosgame M5 (direct)":     (105, 2200),
    "Bosgame M5 (AliExpress)": (118, 4500),
    "DGX Spark (import)":      (118, 5800),
}

for name, mem, cost, toks, cat in systems:
    color = colors[cat]
    size = 180 + (toks / 136) * 380

    ax.scatter(mem, cost, s=size, c=color, alpha=0.9, edgecolors='white',
              linewidth=2.5, zorder=5)

    ax.text(mem, cost, f"{toks}", ha='center', va='center',
            fontsize=9, color='white', fontweight='bold', zorder=7)

    lx, ly = label_positions[name]
    is_strix = 'strix' in cat
    is_primary_strix = cat == 'strix'

    label_color = '#991B1B' if is_primary_strix else ('#C2410C' if is_strix else '#374151')

    bbox_props = None
    if is_primary_strix:
        bbox_props = dict(boxstyle='round,pad=0.4', facecolor='#FEF2F2',
                          edgecolor='#DC2626', alpha=0.95, linewidth=1.5)

    ax.annotate(
        f"{name}\n{mem}GB · AU${cost:,}",
        (mem, cost),
        xytext=(lx, ly),
        ha='center', va='center',
        fontsize=9,
        fontweight='bold' if is_strix else 'normal',
        color=label_color,
        arrowprops=dict(arrowstyle='->', color='#B0B0B0', lw=1,
                        connectionstyle='arc3,rad=0.12'),
        zorder=6,
        bbox=bbox_props,
    )

# ── Winner callout — bold box ──
ax.annotate(
    "BEST VALUE FOR 200B+ MODELS\nAU$30/GB — nothing else under AU$6K gives you 128GB",
    xy=(128, 3887),
    xytext=(78, 1300),
    fontsize=10, fontweight='bold', color='#991B1B',
    ha='center',
    arrowprops=dict(arrowstyle='-|>', color='#DC2626', lw=2.5,
                    connectionstyle='arc3,rad=-0.2',
                    mutation_scale=15),
    zorder=8,
    bbox=dict(boxstyle='round,pad=0.6', facecolor='#FEF2F2',
              edgecolor='#DC2626', linewidth=2, alpha=0.95),
)

# ── Value line ──
x_line = np.array([0, 140])
y_line = x_line * (3887 / 128)
ax.plot(x_line, y_line, '--', color='#DC2626', alpha=0.2, lw=1.5, zorder=1)

# ── Axes ──
ax.set_xlabel("Memory (GB)", fontsize=13, fontweight='bold', labelpad=12,
              color='#1F2937')
ax.set_ylabel("Total System Cost (AU$)", fontsize=13, fontweight='bold',
              labelpad=12, color='#1F2937')
ax.set_title(
    "What Can You Actually Run?\nMemory vs Cost — Local LLM Hardware in Australia",
    fontsize=18, fontweight='bold', pad=22, color='#111827',
)

ax.set_xlim(0, 140)
ax.set_ylim(500, 6600)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x:,.0f}'))
ax.tick_params(colors='#6B7280', labelsize=10)

ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.spines['left'].set_color('#D1D5DB')
ax.spines['bottom'].set_color('#D1D5DB')
ax.grid(axis='y', alpha=0.1, linewidth=0.5, color='#9CA3AF')
ax.grid(axis='x', alpha=0.05, linewidth=0.5, color='#9CA3AF')

# ── Legend ──
legend_items = [
    mpatches.Patch(color=colors['gpu'],          label='Discrete GPU (DIY)'),
    mpatches.Patch(color=colors['gpu_prebuilt'], label='Prebuilt PC'),
    mpatches.Patch(color=colors['mac'],          label='Apple Silicon'),
    mpatches.Patch(color=colors['strix'],        label='Strix Halo 395 ★ best value 128GB'),
    mpatches.Patch(color=colors['dgx'],          label='NVIDIA DGX Spark'),
]
leg = ax.legend(handles=legend_items, loc='upper left', fontsize=9,
                framealpha=0.95, edgecolor='#D1D5DB', fancybox=True)
leg.get_frame().set_linewidth(1)

# ── Footnote ──
fig.text(0.1, 0.005,
         "Numbers in bubbles = tokens/second.  66 hardware configs, 457 benchmarks from localmaxxing.com.  All prices AUD, verified May 2026.",
         fontsize=8, color='#9CA3AF')

plt.tight_layout(rect=[0, 0.025, 1, 1])
out = "agent-workspace/domain-skills/localmaxxing/value-chart.png"
plt.savefig(out, dpi=200, bbox_inches='tight', facecolor='white')
print(f"Saved to {out}")

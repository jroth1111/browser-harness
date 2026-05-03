#!/usr/bin/env python3
"""
Localmaxxing hardware scorer.

Fetches benchmark data from the Localmaxxing API (or loads from local cache),
groups results by hardware, computes multi-dimensional scores, and ranks
hardware for local LLM inference.

Usage:
    python hardware-scorer.py                    # Full rankings
    python hardware-scorer.py --class DISCRETE_GPU  # GPU only
    python hardware-scorer.py --profile efficiency    # Efficiency-focused
    python hardware-scorer.py --json                # Machine-readable output
    python hardware-scorer.py --refresh             # Re-fetch from API

Scoring profiles:
    balanced     - Equal weight across all dimensions (default)
    speed        - Maximize throughput and responsiveness
    efficiency   - Maximize tok/s per GB of memory
    capability   - Maximize model size the hardware can run
    value        - Factor in approximate street price per tok/s
"""

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

DATA_FILE = Path(__file__).parent / "leaderboard-data.json"
API_BASE = "https://www.localmaxxing.com/api"

# Approximate street prices (USD) for cost-efficiency scoring.
# Only populated for common hardware; missing entries get no cost score.
STREET_PRICES = {
    "GTX 1060 6GB": 120, "GTX 1080 Ti": 200, "GTX 1650": 100,
    "NVIDIA GeForce RTX 3060": 250, "NVIDIA GeForce RTX 3070 Ti": 350,
    "NVIDIA GeForce RTX 3090": 600, "RTX 3060": 250, "RTX 3060 Ti": 280,
    "RTX 3070": 330, "RTX 3070 Ti": 350, "RTX 3080": 450, "RTX 3080 Ti": 500,
    "RTX 3090": 600, "RTX 3090 Ti": 700,
    "RTX 4060": 300, "RTX 4060 Ti": 400, "RTX 4060 Ti 16GB": 450,
    "RTX 4070": 550, "RTX 4070 Ti": 600, "RTX 4070 Ti Super": 600,
    "RTX 4080": 900, "RTX 4080 Super": 1000,
    "RTX 4090": 2000, "RTX 5070 Ti": 750, "RTX 5080": 1000, "RTX 5090": 2000,
    "NVIDIA H100 80GB": 25000, "NVIDIA H200 NVL": 30000,
    "A100 80GB": 12000, "A6000": 4500,
    "L40S": 7500, "RTX A4000": 900, "RTX A6000": 4500,
    "AMD Radeon RX 6800": 350, "AMD Radeon RX 7900 XTX": 800,
    "AMD Radeon RX 9070": 500, "AMD Radeon RX 9070 XT": 600,
    "Intel Arc Pro B70": 300, "Intel Arc Pro B70 32GB": 500,
    "M2 Pro": 1300, "M3 Ultra": 4000, "M4 Max": 3500,
    "M5 Max": 4000, "M5 Pro": 2000, "Pro": 3500,
    "395": 900, "Max+ 395": 1700,
    "DGX Spark": 4000, "DGX Spark GB10": 4000, "GB10": 4000,
}

PROFILES = {
    "balanced": {
        "throughput": 0.25, "responsiveness": 0.15, "memory_capacity": 0.20,
        "efficiency": 0.20, "capability": 0.10, "value": 0.10,
    },
    "speed": {
        "throughput": 0.45, "responsiveness": 0.25, "memory_capacity": 0.10,
        "efficiency": 0.10, "capability": 0.05, "value": 0.05,
    },
    "efficiency": {
        "throughput": 0.15, "responsiveness": 0.10, "memory_capacity": 0.10,
        "efficiency": 0.45, "capability": 0.10, "value": 0.10,
    },
    "capability": {
        "throughput": 0.10, "responsiveness": 0.05, "memory_capacity": 0.35,
        "efficiency": 0.10, "capability": 0.35, "value": 0.05,
    },
    "value": {
        "throughput": 0.20, "responsiveness": 0.10, "memory_capacity": 0.10,
        "efficiency": 0.15, "capability": 0.05, "value": 0.40,
    },
}


def fetch_leaderboard():
    """Fetch all leaderboard entries from the API via pagination."""
    import urllib.request

    all_rows = []
    offset = 0
    limit = 200

    while True:
        url = f"{API_BASE}/leaderboard?limit={limit}&offset={offset}"
        req = urllib.request.Request(url, headers={"User-Agent": "localmaxxing-scorer/1.0"})
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode()

        data = json.loads(raw)
        all_rows.extend(data["rows"])
        offset += limit
        if offset >= data["total"]:
            break

    with open(DATA_FILE, "w") as f:
        json.dump(all_rows, f)

    return all_rows


def load_data():
    if not DATA_FILE.exists():
        return fetch_leaderboard()
    with open(DATA_FILE) as f:
        return json.load(f)


def hardware_key(row):
    """Derive a unique key for the hardware in a benchmark row."""
    hw = row.get("hardware", {})
    cls = hw.get("hwClass", "UNKNOWN")
    if cls == "DISCRETE_GPU":
        name = hw.get("gpuName", "unknown")
        count = hw.get("gpuCount", 1)
        return f"GPU:{name}x{count}"
    elif cls == "UNIFIED":
        vendor = hw.get("chipVendor", "")
        variant = hw.get("chipVariant", "")
        mem = hw.get("unifiedMemoryGb", 0)
        return f"UNIFIED:{vendor} {variant} ({mem}GB)"
    elif cls == "CPU_ONLY":
        cpu = hw.get("cpu", "unknown")
        ram = hw.get("ramGb", 0)
        return f"CPU:{cpu} ({ram}GB)"
    return "UNKNOWN"


def normalize(values, higher_is_better=True):
    """Min-max normalize a list of values to 0-100."""
    if not values:
        return []
    min_v = min(values)
    max_v = max(values)
    rng = max_v - min_v
    if rng == 0:
        return [50.0] * len(values)
    if higher_is_better:
        return [(v - min_v) / rng * 100 for v in values]
    else:
        return [(max_v - v) / rng * 100 for v in values]


def score_hardware(rows, profile="balanced"):
    """Group benchmarks by hardware and compute composite scores."""
    groups = defaultdict(list)
    for r in rows:
        groups[hardware_key(r)].append(r)

    hw_stats = {}
    for key, benchmarks in groups.items():
        toks = [b["tokSOut"] for b in benchmarks if b.get("tokSOut")]
        ttfts = [b["ttftMs"] for b in benchmarks if b.get("ttftMs") is not None]
        params = [b["model"]["params"] for b in benchmarks if b.get("model", {}).get("params")]
        peaks = [b["peakVramGb"] for b in benchmarks if b.get("peakVramGb")]

        hw = benchmarks[0].get("hardware", {})
        mem_gb = (
            hw.get("vramGb", 0) or hw.get("unifiedMemoryGb", 0) or hw.get("ramGb", 0) or 0
        )
        gpu_count = hw.get("gpuCount", 1)
        display_name = key.split(":", 1)[1] if ":" in key else key
        hw_class = hw.get("hwClass", "UNKNOWN")
        price = STREET_PRICES.get(hw.get("gpuName"), STREET_PRICES.get(hw.get("chipVariant")))

        median_tok = statistics.median(toks) if toks else 0
        median_ttft = statistics.median(ttfts) if ttfts else float("inf")
        max_params = max(params) if params else 0
        median_peak = statistics.median(peaks) if peaks else 0

        eff_per_gb = median_tok / mem_gb if mem_gb > 0 else 0
        eff_per_price = median_tok / price if price and price > 0 else None

        hw_stats[key] = {
            "display_name": display_name,
            "hw_class": hw_class,
            "gpu_count": gpu_count,
            "mem_gb": mem_gb,
            "price": price,
            "bench_count": len(benchmarks),
            "median_tok_s": round(median_tok, 2),
            "median_ttft_ms": round(median_ttft, 1) if median_ttft != float("inf") else None,
            "max_model_params_B": max_params,
            "median_peak_vram_gb": round(median_peak, 1) if median_peak else None,
            "eff_per_gb": round(eff_per_gb, 2),
            "eff_per_price": round(eff_per_price, 2) if eff_per_price else None,
        }

    # Normalize each dimension across all hardware.
    # For TTFT, only include hardware that has TTFT data; missing gets 0.
    keys = list(hw_stats.keys())
    tok_vals = [hw_stats[k]["median_tok_s"] for k in keys]
    mem_vals = [hw_stats[k]["mem_gb"] for k in keys]
    eff_vals = [hw_stats[k]["eff_per_gb"] for k in keys]
    cap_vals = [hw_stats[k]["max_model_params_B"] for k in keys]
    price_vals = [hw_stats[k]["eff_per_price"] or 0 for k in keys]

    ttft_present = [(i, hw_stats[k]["median_ttft_ms"]) for i, k in enumerate(keys)
                    if hw_stats[k]["median_ttft_ms"] is not None]

    tok_norm = normalize(tok_vals, higher_is_better=True)
    ttft_norm_raw = normalize([t for _, t in ttft_present], higher_is_better=False) if ttft_present else []
    ttft_norm = [0.0] * len(keys)
    for j, (idx, _) in enumerate(ttft_present):
        ttft_norm[idx] = ttft_norm_raw[j]
    mem_norm = normalize(mem_vals, higher_is_better=True)
    eff_norm = normalize(eff_vals, higher_is_better=True)
    cap_norm = normalize(cap_vals, higher_is_better=True)
    val_norm = normalize(price_vals, higher_is_better=True)

    # Confidence penalty: hardware with <3 benchmarks gets a multiplier <1.
    def confidence(n):
        if n >= 5: return 1.0
        if n >= 3: return 0.85
        if n >= 2: return 0.7
        return 0.5

    weights = PROFILES[profile]

    for i, k in enumerate(keys):
        scores = {
            "throughput": tok_norm[i],
            "responsiveness": ttft_norm[i],
            "memory_capacity": mem_norm[i],
            "efficiency": eff_norm[i],
            "capability": cap_norm[i],
            "value": val_norm[i],
        }
        conf = confidence(hw_stats[k]["bench_count"])
        composite = sum(scores[dim] * weights[dim] for dim in weights) * conf
        hw_stats[k]["dimension_scores"] = {d: round(s, 1) for d, s in scores.items()}
        hw_stats[k]["confidence"] = conf
        hw_stats[k]["composite_score"] = round(composite, 1)

    ranked = sorted(hw_stats.values(), key=lambda x: x["composite_score"], reverse=True)
    return ranked


def format_table(ranked, top_n=30):
    """Format ranked hardware as a readable table."""
    if not ranked:
        return "No data."

    lines = []
    lines.append(f"{'#':<4} {'Score':>6} {'Hardware':<40} {'Class':<15} {'tok/s':>8} {'TTFTms':>8} {'MemGB':>6} {'$/tok':>8} {'Runs':>5}")
    lines.append("-" * 105)

    for i, hw in enumerate(ranked[:top_n]):
        name = hw["display_name"][:38]
        cls = hw["hw_class"][:13]
        tok = f"{hw['median_tok_s']:.1f}"
        ttft = f"{hw['median_ttft_ms']:.0f}" if hw["median_ttft_ms"] else "-"
        mem = f"{hw['mem_gb']:.0f}"
        eff_price = f"{hw['eff_per_price']:.1f}" if hw["eff_per_price"] else "-"
        runs = str(hw["bench_count"])
        score = f"{hw['composite_score']:.1f}"

        lines.append(f"{i+1:<4} {score:>6} {name:<40} {cls:<15} {tok:>8} {ttft:>8} {mem:>6} {eff_price:>8} {runs:>5}")

    return "\n".join(lines)


def format_details(hw):
    """Format a single hardware entry with full dimension breakdown."""
    lines = [
        f"== {hw['display_name']} ==",
        f"  Class: {hw['hw_class']}  |  Memory: {hw['mem_gb']}GB  |  Price: ${hw['price'] or '?'}",
        f"  Median throughput: {hw['median_tok_s']} tok/s",
        f"  Median TTFT: {hw['median_ttft_ms']} ms" if hw['median_ttft_ms'] else "  Median TTFT: N/A",
        f"  Max model: {hw['max_model_params_B']}B params",
        f"  Efficiency: {hw['eff_per_gb']} tok/s/GB",
        f"  Benchmarks: {hw['bench_count']}",
        f"  Composite: {hw['composite_score']}",
        "  Dimensions:",
    ]
    for dim, val in hw.get("dimension_scores", {}).items():
        bar = "#" * int(val / 5)
        lines.append(f"    {dim:<20} {val:>6.1f}  {bar}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Localmaxxing hardware scorer")
    parser.add_argument("--class", dest="hw_class", choices=["DISCRETE_GPU", "UNIFIED", "CPU_ONLY"])
    parser.add_argument("--profile", choices=list(PROFILES), default="balanced")
    parser.add_argument("--top", type=int, default=30, help="Number of results to show")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--refresh", action="store_true", help="Re-fetch data from API")
    parser.add_argument("--details", type=int, default=None, help="Show details for rank N")
    args = parser.parse_args()

    rows = fetch_leaderboard() if args.refresh else load_data()

    if args.hw_class:
        rows = [r for r in rows if r.get("hardware", {}).get("hwClass") == args.hw_class]

    ranked = score_hardware(rows, profile=args.profile)

    if args.json:
        print(json.dumps(ranked, indent=2))
        return

    if args.details is not None:
        idx = args.details - 1
        if 0 <= idx < len(ranked):
            print(format_details(ranked[idx]))
        else:
            print(f"Rank {args.details} out of range (1-{len(ranked)})")
        return

    print(f"Localmaxxing Hardware Rankings (profile: {args.profile}, {len(ranked)} hardware configs)")
    print()
    print(format_table(ranked, top_n=args.top))

    if ranked:
        print()
        print("Top recommendation:")
        print(format_details(ranked[0]))


if __name__ == "__main__":
    main()

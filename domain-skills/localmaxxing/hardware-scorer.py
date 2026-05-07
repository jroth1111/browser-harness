#!/usr/bin/env python3
"""
Localmaxxing hardware scorer.

Fetches benchmark data from the Localmaxxing API (or loads from local cache),
groups results by hardware, computes multi-dimensional scores, and ranks
hardware for local LLM inference.

Usage:
    python hardware-scorer.py                          # Full rankings
    python hardware-scorer.py --class DISCRETE_GPU     # GPU only
    python hardware-scorer.py --profile efficiency     # Efficiency-focused
    python hardware-scorer.py --model qwen3 --size 30  # Best hardware for Qwen3-30B
    python hardware-scorer.py --model llama --budget 600  # Cheapest way to run Llama
    python hardware-scorer.py --models                 # List all model families + sizes
    python hardware-scorer.py --json                   # Machine-readable output
    python hardware-scorer.py --refresh                # Re-fetch from API

Scoring profiles:
    balanced     - Equal weight across all dimensions (default)
    speed        - Maximize throughput and responsiveness
    efficiency   - Maximize tok/s per GB of memory
    capability   - Maximize model size the hardware can run
    value        - Factor in approximate street price per tok/s

Model-fit mode (--model):
    Filters benchmarks to a specific model, then ranks hardware by actual
    throughput on that workload. Answers: "what's the cheapest hardware
    that can run model X at usable speed?"
"""

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

DATA_FILE = Path(__file__).parent / "leaderboard-data.json"
API_BASE = "https://www.localmaxxing.com/api"

# Street prices (USD) — Chrome CDP verified 2026-05-04.
# Prices reflect cheapest legitimate working card on eBay BIN (scams/parts excluded).
# See hardware-prices.md for full research with scam analysis.
STREET_PRICES = {
    # Budget/older NVIDIA (parts-only cards excluded)
    "GTX 1060 6GB": 63, "GTX 1080 Ti": 130, "GTX 1650": 70,
    "NVIDIA GeForce RTX 3060": 175, "RTX 3060": 175, "RTX 3060 Ti": 200,
    "NVIDIA GeForce RTX 3070 Ti": 235, "RTX 3070": 250, "RTX 3070 Ti": 235,
    "RTX 2080 Ti": 257,
    # Mid-range NVIDIA (box-only/parts excluded)
    "RTX 3080": 450, "RTX 3080 Ti": 385,
    "RTX 4060 Ti 16GB": 445, "RTX 4060 Ti": 445,
    "RTX 4070": 460, "NVIDIA GeForce RTX 4070": 460,
    "RTX 4070 Ti Super": 549, "RTX 4070 SUPER": 549,
    "NVIDIA GeForce RTX 4060 Ti 16GB": 445,
    # High-end NVIDIA (0% feedback scams excluded)
    "RTX 3090": 1050, "NVIDIA GeForce RTX 3090": 1050,
    "RTX 3090 Ti": 1331, "NVIDIA GeForce RTX 3090 Ti": 1331,
    "RTX 4090": 2449, "NVIDIA GeForce RTX 4090": 2449,
    "RTX 5090": 2500, "NVIDIA GeForce RTX 5090": 2500,
    "RTX 5080": 1199, "NVIDIA GeForce RTX 5080": 1199,
    "RTX 5070 Ti": 895, "RTX 5060 Ti": 475,
    # AMD
    "AMD Radeon RX 6800": 320, "RX 6800": 320,
    "AMD Radeon RX 7900 XTX": 825, "RX 7900 XTX": 825,
    "AMD Radeon RX 9070 XT": 675, "RX 9070 XT": 675,
    "AMD Radeon RX 9070": 590,
    # Intel
    "Intel Arc Pro B70": 1151, "Intel Arc Pro B70 32GB": 1151,
    # Tesla/professional
    "Tesla P100-PCIE-16GB": 200,
    "NVIDIA H200 SXM": 20000, "NVIDIA H200 NVL": 20000,
    "RTX PRO 6000": 8686, "RTX A6000": 3899,
    "NVIDIA GeForce RTX 4070 SUPER": 549,
    # Apple unified memory
    "Apple M2 Pro": 848, "Apple M3 Ultra": 7700,
    "Apple M4 Max": 3269, "Apple M5 Max": 4979, "Apple M5 Pro": 3937,
    "Apple Max": 4979, "Apple Pro": 3937,
    # AMD unified memory
    "AMD Ryzen AI MAX 395 Radeon 8060S": 1699,
    "AMD 395": 1699, "AMD Ryzen AI Max 395": 1699,
    "AMD Ryzen AI Max+ 395": 1699, "AMD Max+ 395": 1699,
    "AMD Minisforum UM790 Pro": 600,
    "AMD Radeon 8060S Graphics (Strix Halo APU)": 1699,
    # NVIDIA dev/edge
    "NVIDIA DGX Spark": 3999, "NVIDIA DGX Spark GB10": 3999,
    "NVIDIA GB10": 3999, "NVIDIA Orin Nano Super Developer Kit": 249,
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


def dict_value(value):
    return value if isinstance(value, dict) else {}


def row_dicts(rows):
    return [row for row in (rows or []) if isinstance(row, dict)]


def numeric_value(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def numeric_values(values):
    return [v for v in (numeric_value(value) for value in values) if v is not None]


def hardware_key(row):
    """Derive a unique key for the hardware in a benchmark row."""
    hw = dict_value(row.get("hardware"))
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
    rows = row_dicts(rows)
    groups = defaultdict(list)
    for r in rows:
        groups[hardware_key(r)].append(r)

    hw_stats = {}
    for key, benchmarks in groups.items():
        toks = numeric_values(b.get("tokSOut") for b in benchmarks)
        ttfts = numeric_values(b.get("ttftMs") for b in benchmarks)
        params = numeric_values(dict_value(b.get("model")).get("params") for b in benchmarks)
        peaks = numeric_values(b.get("peakVramGb") for b in benchmarks)

        hw = dict_value(benchmarks[0].get("hardware"))
        mem_gb = (
            numeric_value(hw.get("vramGb"))
            or numeric_value(hw.get("unifiedMemoryGb"))
            or numeric_value(hw.get("ramGb"))
            or 0
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
    for dim, val in dict_value(hw.get("dimension_scores")).items():
        bar = "#" * int(val / 5)
        lines.append(f"    {dim:<20} {val:>6.1f}  {bar}")
    return "\n".join(lines)


def list_models(rows):
    """List all model families and parameter sizes in the data."""
    families = defaultdict(set)
    for r in row_dicts(rows):
        m = dict_value(r.get("model"))
        fam = m.get("family", "")
        params = m.get("params")
        hf_id = m.get("hfId", "")
        if fam:
            label = f"{params}B" if params else "?"
            families[fam].add((label, hf_id))

    lines = [f"{'Family':<20} {'Sizes':<30} Example HF ID"]
    lines.append("-" * 80)
    for fam in sorted(families):
        sizes = sorted({s for s, _ in families[fam]})
        examples = sorted({h for _, h in families[fam]})[:2]
        lines.append(f"{fam:<20} {', '.join(sizes):<30} {examples[0]}")
    return "\n".join(lines)


def score_model_fit(rows, model_query, size_filter=None, quant_filter=None, budget=None):
    """Rank hardware for a specific model workload.

    Filters benchmarks to those matching model_query (case-insensitive substring
    match on family and hfId), optionally filters by param size and quantization,
    then groups by hardware and ranks by actual tok/s on that model.
    """
    model_query_lower = model_query.lower()

    matched = []
    for r in row_dicts(rows):
        m = dict_value(r.get("model"))
        family = str(m.get("family") or "").lower()
        hf_id = str(m.get("hfId") or "").lower()
        if model_query_lower not in family and model_query_lower not in hf_id:
            continue
        if size_filter is not None:
            params = m.get("params")
            if params != size_filter:
                continue
        if quant_filter is not None:
            q = str(dict_value(r.get("engine")).get("quantization") or "").lower()
            if quant_filter.lower() not in q:
                continue
        matched.append(r)

    if not matched:
        return [], []

    # Group by hardware
    groups = defaultdict(list)
    for r in matched:
        groups[hardware_key(r)].append(r)

    hw_results = []
    for key, benchmarks in groups.items():
        hw = dict_value(benchmarks[0].get("hardware"))
        price = STREET_PRICES.get(hw.get("gpuName"), STREET_PRICES.get(hw.get("chipVariant")))
        if budget is not None and price is not None and price > budget:
            continue

        toks = numeric_values(b.get("tokSOut") for b in benchmarks)
        ttfts = numeric_values(b.get("ttftMs") for b in benchmarks)
        quants = set(dict_value(b.get("engine")).get("quantization") for b in benchmarks if dict_value(b.get("engine")).get("quantization"))
        mem_gb = (
            numeric_value(hw.get("vramGb"))
            or numeric_value(hw.get("unifiedMemoryGb"))
            or numeric_value(hw.get("ramGb"))
            or 0
        )

        median_tok = statistics.median(toks) if toks else 0
        median_ttft = statistics.median(ttfts) if ttfts else None
        best_tok = max(toks) if toks else 0

        display_name = key.split(":", 1)[1] if ":" in key else key

        hw_results.append({
            "display_name": display_name,
            "hw_class": hw.get("hwClass", "UNKNOWN"),
            "mem_gb": mem_gb,
            "price": price,
            "bench_count": len(benchmarks),
            "median_tok_s": round(median_tok, 2),
            "best_tok_s": round(best_tok, 2),
            "median_ttft_ms": round(median_ttft, 1) if median_ttft else None,
            "quantizations": sorted(quants),
            "tok_per_dollar": round(median_tok / price, 2) if price and price > 0 else None,
        })

    ranked = sorted(hw_results, key=lambda x: x["median_tok_s"], reverse=True)
    return ranked, matched


def format_model_table(ranked, model_query, top_n=20):
    """Format model-fit results."""
    lines = [
        f"Hardware rankings for model: {model_query}",
        f"{'#':<4} {'Hardware':<40} {'Class':<15} {'tok/s':>8} {'Best':>8} {'TTFTms':>8} {'MemGB':>6} {'Price':>7} {'Quants':<20} {'Runs':>5}",
        "-" * 130,
    ]

    for i, hw in enumerate(ranked[:top_n]):
        name = hw["display_name"][:38]
        cls = hw["hw_class"][:13]
        tok = f"{hw['median_tok_s']:.1f}"
        best = f"{hw['best_tok_s']:.1f}"
        ttft = f"{hw['median_ttft_ms']:.0f}" if hw["median_ttft_ms"] else "-"
        mem = f"{hw['mem_gb']:.0f}"
        price = f"${hw['price']}" if hw["price"] else "?"
        quants = ", ".join(hw["quantizations"][:3])
        runs = str(hw["bench_count"])
        lines.append(f"{i+1:<4} {name:<40} {cls:<15} {tok:>8} {best:>8} {ttft:>8} {mem:>6} {price:>7} {quants:<20} {runs:>5}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Localmaxxing hardware scorer")
    parser.add_argument("--class", dest="hw_class", choices=["DISCRETE_GPU", "UNIFIED", "CPU_ONLY"])
    parser.add_argument("--profile", choices=list(PROFILES), default="balanced")
    parser.add_argument("--top", type=int, default=30, help="Number of results to show")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--refresh", action="store_true", help="Re-fetch data from API")
    parser.add_argument("--details", type=int, default=None, help="Show details for rank N")
    parser.add_argument("--model", type=str, default=None, help="Model family name (e.g. qwen3, llama, gemma)")
    parser.add_argument("--size", type=int, default=None, help="Model parameter size in billions (e.g. 8, 14, 70)")
    parser.add_argument("--quant", type=str, default=None, help="Quantization filter (e.g. Q4_K_M, BF16)")
    parser.add_argument("--budget", type=int, default=None, help="Max hardware price in USD")
    parser.add_argument("--models", action="store_true", help="List all model families and sizes in data")
    args = parser.parse_args()

    rows = fetch_leaderboard() if args.refresh else load_data()

    if args.hw_class:
        rows = [r for r in rows if dict_value(r.get("hardware")).get("hwClass") == args.hw_class]

    if args.models:
        print(list_models(rows))
        return

    if args.model:
        ranked, matched = score_model_fit(rows, args.model, args.size, args.quant, args.budget)
        if not matched:
            print(f"No benchmarks found for model '{args.model}'"
                  f"{f' size={args.size}B' if args.size else ''}"
                  f"{f' quant={args.quant}' if args.quant else ''}")
            print("Use --models to see available model families.")
            return
        if args.json:
            print(json.dumps(ranked, indent=2))
            return
        print(format_model_table(ranked, args.model, top_n=args.top))
        if ranked:
            best = ranked[0]
            print()
            print(f"Cheapest option: ", end="")
            with_price = [h for h in ranked if h["price"] is not None]
            if with_price:
                cheapest = min(with_price, key=lambda h: h["price"])
                print(f"{cheapest['display_name']} at ${cheapest['price']} ({cheapest['median_tok_s']} tok/s)")
            else:
                print("no price data available")
            print(f"Best value:      ", end="")
            if with_price:
                best_val = max(with_price, key=lambda h: h["tok_per_dollar"] or 0)
                print(f"{best_val['display_name']} at ${best_val['price']} ({best_val['tok_per_dollar']} tok/s/$)")
            else:
                print("no price data available")
        return

    ranked = score_hardware(rows, profile=args.profile)

    if args.budget:
        ranked = [r for r in ranked if r["price"] is None or r["price"] <= args.budget]

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

# Localmaxxing — Hardware Ranking for Local LLM Inference

Data source: [localmaxxing.com](https://www.localmaxxing.com) — community-submitted local LLM benchmarks
covering tok/s, TTFT, VRAM, and hardware efficiency across GPUs, Apple Silicon, and CPU setups.

## Quick Start

```bash
# Full rankings (balanced profile, top 30)
python3 agent-workspace/domain-skills/localmaxxing/hardware-scorer.py

# GPUs only, optimized for value
python3 agent-workspace/domain-skills/localmaxxing/hardware-scorer.py --class DISCRETE_GPU --profile value

# Apple Silicon / unified memory
python3 agent-workspace/domain-skills/localmaxxing/hardware-scorer.py --class UNIFIED

# Machine-readable JSON output
python3 agent-workspace/domain-skills/localmaxxing/hardware-scorer.py --json

# Re-fetch latest data from API
python3 agent-workspace/domain-skills/localmaxxing/hardware-scorer.py --refresh

# Full breakdown for a specific rank
python3 agent-workspace/domain-skills/localmaxxing/hardware-scorer.py --details 1
```

## Scoring Model

Hardware is scored across six dimensions, min-max normalized to 0-100:

| Dimension | Metric | Description |
|-----------|--------|-------------|
| throughput | median tok/s | Output tokens per second (median across all benchmark runs for that hardware) |
| responsiveness | median TTFT | Time to first token in ms (lower = better; missing data scores 0) |
| memory_capacity | total GB | VRAM (discrete GPU) or unified memory (Apple Silicon) or RAM (CPU-only) |
| efficiency | tok/s per GB | Throughput divided by total memory — measures memory utilization |
| capability | max params | Largest model (in billions of parameters) the hardware has successfully run |
| value | tok/s per dollar | Throughput divided by approximate street price |

### Scoring Profiles

Profiles weight the six dimensions differently:

- **balanced** (default): equal consideration across all factors
- **speed**: throughput 45%, responsiveness 25% — for latency-sensitive workloads
- **efficiency**: efficiency 45% — maximize output per GB of memory
- **capability**: memory 35%, capability 35% — for running the largest possible models
- **value**: value 40% — best bang for the buck

### Confidence Factor

Hardware with fewer benchmark runs gets a composite score penalty:
- 5+ runs: 1.0x (full confidence)
- 3-4 runs: 0.85x
- 2 runs: 0.7x
- 1 run: 0.5x

This prevents single-run outliers from dominating the rankings.

## Data Source

The API at `localmaxxing.com/api` provides public GET endpoints:

- `GET /api/leaderboard` — ranked results (max 200/page, paginated)
- `GET /api/benchmarks` — raw benchmark data with filters
- `GET /api/models` — model catalog

Local cache: `leaderboard-data.json` (457 entries as of 2026-05-04).
Use `--refresh` to re-fetch.

## Hardware Classes

- **DISCRETE_GPU** — NVIDIA, AMD, Intel discrete cards (222 benchmarks)
- **UNIFIED** — Apple Silicon, AMD APUs, NVIDIA Grace (234 benchmarks)
- **CPU_ONLY** — CPU-only inference (1 benchmark)

## Interpreting Results

The scorer groups all benchmarks by hardware config (GPU name + count, or
chip variant + memory). For each group it computes median performance across
all model sizes, quantizations, and engines. This means:

- A 3090 running Qwen3-8B at Q4 and another running Llama-3-70B at Q2
  both contribute to the RTX 3090's aggregate score
- Hardware with more diverse benchmarks gets a more representative median
- Use `--details N` to see the full dimension breakdown for any rank
- Use `--class` to compare within a single hardware class only

## Street Prices

Prices in `hardware-scorer.py` are researched USD street prices for used/refurbished
units where applicable. Prices were verified 2026-05-04 via eBay BIN listings and
BestValueGPU tracker. See `hardware-prices.md` for full price research with scam analysis.

To update prices, follow the methodology in `hardware-catalog.md`. Key points:
- Use Chrome CDP to navigate directly to eBay/AliExpress listing pages (not web search)
- BestValueGPU.com provides authoritative new + used price baselines
- AliExpress is unreliable for 30-series NVIDIA and all Apple products (100% scam density)
- eBay PayMore stores and eBay Refurbished program are the most reliable used sources
- Update `STREET_PRICES` dict in `hardware-scorer.py` after research

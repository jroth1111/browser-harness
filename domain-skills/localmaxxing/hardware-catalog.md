# Localmaxxing Hardware Catalog

66 unique hardware configs across 457 community benchmarks. Data from [localmaxxing.com](https://localmaxxing.com), fetched 2026-05-04.

## Price Research Methodology

See `hardware-prices.md` for full researched prices (2026-05-04).

### How to update prices

1. **Baseline check**: Navigate to [BestValueGPU](https://bestvaluegpu.com) via Chrome CDP for the product - gives new Amazon price + used eBay average
2. **eBay verification**: Use Chrome CDP to navigate to `ebay.com/sch/i.html?_nkw=[product]` and take a snapshot of actual listings. Filter for Buy It Now, exclude "for parts"
3. **AliExpress check**: Navigate to `aliexpress.com/w/wholesale-[product].html` and take snapshot - note scam risk level below
4. **Verify specific deals**: Use `mcp__chrome-devtools__take_screenshot` on individual listings to verify product photos match the claimed model
5. **Update STREET_PRICES**: After research, update the `STREET_PRICES` dict in `hardware-scorer.py` with best verified used price

### Search tool priority

1. `mcp__chrome-devtools__navigate_page` + `take_snapshot` - PRIMARY. Navigate directly to eBay/AliExpress listing pages and read actual prices from the page content
2. `mcp__chrome-devtools__take_screenshot` - Verify specific listings visually
3. `mcp__web-search-prime__web_search_prime` - Secondary for quick price lookups
4. `WebSearch` - Last resort (frequent 400 API errors as of 2026-05)

### Scam detection by platform

**AliExpress scam indicators:**
- Title mixes multiple GPU models (e.g., "RTX 3060TI 3070 ti 3080 ti") = keyword-stuffed bait
- "Hot sale", "2025 hot sale" language = bait
- Price below 60% of used market value = confirmed fraud
- 30-series NVIDIA (3090, 3090 Ti, 3080 Ti): 100% scam density on AliExpress
- 50-series NVIDIA: moderate risk, slightly harder to fake but still unverified sellers
- Apple products: no legitimate system listings exist on AliExpress (only accessories)
- Orin Nano Super: one of the few products legitimately available on AliExpress

**eBay scam indicators:**
- Price way below market + seller in China = phished account (confirmed for RTX PRO 6000, DGX Spark, H200)
- 0% feedback + classified ad format = no buyer protection
- "Shop on eBay" placeholder listings = not real listings
- Enterprise GPUs (H200, RTX PRO 6000 Blackwell) at consumer prices = scam
- DGX Spark under $3,000 = confirmed scam (Reddit r/LocalLLaMA)

**Reliable eBay seller patterns:**
- PayMore stores: chain electronics resellers, consistent pricing, tested inventory, return policies
- itsworthmore (149.5K feedback, 99.5%): major refurbisher, eBay Refurbished program
- goroostr (10.5K feedback, 100%): good for Apple/Mac products
- tekdeals (76.7K feedback, 99.9%): good for refurbished laptops

### Key price reference points (2026-05-04)

| Category | Rule of thumb |
|---|---|
| Used GPU floor | eBay BIN from established US sellers |
| New GPU floor | Amazon/retail MSRP + 10-20% for current gen |
| AliExpress GPU | Same as eBay or higher, with more risk |
| Apple systems | AliExpress = 0% legit; eBay Refurbished = best deals |
| Enterprise GPUs | Authorized distributors only; eBay = extreme scam risk |
| Dev boards (Orin) | Both platforms legit at $249 MSRP |

## Discrete GPUs (46 configs)

| Hardware | VRAM (GB) | Benchmarks | Best tok/s | Models tested |
|---|---|---|---|---|
| NVIDIA H200 SXM x4 | 564 | 7 | 878.4 | 7 |
| NVIDIA H200 NVL x2 | 282 | 4 | 338.9 | 4 |
| NVIDIA H200 NVL | 141 | 3 | 2665.1 | 2 |
| NVIDIA RTX PRO 6000 Blackwell x8 | 768 | 2 | 74.5 | 2 |
| NVIDIA RTX PRO 6000 Blackwell | 96 | 6 | 506.2 | 6 |
| NVIDIA RTX A6000 x2 | 96 | 2 | 133.2 | 2 |
| RTX A6000 x2 | 48 | 2 | 165.6 | 1 |
| RTX PRO 6000 x2 | 98 | 1 | 92.8 | 1 |
| RTX 3090 x4 | 96 | 1 | 67.1 | 1 |
| NVIDIA GeForce RTX 3090 x2 | 24 | 9 | 140.1 | 5 |
| NVIDIA GeForce RTX 3090 | 24 | 6 | 150.1 | 4 |
| RTX 3090 x2 | 24 | 28 | 170.5 | 16 |
| RTX 3090 | 24 | 6 | 124.4 | 4 |
| RTX 3090 Ti x2 | 24 | 2 | 131.6 | 2 |
| NVIDIA GeForce RTX 3090 Ti | 24 | 4 | 155.9 | 2 |
| RTX 3090 Ti | 24 | 3 | 140.3 | 3 |
| NVIDIA GeForce RTX 5090 | 32 | 2 | 175.8 | 2 |
| RTX 5090 | 32 | 9 | 215.4 | 6 |
| RTX 4090 | 24 | 11 | 164.1 | 6 |
| NVIDIA GeForce RTX 4090 | 24 | 1 | 165.1 | 1 |
| RTX 5070 Ti | 16 | 1 | 124.0 | 1 |
| NVIDIA GeForce RTX 5080 | 16 | 1 | 150.6 | 1 |
| RTX 5060 Ti x2 | 16 | 2 | 60.9 | 1 |
| 5060 Ti | 16 | 1 | 23.0 | 1 |
| RX 7900 XTX | 24 | 17 | 575.2 | 6 |
| AMD Radeon RX 7900 XTX | 24 | 12 | 104.5 | 10 |
| NVIDIA GeForce RTX 4060 Ti 16GB | 16 | 1 | 60.2 | 1 |
| RTX 4060 Ti 16GB x2 | 16 | 1 | - | 1 |
| AMD Radeon RX 9070 XT | 16 | 9 | 96.6 | 4 |
| AMD Radeon RX 9070 | 16 | 1 | 76.0 | 1 |
| AMD Radeon RX 6800 | 16 | 1 | 89.2 | 1 |
| Intel Arc Pro B70 32GB | 32 | 2 | 45.2 | 1 |
| Intel Arc Pro B70 | 32 | 11 | 70.3 | 3 |
| Tesla P100-PCIE-16GB x2 | 16 | 6 | 144.3 | 6 |
| Tesla P100-PCIE-16GB | 16 | 4 | 136.4 | 4 |
| AMD Radeon 8060S Graphics (Strix Halo APU) | 96 | 1 | 14.8 | 1 |
| NVIDIA GeForce RTX 4070 | 12 | 4 | 62.1 | 1 |
| RTX 4070 SUPER | 12 | 1 | 77.4 | 1 |
| RTX 3080 Ti | 12 | 1 | 15.4 | 1 |
| NVIDIA GeForce RTX 3060 | 12 | 1 | 35.0 | 1 |
| GTX 1080 Ti | 11 | 26 | 94.9 | 10 |
| RTX 2080 Ti | 11 | 3 | 106.0 | 1 |
| Multi-GPU x2 | 48 | 3 | 33.8 | 2 |
| NVIDIA GeForce RTX 3070 Ti | 8 | 1 | 33.5 | 1 |
| GTX 1060 6GB | 6 | 1 | 15.0 | 1 |
| GTX 1650 | 4 | 1 | 30.6 | 1 |

## Unified Memory (19 configs)

| Hardware | Memory (GB) | Benchmarks | Best tok/s | Models tested |
|---|---|---|---|---|
| Apple M3 Ultra | 512 | 9 | 140.8 | 6 |
| Apple Max | 128 | 6 | 117.0 | 6 |
| Apple M5 Max | 128 | 1 | 122.0 | 1 |
| Apple M5 Pro | 64 | 4 | 104.7 | 4 |
| Apple Pro | 64 | 1 | 105.0 | 1 |
| Apple M4 Max | 64 | 3 | 83.4 | 2 |
| NVIDIA DGX Spark | 128 | 18 | 102.0 | 12 |
| NVIDIA DGX Spark | 256 | 1 | 17.7 | 1 |
| NVIDIA DGX Spark GB10 | 128 | 1 | 26.9 | 1 |
| NVIDIA GB10 | 128 | 5 | 90.0 | 1 |
| AMD Ryzen AI MAX 395 Radeon 8060S | 128 | 90 | 107.1 | 18 |
| AMD 395 | 128 | 67 | 82.6 | 18 |
| AMD Ryzen AI Max 395 | 128 | 11 | 56.8 | 6 |
| AMD Ryzen AI Max+ 395 | 128 | 5 | 17.0 | 1 |
| AMD Max+ 395 | 128 | 1 | 12.7 | 1 |
| AMD Minisforum UM790 Pro | 64 | 7 | 24.8 | 6 |
| Apple M4 Max | 48 | 1 | 21.8 | 1 |
| Apple M2 Pro | 16 | 1 | 33.0 | 1 |
| NVIDIA Orin Nano Super Developer Kit | 8 | 2 | 27.9 | 2 |

## CPU Only (1 config)

| Hardware | RAM (GB) | Benchmarks | Best tok/s | Models tested |
|---|---|---|---|---|
| Qualcomm Snapdragon 888 ARM64 | 0 | 1 | 6.2 | 1 |

## Notes

- Some hardware appears under multiple names (e.g., "RTX 3090" vs "NVIDIA GeForce RTX 3090") due to how users entered their hardware config.
- Best tok/s reflects the single fastest benchmark run, which may use aggressive quantization, batching, or speculative decoding.
- The AMD Ryzen AI MAX 395 (Strix Halo) is the most-tested hardware with 157 combined benchmarks across all name variants.

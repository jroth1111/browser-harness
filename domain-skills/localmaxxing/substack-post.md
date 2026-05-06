# I Priced Every Way to Run Local LLMs in Australia. One Clear Winner.

*66 hardware configs. 457 benchmarks. Every listing on AliExpress, eBay, Amazon, and OzBargain checked for scams. Here's what to buy.*

---

## The Setup

You want to run LLMs locally. Private, fast, no API keys, no per-token charges. Maybe you're a developer testing models. Maybe you don't trust OpenAI with your data. Maybe you just think it's cool.

Fair enough. But what hardware do you actually buy?

I pulled 457 community benchmarks from [localmaxxing.com](https://localmaxxing.com), priced every option available to Australian buyers, and checked every listing for scams. I'm going to save you a lot of money.

## The One Thing That Matters

Here's the thing nobody tells you: **memory is the bottleneck, not speed.**

Your RTX 5090 does 117 tokens per second. Impressive. But it has 32GB of VRAM, which means the largest model it can run is about 36 billion parameters. That's Qwen2.5-32B. A good model, sure. But Llama-3-70B? Physically impossible. 70B at Q4 quantisation needs 40GB. Your AU$2,500 GPU simply cannot load it.

This reframes the entire buying decision. The question isn't "what's fastest?" — it's "what can I fit?" And in Australia, where components cost 30-80% more than the US, getting this wrong is expensive.

## What Can You Actually Run?

This is the table that matters. I grouped all 66 hardware configs by the largest model they've successfully run:

| Tier | What fits | Memory needed | Real-world examples |
|---|---|---|---|
| **200B+** | Llama-3-70B (Q4), DeepSeek-R1 distilled, Mixtral 8x22B, Falcon-180B | 128GB+ | The big boys. Near-GPT-4 quality, on your desk. |
| **36B** | Qwen2.5-32B, Command-R, Gemma-2-27B | 24GB | Strong reasoning, great code generation. Most people's sweet spot. |
| **Small** | Llama-3-8B, Mistral-7B, Phi-3 | 8-12GB | Fast, capable, but noticeably below cloud API quality. |

Here's the uncomfortable truth: **there is almost nothing between 36B and 200B.** No affordable hardware sits in that gap. You either settle for 36B models on a consumer GPU, or you jump to 128GB unified memory.

The AMD Strix Halo 395 is the bridge.

## The Best Deal: AMD Strix Halo 395 (Bosgame M5)

The AMD Ryzen AI Max+ 395 — codename "Strix Halo" — puts 128GB of LPDDR5X unified memory on a single chip with an integrated Radeon 8060S GPU. Think of it like Apple Silicon: the CPU and GPU share one pool of memory. No VRAM limit. 128GB is 128GB.

In practice, that means you can load Llama-3-70B at Q4 and get **38-53 tokens per second**. For context, that's about the speed of a fast human typist. You can read along as it generates. It's not the 117 tok/s of an RTX 5090, but the RTX 5090 can't run this model at all.

The cheapest way to get one: the **Bosgame M5**, a mini PC built around this chip. AU$3,887 direct from Bosgame, complete with 2TB SSD, WiFi 7, USB4, and an AU plug. No assembly required.

### Why it beats everything else at this price

| System | Memory | Price (AU) | What it can run |
|---|---|---|---|
| **Bosgame M5 (Strix Halo 395)** | **128GB** | **AU$3,887** | **Up to 229B params** |
| NVIDIA DGX Spark | 128GB | ~AU$6,200+ | Up to 229B, but 60% more expensive and slower |
| RTX 5090 DIY system | 32GB | AU$4,005 | Only up to 36B — same price, 4x less memory |
| HP Omen RTX 5090 prebuilt | 32GB | AU$4,699 | Only up to 36B, no assembly needed |
| Apple Mac Studio M4 Max (36GB) | 36GB | AU$3,149 | Up to 35B tested, works out of the box |

Let that sink in. The RTX 5090 DIY build costs *more* than the Bosgame M5 and fits models 6x smaller.

### The GMKtec alternative

If Bosgame isn't your thing, the [GMKtec EVO-X2](https://www.aliexpress.com/item/1005009584792500.html) uses the same Strix Halo chip for AU$3,034 on AliExpress (no SSD, no plug — you'll need to add those). It's cheaper upfront but the total ends up similar once you add a 2TB NVMe and factor in the hassle.

### The catch

Two words: **software maturity.** AMD's ROCm and Vulkan stacks are years behind NVIDIA's CUDA. Results vary wildly depending on which engine you use — I saw benchmarks ranging from 12 to 53 tok/s on the same hardware. llama.cpp and LM Studio work, but you'll tinker more than you would with an NVIDIA GPU. The community is active and improving fast (90 benchmarks and counting for this chip), but if you want everything to "just work," this isn't it.

### Where to buy

**Best price:** [Bosgame direct](https://www.bosgame.com/products/bosgame-m5-ai-mini-desktop-ryzen-ai-max-395-96gb-128gb-2tb) — AU$3,887 for 128GB + 2TB SSD, AU plug included. Ships from China (~2 weeks).

**With buyer protection:** [Hello Box Mini PC Store on AliExpress](https://www.aliexpress.com/item/1005011965500576.html) — AU$4,034 for the same config. 4.8 store rating, 403 sold, 90-day free returns, AU plug. Select "LPDDR5 128GB 2TB SSD" + "AU" plug on the page.

Avoid the cheaper Nano MINI PC Store listing (AU$3,976) — its 4.2 store rating is a red flag. On AliExpress, reputable stores sit at 4.7+. The AU$147 savings isn't worth the risk on a AU$4,000 purchase.

## The Value King: RX 7900 XTX

Not everyone needs 200B+ models. If Qwen2.5-32B at 136 tok/s sounds good enough — and for most people it is — the RX 7900 XTX is absurd value.

24GB VRAM. 136 tok/s on 36B models. **AU$949 on OzBargain.** That's faster per-token than the AU$2,500 RTX 5090 (117 tok/s) at a third of the price. AMD's RDNA3 architecture is genuinely excellent for inference workloads.

The catch is the same as the Strix Halo: ROCm, not CUDA. If you need CUDA compatibility specifically, swap it for a used RTX 3090 (AU$1,050, 87 tok/s, 24GB). Slower, but mature software.

### Full DIY system cost (AU, May 2026)

| Component | Spec | Price |
|---|---|---|
| Motherboard | X870, WiFi 7, USB4, 2.5GbE | AU$293 |
| CPU | Ryzen 5 7600 | AU$270 |
| RAM | 32GB DDR5 6000 | AU$282 |
| SSD | 2TB NVMe | AU$400 |
| Case | Mid-tower ATX | AU$130 |
| PSU | 850W | AU$130 |
| Cooler | Tower air | AU$60 |
| GPU | **RX 7900 XTX 24GB** | **AU$949** |
| **Total** | | **AU$2,514** |

**Buy the GPU:** [XFX RX 7900 XTX @ Centre Com eBay](https://www.ozbargain.com.au/node/952847) (AU$949 delivered, OzBargain deal)

A note on those component prices: **DDR5 and SSDs have gone insane in 2026.** That AU$282 for 32GB DDR5 was AU$80 in 2024. A 2TB NVMe has tripled. This is genuinely a bad time to build a PC from scratch, which makes prebuilt options like the Bosgame M5 even more compelling.

## The "Just Works" Option: Mac Studio M4 Max

If reading "ROCm" and "Vulkan" makes your eyes glaze over, buy a Mac.

The [Mac Studio M4 Max at digiDirect](https://www.ozbargain.com.au/node/898732) is AU$3,149 with 36GB unified memory. Apple's MLX framework is excellent. Ollama, LM Studio, and llama.cpp all have native Apple Silicon builds. You plug it in, download Ollama, type `ollama run qwen2.5:32b`, and you're running. No driver headaches, no Linux, no tinkering.

36GB fits models up to about 35B parameters. That's enough for Qwen2.5-32B at Q4, which is a genuinely strong model. The M4 Max pushes 122 tok/s — faster than the RTX 5090 on the same model.

The 128GB config exists (Mac Studio M4 Ultra) but costs ~AU$5,000+ and hasn't been widely benchmarked yet. If Apple's track record holds, it'll be the best "just works" option for 70B+ models once the software catches up.

## The Full Picture

Every realistic option, all-in cost, Australian pricing:

| System | Memory | Total AU | Max Model | tok/s | AU$/GB |
|---|---|---|---|---|---|
| **Bosgame M5 (direct)** | **128GB** | **AU$3,887** | **229B** | **38-53** | **AU$30** |
| RX 7900 XTX DIY | 24GB | AU$2,514 | 36B | 136 | AU$105 |
| RTX 3090 DIY (used) | 24GB | AU$2,615 | 36B | 87 | AU$109 |
| **Mac Studio M4 Max** | **36GB** | **AU$3,149** | **35B+** | **122** | **AU$88** |
| Bosgame M5 (AliExpress) | 128GB | AU$4,034 | 229B | 38-53 | AU$32 |
| RTX 5090 DIY | 32GB | AU$4,005 | 36B | 117 | AU$125 |
| HP Omen RTX 5090 (prebuilt) | 32GB | AU$4,699 | 36B | 117 | AU$147 |
| DGX Spark (import) | 128GB | ~AU$6,200 | 229B | 32 | AU$48 |

Three things stand out:

1. **The Bosgame M5 costs AU$30 per GB of memory.** The RTX 5090 costs AU$125. You're paying 4x more per GB for the NVIDIA brand.
2. **No DIY build can touch the Bosgame M5 on memory at this price.** You'd need four RTX 3090s (AU$4,200 in GPUs alone) to get 96GB, and even then multi-GPU inference is a pain.
3. **The Mac Studio is the best "no fuss" option.** Not the most memory, not the cheapest, but zero friction.

## Where to Buy: Platform Price Comparison

Prices vary wildly depending on where you shop. I checked all three major platforms for the key hardware:

### Bosgame M5 (Strix Halo 395, 128GB + 2TB)

| Platform | Store | Price (AU) | Buyer Protection | Notes |
|---|---|---|---|---|
| **Bosgame direct** | Manufacturer | **AU$3,887** | Standard warranty | Cheapest, ships from China ~2 weeks |
| AliExpress | Hello Box Mini PC Store | AU$4,034 | 90-day free returns | 4.8 rating, 403 sold, AU plug |
| AliExpress | Nano MINI PC Store | AU$3,976 | 90-day free returns | 4.2 rating — avoid |
| AliExpress | 7 other stores | AU$3,779-5,635 | Varies | Most don't have AU plug |
| eBay AU | Not available | — | — | No listings at time of writing |
| Amazon AU | Not available | — | — | Not listed |

**Verdict:** Buy direct from Bosgame if you're comfortable waiting. AliExpress (Hello Box) if you want buyer protection. eBay and Amazon don't have this product.

### RX 7900 XTX (24GB GPU)

| Platform | Store | Price (AU) | Notes |
|---|---|---|---|
| **eBay AU** | Centre Com | **AU$949** | OzBargain deal, delivered, 99%+ feedback |
| Amazon AU | Various | AU$1,100-1,300 | Higher but genuine products, fast shipping |
| AliExpress | Various | AU$950-1,100 | Same price range but slower shipping, warranty harder |

**Verdict:** eBay AU via Centre Com is the clear winner — reputable seller, OzBargain-verified price, fast domestic shipping.

### RTX 5090 (32GB GPU)

| Platform | Price (AU) | Notes |
|---|---|---|
| **eBay AU** (used) | AU$4,000-4,500 | Rare, check seller feedback carefully |
| Amazon AU | AU$4,200-4,800 | In stock occasionally, genuine |
| AliExpress | AU$4,500+ | Not recommended for high-value NVIDIA GPUs |

### RTX 3090 (24GB GPU, used)

| Platform | Price (AU) | Notes |
|---|---|---|
| **eBay AU** | **AU$1,050-1,200** | Best source for used 3090s. Check for mining damage. |
| Amazon AU | AU$1,500+ | Rare, usually third-party sellers |
| AliExpress | **Avoid** | 100% scam density for 30-series NVIDIA |

### Mac Studio M4 Max

| Platform | Store | Price (AU) | Notes |
|---|---|---|---|
| **digiDirect** | authorised reseller | **AU$3,149** | OzBargain deal |
| Apple AU | direct | AU$3,599+ | Full RRP |
| eBay AU | various | AU$3,200-3,500 | Check for Apple authorised |
| Amazon AU | various | AU$3,300+ | Usually close to RRP |

**Verdict:** digiDirect via OzBargain is AU$450 under Apple RRP. Jump on it.

### DIY Components (motherboard, RAM, SSD, etc.)

| Component | Best Platform | Price (AU) | Notes |
|---|---|---|---|
| Motherboard (X870 WiFi 7) | Amazon US via AU | AU$293 | Gigabyte X870 Eagle, delivered |
| RAM (32GB DDR5 6000) | OzBargain / Umart | AU$282 | Patriot Viper, prices spiked 3x since 2024 |
| SSD (2TB NVMe) | Amazon AU / Umart | AU$350-450 | Prices doubled since 2024 |
| Case, PSU, Cooler | Umart / PC Case Gear | AU$320 | Stable pricing |

**Verdict:** Shop OzBargain for deals on individual components. Amazon US via AU often beats local pricing on motherboards. RAM and SSDs are expensive everywhere right now.

## Scam Watch

I checked every listing personally. Three things to know:

**AliExpress is a minefield.** 100% of 30-series NVIDIA GPU listings are fake. Every Apple computer listing is fake. I found Bosgame M5 listings where all the reviews were from a completely different product (a GMKtec eGPU). AliExpress reviews are not trustworthy. The platform is fine for mini PCs from reputable stores (4.7+ rating, 100+ sales) — just don't buy GPUs or Apple products there.

**eBay has sophisticated scams.** Enterprise GPUs (H200, RTX PRO 6000, DGX Spark) listed at consumer prices by sellers with 0% feedback are almost certainly phished accounts. The DGX Spark does not cost AU$2,000. The RTX 5090 does not cost AU$500. If a deal seems too good, check the seller's feedback page — phished accounts often have years of inactivity then suddenly list high-value electronics.

**Reliable sellers:** On eBay, look for PayMore stores (chain electronics resellers, 99.5%+ feedback), itsworthmore (149.5K feedback, 99.5%, eBay Refurbished program), and goroostr (Apple specialist). On AliExpress, only buy from stores rated 4.7+ with significant sales volume.

## The Verdict

**AU$2,514 — RX 7900 XTX DIY build** if you're budget-conscious and 36B models are enough. Blazing fast, best value on the market. [Centre Com deal](https://www.ozbargain.com.au/node/952847).

**AU$3,149 — Mac Studio M4 Max** if you don't want to think about drivers, Linux, or ROCm. Plug in, install Ollama, done. [digiDirect deal](https://www.ozbargain.com.au/node/898732).

**AU$3,887 — Bosgame M5 direct** if you want to run 70B+ models locally. Nothing else under AU$6,000 gives you 128GB. You'll tinker with software, but the hardware is unmatched at this price. [Bosgame direct](https://www.bosgame.com/products/bosgame-m5-ai-mini-desktop-ryzen-ai-max-395-96gb-128gb-2tb).

**AU$4,034 — Bosgame M5 AliExpress** if you want buyer protection on the same hardware. [Hello Box Mini PC Store](https://www.aliexpress.com/item/1005011965500576.html).

Everything else is either overpriced for what you get or can't fit the models you want. The data doesn't lie.

---

## Methodology

- **Scoring model:** Each hardware configuration is scored across six dimensions, each normalised to 0–100:
  - *Throughput* (20%) — median tokens per second across all benchmark runs
  - *Responsiveness* (10%) — median time to first token
  - *Memory capacity* (10%) — total GB available (VRAM or unified)
  - *Efficiency* (15%) — tok/s per GB of memory
  - *Capability* (5%) — largest model successfully run (in billions of parameters)
  - *Value* (40%) — tok/s per dollar of street price

  The composite score is the weighted average, multiplied by a confidence factor that penalises hardware with few benchmark submissions (5+ runs: full confidence; 1 run: 50% penalty). This stops single-run outliers from topping the rankings. The "best bang for buck" verdict uses this model with the value dimension weighted at 40%.

- **Benchmarks:** 457 entries from [localmaxxing.com](https://localmaxxing.com) API, fetched 4 May 2026. 66 unique hardware configurations.
- **Pricing:** GPU prices verified via direct browser navigation to eBay BIN listings and AliExpress product pages, cross-referenced with BestValueGPU.com. Australian component prices from OzBargain deals and AU retail.
- **Scam detection:** Every AliExpress listing checked for review authenticity, seller rating, and product photo verification. Every eBay listing checked for seller feedback history and account age.
- **Strix Halo pricing:** Live-checked on Bosgame.com AU store and 10 AliExpress stores on 4 May 2026.

All prices in AUD. Verified within 48 hours of publication. Component prices are particularly volatile in 2026 due to DDR5 and NAND flash supply constraints.

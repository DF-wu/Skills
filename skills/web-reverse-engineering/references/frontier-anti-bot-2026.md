# 2026 Anti-Bot Frontier and Countermeasures (Cloudflare / Anubis / Detection Side)

Three new variables appeared in the 2025-2026 anti-bot landscape: **AI crawler-specific traps**, **paid crawling protocols**, and **proof-of-work gates**. This document covers them along with the current state of the detection side.

## 1. The Cloudflare Trio

### AI Labyrinth (2025-03-19)

**Mechanism**: requests identified as AI crawlers are returned **AI-generated fake pages** containing **hidden decoy links** (invisible to humans, followed by crawlers), drawing the crawler into an infinite loop.

| Item | Value |
|---|---|
| Launch date | 2025-03-19 |
| Available tiers | **opt-in, including the Free plan** |
| Content generation | Workers AI |
| Content storage | R2 |
| Page marking | `noindex` (avoids polluting search indexes) |
| Event names | `AI Labyrinth Served`, `AI Labyrinth Crawls` |

**Countermeasure points**: detect whether a page is `noindex` and whether invisible links exist (`display:none` / zero size / moved out of viewport / same color as background). On a hit, discard the page and mark that source as untrusted.

Source: https://blog.cloudflare.com/ai-labyrinth

### Pay Per Crawl (2025-07-01 private beta → now GA)

**Mechanism**: lets content owners **charge for or refuse** crawling, expressed via HTTP **402 Payment Required**.

| Item | Value |
|---|---|
| Launch | 2025-07-01 private test; on **2025-08-27** AI Audit was renamed AI Crawl Control and reached GA, introducing custom HTTP 402 responses (paid plans) |
| Payer | Stripe (merchant-of-record) |
| Three policies | allow / charge / block |
| Price headers | `crawler-price`, `crawler-exact-price`, `crawler-max-price`, `crawler-charged`, `crawler-error` |
| Protocol rules | `crawler-exact-price` and `crawler-max-price` — **only one is allowed per request**; both present or both absent returns 402 |
| Identity verification | **Web Bot Auth** (HTTP message signatures); from 2026-04-17 payment headers must be included in the `signature-input` signature components |
| Discovery API | `GET https://crawlers-api.ai-audit.cfdata.org/charged_zones` |
| Free paths | `/robots.txt`, `/sitemap.xml`, `/security.txt`, `/.well-known/security.txt`, `/crawlers.json` |
| Routing order | the payment decision runs **after** existing WAF / rate limiting / bot management policies |
| Billing semantics | successful responses carry `crawler-charged` indicating the actual amount billed; **error responses are not billed** |

**Countermeasure points**: on receiving a **402**, do not blindly retry — this is an explicit commercial refusal signal. Check the `crawler-*` headers to determine whether you have already been charged.

**De facto standard family already formed** (no longer a single-vendor behavior):

| Solution | Date | Form |
|---|---|---|
| **Cloudflare Pay Per Crawl** | 2025-07 → GA 2025-08-27 | 402 + `crawler-*` headers; Stripe settlement |
| **x402 Foundation** | 2025-09-23 (jointly launched by Cloudflare + Coinbase) | 402 + machine-readable payment requirement `PAYMENT-REQUIRED`; clients retry with `PAYMENT-SIGNATURE`; network-agnostic (EVM/Solana); a **facilitator** handles verification and settlement |
| **AWS WAF AI Traffic Monetization** | 2026-06 | Bot Control gains a **Monetize** action; unpaid requests receive 402 + a manifest (per-request price in USDC, accepted networks **Base and Solana**, payee address, license terms), **format is exactly x402**; after payment the edge issues a scoped access token |
| **Content Signals** | 2025-09-24 | robots.txt extension, CC0 |
| **RSL (Really Simple Licensing)** | — | an XML licensing standard written in robots.txt, governed by the RSL Collective; **independent of any CDN**, consortium-based |

Cloudflare-side data point: sites on its network **emit more than 1 billion HTTP 402 response codes per day** to bots, crawlers, and agents. Legal status: x402 is currently a **technical open standard**, not yet a regulator-recognized payment system.

Source: https://blog.cloudflare.com/introducing-pay-per-crawl , https://developers.cloudflare.com/ai-crawl-control/changelog , https://developers.cloudflare.com/ai-crawl-control/features/pay-per-crawl/what-is-pay-per-crawl , https://www.cloudflare.com/press/press-releases/2025/cloudflare-and-coinbase-will-launch-x402-foundation , https://aws.amazon.com/about-aws/whats-new/2026/06/aws-waf-ai-traffic-monetization

### Content Signals Policy (2025-09-24)

**Mechanism**: express three usage preferences in machine-readable form inside `robots.txt`:

| Signal | Meaning |
|---|---|
| `search` | allowed for search engine indexing |
| `ai-input` | allowed as AI inference input |
| `ai-train` | allowed for AI training |

| Item | Value |
|---|---|
| License | **CC0** (free to adopt) |
| Legal framework | a **rights reservation** expression under EU DSM Directive Art. 4 |
| Follow-ups | extensions such as `use=reference` appeared |
| Relation to Turnstile | **none** — Turnstile is a challenge mechanism, Content Signals is a preference declaration |

**Important distinction**: Content Signals is **not technical enforcement**, it is a preference declaration; whether it is honored depends on the crawler side. It aligns functionally with the "machine-readable rights reservation" of DSM Art. 4(3).

Source: https://blog.cloudflare.com/content-signals-policy

### Execution Order of Super Bot Fight Mode

**Key fact**: Super Bot Fight Mode runs **after custom WAF rules**. Therefore setting a **`Skip` action** for a specific path can bypass the SBFM check. This is a configuration-layer fact, used to understand protection ordering.

## 2. Anubis (proof-of-work gate)

**Project**: https://github.com/techaroHQ/anubis (MIT, a reverse proxy written in Go)

**Mechanism**: Hashcash-style SHA-256 PoW. Difficulty `d` → work `W = 16^d`.

| Item | Value |
|---|---|
| **Default difficulty** | **5** (about 1,048,576 hashes) |
| Browser JS rate | about 0.5 MH/s |
| Native Go rate | about 50 MH/s |
| Passing credential | JWT + `*-anubis-auth` cookie, valid for about 2 weeks |
| Paid acceleration | Thoth (paid reputation plugin) |

**Design intent**: make the **cost** of AI crawlers higher than the payoff, rather than blocking access. A human browser only needs a few hundred milliseconds.

**Historical events**:

- **CVE-2025-24369**: a client could pass `difficulty=0` to bypass. Fix commit `e09d0226a628f04b1d80fd83bee777894a45cd02`
- **2025-08-15 Codeberg incident**: AI crawlers solved the PoW, causing DoS-like load
- **2026 pivot**: switching to **memory-hard Argon2id (via WebAssembly)**, reducing the gains from GPU/ASIC acceleration

**Countermeasure paths**:

1. Solve the PoW with native code (Go/Rust) — about 100 times faster than browser JS, so difficulty 5 takes only milliseconds
2. Reuse the `*-anubis-auth` cookie (about 2 weeks validity)
3. If the target is a Thoth-protected site, PoW cost is determined by reputation, and pure compute advantage drops

Source: https://github.com/techaroHQ/anubis , https://anubis.techaro.lol/docs/design/how-anubis-works/ , https://anubis.techaro.lol/blog/2026/anubis-wasm/ , https://nvd.nist.gov/vuln/detail/CVE-2025-24369 , https://theregister.com/2025/08/15/codeberg_beset_by_ai_bots/ , https://lock.cmpxchg8b.com/anubis.html

## 3. Current State of the Detection Side

### Detection Tools

| Tool | Source | Checkpoints |
|---|---|---|
| **CreepJS** | https://github.com/abrahamjuliot/creepjs | comprehensive fingerprinting and consistency |
| FingerprintJS | https://github.com/fingerprintjs/fingerprintjs | commercial fingerprinting |
| BotD | https://github.com/fingerprintjs/BotD | automation signals |
| **brotector** | https://github.com/ttlns/brotector | `navigator.webdriver`, **CDP `Runtime.enable` / `Console.enable`**, `window.cdc_*`, `isTrusted === false`, `__pwInitScripts`, stack signatures; `?crash=false` disables it |
| rebrowser-bot-detector | https://github.com/rebrowser/rebrowser-bot-detector | CDP leak detection |
| Are You Headless | https://arh.antoinevastel.com/bots/areyouheadless | basic headless detection |
| **fpscanner** | https://github.com/antoinevastel/fpscanner | fingerprint consistency scanning |
| **bot.incolumitas.com** | https://bot.incolumitas.com | `behavioralClassificationScore` (0 = bot, 1 = human), updated at 1.5/4/7/10/15 seconds |
| BrowserScan / PixelScan | https://browserscan.net / https://pixelscan.net | comprehensive consistency |
| detect-headless | https://github.com/infosimples/detect-headless | classic headless signal set |

### Strongest Signal: CDP `Runtime.enable`

**The currently strongest automation detection signal is the side effect of CDP `Runtime.enable`** — when Playwright/Puppeteer calls it, it changes console serialization behavior, which can be detected.

**Historical evolution**:

- The classic technique was `Error.stack` characteristics, **now defeated by a V8 patch** (research by DataDome and Castle)
- `Page.createIsolatedWorld` can mitigate CDP detection

Reference: https://rebrowser.net/blog/how-to-fix-runtime-enable-cdp-detection... , https://datadome.co/threat-research/how-new-headless-chrome-the-cdp-signal-are-impacting-bot-detection , https://blog.castle.io/why-a-classic-cdp-bot-detection-signal-suddenly-stopped-working-and-nobody-noticed

### Other Common Signals

| Signal | Description |
|---|---|
| `window.chrome` missing | a Chromium-family characteristic object |
| `navigator.plugins` empty | real browsers have plugins |
| Permissions API inconsistency | `Notification.permission` contradicts the result of `navigator.permissions.query` |
| WebGL renderer is SwiftShader / Mesa | software rendering = no GPU = suspected server |
| `outerHeight` / `outerWidth` === 0 | no window |
| `document.hasFocus()` === false | no focus |
| `navigator.languages` missing | real browsers always have it |
| timezone does not match IP | cross-validation |

## 4. Anti-Detection Browser Ladder

**Ordered by effectiveness** (community consensus):

| Tier | Solution | License | Description |
|---|---|---|---|
| 1 (strongest) | **Camoufox** | MPL-2.0 | Firefox fork, modifies fingerprints at the **C++ layer**, invisible to the JS layer |
| 2 | **Patchright** | Apache-2.0 | Chromium only, a **direct drop-in replacement for Playwright** |
| 2 | **nodriver** | AGPL-3.0 | direct Chrome DevTools Protocol connection, no WebDriver |
| 3 | rebrowser-patches | MIT | patches CDP leaks in Playwright/Puppeteer |
| 4 (weakest) | JS-injection stealth plugins | varies | patch at the JS layer, easily defeated by native detection |

**Other options**: SeleniumBase UC/CDP mode, botasaurus (+driver), pydoll, DrissionPage, zendriver, Scrapling.

**Dead solution**: **undetected-chromedriver is effectively unmaintained** (PyPI 3.5.5, last release 2024-02-17). Do not use it in new projects.

| Project | Repository |
|---|---|
| Camoufox | https://github.com/daijro/camoufox |
| Patchright | https://github.com/Kaliiiiiiiiii-Vinyzu/patchright |
| nodriver | https://github.com/ultrafunkamsterdam/nodriver |
| rebrowser-patches | https://github.com/rebrowser/rebrowser-patches |
| SeleniumBase | https://github.com/seleniumbase/SeleniumBase |
| botasaurus | https://github.com/omkarcloud/botasaurus |
| pydoll | https://github.com/autoscrape-labs/pydoll |
| DrissionPage | https://github.com/g1879/DrissionPage |
| zendriver | https://github.com/cdpdriver/zendriver |
| Scrapling | https://github.com/D4Vinci/Scrapling |

## 5. reCAPTCHA v3 Scoring

| Item | Value |
|---|---|
| Score range | 0.0–1.0 |
| Default threshold | 0.5 |
| Free quota | 10,000 assessments/month |
| Beyond that | $8/month up to 100,000 assessments |
| siteverify return fields | `success`, `score`, `action`, `challenge_ts`, `hostname`, `error-codes` |

**Two key points**:

1. **The `action` must be validated** — otherwise an attacker can replay a token from a low-value page against a high-value endpoint (this is explicitly required by the official documentation)
2. **Staging environment scores are unreliable** — the scoring model learns from real traffic, so scores from a test environment have no reference value

Source: https://developers.google.com/recaptcha/docs/v3 , https://cloud.google.com/recaptcha/pricing

## 6. 2026 Landscape Assessment

**Technical trends**:

1. **The barrier shifts from "identification" to "cost"** — Anubis uses PoW to make crawling expensive, while Pay Per Crawl / x402 / AWS WAF Monetize turn crawling into a payment negotiation. Such mechanisms are **not detection that can be "bypassed"**, but an economic game
2. **AI crawler-specific countermeasures** — AI Labyrinth shows defenders starting to distinguish "AI training crawlers" from "traditional crawlers" and feeding them poisoned data
3. **PoW evolves toward memory-hard algorithms** — Argon2id + WASM weakens the compute advantage
4. **Protocol-level preference declarations** — Content Signals turns robots.txt from a "protocol" into an "expression of legal rights reservation", aligning with DSM Art. 4(3)
5. **Identity layer standardization** — Web Bot Auth (RFC 9421 + Ed25519) lets "legitimate agents" prove their identity, thereby treating "unknown agents" as suspicious by default. This is the most important structural change of 2026: **verification shifts from "are you human" to "do you have a signature"**

**Practical recommendations**:

- On encountering 402 → stop retrying and evaluate commercial authorization. **402 already has a de facto standard family (Cloudflare / x402 / AWS WAF Monetize); it is not an isolated case**
- On encountering PoW → solve it with a native implementation, not with browser JS
- On encountering AI Labyrinth characteristics → discard the page and mark it
- On encountering `ai-train`/`ai-input` signals being reserved → reassess at the legal level; this is not merely a technical problem
- On encountering `Signature` / `Signature-Input` / `Signature-Agent` → this is **Web Bot Auth**, an identity declaration rather than a challenge; agents without a signature are classified as suspicious by default

## Sources

- AI Labyrinth: https://blog.cloudflare.com/ai-labyrinth
- Pay Per Crawl: https://blog.cloudflare.com/introducing-pay-per-crawl
- Pay Per Crawl protocol details: https://developers.cloudflare.com/ai-crawl-control/features/pay-per-crawl/what-is-pay-per-crawl
- AI Crawl Control changelog: https://developers.cloudflare.com/ai-crawl-control/changelog
- x402 Foundation (Cloudflare + Coinbase): https://www.cloudflare.com/press/press-releases/2025/cloudflare-and-coinbase-will-launch-x402-foundation
- AWS WAF AI Traffic Monetization: https://aws.amazon.com/about-aws/whats-new/2026/06/aws-waf-ai-traffic-monetization
- Web Bot Auth: https://developers.cloudflare.com/bots/reference/bot-verification/web-bot-auth
- Cloudflare Verified Bots with cryptography: https://blog.cloudflare.com/verified-bots-with-cryptography
- Content Signals Policy: https://blog.cloudflare.com/content-signals-policy
- Anubis: https://github.com/techaroHQ/anubis
- How Anubis works: https://anubis.techaro.lol/docs/design/how-anubis-works/
- Anubis WASM/Argon2id: https://anubis.techaro.lol/blog/2026/anubis-wasm/
- CVE-2025-24369: https://nvd.nist.gov/vuln/detail/CVE-2025-24369
- Codeberg incident: https://theregister.com/2025/08/15/codeberg_beset_by_ai_bots/
- Anubis analysis: https://lock.cmpxchg8b.com/anubis.html
- brotector: https://github.com/ttlns/brotector
- rebrowser-bot-detector: https://github.com/rebrowser/rebrowser-bot-detector
- CDP Runtime.enable detection: https://rebrowser.net/blog/how-to-fix-runtime-enable-cdp-detection...
- DataDome CDP research: https://datadome.co/threat-research/how-new-headless-chrome-the-cdp-signal-are-impacting-bot-detection
- Castle CDP research: https://blog.castle.io/why-a-classic-cdp-bot-detection-signal-suddenly-stopped-working-and-nobody-noticed
- bot.incolumitas.com: https://bot.incolumitas.com
- fpscanner: https://github.com/antoinevastel/fpscanner
- Camoufox: https://github.com/daijro/camoufox
- Patchright: https://github.com/Kaliiiiiiiiii-Vinyzu/patchright
- nodriver: https://github.com/ultrafunkamsterdam/nodriver
- rebrowser-patches: https://github.com/rebrowser/rebrowser-patches
- reCAPTCHA v3: https://developers.google.com/recaptcha/docs/v3
- reCAPTCHA pricing: https://cloud.google.com/recaptcha/pricing

# Emerging Trends (2025 → 2026)

## 1) LLM-Native Extraction Pipelines

Projects like Crawl4AI, Firecrawl, and Browser-Use push toward "LLM-ready output" instead of raw HTML-first workflows.

What changed:
- direct markdown/JSON extraction for RAG and agents
- built-in action models (click/scroll/type/wait) before extraction
- easier orchestration for multi-step collection tasks

Trade-off:
- faster time-to-value
- less control over low-level extraction details unless you keep raw payloads

## 2) Managed Browser Infrastructure

Cloud browser infrastructure is replacing DIY fleets for many teams:
- easier horizontal scaling
- built-in proxy and challenge handling
- better session observability

Trade-off:
- vendor lock-in risk
- higher per-request cost if not tuned

## 3) Anti-Bot Shift: Identity + Intent

Defenders are moving from static signatures to intent-aware scoring:
- user journey plausibility
- session consistency over time
- cross-request anomaly detection

Implication:
- single-request stealth is less important than multi-step identity coherence.

## 4) The Economics Turn (2025–2026, new)

The most significant strategic shift: **defenses are moving from "can we identify you" to "can we make you pay."**

| Mechanism | Vendor | How it works |
|---|---|---|
| **Pay Per Crawl** | Cloudflare (2025-07-01, private beta) | HTTP **402** + `crawler-price` / `crawler-charged` headers; Stripe merchant-of-record; allow/charge/block per zone |
| **AI Labyrinth** | Cloudflare (2025-03-19) | Feeds AI crawlers AI-generated decoy pages with hidden links; `noindex`; events `AI Labyrinth Served` / `Crawls` |
| **Content Signals Policy** | Cloudflare (2025-09-24, CC0) | `robots.txt`-encoded `search` / `ai-input` / `ai-train` preferences; frames EU DSM Art. 4 rights reservation |
| **Proof of Work** | Anubis (MIT, Go) | Hashcash-style SHA-256; default difficulty 5 ≈ 1.05M hashes; JWT cookie ~2 weeks; paid **Thoth** reputation tier |
| **Argon2id PoW** | Anubis (2026) | Memory-hard via WebAssembly, specifically to defeat GPU/ASIC acceleration |

**Implications**:

- A 402 is a **commercial signal, not a technical obstacle**. Stop retrying.
- PoW is beaten by **native code**, not browser JS — ~50 MH/s native vs ~0.5 MH/s in-browser.
- Anubis had a real vulnerability (CVE-2025-24369, client-supplied `difficulty=0`), fixed in commit `e09d0226a628f04b1d80fd83bee777894a45cd02`.
- In 2025-08-15, AI crawlers solved Anubis at Codeberg, causing DoS-like load — proof that PoW shifts cost, it does not eliminate access.
- Content Signals aligns robots.txt with **legal** rights reservation (DSM Art. 4(3)), not just protocol etiquette.

## 5) HTTP Fingerprint Arms Race Continues

Transport-level fingerprints (TLS/HTTP2/3 behavior) remain high-signal. Teams now combine:
- browser-like transport clients for cheap paths
- patched browser runtimes for challenge-heavy paths

**2025–2026 developments**:

- **JA3 is broken for modern Chrome** — Chrome 109/110 introduced TLS extension-order randomization, producing false positives. `salesforce/ja3` was archived 2025-05-01.
- **JA4 replaces it** — order-insensitive by construction, with a human-readable `ja4_a` prefix.
- **JA3N is not a standard** — it is only a curl_cffi ecosystem convention.
- **Licensing split**: JA4 itself is BSD-3-Clause; the rest of JA4+ is FoxIO License 1.1 (non-commercial limits). Matters for commercial tooling.
- **Akamai HTTP/2 fingerprint** (`SETTINGS|WINDOW_UPDATE|PRIORITY|PSEUDO_HEADER_ORDER`) is now a first-class discriminator — pseudo-header order differs between Chrome/Firefox (`m,a,s,p`) and Safari (`m,s,p,a`).

Full reference: `tls-http-fingerprinting.md`.

## 6) CDP Detection Became the Strongest Browser Signal

**The current strongest automation detection signal is the side effect of CDP `Runtime.enable`** — Playwright/Puppeteer calling it mutates console serialization detectably.

- The classic `Error.stack` signal is **mostly defeated by V8 patches** (DataDome and Castle research)
- `Page.createIsolatedWorld` mitigates CDP detection
- Mitigation tooling: `rebrowser-patches`, Patchright

**Practical consequence**: JS-injection stealth plugins (the bottom tier) are increasingly ineffective. The effective ladder is now Camoufox (C++ layer) > Patchright / nodriver > rebrowser-patches > JS injection. And **undetected-chromedriver is effectively dead** (last release 2024-02-17).

## 7) Agentic Web Automation

Agents now orchestrate planning + execution loops:
- discover URLs
- classify pages
- choose extraction strategy
- validate outputs
- recover from failures

This is powerful, but guardrails are mandatory to prevent runaway behavior and legal exposure.

**New guardrail requirement (2026)**: agents must be able to **recognize AI Labyrinth decoy pages** and refuse to follow them, or they will burn budget on adversarial content indefinitely.

## 8) Mobile-First API Exposure

More services expose richer APIs through mobile apps than through web:
- fewer anti-bot layers on mobile endpoints
- simpler authentication flows
- less obfuscation

Implication:
- mobile app RE (mitmproxy + Frida) is increasingly the optimal first approach.

**Countervailing 2025–2026 friction**: Android 14+ moved system CA certs to the Conscrypt APEX, breaking all classic `/system/etc/security/cacerts` tutorials. You now need an APEX-aware module (AlwaysTrustUserCerts). iOS jailbreak availability has narrowed sharply — **A14+ on iOS 17.4+, and A18/A19, have no public full jailbreak**.

## 9) WASM and Binary Logic in Browsers

WebAssembly modules now handle crypto, signing, and protocol logic:
- JS is just the glue; core algorithms are in WASM
- standard JS hooking misses the critical path

**2026 toolchain change**: `wasm-decompile` was **removed from WABT on 2026-06-22** (PR #2769, effective 1.0.42). The practical replacement is `wasm2c` + `-O3` + native decompiler, or `wasm2js` to flatten into JS. Ghidra still has **no native WASM support** — the community plugin `nneonneo/ghidra-wasm-plugin` is the maintained fork (upstream `garrettgu10` has not been pushed in 3 years).

Full reference: `wasm-reverse-engineering.md`.

## 10) The Chinese Risk-Control Ecosystem as a Distinct Field

Chinese defenses differ structurally from Western ones: **signed-parameter-first rather than fingerprint-first**. The near-zero-coverage areas for most practitioners:

- 瑞数 RiverSecurity — dynamic VM + eval, **no universal solution, one script per site**
- JSVMP — obfuscator.io's own docs state no automated deobfuscator exists
- 补环境 (environment simulation) — the highest-leverage technique for the whole ecosystem
- 小程序 (mini-program) reverse engineering — wxapkg / TTPKG / Alipay `.tar`
- Device fingerprint vendors — 易盾 / 数美 / 顶象 / 同盾 Blackbox

**Key structural insight**: passing the challenge layer is **not** passing the risk engine. Short cookies may pass the page but fail the data API, because the fingerprint is validated separately downstream.

New references: `cn-risk-control-ecosystem.md`, `ruishu-river-security.md`, `captcha-vendors-cn.md`, `signature-parameter-re.md`, `environment-simulation-jsvmp.md`, `miniprogram-reverse-engineering.md`.

## 11) Protocol Diversification Beyond HTTP

Real-time features increasingly use:
- WebSocket for live updates
- gRPC-web for internal APIs exposed to browser
- Custom protobuf over WebSocket
- SSE for push notifications

**2025–2026 additions**:
- **gRPC server reflection** means a whole API surface can be enumerated with zero reverse engineering (`grpcurl -plaintext host:port list`)
- **blackboxprotobuf** can both decode and **re-encode** protobuf without a `.proto`, enabling in-proxy request modification
- **TLS keylog is now standardized as RFC 9850** (2026-07), though most tooling still cites the NSS draft
- **`ecapture`** (eBPF uprobe) captures TLS plaintext with **no CA certificate installed** — bypasses the entire cert-trust problem

## 12) Tool Ecosystem Maturation (and Consolidation)

- `curl_cffi` is the standard Python HTTP client for anti-bot; `hrequests`, `rnet` are viable alternatives
- **Camoufox** and **Patchright** replaced vanilla Playwright for serious targets
- **undetected-chromedriver is dead** — do not start new projects on it
- `DrissionPage` dominates Chinese-language anti-bot stacks
- Go (`Rod`, `chromedp`) and Rust (`chromiumoxide`) gain ground for performance-critical deployments

**Archived/dead — do not build on these**:

| Tool | Status |
|---|---|
| `salesforce/ja3` | Archived 2025-05-01 |
| `undetected-chromedriver` | Last release 2024-02-17 |
| `de4js` | Archived |
| `rarecoil/unwebpack-sourcemap` | Archived |
| `crypto-js` | Officially discontinued |
| `ptswarm/reFlutter` | Archived (use `Impact-I/reFlutter`) |
| LSPosed official builds | Stalled 2023-10 (use `JingMatrix/Vector`) |
| `rovo89/Xposed` family | All archived |
| `PortSwigger/protobuf-decoder` | Last update 2021 |

## Practical Recommendations

- keep a dual stack: cheap HTTP path + browser escalation path
- add a mobile interception path for API-heavy services
- **add a layer-2 check**: after a challenge passes, verify the downstream API actually accepts the session
- log every challenge type and outcome
- version parser logic and extraction prompts
- preserve raw evidence for reprocessing and audits
- **pin your client fingerprint version** — a `curl_cffi` upgrade can silently change your TLS profile
- maintain tool-alternatives literacy: know what replaces what before you need it

## Watchlist

- **memory-hard PoW** (Argon2id/WASM) spreading beyond Anubis
- **402-style commercial gating** becoming normalized
- stricter AI crawler governance and content-use controls
- increasing use of browser integrity checks tied to platform trust signals
- broader use of defensive behavioral biometrics
- WASM-based challenge protocols replacing pure JS
- QUIC/HTTP3 fingerprinting as a new detection layer
- Chinese vendors moving more logic into WASM (极验 v4 already partially does)

Treat this field as continuous operations, not a one-time implementation.

## Sources

- AI Labyrinth: https://blog.cloudflare.com/ai-labyrinth
- Pay Per Crawl: https://blog.cloudflare.com/introducing-pay-per-crawl
- Content Signals Policy: https://blog.cloudflare.com/content-signals-policy
- Anubis: https://github.com/techaroHQ/anubis
- Anubis WASM/Argon2id: https://anubis.techaro.lol/blog/2026/anubis-wasm/
- CVE-2025-24369: https://nvd.nist.gov/vuln/detail/CVE-2025-24369
- Codeberg event: https://theregister.com/2025/08/15/codeberg_beset_by_ai_bots/
- JA4 spec: https://github.com/FoxIO-LLC/ja4
- JA3 archived: https://github.com/salesforce/ja3
- CDP detection (DataDome): https://datadome.co/threat-research/how-new-headless-chrome-the-cdp-signal-are-impacting-bot-detection
- CDP detection (Castle): https://blog.castle.io/why-a-classic-cdp-bot-detection-signal-suddenly-stopped-working-and-nobody-noticed
- wasm-decompile removal: https://github.com/WebAssembly/wabt/pull/2769
- Ghidra WASM plugin: https://github.com/nneonneo/ghidra-wasm-plugin
- RFC 9850: https://www.rfc-editor.org/rfc/rfc9850.html
- ecapture: https://github.com/gojue/ecapture
- obfuscator.io JSVMP position: https://obfuscator.io
- sdenv: https://github.com/pysunday/sdenv
- 社区风控集合: https://1997.pro/archives/1713518394359
- Android Conscrypt APEX: https://blog.nviso.eu/2025/06/05/intercepting-traffic-on-android-with-mainline-and-conscrypt/

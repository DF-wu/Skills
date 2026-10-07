# Global Anti-Bot Vendor Landscape

Vendor identification and detection-signature reference. Companion to
[`cn-risk-control-ecosystem.md`](cn-risk-control-ecosystem.md) (Chinese vendors) and
[`frontier-anti-bot-2026.md`](frontier-anti-bot-2026.md) (2025–2026 new mechanisms).

**Why identification comes first**: the single most expensive mistake is applying the
right technique to the wrong vendor. Cloudflare's answer is a browser that passes
Turnstile. Kasada's answer is a proof-of-work solver. DataDome's answer is IP
reputation. Akamai's answer is TLS coherence. These are different problems.

---

## 1. Identify from one response

Three passes, in this order. The first two usually settle it.

### Pass 1 — cookies (`Set-Cookie` on the first response)

| Cookie | Vendor |
|---|---|
| `__cf_bm`, `cf_clearance`, `__cfruid`, `_cfuvid` | Cloudflare |
| `_abck`, `bm_sz`, `ak_bmsc`, `bm_sv`, `AKA_A2` | Akamai |
| `datadome` | DataDome |
| `_px`, `_pxhd`, `_pxvid`, `pxvid`, `_pxde` | HUMAN Security (formerly PerimeterX) |
| `reese84` | Imperva |
| `incap_ses_*`, `visid_incap_*`, `nlbi_*` | Imperva (Incapsula) |
| `aws-waf-token` | AWS WAF Bot Control |
| `__cf_bm` + `cf_chl_*` | Cloudflare Challenge Platform |
| `_imp_apg_r_`, `_imp_apg_s_` | F5 Distributed Cloud (ex-Shape) |
| `vsd_*`, `RT`, `TS*` | Akamai (older / variant deployments) |

### Pass 2 — headers

| Header | Meaning |
|---|---|
| `Server: cloudflare`, `cf-ray` | Cloudflare is in front (does **not** prove Bot Management is on) |
| `cf-mitigated: challenge` | Cloudflare actively challenged this request |
| `x-kpsdk-ct`, `x-kpsdk-cd`, `x-kpsdk-v`, `x-kpsdk-st` | Kasada |
| `x-is-human` | Vercel BotID (Kasada-backed) |
| `crawler-price`, `crawler-charged`, `crawler-exact-price` | Cloudflare Pay Per Crawl |
| `x-datadome`, `x-dd-b` | DataDome |
| `x-iinfo` | Imperva |
| `x-px-*` | HUMAN/PerimeterX |

### Pass 3 — HTML body (script `src` and inline markers)

| Marker | Vendor |
|---|---|
| `/cdn-cgi/challenge-platform/` | Cloudflare Challenge Platform |
| `challenges.cloudflare.com` | Cloudflare Turnstile |
| `sensor.js`, `/akam/`, `_sec/` paths | Akamai |
| `captcha-delivery.com`, `js.datadome.co` | DataDome |
| `px-cdn.net`, `client.px-cloud.net` | HUMAN/PerimeterX |
| `p.js`, `ips.js` (polymorphic) | Kasada |
| `funcaptcha.com`, `arkoselabs.com` | Arkose Labs |
| `https://www.google.com/recaptcha/` | Google reCAPTCHA |
| `js.hcaptcha.com` | hCaptcha |
| `/.within.website/` | Anubis (open source) |

### HTTP status as a vendor tell

| Status | Vendor | Meaning |
|---|---|---|
| **403** with a challenge page | Cloudflare, Imperva | Standard challenge |
| **429** with `x-kpsdk-*` | Kasada | "Run the proof of work" |
| **403** on retry after a 429 | Kasada | Reputation burned — changing technique will not help |
| **202** with an obfuscated `<script>` | 瑞数 RiverSecurity | Chinese vendors use 202/412 |
| **412** | 瑞数, some WAFs | Precondition failed = challenge |
| **402** | Cloudflare Pay Per Crawl | Commercial gate — stop |

Kasada's use of **429 rather than 403** is the detail that trips people up. A 429 with
`x-kpsdk-` headers is an instruction; a bare 403 afterwards means the IP is spent.

---

## 2. Vendor profiles

### Cloudflare

- **Product**: CDN with optional Bot Management, WAF, Turnstile, Challenge Platform
- **Deployment**: the largest by domain count. Independent benchmarking puts it on
  roughly 73% of tested bot-protected domains, ~20% of all websites
- **Mechanism**: TLS/HTTP fingerprint (JA3/JA4), JS challenge, Turnstile (interactive),
  ML scoring, IP reputation. **Crucially, it is configurable**: the same hostname can
  range from no bot product to full ML scoring. Presence of `Server: cloudflare` proves
  the CDN, not the bot product.
- **Tell for the bot product specifically**: `cf-mitigated` header, or a Turnstile script
  tag in the body
- **First move**: `curl_cffi` with a coherent profile. Most Cloudflare blocks at the
  simple tier are a client misconfiguration, not a detection success.
- **Escalation**: patchright/rebrowser/Camoufox + residential egress
- **Do not escalate**: on HTTP 402

Sources: [Cloudflare AI Labyrinth](https://blog.cloudflare.com/ai-labyrinth),
[Pay Per Crawl](https://blog.cloudflare.com/introducing-pay-per-crawl)

### Akamai (Bot Manager / BMP)

- **Tell**: `_abck`, `bm_sz`, `ak_bmsc` cookies; a ~512 KB obfuscated sensor script
- **Mechanism**: `sensor_data` — an encrypted payload encoding 100+ signals: canvas
  hash, WebGL GPU strings, timing measurements, mouse/scroll events, navigator values,
  hardware properties. String-array rotation with runtime decryption; timing traps
  detect debugging; probes for bot-specific APIs (`callPhantom`).
- **Cookie lifecycle**: `_abck` starts invalid (`~-1~`) and turns valid (`~0~`) after
  roughly three sensor posts
- **The practical problem**: the script is updated continuously. Any approach built on
  reverse-engineering a specific version breaks on the next version.
- **Two viable routes**:
  1. **Execute the real script** in a coherent browser — update-proof, expensive
  2. **Reverse the sensor payload format** — cheaper at scale, requires re-doing work
     on updates
- **TLS is the strongest single vector here.** Matching JA3/JA4 to the claimed browser is
  the highest-leverage fix, before touching the sensor.
- **Public RE work exists**: `akamai-vm-reverse` (decompiled v3 VM),
  `akamai-sensordata-decrypt` (Node module for v3 encrypt/decrypt), `akamai-deobfuscator`

Source: [0xdevalias anti-bot notes](https://gist.github.com/0xdevalias/b34feb567bd50b37161293694066dd53),
[Scrapfly: _abck and sensor data](https://scrapfly.io/blog/posts/akamai-bot-manager-understanding-abck-cookies-and-sensor-data)

### DataDome

- **Tell**: `datadome` cookie, `captcha-delivery.com`, `x-datadome` header
- **Mechanism**: **per-site ML models** — reportedly 85,000+ customer-specific models.
  Each protected site is a distinct detection problem; a bypass tuned on one site
  transfers poorly.
- **Scoring model**: scores **every request independently** rather than building trust
  across a session. This makes **IP reputation weigh heavily** — heavier than in
  session-based vendors.
- **Consequence**: for DataDome, proxy quality is the primary lever, not fingerprint.
  A perfect browser on a burnt IP still fails.
- **Pricing**: publishes an Essentials tier (~$3,830/month) — one of the few vendors
  that does

Sources: [Prosopo vendor comparison](https://prosopo.io/compare),
[Scrappey vendor cheatsheet](https://scrappey.com/qa/anti-bot/anti-bot-vendor-detection-cheatsheet)

### HUMAN Security (formerly PerimeterX)

- **Tell**: `_px`, `_pxhd`, `_pxvid`, `pxvid` cookies; `px-cdn.net`,
  `client.px-cloud.net`; `x-px-*` headers
- **Mechanism**: behavioural biometrics and predictive analytics; **reputation is shared
  network-wide across all customer sites**. A single fingerprint signal is evaluated
  against the whole customer base, not per-site.
- **Consequence**: a fingerprint burned on one HUMAN-protected site is burned
  **everywhere HUMAN is deployed**. This is the opposite of DataDome's per-site model,
  and it means the cost of a bad attempt is much higher.
- **Context**: HUMAN formed from the PerimeterX + White Ops merger (2022)

Source: [Scrappey cheatsheet](https://scrappey.com/qa/anti-bot/anti-bot-vendor-detection-cheatsheet)

### Kasada

- **Tell**: `x-kpsdk-ct`, `x-kpsdk-cd`, `x-kpsdk-v`, `x-kpsdk-st` headers; `p.js` /
  `ips.js`; **429** on first contact
- **Mechanism**: proof-of-work inside a heavily obfuscated, **polymorphic** VM. The
  script changes on almost every load, so a hardcoded parser is worthless.
- **Token model** — the part that breaks naive replay:
  - `x-kpsdk-ct` — client token, session-scoped (roughly 30 minutes in public RE writeups)
  - `x-kpsdk-cd` — client data containing the PoW answer, **single-use**
  - `x-kpsdk-h` — a signature binding the two together
  - Replaying captured headers fails because `x-kpsdk-cd` is spent after one use.
- **Difficulty scaling**: PoW difficulty escalates for new or untrusted sessions. A
  warmed residential session faces near-instant puzzles; a cold datacenter IP can face
  multi-second challenges or timeouts. This makes cold-session scaling economically
  painful — the defence is economic, not cryptographic.
- **Headers come back in the response**, not only the request: `x-kpsdk-st` and
  `x-kpsdk-ct` arrive on the `/tl` response and are inputs to `/cd`.
- **Endpoint shape**: `/tl` (token issue), `/cd` (client data), `/mfc` (some sites)
- **Vercel BotID** is Kasada-powered and adds a separate `x-is-human` header requiring
  its own generation path.

Sources: [Browserless Kasada analysis](https://www.browserless.io/blog/kasada-bypass),
[SparkProxy](https://www.sparkproxy.io/blog/how-to-bypass-kasada),
[vercel-llm-api issue #22](https://github.com/ading2210/vercel-llm-api/issues/22)

### Imperva (Incapsula)

- **Tell**: `reese84` cookie, `incap_ses_*`, `visid_incap_*`, `nlbi_*`; `x-iinfo` header
- **Mechanism**: JS challenge + device fingerprint + behavioural scoring. `reese84` is
  the modern challenge token.
- **Observed strength**: independent benchmarking measured Imperva's block rate around
  46.6% (95% CI 40.6–52.6) across 142 domains — high, though the sample is small.
- **Notable asymmetry**: unlike most vendors, Imperva blocked *more* on general web than
  on e-commerce in the benchmark (47.1% vs 13.5%), on a two-domain e-commerce sample too
  small to draw conclusions from.

### F5 (Distributed Cloud, ex-Shape Security)

- **Tell**: `_imp_apg_r_`, `_imp_apg_s_` cookies
- **Context**: F5 acquired Shape Security for ~$1B in 2020. Telemetry-heavy,
  credential-stuffing focused.
- **Observed strength**: moderate in benchmarking

### Arkose Labs

- **Tell**: `funcaptcha.com`, `arkoselabs.com`
- **Mechanism**: interactive challenge ("FunCaptcha") — visual puzzles designed to be
  hard for automation and easy for humans. Enforcement mode escalates challenge
  frequency based on risk.
- **Position**: form-level protection rather than whole-site. Applied at login and
  registration rather than on every request.
- **Approach**: for low volume, a solving service; for high volume, this is one of the
  harder interactive challenges to automate and the economics often favour a different
  route entirely.

### AWS WAF Bot Control

- **Tell**: `aws-waf-token` cookie
- **Mechanism**: managed rule groups, ML-based. The "Targeted" tier is meaningfully
  stronger than the "Common" tier.
- **Note**: pricing is published, unlike most enterprise vendors

### Anubis (open source)

- **Tell**: `/.within.website/` paths; proof-of-work interstitial
- **Origin**: Techaro. Adds a PoW challenge in front of a site with no vendor
  relationship, no telemetry contract, and no per-request billing. Policy file defines
  allow/deny/challenge per route.
- **Default difficulty**: 5
- **CVE-2025-24369** affected the challenge verification path.
- **Observed strength**: 35.7% block rate across 28 domains (95% CI 22.6–49.4) — a wide
  interval on a small sample, so treat the number loosely.
- **Counter**: solve the PoW in native code rather than browser JS (roughly two orders of
  magnitude faster), then reuse the resulting cookie rather than re-solving. See
  [`frontier-anti-bot-2026.md`](frontier-anti-bot-2026.md).

### Others worth knowing

| Vendor | Tell | Note |
|---|---|---|
| Netacea | — | Behavioural, bot-specific ML |
| CHEQ | — | Ad-fraud origin, expanded to bot management |
| Radware | — | WAAP platform with bot module |
| Cequence | — | API-focused bot defence |
| Castle | — | Scores **users**, not requests; login/registration focused |
| reCAPTCHA Enterprise | `google.com/recaptcha` | Widget option for forms |
| hCaptcha Enterprise | `js.hcaptcha.com` | Widget option for forms |
| Vercel BotID | `x-is-human` | Kasada-backed |
| Arcjet | — | Developer-first, free tier, rate limiting focus |
| Prosopo | — | Publishes pricing for all tiers |

---

## 3. Comparison: where the difficulty actually is

| Vendor | Primary detection vector | What actually fixes it | Difficulty |
|---|---|---|---|
| Cloudflare (basic) | TLS/HTTP fingerprint | Coherent client profile | Low |
| Cloudflare (Bot Mgmt) | ML + fingerprint + Turnstile | Browser + residential egress | Medium–High |
| Akamai BMP | TLS + sensor_data | TLS coherence, then real script execution | High |
| DataDome | Per-request IP reputation + per-site ML | Residential/mobile egress | High |
| HUMAN | Shared network-wide reputation | Never burn the fingerprint | High |
| Kasada | PoW + polymorphic VM + tokens | PoW solver + session warming | Very High |
| Imperva | JS challenge + device fingerprint | Browser + `reese84` handling | Medium–High |
| F5 Shape | Telemetry | Browser + egress | Medium–High |
| Arkose | Interactive challenge | Solver service (volume-dependent) | High |
| AWS WAF Bot Control | Managed rules + ML | Coherent client | Medium |
| Anubis | Proof of work | Native PoW solver | Low–Medium |

The tiers are not a ranking of engineering quality. They are a ranking of *what it costs
you* to get through, which depends as much on the deployment as the product.

---

## 4. Public benchmarking data

Independent measurements exist and are worth knowing, with their limits stated.

| Vendor | Block rate (observed) | Domains tested | Notes |
|---|---|---|---|
| Imperva | 46.6% (CI 40.6–52.6) | 142 | Wide interval; small sample |
| Anubis | 35.7% (CI 22.6–49.4) | 28 | Very small sample |
| Akamai | — | 552 | 33.1% on e-commerce, 8.9% on general web (3.7× gap) |
| Cloudflare | — | 2,829 | 30.0% on e-commerce, 6.6% on general web |
| HUMAN | 15.6% | 40 | 2.9-point gap between e-commerce and general web |
| DataDome | — | 92 | Not published in the summary |
| F5 | — | 54 | Not published |
| AWS WAF | — | 69 | Not published |

**How to read this**: block rate is a function of *configuration and target type*, not
just vendor. The e-commerce vs general-web gap (Akamai 3.7×, Cloudflare 4.5×) is larger
than most vendor-to-vendor differences. A vendor "blocking 8.9%" on general web is not
weak; it is configured per-path. Do not conclude from these numbers that one vendor is
easy — conclude that **deployment matters more than brand**.

Source: [AIMultiple bot detection benchmark](https://aimultiple.com/bot-detection-software)

---

## 5. The 2025–2026 shift: agents, not bots

The category was renamed. Forrester moved from "bot management" to **"bot and agent
trust management"** in late 2025, because AI agents now fall between human and unwanted
bot, and a binary block-or-allow decision loses real customers who delegate tasks to an
agent.

Concrete data points:

- DataDome reported malicious automated traffic grew **124%** between July 2025 and June
  2026 — more than nine times the growth rate of human traffic.
- DataDome found **65.3%** of tested websites could not block or challenge a single one
  of 10 bot and AI-agent types thrown at them.
- **80%** of AI agents do not properly identify themselves.
- A spoofed ChatGPT-style User-Agent got through unblocked on **79.7%** of nearly
  700,000 sites tested.
- Cloudflare began blocking AI-based scraping by default in July 2025.
- AI-driven bot attacks reportedly surged 12.5× year over year, with APIs and identity
  systems targeted in 27% of attacks.

**Engineering consequence**: the interesting frontier has moved from "am I a bot?" to
"what is this agent's intent, and is it authorized?" User-Agent-based agent
identification is currently unreliable in both directions — 80% of agents do not
self-identify, and a spoofed agent UA passes almost everywhere. Any system relying on
agent self-declaration is measuring nothing.

Sources: [Prosopo](https://prosopo.io/compare),
[Prophaze](https://www.prophaze.com/bot-mitigation-vendors-usa),
[DataDome State of Bot & Agent Security 2026](https://datadome.co/)

---

## 6. Vendor-agnostic decision path

```text
1. Get one response. Check cookies, then headers, then body. Identify the vendor.
2. Identify the TIER within that vendor (Cloudflare present != Bot Management on).
3. Ask: what is the primary vector for THIS vendor?
     - TLS fingerprint  -> fix the client (curl_cffi, coherent profile)
     - IP reputation    -> fix the egress (residential/mobile), not the fingerprint
     - JS challenge     -> real browser or environment simulation
     - Proof of work    -> native solver, reuse the cookie
     - Interactive CAPTCHA -> solver service, or reconsider volume
4. Fix the primary vector. Do not fix three things at once.
5. Re-measure. If it still fails, the layer you fixed was not the binding constraint.
6. Check for a commercial gate (402 / crawler-*). If present, STOP.
```

The most common error is step 4: changing fingerprint, egress, and behaviour
simultaneously, then having no idea which change mattered.

---

## 7. Relationship to other documents

- Chinese vendors (瑞数/极验/数美/易盾/顶象/同盾): [`cn-risk-control-ecosystem.md`](cn-risk-control-ecosystem.md)
- Per-vendor CAPTCHA parameter breakdown: [`captcha-vendors-cn.md`](captcha-vendors-cn.md)
- 2025–2026 new mechanisms (AI Labyrinth, Pay Per Crawl, Content Signals, PoW):
  [`frontier-anti-bot-2026.md`](frontier-anti-bot-2026.md)
- TLS/HTTP fingerprint mechanics: [`tls-http-fingerprinting.md`](tls-http-fingerprinting.md)
- Client-side implementation: [`http-clients.md`](http-clients.md)
- Avoidance-first strategy: [`anti-bot-bypass.md`](anti-bot-bypass.md),
  [`captcha-bypass.md`](captcha-bypass.md)
- Authorization and scope: [`compliance-and-scope.md`](compliance-and-scope.md)

---

## 中文摘要

**为什么先做识别**：最贵的错误是把正确的技术用在不匹配的厂商上。Cloudflare 的答案是"一个能过 Turnstile 的浏览器"；Kasada 的答案是"工作量证明求解器"；DataDome 的答案是"IP 信誉"；Akamai 的答案是"TLS 一致性"。这是四个不同的问题。

**单次响应识别三步**：① Cookie（`__cf_bm`/`cf_clearance`→Cloudflare，`_abck`/`bm_sz`→Akamai，`datadome`→DataDome，`_px*`→HUMAN/PerimeterX，`reese84`→Imperva，`x-kpsdk-*`→Kasada）；② 响应头（`cf-mitigated` 才证明 Cloudflare 真的开了 Bot Management，仅有 `Server: cloudflare` 不算；`x-kpsdk-ct/cd/v`→Kasada；`crawler-price`→Pay Per Crawl）；③ HTML（`/cdn-cgi/challenge-platform/`、`sensor.js`、`captcha-delivery.com`、`px-cdn.net`、`p.js`/`ips.js`、`funcaptcha.com`、`/.within.website/`）。

**状态码本身是厂商特征**：Cloudflare/Imperva 用 **403**；**Kasada 用 429**（"去跑工作量证明"），重试后变成裸 403 表示 IP 信誉已烧毁；瑞数用 **202/412**；**402** 是商业闸门（停止）。

**各厂商的关键差异**：
- **Cloudflare**：可按站点配置，同一域名可能完全没开 Bot Management。域名覆盖最大（独立基准约 73% 的受保护域名）。
- **Akamai**：`sensor_data` 为加密载荷，编码 100+ 信号（canvas 哈希、WebGL GPU 串、计时、鼠标/滚动、硬件属性），脚本持续更新——**针对具体版本做逆向会在下个版本失效**。`_abck` 需要约 3 次 sensor POST 才转为有效（`~0~`）。**TLS 一致性是最高杠杆的单一修复点。**
- **DataDome**：**逐请求独立评分**而非会话累积信任 → **IP 信誉权重最高**，代理质量是首要杠杆。且按站点训练 ML（据称 85,000+ 模型），一个站点上的方案迁移性差。
- **HUMAN/PerimeterX**：**信誉在整个客户网络内共享**，一个指纹在一个站点烧毁即**全线烧毁**——试错成本最高。
- **Kasada**：多态混淆 VM 内的 PoW。`x-kpsdk-ct` 为会话令牌（约 30 分钟），`x-kpsdk-cd` 含 PoW 答案且**一次性使用**，`x-kpsdk-h` 绑定两者——因此**重放捕获的头必然失败**。难度随会话新鲜度升级，冷启动数据中心 IP 会面对秒级挑战，**这是经济防御而非密码学防御**。
- **Imperva**：`reese84` + 设备指纹，实测阻断率约 46.6%（CI 40.6–52.6，样本 142）。
- **Anubis**（开源）：工作量证明，默认难度 5，曾受 CVE-2025-24369 影响。对策是用原生代码求解（比浏览器 JS 快约两个数量级）并复用 cookie。

**基准数据的正确读法**：阻断率是**配置与目标类型**的函数，不只是厂商。Akamai 在电商域名阻断 33.1%、在通用网页 8.9%（差 3.7 倍），Cloudflare 为 30.0% 与 6.6%——**厂商间差异小于同一厂商不同部署间的差异**。结论是"部署比品牌更重要"。

**2025–2026 的转折**：Forrester 于 2025 年底将该品类从 "bot management" 改名为 **"bot and agent trust management"**。数据：恶意自动化流量在 2025-07 至 2026-06 间增长 **124%**（是人类流量增速的 9 倍以上）；**65.3%** 的受测网站无法拦截 10 种 bot/AI-agent 类型中的任何一种；**80%** 的 AI agent 不自我声明身份；伪造的 ChatGPT 风格 UA 在近 70 万站点中 **79.7%** 畅通无阻。工程含义：**任何依赖 agent 自我声明的识别机制都在测量空气**。

**厂商无关决策路径**：识别厂商 → 识别层级 → 问"这个厂商的主要向量是什么" → **只修一个变量** → 重新测量 → 检查商业闸门。最常见的错误是一次改指纹、改出口、改行为三件事，然后不知道哪一项起了作用。

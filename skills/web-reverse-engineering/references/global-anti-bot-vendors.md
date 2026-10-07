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
| `aws-waf-token`, `x-aws-waf-token` | AWS WAF Bot Control |
| `__cf_bm` + `cf_chl_*` | Cloudflare Challenge Platform |
| `TSPD_101`, `TS*` | F5 BIG-IP Bot Defense / ASM (see §2.8 — **not** the Shape line) |
| `vsd_*`, `RT`, `TS*` | Akamai (older / variant deployments) |
| `_cq_duid`, `_cq_suid`, `_cq_rti`, `_cheq_rti`, `_cq_pxg` | CHEQ |
| `aj_signals` | Arcjet |
| `techaro.lol-anubis-auth` (configurable) | Anubis (EdDSA-signed JWT issued after PoW) |

> **Corrected**: earlier versions of this document listed `_imp_apg_r_` / `_imp_apg_s_` as
> F5/Shape telemetry cookies. That cannot be verified — the string appears in no F5
> documentation. F5's official docs confirm only the `/__imp_apg__/js/<customerid>.js`
> **path prefix** (the F5 Distributed Cloud Account Protection / Authentication
> Intelligence line), with default headers `x-safe-fr` and `x-apg-sr` and backend
> `dip.zeronaught.com`. Treat `_imp_apg_*` as a **namespace** that likely belongs to that
> line, not as a confirmed cookie name. See §2.8.
>
> **Also absent by design**: Netacea and Cequence are **agentless** — they set no
> client-side artifact at all, so no cookie row can exist for them. See §2.9.

### Pass 2 — headers

| Header | Meaning |
|---|---|
| `Server: cloudflare`, `cf-ray` | Cloudflare is in front (does **not** prove Bot Management is on) |
| `cf-mitigated: challenge` | Cloudflare actively challenged this request |
| `x-kpsdk-ct`, `x-kpsdk-cd`, `x-kpsdk-v`, `x-kpsdk-st` | Kasada |
| `x-is-human` | Vercel BotID (Kasada-backed) |
| `crawler-price`, `crawler-charged`, `crawler-exact-price` | Cloudflare Pay Per Crawl |
| `x-datadome`, `x-datadome-response`, `x-datadome-botname` | DataDome |
| `x-iinfo` | Imperva |
| `x-px-*`, `x-px-block` | HUMAN/PerimeterX |
| `Inference` | **F5 Shape** — values like `Token Missing`, `Invalid Token`, `Rate Limit Exceeded`, `Token Denylisted` |
| `X-<token>-a` … `-z` (prefix varies per site) | **F5 Shape** telemetry — no stable name, see §2.8 |
| `akamai-bm-telemetry` | Akamai (derived from sensor_data) |
| `x-safe-fr`, `x-apg-sr` | F5 XC Account Protection / Authentication Intelligence |
| `X-PX-Authorization` | HUMAN mobile SDK |
| `Signature`, `Signature-Input`, `Signature-Agent` | **Web Bot Auth** (RFC 9421) — a signed agent, not a bot defense |

### Pass 3 — HTML body (script `src` and inline markers)

| Marker | Vendor |
|---|---|
| `/cdn-cgi/challenge-platform/` | Cloudflare Challenge Platform |
| `challenges.cloudflare.com` | Cloudflare Turnstile |
| `sensor.js`, `/akam/`, `_sec/`, `/_sec/cp_challenge/` | Akamai |
| `captcha-delivery.com`, `js.datadome.co` | DataDome |
| `px-cdn.net`, `client.px-cloud.net`, `pxchk.net`, `perimeterx.net` | HUMAN/PerimeterX |
| `p.js`, `ips.js` — or better, the two-UUID path `149e9513-01fa-4fb0-aad4-566afd725d1b/…` | Kasada |
| `funcaptcha.com`, `arkoselabs.com`, `FunCaptcha-Token` | Arkose Labs |
| `https://www.google.com/recaptcha/` | Google reCAPTCHA |
| `js.hcaptcha.com` | hCaptcha |
| `/.within.website/` + "Making sure you're not a bot!" | Anubis (open source) |
| `challenge.js` + `*.awswaf.com` | AWS WAF Bot Control |
| `/_Incapsula_Resource` + "Powered by Incapsula" | Imperva |
| `sec-cpt-if` iframe, `crypto_message-*.htm` | Akamai sec-cpt (second layer) |
| `<script id="arcjet-signals">` | Arcjet |

### HTTP status as a vendor tell

| Status | Vendor | Meaning |
|---|---|---|
| **403** with a challenge page | Cloudflare, Imperva | Standard challenge |
| **200 with a fake page** | **Imperva** | "Pardon Our Interruption" — **only checking the status code makes you think you succeeded** |
| **429** with `x-kpsdk-*` | Kasada | "Run the proof of work" |
| **403/429 with no body at all** | Kasada | Rejected; the *absence* of a block page is the tell |
| **200 with a poisoned body** | **F5 Shape** | Transform-200 on a specific endpoint; the homepage may be clean |
| **428** | Akamai sec-cpt | Precondition Required — forced wait + PoW |
| **405** | AWS WAF | CAPTCHA/Challenge interception on a POST |
| **202** with an obfuscated `<script>` | 瑞数 RiverSecurity | Chinese vendors use 202/412 |
| **412** | 瑞数, some WAFs | Precondition failed = challenge |
| **402** | Cloudflare / AWS WAF / x402 | Commercial gate — stop |

Kasada's use of **429 rather than 403** is the detail that trips people up. A 429 with
`x-kpsdk-` headers is an instruction; a bare 403 afterwards means the IP is spent.

**Three status codes that actively mislead**: Imperva's 200-disguised block, F5 Shape's
200-with-poisoned-body, and Kasada's body-less rejection. In all three cases, checking the
status code tells you the opposite of the truth.

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
- **Cookie lifetimes (use the vendor's own table, not community folklore)**: `_px` /
  `_px2` / `_px3` are **JS cookies with a 5.5-minute lifetime** — the widely repeated
  "60 seconds" figure is wrong. `_pxhd` (device hash, HTTP cookie) and `_pxvid` (visitor
  ID) both last a year. `pxcts` is session-scoped.
- **Mechanism**: behavioural biometrics and predictive analytics; **reputation is shared
  network-wide across all customer sites**. A single fingerprint signal is evaluated
  against the whole customer base, not per-site.
- **Consequence**: a fingerprint burned on one HUMAN-protected site is burned
  **everywhere HUMAN is deployed**. This is the opposite of DataDome's per-site model,
  and it means the cost of a bad attempt is much higher.
- **Architecture**: Sensor (site JS collecting 100+ signals + behavioural biometrics) →
  Detector (cloud ML verdict) → Enforcer (CDN layer). A separate Code Defender product
  monitors client-side tampering (including `toString()` patching) — relevant if you are
  running a spoofed environment.
- **Testing hooks the vendor publishes** (for integration validation, not a bypass):
  `User-Agent: PhantomJS` triggers a challenge; `x-px-captcha-testing: <token>` skips
  detection.
- **Context**: HUMAN formed from the PerimeterX + White Ops merger (2022-07-27). The
  `AgenticTrust` line (2025) distinguishes human / bot / agentic traffic.

Sources: [HUMAN cookie documentation](https://docs.humansecurity.com/applications/use-of-cookies-web-storage),
[Bot Defender overview](https://docs.humansecurity.com/applications/bd-overview)

Source: [Scrappey cheatsheet](https://scrappey.com/qa/anti-bot/anti-bot-vendor-detection-cheatsheet)

### Kasada

- **Tell**: `x-kpsdk-ct`, `x-kpsdk-cd`, `x-kpsdk-v`, `x-kpsdk-st` headers; `p.js` /
  `ips.js`; **429** on first contact
- **Script path is a reliable fingerprint**: the script lives under a path containing
  **two fixed UUID segments** —
  `/149e9513-01fa-4fb0-aad4-566afd725d1b/2d206a39-8ed7-437e-a3be-862e0f06eea3/ips.js`.
  Those UUIDs recur across many sites, which makes them more useful for identification
  than the file name (`p.js` / `ips.js` are used interchangeably).
- **Cookie names are customer-chosen** (observed `KP_UIDz`, `tkrm_alpekz`) and therefore
  are **not** a usable fingerprint. Use the headers and the script path instead.
- **Mechanism**: proof-of-work inside a heavily obfuscated, **polymorphic** VM. The script
  changes on almost every load, so a hardcoded parser is worthless. Three layers stack:
  1. `p.js`/`ips.js` runs an in-page **custom JS VM executing encrypted bytecode**
  2. the server issues a cryptographic puzzle; the client solves it and encodes the answer
     *and the elapsed time* into `x-kpsdk-cd`
  3. CT/CD/HMAC trio plus JA3/JA4 and header-order validation
- **Hardware fingerprinting**: Kasada binds to the hardware that actually executes the JS,
  not merely browser properties. This is why a datacenter VM with perfect TLS and IP still
  fails.
- **Token model** — the part that breaks naive replay:
  - `x-kpsdk-ct` — client token, session-scoped (roughly 30 minutes in public RE writeups)
  - `x-kpsdk-cd` — client data containing the PoW answer, **single-use, derived per
    request**
  - `x-kpsdk-h` — an HMAC signature binding CT and CD together
  - Replaying captured headers fails because `x-kpsdk-cd` is spent after one use.
- **Difficulty scaling**: PoW difficulty escalates for new or untrusted sessions. A
  warmed residential session faces near-instant puzzles; a cold datacenter IP can face
  multi-second challenges or timeouts. This makes cold-session scaling economically
  painful — **the defence is economic, not cryptographic.**
- **Headers come back in the response**, not only the request: `x-kpsdk-st` and
  `x-kpsdk-ct` arrive on the `/tl` response and are inputs to `/cd`.
- **Endpoint shape**: `/fp` (fingerprint endpoint; a background GET returns 429 with the
  ips.js reference), `/tl` (submit payload, returns `x-kpsdk-st` + `x-kpsdk-ct`), `/cd`
  (client data), `/.k`, `/_ato`, `/mfc` (some sites); CDN `*.kpsdk.io`
- **The block page is absent, and that is the fingerprint.** On rejection Kasada returns a
  **bare 403 or 429 with no CAPTCHA, no branding, no body.** "I cannot find the block page"
  is itself the signal that you are looking at Kasada.
- **Vercel BotID** is Kasada-powered and adds a separate `x-is-human` header requiring
  its own generation path. `Vercel BotID Deep Analysis` inherits Kasada's full difficulty;
  the free `Basic` tier is a much weaker client-side self-attestation.

Sources: [Browserless Kasada analysis](https://www.browserless.io/blog/kasada-bypass),
[SparkProxy](https://www.sparkproxy.io/blog/how-to-bypass-kasada),
[Decodo Kasada](https://decodo.com/blog/kasada-bypass),
[vercel-llm-api issue #22](https://github.com/ading2210/vercel-llm-api/issues/22),
[Hyper Solutions Kasada](https://hypersolutions.co/products/kasada)

### Imperva (Incapsula)

- **Tell**: `reese84` cookie, `incap_ses_*`, `visid_incap_*`, `nlbi_*`; `x-iinfo` header
- **Cookie details**: `reese84` is the ABP sensor output, formatted as three segments
  `3:<base64>:<base64>`. `incap_ses_<siteid>` is session-scoped; `visid_incap_<siteid>`
  lasts about a year. A useful **structural** (not semantic) check: the trailing site ID
  in `visid_incap_*` and `incap_ses_*` should match.
- **`x-iinfo` is present on every response** that passes through Imperva's edge. Its field
  meanings are **not publicly documented** by the vendor; community interpretations are
  unverified. Use it as a presence indicator, not as a decoder ring.
- **The block page lies about its status code.** Imperva frequently returns **HTTP 200
  with a fake page** ("Pardon Our Interruption"). **Checking only the status code will
  make you think you succeeded.** Validate that you got the content you asked for.
- **Mechanism**: TLS/JA3 + a `reese84` challenge (client script collects 180+ browser
  signals and POSTs; server returns a token) + a four-cookie chain consistency check +
  device fingerprint (Canvas/WebGL/AudioContext/navigator/font enumeration) + a
  **700-dimension behavioural analysis**.
- **`reese84` can only be minted by running the real sensor in a real browser.** A plain
  HTTP client cannot produce it. Two challenge generations coexist: `___utmvc` (legacy,
  sometimes runnable in a JS engine) and `reese84` (current, no shortcut).
- **Observed strength**: independent benchmarking measured Imperva's block rate around
  46.6% (95% CI 40.6–52.6) across 142 domains — high, though the sample is small and the
  measurement conditions matter (see §4).
- **Difficulty**: **high** — `reese84` rotates aggressively per deployment, static replay
  does not survive a version bump, and the 200-disguised block page causes automation to
  misreport success.

Sources: [CapSolver Imperva](https://docs.capsolver.com/en/guide/captcha/imperva),
[SparkProxy Imperva](https://www.sparkproxy.io/blog/how-to-bypass-imperva-incapsula),
[Aethyn: which engine blocked you](https://www.aethyn.io/solutions/imperva-incapsula-which-engine-blocked-you)

### F5 / Shape Security

Two distinct product lines, routinely confused. Get this right before diagnosing.

**1. BIG-IP line** (`TSPD_101`, `TS*` cookies)

- `TS*` belongs to **BIG-IP ASM**; `TSPD_101` to **BIG-IP Bot Defense**
- Easy to misattribute: `f5_cspm` is an AVR cookie and **not** a bot-defense signature;
  `BIGipServer*` is LTM persistence; `reese84` belongs to Imperva
- **Tell**: `TS*` / `TSPD_101` cookie families

**2. Shape line** (F5 Distributed Cloud Bot Defense, acquired 2020 for ~$1B)

This is the one that breaks expectations, and the reason it matters:

- **No single fixed cookie name.** Shape expects the client to *actively send telemetry*
  after JS execution — as custom HTTP headers on XHR/fetch, or in the POST body. Header
  names are **obfuscated per deployment**, observed as a family like
  `X-<token>-a` / `-b` / `-c` / `-d` / `-f` / `-z`, where the prefix changes per site and
  per script version. There is no stable name to grep for.
- **Policy binds to endpoint + method, not to hostname.** The homepage returns 200 while a
  specific XHR or login POST returns "transformed garbage" content — a **200 status with a
  poisoned body**. Checking the homepage and concluding "unprotected" is the standard
  mistake.
- **Diagnostic header `Inference`** — values include `Token Missing` (JS never ran),
  `Invalid Token` / `AI Payload Missing` / `AI Payload Invalid` (header tampered),
  `Rate Limit Exceeded` / `Token Denylisted` (replay), `Attack Inference`,
  `Threat Intelligence`. This header is the fastest way to see *why* you were rejected.
- **Mechanism**: a reverse proxy serves obfuscated JS → environment/behaviour signals are
  collected → encrypted into telemetry attached to a request header or POST body → ML
  analysis in Shape AI Cloud. Client code uses a **custom JS VM with frequently
  randomized opcode mapping**, which keeps static RE cost high indefinitely.
- **Telemetry is single-use and IP-bound.** It cannot be cached and replayed in batch.
- **Community observation**: on some Shape sites, opening DevTools breaks the session and
  closing it restores it. Recommended route is Playwright + Firefox.
- **`_imp_apg_*` is NOT a confirmed Shape cookie.** F5 docs confirm only the
  `/__imp_apg__/js/<customerid>.js` path prefix (the F5 XC Account Protection /
  Authentication Intelligence line) with default headers `x-safe-fr` / `x-apg-sr` and
  backend `dip.zeronaught.com`. Do not treat `_imp_apg_r_` as a fact.
- **Difficulty**: **very high** — obfuscated per-deployment header names, single-use
  IP-bound telemetry, and endpoint-granular policy combine to make each target a fresh
  problem.

Sources: [F5 Shape analysis](https://scrapfly.io/blog/posts/how-to-bypass-f5-when-web-scraping),
[Shape telemetry collector](https://github.com/Johnw7789/shape),
[F5 DevCentral Inference header](https://community.f5.com/t/do-f5-shape-security-instert-http-header-showing-the-bot-name-category-etc-of-the-http-traffic/69133),
[F5 XC APG configuration](https://techdocs.f5.com/en-us/bigip-17-1-0/big-ip-distributed-cloud-services-bd-ap-ai/configuring-ap-ai-profile.html)

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

### Agentless vendors — no client artifact exists

Two vendors in this market are **server-side only, by design**. This is not a gap in the
research; it is the product.

| Vendor | Product | Stated position |
|---|---|---|
| **Netacea** | Bot Protection (intent engine "Talos") | "Agentless edge integration, no JavaScript or SDK required, nothing for an attacker to reverse-engineer, fails open" |
| **Cequence** | Bot Management (CQ botDefense) | "No client-side JavaScript or SDK integration; protects at the network layer" via an inline reverse proxy that drops requests |

**Why this matters for diagnosis**: for these two, **there is no cookie, script, or header
to fingerprint**. Positive identification is impossible. Reverse identification works only
by behaviour (request-rate structure, session topology) and by elimination — "nothing
matches any known vendor signature".

**Why it matters for technique**: there is no payload to reverse and nothing to replay
offline. The entire bypass question collapses into **behaviour shaping** — real pacing,
real session topology — because that is the only surface being scored. Netacea states it
deliberately does **not** use TLS fingerprinting, considering it weak.

Both are Strong Performer / Contender tier in the Forrester Wave (§5), which reflects that
the agentless approach is a legitimate architectural position rather than a limitation.

Sources: [Netacea platform](https://netacea.com/platform),
[Netacea: why server-side](https://netacea.com/blog/why-server-side-bot-management),
[Cequence bot management](https://www.cequence.ai/products/bot-management)

### Others worth knowing

| Vendor | Tell | Note |
|---|---|---|
| **Arkose Labs** | `<input id="FunCaptcha-Token" name="fc-token">`, `data-pkey`, `client-api.arkoselabs.com` | BDA encrypted fingerprint blob (~50+ fields, AES-CBC, key derived from UA + timestamp) + a session-bound **`tguess`/MatchKey** that requires real script execution — solving the puzzle without it still fails. Puzzles carry a ~15s inactivity reset and escalate difficulty with accumulated failures. Uses **Jscrambler** for polymorphic obfuscation. |
| **CHEQ** | `_cq_duid`, `_cq_suid`, `_cq_rti`, `_cheq_rti`, `_cq_pxg` | Claims 2,000+ background security challenges per session across Traffic Integrity / User Input Validation / Identity Intelligence. No public solver. |
| **Radware** | **No stable public cookie or header name** | Acquired ShieldSquare (2019). IDBA collects 250+ parameters; Collective Bot Intelligence spans 80,000+ assets. Identification relies on behaviour + elimination. |
| **Castle** | — | Scores **users**, not requests; login/registration focused |
| **reCAPTCHA Enterprise** | `google.com/recaptcha` | Widget option for forms |
| **hCaptcha Enterprise** | `js.hcaptcha.com` | Widget option for forms |
| **Vercel BotID** | `x-is-human` header; `c.js` under the Kasada UUID path | **Basic** is a weak client-side self-attestation (free); **Deep Analysis** is Kasada ML ($1/1000 `checkBotId()` calls). Independent RE found Basic essentially always returned "human" and only flagged a bot when the signal payload was replaced with an empty object. |
| **Arcjet** | `aj_signals` cookie, `ARCJET_SIGNALS` reason string, `<script id="arcjet-signals">` | Runs **in the application process**, not at the CDN. Advanced signals are collected by a **WASM** module. The bot identification list is **fully open source** (`arcjet/well-known-bots`, MIT) — so reading it is faster than reversing anything. |
| **Prosopo** | — | Publishes pricing for all tiers |

Sources: [Arkose API guide](https://developer.arkoselabs.com/docs/arkose-labs-api-guide),
[Jscrambler + Arkose case study](https://jscrambler.com/blog/case-study-preventing-automated-abuse-with-arkose-labs-and-jscrambler),
[Reversing BotID](https://nullpt.rs/reversing-botid),
[Arcjet advanced signals](https://docs.arcjet.com/bot-protection/advanced-signals),
[Arcjet well-known-bots](https://github.com/arcjet/well-known-bots)

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
| F5 BIG-IP | `TS*` / `TSPD_101` challenge | Browser + egress | Medium–High |
| F5 Shape (Distributed Cloud) | Per-deployment obfuscated telemetry, endpoint-bound | Browser + coherent egress; no replay | Very High |
| Arkose | Interactive challenge | Solver service (volume-dependent) | High |
| AWS WAF Bot Control | Managed rules + ML | Coherent client | Medium |
| Anubis | Proof of work | Native PoW solver | Low–Medium |

The tiers are not a ranking of engineering quality. They are a ranking of *what it costs
you* to get through, which depends as much on the deployment as the product.

---

## 4. Public benchmarking data

Independent measurements exist and are worth knowing — **but the numbers are only
comparable within one study.** Two studies of the same vendors differ by a factor of
five, because they measured different things.

| Vendor | AIMultiple block rate | AIMultiple domains | arXiv block rate |
|---|---|---|---|
| Imperva | **46.6%** (CI 40.6–52.6) | 142 | 0–16% band |
| Anubis | **35.7%** (CI 22.6–49.4) | 28 | — |
| Akamai | 10.7% | 552 | **26.4%** |
| Cloudflare | 6.7% | 2,829 | **37.0%** |
| HUMAN | 15.6% | 40 | — |
| DataDome | not published | 92 | — |
| F5 | not published | 54 | — |
| AWS WAF | not published | 69 | — |

**Why Cloudflare is 6.7% in one study and 37.0% in the other.** This is the single most
important methodological point on this page:

- **AIMultiple** (2026-09; 3,859 domains; 50,000 requests) drove traffic through
  **commercial scraping APIs** — Bright Data, Zyte, Nimble — which already perform
  anti-detection. That measures *how well a well-equipped scraper does*.
- **arXiv 2606.14525** (University of Bamberg; Tranco top 10k; 4 browser configurations;
  40,000 visits) compared **browser configurations including a headless control**. That
  measures *how often a default client is blocked*.

The ranking almost inverts between the two. **Never cite either number without its test
condition**, and never compare them to each other.

Additional findings from the arXiv study worth internalizing:

- **82%** of all blocks were attributable to bot detection (59% vendor-confirmed, 23%
  inferred from conditional behaviour).
- Chromium headless soft-block rate was **15%**, other configurations **7%**.
- **75% of "headless-only" blocks were caused by header-layer signals alone.**
- **46%** of sites probed for JS properties that exist only in automation browsers — the
  probe surface is much larger than the actual block surface.
- **83% of 81 top-conference crawling papers do not discuss bot-detection blocking at
  all**, and only 5% quantify it.

**AIMultiple's own methodological caveat** (stated by the authors): Cloudflare and Akamai
deployments mostly arrive via free-CDN defaults or enterprise contracts, while
Imperva/DataDome/HUMAN/Anubis were installed deliberately by someone. The benchmark
therefore compares **deployment paths as well as products**, and does not hold that
variable fixed.

**Deployment share** (W3Techs — the only transparent method here): Cloudflare serves
25.1–26.5% of *all* websites and 85.0–85.3% of sites with a known reverse proxy. By rank:
61.8% of the top 1,000, 66.3% of the top 10,000, 72.7% of the top 100,000, 80.9% of the
top 1M. Akamai is only 0.6–0.7% of all websites but rises to **21.3% of the top 1,000** —
head-site concentration is far higher than全网 share.

**How to read any of this**: block rate is a function of *configuration, target type, and
who is driving the traffic*, not just vendor. The e-commerce vs general-web gap (Akamai
3.7×, Cloudflare 4.5× in the AIMultiple data) is larger than most vendor-to-vendor
differences. A vendor "blocking 8.9%" on general web is not weak; it is configured
per-path. **Deployment matters more than brand.**

Sources: [AIMultiple](https://aimultiple.com/bot-detection-software),
[arXiv 2606.14525](https://arxiv.org/html/2606.14525v1),
[W3Techs proxy statistics](https://w3techs.com/technologies/overview/proxy)

---

## 5. The 2025–2026 shift: agents, not bots

The category was renamed, and the rename is verifiable.

**Forrester, 2025-10-03** — Sandy Carielli (VP, Principal Analyst) published *"Bot
Management Graduates — Introducing The Bot And Agent Trust Management Market"*, moving the
category from "bot management software" to **"bot and agent trust management software"**.
Forrester's own definition:

> 识别并分析指向应用的自动化流量的意图，与良好 bot 和 AI agent 建立持续信任关系，同时拒绝
> 并误导恶意 bot 与 AI agent，以保护合法客户业务并提高攻击者成本。
> (Identify and analyze the intent of automated traffic to applications, build ongoing
> trust relationships with good bots and AI agents, while denying and misleading
> malicious bots and AI agents — to protect legitimate customer business and raise
> attacker cost.)

Report timeline:

| Report | Date | Coverage |
|---|---|---|
| Landscape, Q4 2025 | 2025-12-18 | 19 vendors |
| Wave, Q2 2026 | 2026-06-15 | Leaders: **DataDome, HUMAN, Kasada**; Strong Performers: Arkose Labs, CHEQ, Netacea; Contenders: hCaptcha, Google (reCAPTCHA Enterprise / Google Cloud Fraud Defense) |

DataDome received the highest Current Offering score (4.12/5), scoring 5 on 12 of 24
criteria. **Cloudflare and Akamai are not in that Wave** — the two largest CDN-layer
incumbents are not evaluated in that particular report, though both shipped agent-trust
capabilities on their own schedules in 2026.

> **Partially unverified**: the Wave itself is paywalled (direct fetch returns 403). The
> three Leaders are corroborated by multiple independent sources; the Strong Performer and
> Contender tiers rest on vendor press releases and third-party summaries.

Concrete data points (vendor-reported, except where noted):

- DataDome reported malicious automated traffic grew **124%** between July 2025 and June
  2026 — more than nine times the growth rate of human traffic. Crawlers were 70.9% of
  bad-bot traffic, up 185.2% year over year.
- DataDome measured **65.3%** of tested websites unable to block or challenge a single one
  of 10 bot and AI-agent types. Full protection fell from 8.4% (2024) → 2.8% (2025) →
  **2.4%** (2026) — three consecutive years of decline.
- **80%** of AI agents do not properly identify themselves.
- A spoofed ChatGPT-style User-Agent got through unblocked on **79.7%** of ~698,000 sites.
- HUMAN reported agentic traffic grew **6900%** in 2025.
- Cloudflare began blocking AI-based scraping by default in July 2025.
- Thales/Imperva's 2026 Bad Bot Report: automated traffic was **53%** of all traffic in
  2025 (51% in 2024), bad bots **40%**, AI-driven attacks up **12.5×**, and **27%** of bot
  attacks targeted APIs directly.

**Engineering consequence**: the frontier has moved from "am I a bot?" to "what is this
agent's intent, and is it authorized?" User-Agent-based agent identification is currently
unreliable in both directions — 80% of agents do not self-identify, and a spoofed agent UA
passes almost everywhere. **Any system relying on agent self-declaration is measuring
nothing.**

### The identity layer: Web Bot Auth

The standards answer to "who is this agent" is **Web Bot Auth**, built on **RFC 9421 HTTP
Message Signatures**:

- Each bot generates an **Ed25519** private key; the public key is published as JWKS at
  `/.well-known/http-message-signatures-directory`
- Requests carry `Signature`, `Signature-Input`, and `Signature-Agent` headers
- Cloudflare folded it into its Verified Bots Program (from 2025-07-01); verified bots are
  no longer challenged by bot management
- **Verifier side**: Cloudflare, Akamai (App & API Protector), Vercel, HUMAN, AWS WAF
  (CloudFront only)
- **Signer side**: OpenAI, Google (experimental subset — the main Googlebot index crawler
  is **not** signed), Shopify, Amazon Bedrock AgentCore
- IETF working group formed after IETF 123; if it stays on schedule an RFC could land
  around 2027

**Terminology change worth knowing (Cloudflare, 2026-07-01)**: the old "verified bot"
category became **`direct`**, and the deprecated "signed agent" became **`intermediary`**.

Sources: [Forrester rename](https://www.forrester.com/blogs/bot-management-graduates-introducing-the-bot-and-agent-trust-management-market),
[Cloudflare Verified Bots with cryptography](https://blog.cloudflare.com/verified-bots-with-cryptography),
[Cloudflare Web Bot Auth](https://developers.cloudflare.com/bots/reference/bot-verification/web-bot-auth),
[Imperva Bad Bot Report 2026](https://www.imperva.com/blog/bad-bot-report-2026-bots-agentic-age)

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

**为什么先做识别**：最贵的错误是把正确的技术用在不匹配的厂商上。Cloudflare 的答案是"一个能过 Turnstile 的浏览器"；Kasada 的答案是"工作量证明求解器"；DataDome 的答案是"IP 信誉"；Akamai 的答案是"TLS 一致性"；F5 Shape 的答案是"真实浏览器 + 可复用性为零"。这是五个不同的问题。

**单次响应识别三步**：① Cookie（`__cf_bm`/`cf_clearance`→Cloudflare，`_abck`/`bm_sz`→Akamai，`datadome`→DataDome，`_px*`→HUMAN/PerimeterX，`reese84`→Imperva，`_cq_*`→CHEQ，`aj_signals`→Arcjet）；② 响应头（`cf-mitigated` 才证明 Cloudflare 真的开了 Bot Management，仅有 `Server: cloudflare` 不算；`x-kpsdk-ct/cd/v`→Kasada；`Inference`→F5 Shape；`crawler-price`→Pay Per Crawl）；③ HTML（`/cdn-cgi/challenge-platform/`、`sensor.js`、`captcha-delivery.com`、`px-cdn.net`、Kasada 的双 UUID 路径、`funcaptcha.com`、`challenge.js`、`/.within.website/`）。

**状态码本身是厂商特征，但有三个会主动误导你**：
- **Imperva** 常用 **200 + 假页面**（"Pardon Our Interruption"）——只看状态码会以为成功。
- **F5 Shape** 在特定 endpoint 返回 **200 + 被投毒的 body**（transform 200）——首页可能是干净的 200。
- **Kasada** 拒绝时返回**裸 403/429 且完全没有 body**——"找不到阻断页"本身就是特征。
- 其余：Cloudflare/Imperva 常规用 403；**Kasada 首触用 429**（"去跑工作量证明"）；Akamai sec-cpt 用 **428**；AWS WAF 拦截 POST 用 **405**；瑞数用 **202/412**；**402** 是商业闸门（停止）。

**各厂商的关键差异**：
- **Cloudflare**：可按站点配置，同一域名可能完全没开 Bot Management。域名覆盖最大（W3Techs：全网 25.1–26.5%，已知反向代理中 85%；top 1,000 中 61.8%）。
- **Akamai**：`sensor_data` 为加密载荷，编码 100+ 信号，脚本持续更新——**针对具体版本做逆向会在下个版本失效**。`_abck` 需要约 3 次 sensor POST 才转为有效（`~0~`），且 v3 sensor 以 `bm_sz` 派生值为输入，**跨 session 复用 `bm_sz` 会导致 sensor 被拒**。**TLS 一致性是最高杠杆的单一修复点。**
- **DataDome**：**逐请求独立评分**而非会话累积信任 → **IP 信誉权重最高**，代理质量是首要杠杆。按站点训练 ML（据称 85,000+ 模型），一个站点上的方案迁移性差。**2026-01 起换装浏览器内 VM**（bytecode + XOR 字符串 + 自定义 opcode），难度再次抬升。
- **HUMAN/PerimeterX**：**信誉在整个客户网络内共享**，一个指纹在一个站点烧毁即**全线烧毁**——试错成本最高。架构为 Sensor → Detector → Enforcer，另有 Code Defender 监测客户端篡改（含 `toString()` 修补）。**`_px`/`_px2`/`_px3` 是 5.5 分钟的 JS cookie**——社区常说的"60 秒"是错的，以官方 cookie 表为准。
- **Kasada**：多态混淆 VM 内的 PoW。`x-kpsdk-ct` 为会话令牌（约 30 分钟），`x-kpsdk-cd` 含 PoW 答案（**含耗时**）且**一次性使用、逐请求派生**，`x-kpsdk-h` 是绑定两者的 HMAC——因此**重放捕获的头必然失败**。另有**硬件指纹**（绑定实际执行 JS 的硬件），这是数据中心 VM 即使 TLS 与 IP 全对仍失败的原因。难度随会话新鲜度升级，**这是经济防御而非密码学防御**。
- **Imperva**：`reese84` 三段格式 `3:<base64>:<base64>`，**只能由真实浏览器运行 sensor 产生**，裸 HTTP 客户端无法铸造；另有 700 维行为分析与四件套 cookie 链一致性检查。实测阻断率约 46.6%（CI 40.6–52.6，样本 142）。
- **F5 两条线必须分开**：`TS*`/`TSPD_101` 属 **BIG-IP**（ASM / Bot Defense）；Shape 线**没有固定 cookie 名**，靠 JS 执行后主动发送的**逐部署混淆遥测头**（`X-<token>-a…z`），且**策略挂在 endpoint + method 上而非 hostname**——只探测首页会得出"未受保护"的错误结论。遥测**一次性且绑 IP**，无法缓存重放。难度 **very high**。**`_imp_apg_r_` 无法证实为 Shape 签名，不要当事实用。**
- **无客户端产物的两家**：**Netacea** 与 **Cequence** 按设计不做客户端集成（agentless），**没有 cookie/脚本/头可指纹化**，正向识别不可能，只能靠行为面 + 排除法；也**没有 payload 可逆向或离线重放**，规避问题完全塌缩为"行为塑形"。
- **Anubis**（开源）：PoW，默认难度 5，曾受 CVE-2025-24369 影响。对策是用原生代码求解（比浏览器 JS 快约两个数量级）并复用 JWT cookie。

**基准数据的正确读法（重要）**：**同一厂商在不同研究里的阻断率能差 5 倍**——Cloudflare 在 AIMultiple 是 6.7%、在 arXiv 是 37.0%。原因是测的东西不同：AIMultiple 走**商业抓取 API**（Bright Data/Zyte/Nimble，本身已做反检测），arXiv 对比**四种浏览器配置含 headless 对照**。**两个数字不能互相比较，引用时必须带测试条件。** arXiv 另外的发现值得记住：**82%** 的阻断可归因于 bot 检测；**75% 的"仅 headless 被拦"由 header 层信号单独造成**；**46%** 的站点探测了只存在于自动化浏览器的 JS 属性（探测面远大于阻断面）；81 篇顶会爬虫论文中 **83% 完全未讨论 bot 检测阻断**。W3Techs 是唯一方法透明的部署数据。

**2025–2026 的转折（已核实）**：Forrester 于 **2025-10-03** 由 Sandy Carielli 发布博文，把品类从 "bot management" 改为 **"bot and agent trust management"**；Landscape Q4 2025（2025-12-18，19 家）；**Wave Q2 2026（2026-06-15）：Leader 为 DataDome / HUMAN / Kasada**，Strong Performer 为 Arkose / CHEQ / Netacea，Contender 为 hCaptcha / reCAPTCHA Enterprise。**Cloudflare 与 Akamai 不在该 Wave 名单内。** 数据：恶意自动化流量 2025-07 至 2026-06 增长 **124%**；**65.3%** 的受测网站对 10 种 bot/AI-agent 类型完全无防护（完全防护率 8.4%→2.8%→**2.4%** 连续三年下降）；**80%** 的 AI agent 不自我声明身份；伪造的 ChatGPT 风格 UA 在约 69.8 万站点中 **79.7%** 畅通无阻。工程含义：**任何依赖 agent 自我声明的识别机制都在测量空气**。

**身份层底座 Web Bot Auth**：基于 **RFC 9421 HTTP Message Signatures**，每个 bot 用 **Ed25519** 私钥签名，公钥以 JWKS 形式放在 `/.well-known/http-message-signatures-directory`，请求带 `Signature`/`Signature-Input`/`Signature-Agent`。验证方含 Cloudflare / Akamai / Vercel / HUMAN / AWS WAF（仅 CloudFront）；签名方含 OpenAI / Google（实验性子集，**Googlebot 主索引爬虫尚未签名**）/ Shopify / Amazon。**Cloudflare 2026-07-01 术语变更**：旧 "verified bot" → **`direct`**，旧 "signed agent" → **`intermediary`**。

**厂商无关决策路径**：识别厂商 → 识别层级 → 问"这个厂商的主要向量是什么" → **只修一个变量** → 重新测量 → 检查商业闸门。最常见的错误是一次改指纹、改出口、改行为三件事，然后不知道哪一项起了作用。

**引用纪律**：本文所有厂商规模数字均为厂商自述或方法未公开的商业数据库口径，**不可作为中立事实**。可引用的中立数据只有 W3Techs（方法公开）与 arXiv 论文（数据集已发布 Zenodo）。标注为 unverified 的条目包括：Forrester Wave 完整分档（付费墙）、Cloudflare "19 个 Verified AI Agent / 84% / 57.5%"、AWS WAF Web Bot Auth 标签、Content Signals 域名数、Imperva cookie 溢出绕过（需按当前版本复验）、BotStopper 高级指纹（路线图未发布）。

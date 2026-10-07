# Anti-Bot Bypass by Vendor

This page is tactical: detection vectors + recommended response stack.

## Service Matrix

### Western / global

| Service | Difficulty | Typical detection stack |
|---|---|---|
| Cloudflare | High | TLS/HTTP fingerprint, JS challenge, Turnstile, behavior scoring, **AI Labyrinth, Pay Per Crawl** |
| Akamai Bot Manager | Very High | sensor telemetry, browser integrity checks, behavior models, **HTTP/2 fingerprint** |
| DataDome | Very High | client fingerprint, network reputation, intent/behavior models, **CDP signal research** |
| Kasada | Very High | script integrity, dynamic challenge protocol, behavior + network |
| PerimeterX / HUMAN | High | browser + interaction telemetry, anomaly scoring |
| Imperva | High | layered reputation + challenge policy |
| **Anubis** | Medium | proof-of-work (cost-based, not recognition-based) — see below |

### Chinese risk-control vendors

| Vendor | Product | Core mechanism | Difficulty |
|---|---|---|---|
| 瑞数 RiverSecurity | Botgate | Dynamic obfuscation + VM + eval | Very High (per-site) |
| 阿里云盾 / 阿里 WAF | ESA / WAF 3.0 | Cookie tracking + JS challenge + slider | High |
| 腾讯 | TCaptcha (天御/防水墙) | JSVMP device fingerprint + PoW | Very High |
| 网易易盾 | NECaptcha | Device fingerprint + behavior | High |
| 数美 shumei | 天网 | Device fingerprint + content | Medium |
| 顶象 dingxiang | 智能无感验证 | Dynamic JS + env checks | High |
| 同盾 | 设备指纹 / tdCaptcha | Blackbox fingerprint + slider | High |
| 极验 GeeTest | Sensebot | Trajectory + fingerprint + PoW | Medium |

**Chinese vendors need a different approach than Western ones.** Western defenses are fingerprint-first; Chinese defenses are **signed-parameter-first**. See `cn-risk-control-ecosystem.md` and `captcha-vendors-cn.md`.

## Cloudflare Playbook

1. Probe with `curl_cffi` + consistent header profile.
2. Move to residential/ISP proxy pool with ASN diversity.
3. Escalate to patched browser automation for JS/Turnstile flows.
4. Reduce noisy retries; challenge loops usually indicate identity mismatch, not "try harder".
5. **Watch for 402** — that is Pay Per Crawl, a commercial rejection, not a technical obstacle. Stop retrying.
6. **Watch for AI Labyrinth** — check for `noindex` and invisible decoy links. If present, discard the page and mark the source untrusted.

Note: **Super Bot Fight Mode runs after custom WAF rules**, so a `Skip` action on a specific path bypasses SBFM. Useful for understanding protection ordering.

## Akamai Playbook

1. Assume deep telemetry and strict behavioral checks.
2. **Check your HTTP/2 fingerprint early** — Akamai's H2 fingerprint is `SETTINGS|WINDOW_UPDATE|PRIORITY|PSEUDO_HEADER_ORDER`, and pseudo-header order is a strong discriminator (Chrome/Firefox `m,a,s,p` vs Safari `m,s,p,a`).
3. Use browser path early; HTTP-only often fails at scale.
4. Keep session continuity and realistic clickstream order.
5. If economics fail, evaluate managed scraping providers.

## DataDome Playbook

1. Prioritize proxy quality over proxy quantity.
2. Patch runtime leaks and avoid deterministic action cadence.
3. **The CDP `Runtime.enable` signal is the current strongest detection vector** — DataDome published the research. Use `rebrowser-patches` or Patchright.
4. Track challenge rate per proxy ASN and isolate toxic pools quickly.
5. For critical targets, maintain target-specific browser/profile templates.

## Kasada Playbook

1. Treat as top-tier defense with frequent challenge updates.
2. Use full browser automation with strong identity coherence.
3. Minimize deviations from ordinary user journeys.
4. Expect ongoing maintenance, not one-time bypass.

## Anubis Playbook

Anubis is **cost-based**, not recognition-based — different rules apply.

1. The PoW is Hashcash-style SHA-256. Default difficulty 5 → `W = 16^5` ≈ 1,048,576 hashes.
2. Browser JS does ~0.5 MH/s; **native Go does ~50 MH/s** — a native solver is ~100x faster and finishes in milliseconds.
3. Reuse the `*-anubis-auth` JWT cookie (~2 weeks validity) instead of re-solving.
4. If the site uses the paid **Thoth** reputation add-on, raw compute advantage shrinks.
5. 2026 versions use **Argon2id via WebAssembly** (memory-hard), which specifically defeats GPU/ASIC acceleration — expect this to get harder.

## Chinese Vendor Playbook

The failure mode is different: you usually **pass the challenge and still get rejected**.

1. Determine **which layer** is blocking (see the layer decision tree in `cn-risk-control-ecosystem.md`).
2. If a signed parameter is missing → `signature-parameter-re.md`.
3. If the challenge passes but the API rejects → **device fingerprint layer**. Passing layer 1 is not passing layer 2.
4. Preferred route for complex vendors: **environment simulation** (run the vendor's own JS in Node) rather than hand-porting.
5. Make sure your JS environment's UA matches your request UA — this single fix has taken NetEase Yidun pass rates from <20% to 100%.

## Strategy Selection

| Situation | Recommended route |
|---|---|
| low volume, strict SLA | managed scraping API may be cheaper overall |
| medium volume, engineering bandwidth available | patched browser stack + quality proxies |
| high volume, many target variants | framework + identity orchestration + observability |
| Chinese risk-control target | environment simulation or pure-algorithm reversal, not browser automation |
| proof-of-work gate | native-code solver, not browser JS |

## Metrics That Matter

- challenge rate by target
- challenge rate by ASN/provider
- median solved page time
- **downstream rejection rate after a successful challenge** (catches the "passed layer 1, failed layer 2" problem)
- useful-data-per-dollar

## Red Flags

- same fingerprint with many IPs in short windows
- same IP with many incompatible fingerprints
- abrupt burst traffic after challenge failures
- **UA that does not match the TLS fingerprint** — the mismatch itself is the signal
- **spoofed UA with an untouched JA3** — negative value; you were better off not spoofing

Bypass success is less about single-request wins and more about stable, repeatable extraction economics.

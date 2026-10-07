# Proxy Strategies

Proxy quality is often the top predictor of success on defended targets.

For deep operational detail (health scoring, pools, rotation algorithms, vendor comparison), see `proxy-rotation-strategies.md`. This page is the decision layer.

## Proxy Types

| Type | Reputation | Speed | Cost | Best for |
|---|---|---|---|---|
| Datacenter | Low to medium | High | Low | low-friction targets, bulk fetches |
| Residential | High | Medium | Medium-high | defended consumer websites |
| ISP (static residential) | High | High | High | session continuity, account workflows |
| Mobile | Very high | Medium | Highest | hardest anti-bot environments |

**ASN type matters more than raw IP count.** A residential IP from a consumer ISP ASN behaves differently from a "residential" IP resold from a hosting ASN. Vastel maintains public bot-IP lists useful for auditing your own pool: https://github.com/antoinevastel/avastel-bot-ips-lists

## Rotation Models

### Per-request rotation
- strongest anonymity
- weak continuity

### Sticky session rotation
- same IP for N minutes or N requests
- needed for login/cart/search journey continuity

### Adaptive rotation (recommended)
- rotate by challenge signals, failure class, and ASN health
- avoid blind rotation that destroys valid sessions

**Key rule**: rotate on **challenge spike**, not on a timer. Blind rotation destroys sessions that were already working and re-rolls a proxy you might already have burned.

## Proxy Pool Health Model

Track for each proxy:
- success rate
- challenge rate
- median latency
- target-specific block history
- ASN and country consistency
- **IP lifetime** (how long the IP has been in rotation — fresh IPs are often already burned)

Score proxies and route traffic accordingly.

## Example Selection Logic

```python
# pseudo-code
if target_defense_level >= 4:
    pool = residential_or_isp
elif target_defense_level == 3:
    pool = mixed_pool
else:
    pool = datacenter_pool

proxy = pick_best_health_score(pool, target=target_name)
```

## Geo and Locale Coherence

Always align:
- proxy country/city
- `Accept-Language`
- timezone in browser context
- market-specific page variant assumptions

Incoherent identity is a common hidden blocker. **A US IP with `Accept-Language: zh-CN` and `Asia/Shanghai` timezone is a stronger signal than a datacenter IP.**

## Cost Governance

- route low-risk pages to cheaper pools
- reserve expensive pools for challenge-prone endpoints
- enforce per-target budget and automatic downgrade paths

**Vendor pricing (unverified marketing claims — treat as rough magnitude only)**:

| Vendor | Claimed pool | Claimed entry price |
|---|---|---|
| Bright Data | 400M+ residential, 7M+ mobile | ~$8/GB PAYG |
| Oxylabs | 175M+ residential | — |
| Decodo | 115M+ | — |
| IPRoyal | 80M+ | ~$1.57/proxy |
| SOAX | 155M+ | — |
| ProxyEmpire | — | ~$1.50/GB |

These numbers come from vendor marketing and are **not independently verified**. Evaluate on measured success rate for your specific target, not on advertised pool size.

## Self-Hosted Option

For targets that only need IP diversity rather than residential reputation, self-hosted proxy stacks are far cheaper:

- Mihomo / Clash Meta
- sing-box
- Xray-core (REALITY)

> **Compatibility note**: REALITY is not interoperable between Xray v26.7.11 and mihomo v1.19.28. Pin versions when chaining them.

## Failure Handling

| Failure | Action |
|---|---|
| timeout spike | quarantine proxy temporarily |
| repeated challenge loops | switch ASN and identity profile |
| 403 burst on one target | isolate target-specific blocklist for that pool |
| works on target A, instantly blocked on target B | the pool is burned for B — do not generalize |
| **HTTP 402** | Not a proxy problem. Pay Per Crawl commercial gate — stop, do not rotate |

## Measuring Pool Quality

Do not trust the vendor. Measure:

```python
# per (proxy, target) pair
metrics = {
    "requests": n,
    "success": s,          # 200 with expected content
    "challenged": c,       # challenge page returned
    "blocked": b,          # 403/429/402
    "median_latency_ms": t,
}
# Track success/(requests) per ASN, and challenge rate per ASN.
# Isolate any ASN whose challenge rate diverges >2x from the pool median.
```

**The metric that matters is challenge rate per ASN for a specific target** — not pool size, not country count.

Good proxy ops is an engineering problem, not just a vendor purchase.

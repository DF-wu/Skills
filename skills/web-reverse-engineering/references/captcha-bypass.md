# CAPTCHA Bypass Strategy

CAPTCHA should be treated as a symptom, not the core problem.

## Avoidance-First Model

1. fix fingerprint coherence
2. improve proxy reputation
3. tune behavior pacing
4. only then add CAPTCHA solving

## CAPTCHA Classes

| Type | Typical systems | Notes |
|---|---|---|
| image checkbox/grid | reCAPTCHA v2, hCaptcha | solvable via provider APIs |
| score-based invisible | reCAPTCHA v3 | highly sensitive to identity quality |
| managed challenges | Turnstile, enterprise variants | often triggered by risk scoring, not static puzzles |
| slider / drag | 极验, 阿里, 腾讯, 数美 | dominant in the Chinese ecosystem; trajectory-sensitive |
| click-order / puzzle | 极验 click, 易盾 type 7 | coordinate sequence matters |
| proof-of-work | Anubis, 腾讯 TCaptcha | cost-based, not recognition-based |

For the Chinese vendor breakdown (GeeTest, Aliyun, Tencent TCaptcha, NetEase Yidun, Shumei, Dingxiang, Tongdun) see `captcha-vendors-cn.md`.

## Solving Options

| Option | Pros | Cons |
|---|---|---|
| 2Captcha / Anti-Captcha | broad support, mature | latency + variable solve quality |
| CapSolver-like APIs | modern challenge coverage | cost and provider dependency |
| in-house model approach | control and privacy | expensive to build/maintain |
| **pure-algorithm reversal** | zero per-solve cost, high throughput | high upfront cost, breaks on target updates |
| **environment simulation (补环境)** | runs vendor JS locally | must defeat environment checks |

## Choosing a Route

The route depends on **volume** first:

| Volume | Recommended route |
|---|---|
| < 1k / day | third-party solving API |
| 1k – 10k / day | solving API, or RPC to a real browser |
| > 10k / day | pure-algorithm reversal or environment simulation |

For slider/click CAPTCHAs, note that **trajectory quality matters as much as the crypto**. A correctly signed request with a straight-line drag still fails. Use bezier curves, ease-in-out cubic easing, or an AI-generated trajectory function.

## Integration Pattern

```text
request -> challenge detected -> create solve task -> poll result -> inject token -> continue flow
```

## Minimal API Flow (Pseudo)

```python
# pseudo-code only
task_id = solver.create_task(site_key, page_url)
solution = solver.wait(task_id, timeout=120)
submit(solution.token)
```

## Environment Simulation Route

For vendors whose logic runs in obfuscated JS (极验, 数美, 易盾), the highest-leverage route is to run their own code in a controlled Node environment:

1. Build a browser-like environment (`window`, `document`, `navigator`, `screen`, Canvas)
2. Execute the vendor's challenge script inside it
3. Capture the generated parameters
4. Replay them in your own request

This is far cheaper to maintain than hand-porting the algorithm. See `environment-simulation-jsvmp.md`.

**Prerequisite**: your JS environment's `navigator.userAgent` **must match the request's `User-Agent`**. NetEase Yidun reports show pass rate jumping from <20% to 100% after fixing this alone.

## Score-Based Challenges (reCAPTCHA v3)

| Item | Value |
|---|---|
| Score range | 0.0–1.0 |
| Default threshold | 0.5 |
| Free tier | 10,000 assessments/month |
| Beyond | $8/month up to 100,000 |
| siteverify fields | `success`, `score`, `action`, `challenge_ts`, `hostname`, `error-codes` |

Two operational notes:

1. **Validate `action` server-side.** Without it, a token from a low-value page can be replayed against a high-value endpoint.
2. **Staging scores are unreliable.** The model learns from real traffic, so test-environment scores carry no signal.

## Operational Rules

- do not send every challenge to solver; first evaluate if identity mismatch is root cause
- cap max solve attempts per session
- move failed sessions to cooldown queue
- log challenge type, solver latency, acceptance rate
- for slider CAPTCHAs, log trajectory generation parameters alongside acceptance rate — a sudden drop often means the trajectory model, not the crypto, broke

## When to Stop Solving

Stop and reprofile traffic when:
- solve acceptance rate collapses
- challenge loops increase after valid tokens
- target rotates challenge mode aggressively
- **the challenge passes but the downstream API still rejects** — this means the target validates device fingerprint separately from the challenge. Passing the CAPTCHA is not the same as passing the risk engine.

That usually means your identity layer is broken, not your solver.

## Context Note

Challenge solving is a standard operational technique. The legal posture depends on what data you access after solving, not the solving itself. Public data behind a challenge remains public data. See `legal-ethical.md` for the risk matrix.

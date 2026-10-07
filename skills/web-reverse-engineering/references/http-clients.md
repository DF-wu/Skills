# HTTP Clients (Network-Layer Evasion)

Use HTTP clients first when you do not need heavy DOM interaction. They are faster, cheaper, and easier to scale than browser automation.

## Tool Matrix

| Tool | Stack | What it does | Install | Pros | Cons |
|---|---|---|---|---|---|
| curl_cffi | Python | Browser-like TLS/JA3/JA4/HTTP2 impersonation | `pip install -U curl_cffi` | Mature, fast, strongest anti-bot baseline | No JS runtime |
| hrequests | Python | High-level requests API + browser-like transport | `pip install -U hrequests` | Convenient API, async options, anti-fingerprint support | Smaller ecosystem than requests/httpx |
| rnet | Python | Fine-grained TLS/HTTP2 fingerprint control | `pip install -U --pre rnet` | Low-level control, performance-focused | Younger project, more tuning required |
| httpx / requests | Python | Standard HTTP clients | `pip install -U httpx` | Stable and simple | Easy to detect on protected targets |
| got-scraping / impit | Node.js | Browser-like HTTP in JS ecosystem | `npm i got-scraping` | Good Node integration | Tooling fragmentation |
| **curl-impersonate** | C | The underlying C library many Python wrappers bind to | build from source | Reference implementation | Build complexity |

Note: version velocity is high. Always verify with `pip index versions <pkg>` or package release pages before pinning.

## curl_cffi: The Details That Matter

`impersonate="chrome"` alone is **not** enough for modern Chrome targets. Chrome 109+ randomizes TLS extension order, so you must reproduce that behavior explicitly:

```python
from curl_cffi import requests

resp = requests.get(
    "https://target.example",
    impersonate="chrome",
    extra_fp={
        "tls_permute_extensions": True,   # reproduce Chrome 109+ extension-order randomization
    },
    timeout=20,
)
```

**Why this matters**: JA3 (order-sensitive) breaks on modern Chrome because of extension randomization. JA3N and JA4 are order-insensitive by construction. If your client sends a fixed extension order while claiming to be modern Chrome, the mismatch is detectable.

> **Terminology caution**: JA3N is **only a curl_cffi ecosystem convention, not a formal standard**. Do not assume other tools implement it identically.

### The UA/OS trap in curl_cffi's version aliases (verified)

Measured against `tls.browserleaks.com` with curl_cffi 0.16.3:

| impersonate | UA platform | Chrome | JA4 |
|---|---|---|---|
| `chrome99` | **Windows** | 99 | `t13d1516h2_8daaf6152771_e5627efa2ab1` |
| `edge101` | **Windows** | 101 | `t13d1516h2_8daaf6152771_e5627efa2ab1` |
| `chrome120` | **macOS** | 120 | `t13d1516h2_8daaf6152771_02713d6af862` |
| `chrome131` | **macOS** | 131 | `t13d1516h2_8daaf6152771_02713d6af862` |
| `chrome136` | **macOS** | 136 | `t13d1516h2_8daaf6152771_d8a2da3f94cd` |
| `chrome150` | **macOS** | 150 | `t13d1516h2_8daaf6152771_806a8c22fdea` |
| `firefox133` | macOS | — | `t13d1716h2_5b57614c22b0_eeeea6562960` |
| `safari180` | macOS | — | `t13d2014h2_a09f3c656075_e42f34c56612` |

Two consequences that bite in practice:

1. **`impersonate="chrome"` is an alias that resolves to the newest build** (currently `chrome150`) and therefore reports a **macOS** User-Agent. If you then override the UA with a Windows string to match a Windows-looking session, you have created exactly the UA-vs-fingerprint mismatch this page warns about.
2. **`chrome120` and `chrome131` share an identical JA4** (`...02713d6af862`). Pinning a specific version for JA4 stability will not distinguish you between those builds — the JA3 differs but JA4 does not.

Correct approach: pick the impersonate target whose **UA platform matches the session you are pretending to be**, then do not override the UA. If you need a Windows Chrome profile on a modern version, override the UA **and** accept that the TLS profile is macOS-derived; verify the resulting combination against the echo endpoint rather than assuming it is coherent.

```python
from curl_cffi import requests

# Read back what the profile actually claims, instead of assuming.
r = requests.get("https://tls.browserleaks.com/json", impersonate="chrome136", timeout=25)
print(r.json()["user_agent"])   # -> macOS string; do NOT paste a Windows UA over this
```

`scripts/fingerprint_probe.py --json` prints `summary.user_agent` alongside `ja3_hash`/`ja4` so you can catch this before deploying.

### JA3 changes on every request once permutation is on (verified)

With `tls_permute_extensions: True`, two consecutive requests from the same session produced:

| run | JA3 | JA4 |
|---|---|---|
| 1 | `0ba99caf26b07a146f0cb49cb7431976` | `t13d1516h2_8daaf6152771_806a8c22fdea` |
| 2 | `6988ac858ec7f28b6700dcd048f8e3e6` | `t13d1516h2_8daaf6152771_806a8c22fdea` |

**Do not diff JA3 against a stored reference when permutation is enabled** — the difference is expected behavior, not a misconfiguration. Use **JA4** (and JA3N) for baseline comparison; they are order-insensitive by construction. This also means a target fingerprinting on JA3 cannot rely on a stable value for modern Chrome, which is precisely why extension randomization was introduced.

Corollary for the reverse-engineering side: if a site rejects you based on a JA3 you recorded from a browser, the browser's own JA3 is not reproducible either. The site is almost certainly keying on JA4 or on a non-TLS signal.

## Minimal Patterns

### 1) Baseline request (cheap path)

```python
import httpx

resp = httpx.get("https://example.com", timeout=15)
print(resp.status_code)
```

### 2) TLS/browser impersonation with curl_cffi

```python
from curl_cffi import requests

resp = requests.get(
    "https://target.example",
    impersonate="chrome",  # keep this aligned with your UA/header profile
    timeout=20,
)
print(resp.status_code)
```

### 3) hrequests session

```python
import hrequests

s = hrequests.Session(browser="chrome")
resp = s.get("https://target.example")
print(resp.status_code)
```

## Verify Your Fingerprint Before Blaming the Target

```python
from curl_cffi import requests

r = requests.get("https://tls.browserleaks.com/json", impersonate="chrome")
print(r.json())   # compare ja3_hash / ja3n_hash / ja4 / akamai_hash / akamai_text
```

Compare against a real browser hitting the same page. If the values differ, fix the client before writing any bypass code.

## Practical Hardening

- Keep `User-Agent`, TLS profile, `Accept-Language`, and proxy geography coherent.
- Add randomized pacing and exponential backoff.
- Rotate proxies on challenge spikes, not every single request by default.
- Persist cookies/session tokens for stateful flows.
- Match header **order** and **set**, not just values — header order is itself a fingerprint.

## Failure Signatures and Actions

| Symptom | Likely cause | Next action |
|---|---|---|
| Immediate 403 / 1020 | TLS/HTTP fingerprint mismatch | switch to curl_cffi profile + trusted residential/ISP proxy |
| Infinite challenge page | low IP reputation or incoherent fingerprint | rotate proxy ASN and align locale/timezone headers |
| Works manually, fails in code | missing dynamic tokens/cookies | replay full request chain from DevTools |
| Works for a while, then 403 | session/token lifetime expired | refresh the full session chain, not just the cookie |
| **HTTP 402** | Pay Per Crawl (Cloudflare) | stop retrying; check `crawler-*` headers; evaluate commercial access |
| Challenge passes but API rejects | device fingerprint validated separately | see `cn-risk-control-ecosystem.md` — passing layer 1 is not passing layer 2 |
| Blocked only after you set a custom UA | UA platform contradicts the TLS profile | check `summary.user_agent` from `fingerprint_probe.py`; see the UA/OS trap above |

## Upgrade Path

If HTTP clients fail after fingerprint alignment:
1. move to patched browser automation (`browser-automation.md`)
2. apply anti-detection controls (`anti-detection.md`)
3. execute service-specific strategy (`anti-bot-bypass.md`)
4. if the target is a Chinese risk-control vendor, go to `cn-risk-control-ecosystem.md` — the failure mode is usually a signed parameter, not a fingerprint

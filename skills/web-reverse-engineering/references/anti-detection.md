# Anti-Detection Fundamentals

Modern detection is multi-layer. Winning requires coherence across layers, not a single stealth plugin.

## Detection Surfaces

### 1) Network Layer

- TLS ClientHello fingerprint (JA3 / JA3N / JA4 / JA4+)
- HTTP/2 frame fingerprint (SETTINGS / WINDOW_UPDATE / PRIORITY / pseudo-header order)
- ASN reputation and IP history
- TCP/IP stack fingerprint (JA4T / p0f-style)

Mitigation:
- use browser-like transport (`curl_cffi`, `hrequests`, `rnet`)
- rotate proxies by quality and ASN diversity
- keep headers and transport profile consistent
- **never spoof UA without matching the TLS/H2 fingerprint** — inconsistency is itself a strong signal

See `tls-http-fingerprinting.md` for the full fingerprint reference and `frontier-anti-bot-2026.md` for detection tooling.

### 2) Browser Runtime Layer

- `navigator.webdriver` and automation artifacts
- **CDP leaks — currently the strongest signal.** Playwright/Puppeteer calling `Runtime.enable` / `Console.enable` mutates console serialization in a detectable way
- canvas / WebGL / audio / font entropy mismatches
- plugin / device / screen inconsistencies
- `Error.stack` signatures (**mostly defeated by V8 patches** — DataDome and Castle research)
- `window.cdc_*` (ChromeDriver), `__pwInitScripts` (Playwright), `isTrusted === false`

Mitigation:
- patched automation stacks (Patchright / rebrowser-patches)
- anti-detect browser profiles where needed
- avoid impossible hardware/browser combinations
- `Page.createIsolatedWorld` mitigates some CDP detection

**Specific signals worth checking**:

| Signal | Why it fails |
|---|---|
| `window.chrome` missing | Chromium-family marker object |
| `navigator.plugins` empty | Real browsers have plugins |
| Permissions API inconsistency | `Notification.permission` vs `navigator.permissions.query` disagree |
| WebGL renderer = SwiftShader / Mesa | Software rendering = no GPU = likely server |
| `outerHeight` / `outerWidth` === 0 | No window |
| `document.hasFocus()` === false | No focus |
| `navigator.languages` missing | Real browsers always have it |
| Timezone vs IP mismatch | Cross-check |

### 3) Behavioral Layer

- deterministic click/scroll timing
- no idle/reading behavior
- impossible interaction velocity
- bot.incolumitas.com computes a `behavioralClassificationScore` (0 = bot, 1 = human) re-evaluated at 1.5 / 4 / 7 / 10 / 15 seconds

Mitigation:
- action pacing with jitter
- realistic dwell times near content blocks
- bounded retries and session-level memory

## Anti-Detect Browser Ladder

Ordered by effectiveness:

| Tier | Option | License | Notes |
|---|---|---|---|
| 1 | **Camoufox** | MPL-2.0 | Firefox fork, patches at the **C++ layer** — invisible to JS-level detection |
| 2 | **Patchright** | Apache-2.0 | Chromium only, **drop-in Playwright replacement** |
| 2 | **nodriver** | AGPL-3.0 | Direct CDP, no WebDriver |
| 3 | rebrowser-patches | MIT | Patches Playwright/Puppeteer CDP leaks |
| 4 | JS-injection stealth plugins | varies | Patch at JS layer; defeated by native checks |

**Also viable**: SeleniumBase (UC/CDP mode), botasaurus (+driver), pydoll, DrissionPage, zendriver, Scrapling.

**Dead — do not use**: **undetected-chromedriver** is effectively unmaintained (PyPI 3.5.5, last release 2024-02-17).

## Coherence Checklist

If any row is inconsistent, risk rises quickly.

| Signal | Must align with |
|---|---|
| IP geo | timezone, locale, language headers |
| Browser UA | TLS profile family |
| Device profile | screen size, hardware threads, memory hints |
| Session cookies | navigation flow and referrer chain |
| JS `navigator.userAgent` | actual request `User-Agent` header |
| `screen` + `devicePixelRatio` | plausible hardware combination |

## Fingerprint Validation Targets

Use these pages only for diagnostics, not as absolute pass/fail:

| Page | What it reports |
|---|---|
| `https://bot.incolumitas.com` | behavioral score + fingerprint consistency |
| `https://bot-detector.rebrowser.net` | CDP leak detection |
| `https://tls.peet.ws` | JA3 / JA4 / Akamai H2 fingerprint |
| `https://bot.sannysoft.com` | classic automation signals |
| `https://abrahamjuliot.github.io/creepjs/` | deep fingerprint consistency |
| `https://arh.antoinevastel.com/bots/areyouheadless` | basic headless detection |
| `https://browserscan.net` / `https://pixelscan.net` | composite consistency |

## Practical Escalation

1. Start with transport-level impersonation and quality proxies.
2. If challenged, move to patched browser runtime.
3. If still challenged, improve behavior model and session continuity.
4. If still failing, decide if target should be handled by managed scraping APIs.

## Why Teams Still Fail

- They optimize one layer only.
- They rotate IPs aggressively but keep an obvious browser signature.
- They keep perfect browser signatures but use robotic timing.
- They spoof the UA but leave the TLS fingerprint untouched — **the mismatch itself is the tell**.
- They use an abandoned stack (undetected-chromedriver) and assume it still works.

The anti-detection game is about believable end-to-end identity, not one magic tool.

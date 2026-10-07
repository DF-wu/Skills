# Browser Automation (JS + Interaction Targets)

When data is rendered client-side or protected by JS challenges, browser automation is required.

## Tool Comparison

| Tool | Stack | Install | Best use | Pros | Cons |
|---|---|---|---|---|---|
| Playwright | Py/Node | `pip install playwright` + `playwright install` | Standard automation/testing | Stable API, strong ecosystem | Detectable without hardening |
| **Patchright** | Node/Py | `npm i patchright` / `pip install patchright` | **Chromium stealth baseline** | Drop-in Playwright replacement, patches CDP leaks | Chromium-only |
| rebrowser-patches | Node/Py | package-specific | Harden existing Playwright/Puppeteer | Patches the `Runtime.enable` leak | Patch maintenance overhead |
| **Camoufox** | Python | `pip install camoufox[geoip]` | **High-pressure anti-bot** | Firefox fork patched at the **C++ layer** | Firefox-only; platform constraints vary |
| **nodriver** | Python | `pip install nodriver` | CDP-native async | No WebDriver, no chromedriver binary | Non-trivial migration from Selenium |
| SeleniumBase | Python | `pip install seleniumbase` | UC/CDP mode suites | Mature, broad driver support | Heavier abstraction |
| DrissionPage | Python | `pip install DrissionPage` | Chinese-language stacks | Popular in CN ecosystem | Docs mostly Chinese |
| pydoll / zendriver / botasaurus | Python | various | CDP-native alternatives | Active, no driver binary | Smaller ecosystems |
| Browser-Use | Python | `pip install browser-use` | agent-style web tasks | High-level orchestration | Abstraction overhead for scraping |

**Dead — do not use**: **undetected-chromedriver** (last release 2024-02-17, PyPI 3.5.5). It is still the most commonly recommended tool in old tutorials and it no longer works reliably.

## Anti-Detect Ladder (effectiveness order)

| Tier | Option | Why |
|---|---|---|
| 1 | **Camoufox** | Patches at the C++ layer — invisible to JS-level detection |
| 2 | **Patchright** / **nodriver** | Removes the CDP signals, Chromium-native |
| 3 | rebrowser-patches | Patches the `Runtime.enable` leak in existing stacks |
| 4 | JS-injection stealth plugins | Patches at JS layer; defeated by native checks |

**Why the ordering matters**: the current strongest automation signal is the **side effect of CDP `Runtime.enable`** — Playwright/Puppeteer calling it mutates console serialization in a detectable way. DataDome and Castle both published research on this. JS-injection plugins cannot fix it because the mutation happens below them.

The classic `Error.stack` signal is **mostly defeated by V8 patches** — do not rely on it either way.

`Page.createIsolatedWorld` mitigates some CDP detection but is not a complete fix.

## Baseline Playwright Pattern

```python
import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto("https://example.com", wait_until="domcontentloaded")
        title = await page.title()
        print(title)
        await browser.close()

asyncio.run(run())
```

## Patchright Pattern (drop-in replacement)

```python
# Same API as Playwright, different engine.
# Install: pip install patchright && patchright install chromium
from patchright.async_api import async_playwright

# Key: use launch_persistent_context, not launch + new_context.
# A persistent context keeps a stable profile, which matches real user behavior
# and avoids the "fresh profile every request" tell.
async with async_playwright() as p:
    context = await p.chromium.launch_persistent_context(
        user_data_dir="./profile",
        channel="chrome",       # real Chrome, not bundled Chromium
        headless=False,
    )
```

## Hardening Layers

1. Transport coherence: proxy + locale + timezone + language headers.
2. Runtime leak reduction: patched frameworks that mitigate known CDP markers.
3. Humanized interaction: non-linear cursor paths, realistic think time, bounded concurrency.
4. Session continuity: reuse warm profiles for stateful targets where allowed.

## Browser Choice Heuristics

- Chromium-patched (Patchright/rebrowser): best default for most anti-bot targets.
- Camoufox/Firefox path: use when Chromium-specific detections are strong, or when you need C++-level patching.
- nodriver: when you want minimal footprint and direct CDP control.
- Hybrid strategy: probe with HTTP clients, escalate to browsers only for pages requiring JS.

## Common Pitfalls

- Running too many concurrent tabs from a single identity.
- Fresh profile every request on a target expecting continuity.
- Inconsistent `Accept-Language` vs IP region.
- Overusing one proxy ASN across all traffic.
- **Running headless when the target's risk engine weights headless heavily.** `headless=False` under Xvfb is often the cheapest single improvement.
- **Not matching `screen` dimensions to the window size.** A 1920x1080 screen with a 800x600 viewport is a tell.

## In-Page Fetch (same-origin, passes CF)

To call a Cloudflare-gated same-origin API from an authed browser, run `fetch` **inside the page**:

```python
data = await page.evaluate(
    """async (u) => {
        const r = await fetch(u, {credentials: 'include'});
        return {status: r.status, body: await r.text()};
    }""", api_url)
```

It executes in the real origin → carries cookies + CF clearance and passes exactly like the site's
own AJAX. `context.request` (APIRequestContext) and curl_cffi do NOT run CF JS and get 403 on gated
endpoints. Combine with session-cookie injection to map authed APIs — see
`authenticated-session-mapping.md`.

## When NOT to Use Browser Automation

This is the most common waste of engineering time in this field. Do not reach for a browser when:

| Situation | Better approach |
|---|---|
| API has a signed parameter | `signature-parameter-re.md` — browser does not help at all |
| Target is RiverSecurity-protected | `ruishu-river-security.md` — per-site VM, browser automation is not the answer |
| Challenge passes but API rejects | `cn-risk-control-ecosystem.md` — device fingerprint layer |
| Response is a proof-of-work gate | Solve in native code (~50 MH/s vs ~0.5 MH/s) |
| You only need JSON that an XHR returns | Replay the XHR directly |
| HTTP 402 | Stop. Commercial gate, not a technical one |

## Observability You Need

Track per target:
- success rate
- challenge rate
- median time to first useful data
- failure buckets (network, challenge, parsing, auth)
- **downstream rejection rate after a successful challenge**

Without these metrics, anti-bot tuning is guesswork.

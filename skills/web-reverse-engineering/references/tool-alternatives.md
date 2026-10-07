# Tool Alternatives and Replacement Matrix

This page maps common tools to their specialized or stealth-oriented replacements. The goal is to upgrade your stack without relearning everything.

> **Read the "Dead Tools" section at the bottom first.** Several tools still recommended in most tutorials are archived or removed, and using them wastes weeks.

## HTTP Clients: Standard → Stealth

| Use case | Standard tool | Stealth replacement | Why upgrade |
|---|---|---|---|
| Simple GET/POST | `curl` / `wget` | `curl_cffi` | Real browser TLS/JA3/JA4 fingerprint |
| Python requests | `requests` / `httpx` | `curl_cffi` | Drop-in with `impersonate="chrome"` |
| Async Python | `aiohttp` / `httpx` | `hrequests` / `rnet` | Built-in anti-fingerprint + async |
| Node.js | `axios` / `node-fetch` | `got-scraping` / `impit` | Browser-like HTTP/2 behavior |
| Go | `net/http` | `req` (with TLS customization) | Fine-grained JA3/HTTP2 control |
| Rust | `reqwest` | `rquest` | TLS/HTTP2 impersonation, curl_cffi equivalent |

**Chrome 109+ caveat**: `impersonate="chrome"` alone is not enough. Add `extra_fp={"tls_permute_extensions": True}` to reproduce extension-order randomization. Without it your JA3 is order-fixed while claiming to be modern Chrome.

## Browser Automation: Detectable → Undetectable

| Use case | Standard tool | Stealth replacement | Why upgrade |
|---|---|---|---|
| General automation | Playwright / Selenium | **Patchright** | Drop-in Playwright replacement, patches CDP leaks |
| Existing Playwright/Puppeteer | — | **rebrowser-patches** | Patches the `Runtime.enable` signal |
| High-pressure anti-bot | Playwright | **Camoufox** | Patched at the **C++ layer** — invisible to JS detection |
| Lightweight CDP | Selenium | **nodriver** | Native async CDP, no driver binary |
| Agent orchestration | Playwright + custom code | `Browser-Use` | High-level task planning |
| Chinese market targets | Playwright | `DrissionPage` | Anti-detection optimized for CN defenses |
| Go browser automation | Playwright | `Rod` / `chromedp` | Native Go, single binary, fast |
| Rust browser automation | Playwright | `chromiumoxide` / `headless_chrome` | Memory safe, high performance |
| Test suites | Selenium | `SeleniumBase` (UC/CDP mode) | Mature, broad driver support |

**Effectiveness ladder**: Camoufox (C++ layer) > Patchright / nodriver > rebrowser-patches > JS-injection stealth plugins.

## Proxy: Datacenter → Residential/ISP

| Use case | Budget option | Quality replacement | Why upgrade |
|---|---|---|---|
| Low-friction targets | Free/datacenter proxies | Residential/ISP rotating | Passes ASN reputation checks |
| Session continuity | Per-request rotation | Sticky sessions (N min) | Login/cart journey support |
| Mobile-only content | Residential | Mobile proxy pool | Highest reputation tier |
| Self-hosted | Individual IPs | Mihomo / sing-box / Xray-core | Cheap IP diversity when you don't need residential reputation |
| Bot-IP auditing | — | `antoinevastel/avastel-bot-ips-lists` | Check whether your own pool is on public bot lists |

**REALITY compatibility trap**: Xray v26.7.11 and mihomo v1.19.28 are **not interoperable** for REALITY. Pin versions when chaining them.

## Scraping Frameworks: Script → Production

| Scale | Approach | Framework | Why upgrade |
|---|---|---|---|
| One-off script | `requests` + `BeautifulSoup` | `Scrapy` | Middleware, pipelines, retries |
| Browser-heavy | Playwright scripts | `Crawlee` / `PlaywrightCrawler` | Queue + orchestration built-in |
| Go stack | Python scripts | `Colly` / `Rod` / `chromedp` | Speed + single-binary deploy |
| Rust stack | Python/Node | `Ferret` / `spider` | Memory safety + performance |
| Distributed queue | Single-machine Scrapy | `Scrapy-Redis` / `Crawlee` + Redis | Horizontal scaling |
| Serverless | Self-hosted | `ScrapyRT` / `ScrapingHub` / `Apify` | Pay-per-request, no infra mgmt |

**When a framework is the wrong answer**: a single API with a signed parameter, or under ~10k requests total. Write a thin client instead.

## CAPTCHA: Manual → Automated

### Western

| Type | Service | Notes |
|---|---|---|
| Image challenges | 2Captcha / Anti-Captcha | Broad support, variable quality |
| Invisible score-based | CapSolver / Anti-Captcha Enterprise | reCAPTCHA v3 / Turnstile focus |
| Self-hosted | Open-source models (YOLO-based) | High maintenance, privacy control |
| Browser extension | `Buster` / `NopeCHA` | Free tier, rate-limited |
| Audio challenges | `SpeechRecognition` + solver | Accessibility fallback paths |

### Chinese

| Vendor | Route |
|---|---|
| GeeTest | Trajectory model + `w` parameter; environment simulation |
| Aliyun | `unsbox` / `hexXor` algorithm; fixed key |
| Tencent TCaptcha | JSVMP + PoW; environment simulation |
| NetEase Yidun | Device fingerprint; official field list available |
| Shumei | AES-CBC with fixed iv `0102030405060708` |
| Dingxiang | Dynamic JS + env checks |
| Tongdun | `blackbox` / `p1`–`p9` |

See `captcha-vendors-cn.md` for parameters and `environment-simulation-jsvmp.md` for the simulation harness.

## Reverse Engineering: Basic → Advanced

| Layer | Basic tool | Advanced replacement | Why upgrade |
|---|---|---|---|
| API interception | Browser DevTools | `mitmproxy` / `HTTP Toolkit` | Mobile app + modification + scripting |
| API → spec | Manual documentation | **`mitmproxy2swagger`** | Auto-derive OpenAPI from captured traffic |
| GUI interception | `Charles Proxy` | `Burp Suite` / `Fiddler Everywhere` | Security testing + extensibility |
| Mobile GUI proxy | Charles | **`Reqable`** (formerly HttpCanary) | Mobile-first design |
| Traffic analysis | Browser Network | `Wireshark` / `tcpdump` / `tshark` | Full packet-level inspection |
| Mobile SSL pinning | None (blocked) | `Frida` / `objection` / **`ecapture`** | `ecapture` needs no CA at all |
| Root-level mobile | `Frida` scripts | `Magisk` + **JingMatrix/Vector** | LSPosed official is stalled since 2023-10 |
| APK analysis | Online decompilers | `jadx` / `apktool` + `dex2jar` | Local, scriptable, batchable |
| Packed APK | `jadx` (gives you the shell) | **`frida-dexdump`** | Dumps decrypted DEX at runtime |
| Dalvik/ART runtime | `dex2jar` + `jd-gui` | `GDA` / `JEB` | Direct Dalvik analysis |
| Binary analysis | `strings` / `grep` | `Ghidra` / `radare2` / `IDA Pro` | Disassembly + decompilation |
| Windows PE | `CFF Explorer` | `x64dbg` / `dnSpy` / `ILSpy` | Dynamic debugging + .NET analysis |
| macOS/iOS binary | `otool` / `nm` | `Hopper` / `Ghidra` + `frida-ios-dump` | ARM64 analysis + decryption |
| **WASM** | `wasm2wat` | `wasm2c` + `-O3` → Ghidra, or `wasm2js` | `wasm-decompile` is **removed** — see below |
| WASM dynamic | — | **`Wasabi`** / **`Cetus`** | Bytecode instrumentation / memory watchpoints |

## JS Deobfuscation: Manual → Automated

| Approach | Basic tool | Advanced replacement | Why upgrade |
|---|---|---|---|
| Identify obfuscator | Guesswork | **`obfuscation-detector`** | AST-based classifier; tells you which tool to use |
| Formatting | `prettier` | `js-beautify` | Marginally better for some patterns |
| All-round deobfuscation | Manual | **`webcrack`** | Deobfuscate + unminify + webpack unpack |
| obfuscator.io specific | Manual | **`obfuscator-io-deobfuscator`** | Handles **control-flow flattening**; does not execute untrusted code |
| String decoding | Regex | **`synchrony`** / **`REstringer`** | Zero-config string array resolution |
| Self-defending removal | Manual | `js-deobfuscator` | Also removes anti-debug |
| Custom transforms | Manual | Babel AST (`@babel/parser` + `traverse`) | Full control |
| **JSVMP** | — | **None exists** | obfuscator.io states this explicitly — instrument manually |

## Fingerprint Evasion: Naive → Surgical

| Approach | Basic tool | Advanced replacement | Why upgrade |
|---|---|---|---|
| User-Agent rotation | Hardcoded list | `fake-useragent` / `user-agents` | Real-world UA distribution |
| Fingerprint generation | Manual | `fingerprint-suite` | Consistent canvas/webgl/audio |
| Profile management | Fresh profile each time | Persistent context (`launch_persistent_context`) | Matches real user behavior |
| Hardware spoofing | None | `Camoufox` / custom CDP commands | Believable GPU/CPU/memory hints |
| **Verifying your fingerprint** | Trust it | **`scripts/fingerprint_probe.py`** | Compare against a real browser before writing bypass code |

## Data Extraction: Brittle → Robust

| Approach | Basic tool | Robust replacement | Why upgrade |
|---|---|---|---|
| CSS parsing | `BeautifulSoup` | `selectolax` / `lxml` | 10-100x faster, less memory |
| XPath | Manual | `parsel` (Scrapy) | Built-in selector fallback |
| JSON extraction | `json` module | `jmespath` / `jsonpath-ng` | Query language for nested data |
| Schema validation | Manual asserts | `pydantic` / `cerberus` / `voluptuous` | Type-safe + auto-docs |
| HTML to structured | Regex | `Readability-lxml` / `trafilatura` | Article/content extraction |
| LLM extraction | Raw prompts | `instructor` / `marvin` / `outlines` | Structured output from LLMs |

## Protocol Analysis: Guessing → Instrumentation

| Approach | Basic tool | Advanced replacement | Why upgrade |
|---|---|---|---|
| HTTP inspection | Browser DevTools | `mitmproxy` + custom scripts | Programmable interception |
| WebSocket | DevTools Network | `wscat` / `websocat` / `mitmproxy` | CLI testing + proxy inspection |
| gRPC | Browser + guesswork | **`grpcurl`** (try reflection first!) | May enumerate the whole API surface |
| Protobuf reverse | Manual hex reading | `protoc --decode_raw` / **`blackboxprotobuf`** | Decode **and re-encode** unknown protobuf |
| Binary protocol | `hexdump` / `xxd` | `ImHex` / `010 Editor` / **`Kaitai Struct`** | Structured binary templates |
| Protocol grammar | Manual inference | `Netzob` / `FieldHunter` | Automatic grammar inference |
| Network scanning | `nmap` | `masscan` / `rustscan` | 1000x faster for large ranges |
| Service discovery | `nmap` scripts | `zmap` + `zgrab` | Internet-scale scanning |
| **TLS plaintext** | mitmproxy (needs CA) | **`ecapture`** (eBPF uprobe) | No CA, no client modification |

## Fingerprint Analysis

| Approach | Basic tool | Advanced replacement | Why upgrade |
|---|---|---|---|
| TLS fingerprint | `ja3` | **JA4** | JA3 is order-sensitive and broken by Chrome 109+ randomization |
| HTTP/2 fingerprint | — | **Akamai H2 fingerprint** | Pseudo-header order is a strong discriminator |
| QUIC fingerprint | — | qlog + custom analysis | Emerging detection layer |
| Verification endpoint | — | `tls.peet.ws` / `tls.browserleaks.com` | Compare your client against a real browser |

## Dead / Archived Tools (do not build on these)

| Tool | Status | Replacement |
|---|---|---|
| **undetected-chromedriver** | Last release 2024-02-17 (PyPI 3.5.5) | Patchright / Camoufox / nodriver |
| **`salesforce/ja3`** | Archived 2025-05-01 | JA4 / `ja4` reference implementation |
| **`de4js`** | Archived (v1.12.0) | webcrack / obfuscator-io-deobfuscator |
| **`rarecoil/unwebpack-sourcemap`** | Archived | Forks (`An-GG/`, `1qr4h/`) or reimplement |
| **`crypto-js`** | Officially discontinued | Web Crypto API, or pin a known version |
| **`wasm-decompile`** | **Removed from WABT 2026-06-22** (PR #2769) | `wasm2c` + `-O3` → native decompiler; or `wasm2js` |
| **LSPosed official** | Stalled at v1.9.2 (2023-10-11) | `JingMatrix/Vector` |
| **`ptswarm/reFlutter`** | Archived | `Impact-I/reFlutter` |
| **`rovo89/Xposed`** | Archived | LSPosed (JingMatrix/Vector) |
| **`PortSwigger/protobuf-decoder`** | Last update 2021 | `blackboxprotobuf` |
| **Ghidra WASM support** | Never existed natively; upstream plugin stale 3 years | `nneonneo/ghidra-wasm-plugin` |

## Language Ecosystem Migration

| From | To | When it makes sense |
|---|---|---|
| Python scripts | Go binaries | Deploy to edge/IoT, single binary, faster |
| Python frameworks | Rust services | Memory-critical, 10x throughput needed |
| Node.js | Bun | Faster startup, compatible API |
| Selenium | Playwright | Modern web, auto-wait, better traces |
| Playwright | `nodriver` / `Rod` | Headless-only, no browser binary bloat |
| Scrapy | `Colly` (Go) | CPU-bound crawling, cross-compile deploy |
| BeautifulSoup | `selectolax` (C-backed) | 50-100x parse speed improvement |

## Decision Heuristic

When choosing a replacement, ask:
1. Is the current tool failing on **detection** or **performance**?
2. Does the replacement integrate with your existing stack?
3. Is the learning curve worth the success rate gain?
4. Can you A/B test both before committing?
5. **Is the current tool actually still maintained?** Check the last release date before investing in a workaround.

Do not upgrade everything at once. Replace the bottleneck first.

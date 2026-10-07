# Language Ecosystems

The rest of this skill is Python-heavy because that is where most of the tooling lives.
That is a fact about the ecosystem, not a requirement about you. This document maps the
equivalents per language so you can work in the stack you actually deploy.

**Read this first**: the "TLS impersonation" column is the one that decides whether a
language is viable for a given target. Most languages have HTTP clients. Very few have a
client that can reproduce a browser's ClientHello. If your target fingerprints TLS, the
language choice is effectively made for you.

---

## 1. Capability matrix: which languages can actually impersonate a browser

| Language | HTTP client with browser TLS | Browser automation | Notes |
|---|---|---|---|
| **Python** | **Yes** — `curl_cffi` | Yes — full ecosystem | Richest ecosystem by a wide margin |
| **Node.js** | **Yes** — `impit`, `got-scraping` (partial) | Yes — Playwright, Puppeteer | Strong; JS runtime is native |
| **Go** | **Yes (low-level)** — `utls` + your own HTTP stack; `bogdanfinn/tls-client` | Yes — `chromedp`, `playwright-go` | `utls` controls the ClientHello only; you assemble the rest |
| **Rust** | **Yes** — `wreq` | Yes — `chromiumoxide`, `fantoccini` | `wreq` is the only mature Rust option — see the note below |
| **C / C++** | **Yes** — `lexiforest/curl-impersonate` | Via CEF, or shell out | You are writing infrastructure, not scripts |
| **Java / Kotlin** | **Community-grade** — `zhkl0228:impersonator` | Yes — Playwright Java, Selenium, HtmlUnit | Does JA3/JA4 + HTTP/2 + HTTP/3 emulation; production reliability unverified |
| **C# / .NET** | **Immature** — `Loxifi.CurlImpersonate`, `CurlImpersonate` | Yes — Playwright .NET, PuppeteerSharp | Small projects; treat as experimental |
| **PHP** | **Immature** — small projects only | Via headless Chrome wrappers | Not a serious option for TLS-sensitive targets |
| **Ruby** | **Immature** — `ruby-curl-impersonate` (0 stars, no release) | Yes — Capybara, Ferrum (CDP) | Ferrum is CDP-direct and reasonable for the non-TLS case |
| **Swift** | **No option exists** | WebKit automation, WebDriverAgent, idb | Search for Swift TLS-impersonation work returns nothing; there is also no maintained Swift SM2/SM3/SM4 library |
| **Elixir / Erlang** | **No** — use a sidecar | Via external process | Concurrency strengths, small RE ecosystem |
| **Lua** | **No** — use a sidecar | No | Relevant for WAF rule authoring (OpenResty) and game scripting, not clients |

The practical summary: **if the target fingerprints TLS, the mature choices are Python,
Node, Go, Rust, or C.** JVM has a community-grade option. Everything else means running a
browser or a sidecar.

### Four corrections that trip people up

1. **`rquest` is dead.** Every version on crates.io is **yanked** (last: 5.2.0,
   2025-07-11). Do not start new Rust work on it — use `wreq`.
2. **There is no `rustls-tls` crate.** crates.io search hits are dependency names, not a
   package. Rust fingerprint emulation lives in `wreq` (a hard fork of `reqwest`) and
   `impit` (a patched rustls + h2 requiring `[patch.crates-io]` and
   `--cfg reqwest_unstable`).
3. **`curl-impersonate` moved.** The original `lwthiker/curl-impersonate` stopped at
   v0.6.1 (2024-03-02). Active maintenance is at **`lexiforest/curl-impersonate`**
   (v2.2.3, 2026-09), which is merged into curl 8.22.0 and ships HTTP/3 plus prebuilt
   Android/iOS/Windows/LoongArch/RISC-V binaries.
4. **JVM is not "no option".** `com.github.zhkl0228:impersonator` (1.10.2, Maven Central
   2026-09) performs JA3/JA4 + HTTP/2 + HTTP/3 emulation. It is a small project (double-
   digit GitHub stars), so the honest classification is *community-grade, production
   reliability unverified* — not *impossible*.
5. **HtmlUnit has a groupId trap.** `org.htmlunit:htmlunit` is the current line (5.5.0,
   2026-08); the legacy `net.sourceforge.htmlunit:htmlunit` is frozen at 2.70.0
   (2023-01). Both still resolve, so you can silently pull the ancient one.

---

## 2. Python

The default choice for RE work, and the one with the most complete tooling.

### HTTP clients

| Package | Registry | What it does | Status / notes |
|---|---|---|---|
| **curl_cffi** | PyPI | Browser-like TLS/JA3/JA4/HTTP2 impersonation | The baseline. See [`http-clients.md`](http-clients.md) for the UA/OS trap. |
| **primp** | PyPI | Rust-backed HTTP client with browser impersonation | Fast, from the same lineage as the Rust `rquest` |
| **rnet** | PyPI (`--pre`) | Fine-grained TLS/HTTP2 fingerprint control | **Treat with caution** — the GitHub repo API returns 404 and there has been no release in over a year |
| **python-tls-client** | PyPI | Go binding to `bogdanfinn/tls-client` | **Use this, not `tls-client`** — the `tls-client` PyPI package stopped at 1.0.1 (2024-02) |
| **hrequests** | PyPI | High-level requests-like API with browser transport | **Discontinued** — last release 0.9.2 (2024-12) |
| **httpx** | PyPI | Modern async HTTP client | 0.28.1 has been current since 2024-12; stable and fine, just note the slow release cadence |
| **requests** | PyPI | The classic | Easy to detect on protected targets |

### Browser automation

| Package | Status | Notes |
|---|---|---|
| **Playwright** | Active | The baseline. Leaks `Runtime.enable`; see patching below. |
| **Patchright** | **Active** | Patched Playwright fork. Patches the CDP-leak classes. Current Chrome bundled. |
| **rebrowser-playwright** | **Effectively unmaintained** | Last real code commit **September 2024**; the 2025-05 `pushed_at` is a metadata-only touch. Bundled Chromium 136. No LICENSE file. Do not start new work on it. |
| **nodriver** | Active | Successor to undetected-chromedriver, same author. Drives system Chrome over a **direct CDP WebSocket** — no Playwright shim, no `Runtime.enable` sequence. |
| **undetected-chromedriver** | **Dead** | Last PyPI release 3.5.5, **2024-02-17**. Superseded by nodriver. |
| **Camoufox** | Active | Firefox with fingerprint spoofing in the **C++ engine layer** rather than JS overrides. Slowest, strongest on hard fingerprinting targets. |
| **SeleniumBase (UC mode)** | Active | Good for Cloudflare/CAPTCHA interstitials |
| **DrissionPage** | Active | Pure Python, CDP-direct, no Node dependency, no driver binary. `ChromiumPage` (CDP) + `SessionPage` (HTTP) with `WebPage` switching between them. Stealth comes from **not adding automation markers**, not from spoofing — it does not spoof TLS, canvas, or WebGL. |

**The honest state of stealth browsers**: every open-source tool leaks eventually and
needs re-patching after each browser release. Choosing one is choosing a maintenance
burden. Pick by success rate and maintenance activity, not by knob count.

### Parsing and extraction

| Package | Use |
|---|---|
| **selectolax** | Fastest HTML parser (Lexbor/Modest backends) |
| **lxml** | XPath, robust, widely used |
| **parsel** | Scrapy's selector layer; XPath + CSS on lxml |
| **BeautifulSoup** | Lenient, good for malformed HTML; slow |
| **js2py / quickjs / py_mini_racer** | Execute JS from Python when needed |

### Cryptography (including Chinese national standards)

| Package | Notes |
|---|---|
| **pycryptodome** | The general-purpose crypto library |
| **cryptography** | Modern, well-maintained; OpenSSL-backed |
| **gmssl-python** | ctypes binding to the GmSSL C library. SM2/SM3/SM4/SM9/ZUC. **Requires GmSSL installed first** — it calls `libgmssl.so` via ctypes, it is not pure Python. |
| **gmssl** (pure Python) | The older pure-Python SM implementation. Different package, often confused with the above. |
| **snowland-smx** | Pure-Python SM2/SM3/SM4/SM9 |

**Two naming traps here, and both are common:**

1. `gmssl` and `gmssl-python` are different packages with the same import name (`gmssl`).
   The ctypes one needs the native library; the pure-Python one does not. Check which you
   have before debugging a load error.
2. **`pip install pysmx` does not install a 国密 library.** The PyPI package `pysmx` is a
   **SourceMod plugin tool** ("Interact with SourceMod plug-ins"). The library people mean
   when they say "pysmx" is published as **`snowland-smx`** — its *import* name happens to
   be `pysmx` (`from pysmx.SM2 import ...`), which is where the confusion comes from. Any
   document telling you to `pip install pysmx` for SM2/SM3/SM4 is wrong.

### Others

| Package | Use |
|---|---|
| **mitmproxy** | Intercepting proxy with Python scripting — the core RE tool |
| **Frida (frida, frida-tools)** | Dynamic instrumentation |
| **Scrapy** | Large-scale crawling framework |
| **Crawlee (Python)** | Alternative crawling framework |
| **psutil, pywin32** | Process/system introspection on Windows |

---

## 3. JavaScript / TypeScript (Node.js)

The advantage here is that you already have a JS engine — running vendor JS requires no
bridging.

| Package | Registry | What it does |
|---|---|---|
| **impit** | npm | Browser-impersonating HTTP client (Rust-backed) |
| **got-scraping** | npm | HTTP client with browser-like header generation |
| **crawlee** | npm | Crawling framework with automatic retry/queue/rotation |
| **playwright** | npm | Browser automation |
| **patchright** | npm | Patched Playwright fork |
| **puppeteer / puppeteer-core** | npm | CDP automation |
| **puppeteer-extra + plugin-stealth** | npm | Older stealth approach; largely superseded by patched forks |
| **rebrowser-puppeteer** | npm | Puppeteer with rebrowser patches applied (maintained, unlike the Playwright variant) |
| **cheerio** | npm | jQuery-like HTML parsing |
| **jsdom** | npm | Full DOM implementation in Node |
| **tough-cookie** | npm | Cookie jar |
| **node-forge** | npm | Pure-JS crypto |
| **sm-crypto** | npm | SM2/SM3/SM4 in JS |
| **protobufjs** | npm | protobuf without codegen — useful for RE |
| **ws** | npm | WebSocket client |
| **@electron/asar** | npm | Electron archive extraction (the old `asar` is deprecated) |

**Deno / Bun**: both run most npm packages. Bun's native HTTP stack is faster but is its
own fingerprint; Deno's permission model is useful for running untrusted vendor JS. For
RE work, the deciding factor is usually which ecosystem has the impersonation library you
need — currently Node.

---

## 4. Go

Go is the right choice when you need a single static binary and high concurrency. The
tradeoff: `utls` gives you ClientHello control but not a full HTTP client, so you assemble
the stack.

| Package | Registry | What it does |
|---|---|---|
| **utls** (`refraction-networking/utls`) | pkg.go.dev | Fork of `crypto/tls` providing ClientHello control. **Handshake is still performed by `crypto/tls`** — this library only changes the ClientHello. BSD-3-Clause. Active (roughly quarterly tagged releases). |
| **bogdanfinn/tls-client** | GitHub / pkg.go.dev | Full HTTP client with impersonation profiles. What the Python binding wraps. |
| **req** (`imroc/req`) | pkg.go.dev | Ergonomic HTTP client with middleware |
| **fasthttp** | pkg.go.dev | High-performance HTTP; not net/http compatible |
| **chromedp** | pkg.go.dev | CDP browser automation — **prefer this**; see the `go-rod` note below |
| **playwright-go** | pkg.go.dev | Playwright bindings for Go |
| **go-rod** | pkg.go.dev | CDP browser automation — **no release in over two years**; use `chromedp` or `playwright-go` for new work |
| **colly** | pkg.go.dev | Crawling framework |
| **goquery** | pkg.go.dev | jQuery-like HTML parsing |
| **gorilla/websocket** | pkg.go.dev | WebSocket |
| **emmansun/gmsm** | pkg.go.dev | SM2/SM3/SM4 — **use this**; `tjfoc/gmsm` last released in 2021 |
| **google.golang.org/protobuf** | pkg.go.dev | protobuf |

**WASM runtime bindings in Go**: both `wasmerio/wasmer-go` and
`bytecodealliance/wasmtime-go` have been without a release since 2021–2022. For current Go
work, **Wazero** (pure Go, no CGo) is the maintained path — it is what the `QJS` JavaScript
runtime uses.

**`utls` details worth knowing**:

- `HelloRandomized` gives you a randomized ClientHello — good against blacklists because
  there is no single fingerprint to block. The README notes a small chance a generated
  fingerprint will not work; `utls.Roller` automatically reuses a working one.
- **`Fingerprinter.FingerprintClientHello()`** takes raw captured ClientHello bytes
  (including the TLS record header) and produces a `ClientHelloSpec` you can apply with
  `ApplyPreset()`. This is the workflow for cloning a specific browser.
- The README explicitly recommends using **multiple fingerprints, including randomized
  ones**, rather than relying on a single one.
- **Embeddable JS**: `goja` is a pure-Go ES5.1+ engine (no CGo). `dop251/goja` is the
  mainstream choice. A pure-Go QuickJS port exists (transpiled from C, ~4x slower than
  the C original in some microbenchmarks but competitive with goja), and `QJS` runs
  QuickJS compiled to WASM under Wazero for a CGo-free ES2023 environment.

**Go binary RE note**: `go version -m ./binary` reports the Go version and every module
dependency with versions. This is often enough to identify a known CVE without any
disassembly. See [`software-reverse-engineering.md`](software-reverse-engineering.md).

---

## 5. Rust

Rust has become a genuine option for this work, primarily because of `wreq`.

| Crate | Registry | What it does | Status |
|---|---|---|---|
| **wreq** | crates.io | **Hard fork of `reqwest`** adding precise TLS + HTTP/2 fingerprint control. Fine-grained control over TLS extensions and HTTP/2 settings rather than string-based fingerprint matching. Companion `wreq-util` crate holds browser emulation templates. | **Active — the only mature option.** Maintained by the author of `reqwest-impersonate` (`0x676e67`). |
| **rquest** | crates.io | Earlier impersonating client from the same lineage | **Dead — every version is yanked** (last 5.2.0, 2025-07-11). Do not use. |
| **impit** | crates.io | Patched rustls + h2 for browser emulation | Active, but requires `[patch.crates-io]` and `--cfg reqwest_unstable` |
| **reqwest** | crates.io | The standard Rust HTTP client | Active |
| **chromiumoxide** | crates.io | Async CDP browser automation | Active |
| **fantoccini** | crates.io | WebDriver client | Active |
| **thirtyfour** | crates.io | Alternative WebDriver client | Active |
| **scraper** | crates.io | HTML parsing (html5ever) | Active |
| **select** | crates.io | CSS selector extraction on scraper | Active |
| **rustls** | crates.io | Modern TLS implementation | Active |
| **boring** | crates.io | BoringSSL bindings — low-level TLS control | Active |
| **rquickjs** | crates.io | High-level QuickJS bindings; ES2020+, async bridging to Rust | Active |
| **tokio-tungstenite** | crates.io | WebSocket | Active |
| **sm2 / sm3 / sm4** | crates.io | 国密 algorithms (RustCrypto) | Active |

**There is no `rustls-tls` crate.** A crates.io search returns dependency names, not a
package. If you see it referenced as a Rust fingerprinting library, that is a
misreading — the actual mechanisms are `wreq` (fork) and `impit` (patched rustls + h2).

**Why `wreq` matters**: it explains its own design decision, and the reasoning is
correct — browser fingerprints like JA3, JA4, and Akamai cannot be reliably emulated with
simple fingerprint strings. Instead of parsing and replaying a string, `wreq` gives you
direct control over the TLS and HTTP/2 extension parameters so you produce the fingerprint
by construction. Note also its observation that most browser device models share identical
TLS and HTTP/2 configurations and differ only in the User-Agent.

**Embeddable JS in Rust**: `rquickjs` is the mature option (QuickJS-NG under the hood).
Also `boa` (pure Rust, ES2025 nearly complete) and `deno_core` (V8 bindings, heavy).

**Rust binary RE note**: symbols are mangled — use `rustfilt` to demangle. Panic strings
survive stripping and identify a binary as Rust; the `rustc` version is often
fingerprintable from panic formats.

---

## 6. Java / Kotlin

The JVM is a strong platform for *analysing* Java, and a **community-grade** one for
*impersonating a browser*.

**The constraint, stated accurately**: `OkHttp` and `Apache HttpClient` send Java TLS
fingerprints. There **is** a third-party option for ClientHello shaping —
`com.github.zhkl0228:impersonator` (1.10.2, Maven Central 2026-09), which does JA3/JA4 plus
HTTP/2 and HTTP/3 emulation. It is a small project (double-digit GitHub stars), so treat
it as **community-grade with unverified production reliability**, not as equivalent to
`curl_cffi`. If you need production reliability, plan for a real browser or a sidecar
(call a Go/Rust binary or a Python service); building a custom `SSLEngine` is a
significant project of its own.

| Library | Registry | Use |
|---|---|---|
| **Jsoup** | Maven | HTML parsing (the standard) |
| **HtmlUnit** | Maven | Headless browser in pure Java; useful, but its fingerprint is distinctive. **GroupId trap**: `org.htmlunit:htmlunit` is the current line (5.5.0, 2026-08); the legacy `net.sourceforge.htmlunit:htmlunit` is frozen at 2.70.0 (2023-01). Both still resolve. |
| **impersonator** | Maven (`com.github.zhkl0228`) | JA3/JA4 + HTTP/2 + HTTP/3 impersonation. Community-grade. |
| **Selenium** | Maven | Browser automation |
| **Playwright (Java)** | Maven | Browser automation with the Playwright API |
| **OkHttp** | Maven | HTTP client |
| **Apache HttpClient** | Maven | HTTP client |
| **BouncyCastle (bcprov, bcpkix)** | Maven | Crypto. **1.86 confirmed to include `SM2Engine`, `SM3Digest`, `SM4Engine`, `SM9Engine`, `SM2Signer`**, plus JCA registration for SM3/SM4 — a genuinely complete 国密 implementation. |
| **Netty** | Maven | Async networking; if you must build a custom TLS stack, this is the base |
| **CFR / Vineflower / Procyon** | JAR | Java decompilers — see [`software-reverse-engineering.md`](software-reverse-engineering.md) |
| **Recaf** | JAR | Interactive bytecode editor |
| **jadx** | JAR | Android/DEX decompiler |

For JVM-based *analysis* work (decompiling JARs, understanding Android apps), Java is
excellent. For JVM-based *client* work against a TLS-fingerprinting target, budget for
either the community library or a sidecar.

---

## 7. C# / .NET

Same constraint as the JVM: no mature ClientHello-shaping client.

| Library | Registry | Use |
|---|---|---|
| **HtmlAgilityPack** | NuGet | HTML parsing |
| **AngleSharp** | NuGet | Spec-compliant HTML/CSS/DOM |
| **Playwright (.NET)** | NuGet | Browser automation |
| **PuppeteerSharp** | NuGet | CDP automation |
| **HttpClient** | Built-in | HTTP |
| **BouncyCastle.Cryptography** | NuGet | Crypto. **bc-csharp 2.7.0 confirmed to include `SM2Engine`, `SM3Digest`, `SM4Engine`, `SM9Engine`, `SM2Signer`** — the 国密 story on .NET is complete. |
| **Loxifi.CurlImpersonate** / **CurlImpersonate** | NuGet | TLS impersonation wrappers — **small, experimental projects**. Treat as proof-of-concept, not infrastructure. |
| **dnSpyEx** | GitHub | .NET decompiler/debugger/editor — the primary .NET RE tool |
| **ILSpy** | GitHub | .NET decompiler |
| **de4dot / de4dot-cex** | GitHub | Obfuscator removal |
| **dnlib** | NuGet | IL manipulation library |

**RE note**: .NET is the easiest major runtime to reverse, which makes it the *easiest*
target and the *worst* choice for protecting your own logic. If you are on the defensive
side, that is the relevant fact. And remember **NativeAOT** breaks the traditional
toolchain entirely — see [`software-reverse-engineering.md`](software-reverse-engineering.md).

**TLS impersonation on .NET is genuinely immature.** Unlike the JVM, there is not even a
community-grade single library to point at — only small wrappers around curl-impersonate.
If your target fingerprints TLS, budget for a sidecar.

---

## 8. C / C++

You write infrastructure here, not scripts. The payoff is total control.

| Library | Use |
|---|---|
| **curl-impersonate** | **The reference implementation.** A curl build that reproduces browser TLS/HTTP2 fingerprints. Most higher-level impersonation libraries are ported from or inspired by its profile data. **Use `lexiforest/curl-impersonate`** — the original `lwthiker` repo stopped at v0.6.1 (2024-03-02). The maintained fork is v2.2.3 (2026-09), merged into curl 8.22.0, and ships HTTP/3 plus prebuilt Android/iOS/Windows/LoongArch/RISC-V binaries. |
| **libcurl** | The base HTTP library |
| **OpenSSL / BoringSSL** | TLS; BoringSSL is what Chrome uses, so its fingerprints are authentic |
| **mbedTLS** | Embedded-friendly TLS |
| **libwebsockets** | WebSocket |
| **libpcap** | Packet capture |
| **Capstone** | Disassembly framework (used by many RE tools) |
| **Unicorn** | CPU emulation |
| **Zydis** | x86/x64 disassembler |

Where C/C++ wins: embedded targets, firmware, custom protocol clients, and anything where
you need to control the wire at byte level. Where it loses: development speed, memory
safety, and ecosystem.

**curl-impersonate is the origin of the profile data** that `curl_cffi`, `primp`, and
others consume. When a Python library's impersonation breaks on a new browser version,
the fix usually originates upstream in the profile definitions — which is why knowing
*which fork* is maintained matters.

---

## 9. Embeddable JavaScript engines

Needed when your language is not JS but the target's logic is. Choose by ES version
support and performance.

| Engine | Language | ES support | Notes |
|---|---|---|---|
| **V8** | C++, bindings everywhere | Full, current | Heaviest; what Node/Chrome use. `deno_core` wraps it for Rust. |
| **QuickJS** | C | ES2023 | Small, fast to embed, good spec coverage. The common choice. |
| **QuickJS-NG** | C | ES2023 | Actively maintained fork; what `rquickjs` and `wasm-rquickjs` build on |
| **goja** | Pure Go | ES5.1 + much of ES6+ | No CGo. 13.2 MB, slower than QuickJS but zero dependencies. |
| **dop251/goja** | Pure Go | Same | The mainstream Go option |
| **pure-Go QuickJS port** | Pure Go | ES2023 | Transpiled from C to Go; ~4x slower than C QuickJS in some microbenchmarks |
| **QJS (Wazero)** | Go + WASM | ES2023 | QuickJS compiled to WASM, run under Wazero. CGo-free, sandboxed with filesystem/network isolation by default, configurable memory/time limits. |
| **rquickjs** | Rust | ES2020+ | High-level QuickJS bindings, native async↔Promise bridging |
| **Boa** | Pure Rust | Nearly complete ES2025 | No C dependency |
| **Duktape** | C | ES5.1 | Tiny footprint; old but very portable |
| **mujs** | C | ES5 | Smallest; very limited |
| **Jint** | C# | ES2020+ | The .NET option |
| **Hermes** | C++ | ES6-ish | React Native's engine; bytecode is a RE target (see `hbctool`, version-limited to HBC 59/62/74/76) |

**For 补环境 (environment simulation) work**, QuickJS is usually the right choice: small,
ES2023-complete, easy to embed, and its global object is straightforward to shape. V8 is
heavier but is what the target actually runs, so behavioural differences are smaller.

**Performance caveat**: for proof-of-work challenges, do the work in your host language
(native code), not in the embedded JS engine. The difference is roughly two orders of
magnitude. See [`frontier-anti-bot-2026.md`](frontier-anti-bot-2026.md).

---

## 10. WASM runtimes

Relevant both for analysing WASM targets and for sandboxing untrusted code.

| Runtime | Language | Notes |
|---|---|---|
| **wasmtime** | Rust | Bytecode Alliance reference runtime. Standalone, WASI + Component Model. |
| **wasmer** | Rust | Alternative with multiple backends |
| **wasm3** | C | Interpreter, very small, good for embedded |
| **Wazero** | Go | Pure Go, no CGo. What QJS uses. |
| **wasm2c (WABT)** | C output | Transpile to C then compile with a real C compiler — often faster than a dedicated runtime, and gives you readable C |
| **Node's built-in WebAssembly** | JS | Fine for testing |

**WABT note**: `wasm-decompile` was **removed from WABT on 2026-06-22** (PR #2769, 1.0.42).
Pin WABT ≤1.0.41 if you depend on it. See [`wasm-reverse-engineering.md`](wasm-reverse-engineering.md).

---

## 11. Ruby, PHP, and others

Covered briefly because they come up but are rarely the right answer.

**Ruby**: `Ferrum` (CDP-direct, reasonable), `Capybara` + a driver, `Nokogiri` (HTML),
`Mechanize`. TLS impersonation is effectively absent — `ruby-curl-impersonate` has zero
stars and no release. Use it if your team lives in Ruby and your target does not
fingerprint TLS.

**PHP**: `Guzzle` for HTTP, various headless-Chrome wrappers. TLS impersonation is limited
to small projects. The 国密 story is better than the impersonation story: **`pohoc/crypto-sm`**
(pure PHP) and **`appla/php-ext-gmsm`** (a PHP 8.3+ C extension built on OpenSSL) both
exist and are maintained.

**Swift**: **there is a hard gap here.** A search for Swift TLS-fingerprint impersonation
work returns nothing, and there is **no maintained Swift 国密 library** (SM2/SM3/SM4
appears only as 2018-era personal demos). Swift is usable for Apple-platform automation
(WebDriverAgent, `idb`) and for WASM (`swiftwasm/WasmKit`) — not as a client language for a
TLS-fingerprinting target.

**Elixir / Erlang**: excellent concurrency, small RE ecosystem. Shell out to a Python or
Go sidecar for the actual work.

**Lua**: not a client language. Relevant for **OpenResty/nginx WAF rule authoring** (the
defensive side — see [`waf-bypass-techniques.md`](waf-bypass-techniques.md)) and for game
scripting. Note that LuaRocks has no stable JSON API, so version checks go through
`luarocks.org/manifests/<author>/manifest` or GitHub tags. One practical gotcha if you use
`lua-resty-http`: **from v0.18.0, `POST`/`PUT`/`PATCH` with no body require an explicit
`body = ""`.**

---

## 12. Choosing

```text
Does the target fingerprint TLS or HTTP/2?
  |
  +-- YES, and I need to pass it
  |     -> Python (curl_cffi/primp)  -- fastest path, best tooling
  |     -> Node (impit)              -- if you need JS natively
  |     -> Go (utls / tls-client)    -- if you need a static binary or concurrency
  |     -> Rust (wreq)               -- if you need fine-grained control
  |     -> C (lexiforest/curl-impersonate) -- if you need to build the infrastructure
  |     -> JVM (impersonator)        -- community-grade; verify before production
  |     -> .NET / PHP / Ruby / Swift -- run a browser, or call a sidecar
  |
  +-- NO
        -> Any language with a decent HTTP client and parser.
           Pick by team familiarity, not by this document.
```

**Maturity summary**, so you can set expectations honestly:

| Tier | Languages |
|---|---|
| **Mature** | Python (`curl_cffi`), Node (`impit`), Go (`bogdanfinn/tls-client` + `utls`), Rust (`wreq`), C (`lexiforest/curl-impersonate`) |
| **Community-grade** | JVM (`zhkl0228:impersonator`) |
| **Immature / experimental** | .NET, PHP, Ruby |
| **Blank** | Swift |
| **None — sidecar required** | Elixir/Erlang, Lua |

Two secondary questions that often decide it:

1. **Do you need to execute the target's JavaScript?** If yes, JS-native (Node) or an
   embeddable engine (QuickJS, goja, rquickjs) is a large advantage. Running vendor JS in
   a QuickJS context is the core of 补环境 work — see
   [`environment-simulation-jsvmp.md`](environment-simulation-jsvmp.md).
2. **Is this a one-off or a production system?** For a one-off, use whatever you know. For
   production, the maintenance burden of an impersonation client is real and version-
   sensitive — pin your dependencies (see SKILL.md operating principle 10).

---

## 13. Relationship to other documents

- Client selection and the curl_cffi UA/OS trap: [`http-clients.md`](http-clients.md)
- Fingerprint mechanics: [`tls-http-fingerprinting.md`](tls-http-fingerprinting.md),
  [`traffic-camouflage.md`](traffic-camouflage.md)
- Environment simulation: [`environment-simulation-jsvmp.md`](environment-simulation-jsvmp.md)
- Binary RE tooling per platform: [`software-reverse-engineering.md`](software-reverse-engineering.md)
- Chinese national crypto standards: [`signature-parameter-re.md`](signature-parameter-re.md)

---

## 中文摘要

**先说结论**：这个技能文档以 Python 为主，是因为生态确实在 Python，不是因为你必须用 Python。但有一个约束会替你决定语言：**如果目标对 TLS 做指纹识别，成熟选择只有 Python / Node / Go / Rust / C**；JVM 有社区级方案；其他语言只能跑浏览器或挂 sidecar。

**成熟度分层（按实际 registry 状态核对）**：
- **成熟**：Python（`curl_cffi`）/ Node（`impit`）/ Go（`bogdanfinn/tls-client` + `utls`）/ Rust（`wreq`）/ C（`lexiforest/curl-impersonate`）
- **社区级**：JVM（`com.github.zhkl0228:impersonator` 1.10.2，做 JA3/JA4 + HTTP/2 + HTTP/3，但项目很小，生产可靠性**未核实**）
- **极不成熟**：.NET（只有 curl-impersonate 的小型包装）/ PHP / Ruby（`ruby-curl-impersonate` 零 star 无 release）
- **完全空白**：**Swift**——搜 Swift TLS 指纹仿真返回 0 结果，且**无维护中的 Swift 国密库**（SM2/SM3/SM4 只有 2018 年个人 Demo）
- **必须 sidecar**：Elixir/Erlang、Lua

**五条必须纠正的常见错误**：
1. **`rquest` 已死**——crates.io 上**所有版本均已 yank**（最后 5.2.0 / 2025-07-11）。Rust 侧请用 `wreq`。
2. **`rustls-tls` crate 不存在**——crates.io 搜到的只是依赖名，不是包。
3. **`curl-impersonate` 已迁移**——原仓库 `lwthiker` 停在 v0.6.1（2024-03-02），实际维护在 **`lexiforest/curl-impersonate`**（v2.2.3 / 2026-09，已并入 curl 8.22.0，含 HTTP/3 与 Android/iOS/Windows/LoongArch/RISC-V 预编译）。
4. **`pip install pysmx` 装不到国密库**——PyPI 上的 `pysmx` 是 **SourceMod 插件工具**。真正要装的是 **`snowland-smx`**（1.1.0），只是它的 **import 名恰好是 `pysmx`**，混淆由此而来。
5. **HtmlUnit 的 groupId 陷阱**——`org.htmlunit:htmlunit` 是现行线（5.5.0 / 2026-08），`net.sourceforge.htmlunit:htmlunit` 冻结在 2.70.0（2023-01），两者都能解析，可能静默拉到旧版。

**Python 侧的停更清单（带日期）**：`undetected-chromedriver` 3.5.5（2024-02-17，被 nodriver 取代）、`hrequests` 0.9.2（2024-12-01）、PyPI `tls-client` 1.0.1（2024-02-02，替代是 `python-tls-client`）、`rnet`（GitHub 仓库 API 返回 404 且 14 个月无发版）。`go-rod` 已 27 个月无 release，Go 侧改用 `chromedp` / `playwright-go`。Go 的 WASM 绑定 `wasmer-go`（2021）与 `wasmtime-go`（2022）均已停滞，改用 **Wazero**。国密 Go 库用 **`emmansun/gmsm`**，不用 2021 年停更的 `tjfoc/gmsm`。

**国密覆盖（源码级已确认）**：BouncyCastle Java 1.86 与 bc-csharp 2.7.0 均含 `SM2Engine`/`SM3Digest`/`SM4Engine`/`SM9Engine`/`SM2Signer`（bc-java 另有 JCA 注册）；Go 用 `emmansun/gmsm`；Rust 用 RustCrypto 的 `sm2`/`sm3`/`sm4`；PHP 有 `pohoc/crypto-sm`（纯 PHP）与 `appla/php-ext-gmsm`（PHP 8.3+ C 扩展）。

**浏览器自动化的当前状态（重要）**：
- **`undetected-chromedriver` 已死**（2024-02-17），后继者是同作者的 **nodriver**（直连 CDP WebSocket，无 Playwright 垫片、无 `Runtime.enable` 序列）。
- **`rebrowser-playwright` 实质停止维护**（最后 release 1.52.0 / 2025-05-09，最后真实代码提交 2024-09），不要在新项目上用。`rebrowser-puppeteer` 的维护情况好于 Playwright 变体。
- **Patchright** 活跃；**Camoufox** 在 **C++ 引擎层**做指纹伪装而非 JS 覆盖（最慢、对硬指纹目标最强）；**SeleniumBase UC mode** 适合过 Cloudflare/CAPTCHA 插页；**DrissionPage** 纯 Python、直连 CDP，其隐蔽性来自"不加明显的自动化标记"，**并不伪造 TLS/canvas/WebGL**。
- **诚实结论：所有开源隐蔽浏览器最终都会泄漏，每次浏览器发版都需要重新打补丁。**选型就是选维护负担。

**可嵌入 JS 引擎**：QuickJS（C，ES2023，常用选择）、QuickJS-NG（活跃分支，`rquickjs` 与 `wasm-rquickjs` 的基础）、**goja**（纯 Go，无 CGo，比 QuickJS 慢）、QJS（QuickJS 编译为 WASM 跑在 Wazero 上，CGo-free 且默认隔离文件系统与网络）、`rquickjs`（Rust）、Boa（纯 Rust，接近完整 ES2025）、Duktape/mujs（小但老旧）、Jint（.NET）、Hermes（React Native，字节码本身是逆向目标）。

**补环境选型**：QuickJS 通常是正确选择——小、ES2023 完整、易嵌入、全局对象易于塑形。V8 更重但目标实际跑的就是它，行为差异更小。

**性能警告**：工作量证明类挑战要在宿主语言（原生代码）里算，不要在嵌入的 JS 引擎里算——差约两个数量级。

**WASM 运行时**：wasmtime、wasmer、wasm3、Wazero（纯 Go）、**wasm2c（转成 C 再用真实 C 编译器编译，常常比专用运行时更快且产出可读 C）**。**WABT 注意：`wasm-decompile` 已于 2026-06-22 从 WABT 移除**（PR #2769，1.0.42），依赖它的项目需 pin ≤1.0.41。

**选型决策**：目标是否对 TLS 指纹识别？是 → Python（最快路径）/ Node（需要原生 JS）/ Go（需要静态二进制或高并发）/ Rust（需要细粒度控制）/ C（要自己造基础设施）；JVM 可试社区库但需自行验证；.NET/PHP/Ruby/Swift 走 sidecar。否 → 任何有像样 HTTP 客户端与解析器的语言，按团队熟悉度选。两个常见的决定性次问：**是否需要执行目标的 JS**（是则 JS 原生或嵌入引擎优势巨大）与**这是一次性还是生产系统**（生产的指纹客户端维护成本是真实的且对版本敏感，务必 pin 依赖）。

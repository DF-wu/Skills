---
name: web-reverse-engineering
description: "Universal reverse-engineering and anti-bot guide: web scraping, API RE, signed-parameter reversal, environment simulation (bu-huanjing), JS deobfuscation and JSVMP, session mapping, mobile RE (Android/iOS/Flutter/Hermes), mini-programs (wxapkg/TTPKG), protocols (WebSocket/gRPC/QUIC/MQTT/CAN), binary RE (WASM, native, .NET, Go, Rust, Electron, Tauri, PyInstaller, installers, VMProtect/Themida), desktop app RE, game engines (Unity IL2CPP/Unreal/Godot), firmware/embedded/IoT/hardware/automotive RE, document and proprietary formats, traffic camouflage, TLS/HTTP fingerprinting, device fingerprint spoofing, identity separation, anti-bot vendor ID (Cloudflare/Akamai/DataDome/HUMAN/Kasada/Imperva/Anubis) plus Chinese risk control (RiverSecurity/GeeTest/Shumei/Yidun/Dingxiang/Tongdun). Use to understand an undocumented protocol or format, reproduce a client, analyze a binary or firmware, test a bot defense, map an authenticated API, or check the authorization boundaries of such work."
---

# Web Reverse Engineering (Universal)

Reverse engineering across the whole stack: network clients, protocols, JavaScript,
browsers, mobile apps, mini-programs, binaries, firmware, hardware, games, and document
formats. Framework-agnostic, language-agnostic, and jurisdiction-agnostic — the tooling
map covers Python, Node, Go, Rust, JVM, .NET, and C, and the legal section covers US, EU,
and China rather than assuming one.

The focus is practical: choose the minimum-complexity approach that still works, and
escalate through layers only when the layer above fails.

## Compliance and Scope — read this first

This skill is a knowledge base and a set of tooling templates. It is dual-use, and it
says so plainly. **The techniques are neutral; the authorization is not.**

The dividing line is not which tool you use, but whose system you point it at.

**In scope:** authorized penetration testing, bug bounty programs, security research with
coordinated disclosure, incident response and malware analysis, interoperability
engineering, data portability and archival, academic study and CTF, access to your own
accounts and systems, and lawful access to public data at a rate that does not damage the
service.

**Three distinct risk categories, routinely conflated:**

- **Terms of service** — a contract. Breaching one is a civil matter. It is not a crime.
- **Access control circumvention** — this is where criminal law attaches. The line courts
  draw is roughly *gates-up-or-down*: bypassing **authentication** without permission is
  the criminal line. Reading a publicly reachable resource generally is not.
- **Anti-circumvention of technical protection measures** — separate again (US DMCA
  §1201, EU directives). Statutory research exemptions exist and are time-limited.

Operationally: ToS breach ≠ crime. Bypassing a bot challenge ≠ unauthorized access,
*unless* authentication is also being bypassed. Bypassing authentication **is** the line.

**Stop conditions:** you cannot state who authorized this and what the scope is; you are
about to bypass authentication rather than a bot challenge; the target is safety-critical
or medical; the work needs another person's account or data; you are asked to evade
monitoring on a system you do not own; a commercial gate has been returned; legal process
has arrived.

Note that "the site blocks me" is **not** a stop condition. It is a technical fact and a
signal to diagnose which layer is failing.

Full detail — statutory exemptions with expiry dates, dual-use reasoning, machine-readable
preference signals (robots.txt, TDMRep, Content-Signal, ai.txt, llms.txt), commercial
gates, and agent-specific guidance: **[`references/compliance-and-scope.md`](references/compliance-and-scope.md)**.
Case law and jurisdiction thresholds: **[`references/legal-ethical.md`](references/legal-ethical.md)**.

## Operating Principles

1. Start cheap, escalate only when blocked.
2. Keep fingerprints consistent (UA, TLS, locale, timezone, IP geo, TCP stack).
   **An inconsistent identity is worse than a plain one.**
3. Prefer API extraction over DOM scraping whenever possible.
4. Prevention-first anti-bot strategy; CAPTCHA solving is last resort.
5. **Diagnose the layer before choosing a tool.** "The site blocks me" is not a
   diagnosis. Transport fingerprint, browser runtime, behaviour, signed parameter, and
   device fingerprint are different problems with different fixes.
6. **Verify your client before blaming the target.** Run `scripts/fingerprint_probe.py`
   before writing any bypass code.
7. **Identify the vendor before choosing a technique.** Cloudflare's answer is a browser
   that passes Turnstile; Kasada's is a proof-of-work solver; DataDome's is IP reputation;
   Akamai's is TLS coherence. Four different problems. See
   `references/global-anti-bot-vendors.md`.
8. Behind an auth wall? Inject a real (manually-exported) session before re-implementing
   login — and verify the session at its source before assuming a code bug.
9. **A challenge passing is not the API accepting.** Check layer 2 separately.
10. Pin your dependency versions. A client upgrade can silently change your fingerprint.
11. **Identify what the artifact actually is before opening a disassembler.** Most wasted
    hours are spent loading a managed-runtime or installer payload into Ghidra.
12. **Record a real client profile; never hand-tune fingerprint values.** A profile
    captured from a real machine is coherent by construction.

## Fast Decision Tree

```text
Target -> What is required?

 1) Public JSON/API exists?
    -> API reverse engineering flow first (references/api-reverse-engineering.md).

 2) Static HTML, no JS dependency?
    -> requests/httpx (baseline) or curl_cffi/hrequests (if blocked).

 3) JS-rendered site with low bot pressure?
    -> Playwright (or Selenium) + sane pacing.

 4) Bot defenses triggered (Cloudflare/DataDome/Akamai)?
    -> IDENTIFY THE VENDOR FIRST (references/global-anti-bot-vendors.md).
    -> Patchright/nodriver/Camoufox + residential/ISP proxies + behavior model.
    -> Run scripts/fingerprint_probe.py FIRST. Most "blocks" are client misconfig.

 5) Turnstile/hCaptcha/Funcaptcha appears repeatedly?
    -> Fix fingerprint + proxy reputation first, then selective CAPTCHA solving.

 6) Need >100k pages/day reliability?
    -> Scrapy/Crawlee + queue + rotating proxy pool + observability.

 7) Target is a mobile app?
    -> mitmproxy + Frida/objection -> SSL pinning bypass -> API extraction.
    -> Android 14+: APEX-aware CA module. iOS 17.4+/A18: assume no jailbreak.
    -> Flutter? blutter. Hermes? hbctool (version-limited).
    -> See references/mobile-app-reverse-engineering.md.

 8) JS challenge scripts are obfuscated?
    -> Identify the obfuscator FIRST (npx obfuscation-detector), then match the tool.
    -> See references/js-deobfuscation.md.

 9) Protocol is WebSocket/gRPC/custom TCP/QUIC/MQTT?
    -> Traffic capture -> framing analysis -> minimal client reproduction.
    -> gRPC: try server reflection (grpcurl) before reversing anything.
    -> See references/protocol-reverse-engineering-advanced.md.

10) Security logic is in native binary (.so, .exe, .wasm)?
    -> Strings/imports scan -> Ghidra/radare2 -> dynamic hooking -> reimplementation.
    -> WASM: run scripts/wasm_triage.py first; hook imports before decompiling.
    -> See references/wasm-reverse-engineering.md.

11) Target is a HuggingFace Space / Gradio app?
    -> Check /config for endpoints -> map component IDs to fn params -> REST/WS/SSE.

12) Data/action is behind login AND Cloudflare (member dashboard, checkin)?
    -> Inject a manually-exported session -> drive in-page fetch to map read-only.
    -> Don't re-implement the login first. See authenticated-session-mapping.md.

13) Need to automate login for scheduled tasks (checkin, scraping, monitoring)?
    -> Browser automation with email/password -> persistent profile -> validation.
    -> See references/automated-login-solver.md.

14) WAF blocks HTTP requests even with correct cookies?
    -> Dual-cookie strategy: user session (long-lived) + WAF cookie (ephemeral).
    -> See references/waf-bypass-techniques.md.

15) Need reliable proxy rotation for production scraper?
    -> Clash/Mihomo + subscription + health checking + url-test mode.
    -> See references/proxy-rotation-strategies.md.

16) Response is a 202/412 page with an obfuscated <script>, cookie like
    FSSBBIl1UgzbN7N80S, or window.$_ts?
    -> RiverSecurity. Per-site dynamic VM. NO universal solution.
    -> Two routes: environment simulation (bu-huanjing) or pure algorithm (rs-reverse).
    -> See references/ruishu-river-security.md.

17) API request contains an opaque parameter (sign/token/w/blackbox/data/msg)
    that you cannot find by name in the source?
    -> Signature parameter RE. Use scripts/signature_probe.js to find the call site.
    -> See references/signature-parameter-re.md.

18) Vendor JS is a VM (JSVMP) with a giant switch dispatch loop?
    -> No automated deobfuscator exists (obfuscator.io states this explicitly).
    -> Instrument the dispatch loop; extract the bytecode array.
    -> See references/environment-simulation-jsvmp.md.

19) Challenge passes but the data API still rejects you?
    -> Device fingerprint layer. You passed layer 1, not layer 2.
    -> See references/cn-risk-control-ecosystem.md (layer decision tree).

20) Target is a WeChat / Alipay / Douyin mini-program?
    -> Get the package (wxapkg / .tar / TTPKG) -> unpack -> map cloud functions.
    -> See references/miniprogram-reverse-engineering.md.

21) HTTP 402, or crawler-* headers, or invisible decoy links?
    -> Commercial gate (Cloudflare Pay Per Crawl) or AI Labyrinth. STOP retrying.
    -> A 402 is a commercial signal, not a technical obstacle.

22) Proof-of-work challenge (Anubis / Kasada style)?
    -> Solve in native code, not browser JS (~50 MH/s vs ~0.5 MH/s).
    -> Reuse the auth cookie instead of re-solving.
    -> See references/frontier-anti-bot-2026.md.

23) Target is a Chinese CAPTCHA (GeeTest/Shumei/Yidun/Dingxiang/Tongdun)?
    -> Route by volume: <1k/day -> solving API; >10k/day -> algorithm reversal.
    -> Slider CAPTCHAs: trajectory quality matters as much as the crypto.
    -> See references/captcha-vendors-cn.md.

24) Target is a desktop application (Electron/Tauri/Qt/.NET/JVM/Python/Go/Rust)?
    -> Triage FIRST: Detect It Easy / file / binwalk. Managed runtime? -> decompile.
    -> Electron? @electron/asar extract, then check fuses.
    -> .NET? dnSpyEx + de4dot. NativeAOT -> treat as native.
    -> Python? PyInstaller -> pyinstxtractor. Nuitka -> native, no bytecode.
    -> See references/software-reverse-engineering.md.

25) Target is an installer or self-extracting archive?
    -> MSI: msiexec /a (administrative install extracts without running it).
    -> Inno: innoextract. InstallShield: unshield. NSIS: 7-Zip. MSIX: it's a zip.
    -> See references/software-reverse-engineering.md §5.

26) Target is packed, or the binary is mostly high-entropy?
    -> Identify the packer (DIE / section names).
    -> UPX -> upx -d. Stub-based -> debugger + dump + Scylla + ScyllaHide.
    -> VM-based (VMProtect/Themida) -> behavioural triage; devirtualization is
       a research problem, not a workflow.
    -> See references/software-reverse-engineering.md §4.

27) Target is a game?
    -> Engine ID first. Unity: Mono (dnSpy) or IL2CPP (Il2CppDumper)?
    -> Unreal: repak / FModel / CUE4Parse; UE5 uses IoStore.
    -> Godot: gdsdecomp. GameMaker: UndertaleModTool.
    -> See references/software-reverse-engineering.md §7.

28) Target is firmware / an IoT device / a router / an ECU?
    -> Software acquisition route first (vendor portal, OTA, companion app).
    -> Then UART / SPI flash (flashrom + CH341A) / JTAG.
    -> See references/firmware-and-hardware-re.md.

29) Unknown binary file format?
    -> DIFFERENTIAL analysis: change one field in the producer, diff the output.
    -> Then formalize with Kaitai Struct or an ImHex pattern.
    -> See references/software-reverse-engineering.md §6.

30) Need this in Go / Rust / Node / Java / C# rather than Python?
    -> Check the capability matrix first: most languages cannot shape a ClientHello.
    -> See references/language-ecosystems.md.
```

## Common Playbooks

### A) "I only need a few fields from one page"
1. Inspect Network panel for JSON-LD or XHR.
2. If present, parse structured JSON directly.
3. If absent, CSS/XPath extraction with robust selectors.

### B) "Cloudflare blocks my Python requests"
1. Identify whether Bot Management is actually on (`cf-mitigated`, Turnstile tag) —
   `Server: cloudflare` alone does not prove it.
2. Switch to curl_cffi impersonation. **Check which UA platform the profile reports.**
3. Align headers + TLS profile + proxy geo.
4. Add jitter/backoff.
5. Escalate to a patched browser if still blocked.
6. Check for 402 / AI Labyrinth before assuming a technical problem.

### C) "Need production crawler"
1. Framework: Scrapy (Py) or Crawlee (Node).
2. Externalize proxy pool and health scoring.
3. Add retries, circuit breakers, dead-letter queue.
4. Store raw + parsed + trace metadata for replay.
5. Route transport **per target**, not per request.

### D) "Wrap a Gradio/HF Space into a production API"

Gradio Spaces expose different API protocols depending on version. `/config` reveals everything.

**Step 1: Fetch and parse config**
```bash
curl -s https://{space}.hf.space/config | python3 -c "import json,sys; d=json.load(sys.stdin); print(json.dumps({c['id']:c['type'] for c in d['components']}, indent=2))"
```

**Step 2: Determine protocol**

| Protocol | Gradio | Endpoint | When |
|----------|--------|----------|------|
| **REST named** | 3.x | `/api/{api_name}/` POST | `api_name` set in app.py |
| **REST unnamed** | 3.x | `/api/predict/` POST | No api_name |
| **WebSocket** | 3.x | `/queue/join` | Queue enabled |
| **SSE** | 4+ | `/gradio_api/call/{fn}` | Newer Spaces |

**Step 3: Map parameters**
Config `dependencies` maps components to function params. Dropdowns with `type="index"` send the INDEX integer via REST but the LABEL string via WebSocket — test both.

**Step 4: Handle output formats**
- Audio: check `app.py` for `gr.Audio.postprocess` monkeypatch (may return base64 data URI)
- File download: `{base_url}/file={path}` (3.x) or `{base_url}/gradio_api/file={path}` (4+)
- File upload: `{base_url}/upload` (3.x) or `{base_url}/gradio_api/upload` (4+)

**Step 5: Build resolution layer**
Gradio dropdown choices rarely match user-facing names. Build multi-layer fallback:
```
exact match → prefix match → alias table → case-insensitive → substring
```

**Step 6: Add fallback**
If the Space has mirrors, add REST primary + WebSocket fallback with different text
limits. Truncate before the fallback call.

See `references/gradio-space-reverse-engineering.md`.

### E) "Map a logged-in, Cloudflare-gated SPA (dashboard/checkin/rewards)"

A valid session cookie is a skeleton key — use it to map the authed API instead of
re-implementing the login.

1. **Log in by hand once**, export cookies (Cookie-Editor JSON).
2. **Inject** into a stealth browser (`add_cookies`) → `goto(dashboard)` → pass CF once.
3. **Confirm auth** via the framework's session endpoint (`/api/auth/session`,
   `/session/current.json`).
4. **Enumerate read-only** with **in-page `fetch`** — `page.evaluate(() => fetch(u,{credentials:'include'}))`
   runs in the real origin and passes CF; `context.request`/curl_cffi do NOT run CF JS
   and get 403 on gated endpoints.
5. **Grep the JS bundles** (`/_next/static/*.js`) for `"/api/..."` literals + field names
   — the SPA page route is NOT the API route.
6. **Stay read-only** during recon: GET + grep only.

Key sub-techniques:
- **Cookie names fingerprint the framework/version** — `next-auth.session-token`
  (NextAuth v4) vs `__Secure-authjs.session-token` (Auth.js v5).
- **Isolate stale credentials from code bugs FIRST.**
- **JWT/JWE sessions** self-validate independent of the OAuth upstream.

See `references/authenticated-session-mapping.md` + `scripts/session_probe_template.py`.

### F) "Automate login flow for scheduled tasks (daily checkin, monitoring)"

For production automation, email/password login beats cookie injection: session cookies
expire unpredictably, manual export does not scale, and login automation is more reliable
long-term.

**Architecture**: Browser profile persistence + session validation + credential-first fallback

**Key techniques**:
1. **WAF pass before login** — navigate homepage first (3-5s warmup), then login page.
2. **Popup dismissal** — MutationObserver to auto-close announcement modals, consent.
3. **Multi-strategy form discovery** — selector match → icon button → tab switching → JS
   greedy search.
4. **Framework-aware credential injection** — JS property setter + event dispatch to
   trigger React/Vue onChange.
5. **API interception for validation** — navigate `/console`, intercept `/api/user/self`.
6. **Persistent browser profiles** — reuse across runs, skip login if session valid.

See `references/automated-login-solver.md`.

### G) "Bypass WAF for API calls"

**Problem**: WAF challenge cookies are cryptographically bound to TLS fingerprint, IP, and
timestamp. Cannot be injected from browser devtools.

**Solution**: Dual-cookie strategy — harvest the WAF cookie fresh per request, merge with
the long-lived session cookie.

**WAF-specific patterns**:
- **Cloudflare**: `cf_clearance` (~30 min TTL); `curl_cffi` + `tls_permute_extensions`
- **Akamai**: `_abck` sensor data; `_abck` needs ~3 sensor posts to become valid (`~0~`)
- **Aliyun**: `acw_tc` (2-5 min TTL), `acw_sc__v2` requires algorithm reversal
- **Imperva**: `reese84`
- **RiverSecurity**: `FSSBBIl1UgzbN7N80S` + `window.$_ts` — per-site, no universal solution

**Optimization**: Cache WAF cookies for 1-3 minutes. Test expiry empirically.

See `references/waf-bypass-techniques.md`.

### H) "Deploy production proxy rotation (health checking, failover)"

**Architecture**: Clash/Mihomo proxy manager with subscription support + automatic health
checking.

```yaml
proxy-groups:
  - name: AUTO
    type: url-test
    url: https://www.google.com/generate_204
    interval: 300
    tolerance: 150
    lazy: false
    use:
      - subscription

rules:
  - MATCH,AUTO
```

**Integration**:
- Playwright: `browser.launch(proxy={'server': 'http://127.0.0.1:7890'})`
- httpx: `httpx.Client(proxy='http://127.0.0.1:7890', http2=True)`

See `references/proxy-rotation-strategies.md`.

### I) "Reverse a signed parameter (sign / w / blackbox)"

**Step 1: Determine whether it is even necessary.**

| Volume | Route | Why |
|---|---|---|
| < 1k/day | RPC to a real browser | Cheapest to build; call the vendor's own JS |
| 1k–10k/day | Environment simulation (bu-huanjing) | Run vendor JS in Node; no algorithm porting |
| > 10k/day | Pure-algorithm reversal | Highest upfront cost, lowest marginal cost |

**Step 2: Locate the generation point.**

Inject `scripts/signature_probe.js`. It hooks XHR/fetch, cookie setters, `crypto.subtle`,
and common crypto libraries, then prints a numbered trace.

**Step 3: If the parameter name does not appear in the source**, use the four fallback
techniques in `references/signature-parameter-re.md`: search the value pattern, search the
request-URL string, breakpoint on `XMLHttpRequest.send`, or hook `JSON.stringify`.

**Step 4: Handle the common crypto families.**

| Family | Signature | Notes |
|---|---|---|
| crypto-js | `CryptoJS.AES.encrypt(...)`, `CryptoJS.MD5` | Check the version — API changed across majors. **crypto-js is discontinued.** |
| JSEncrypt | `JSEncrypt`, PEM public key | PEM↔jsbn parameter mapping is the usual bug |
| Chinese national crypto (SM) | `sm2` / `sm3` / `sm4` | `sm-crypto` in JS; `pysmx` / `gmssl` in Python |
| Permuted Base64 | Custom alphabet | Find the 64-char permutation table |
| GeeTest | `w = aes_hex(plaintext, key_16) + rsa_hex(key_16, public_key)` | Key is random per challenge |
| RSA-PKCS1 | Base64 of a fixed-length blob | Check padding scheme and byte order |

**Step 5: Reproduce and verify against a captured fixture** before scaling.

See `references/signature-parameter-re.md` and `references/captcha-vendors-cn.md`.

### J) "Run vendor JS locally (environment simulation / bu-huanjing)"

The highest-leverage technique against vendor risk engines: instead of porting an
algorithm, run the vendor's own code in a controlled Node environment.

```javascript
const { buildWindow, run } = require('./scripts/env_harness_template.js');
const win = run('./vendor_challenge.js');
console.log(win.$_ts, win.document.cookie);
```

**Three non-obvious facts about `node:vm` that the template handles** (all verified on
Node 24 — most self-written harnesses get at least one wrong):

1. **A vm context has its own intrinsics.** Patching the outer realm's
   `Function.prototype.toString` or `String.prototype.indexOf` has **no effect** on code
   inside the context. Every spoof must be installed a second time from inside.
2. **`Symbol.for()` uses a global registry that IS shared across vm contexts.** This is
   what lets you mark a function in one realm and have the spoof in the other see it.
3. **Patching one realm leaves a bypass.** `fn.toString()` resolves via fn's own prototype;
   `Function.prototype.toString.call(fn)` resolves via the *caller's* realm. Both must be
   patched, or one form leaks your stub's real source.

| Check | Countermeasure |
|---|---|
| `Function.prototype.toString` on patched fns | Dual-realm spoof (outer + in-context) |
| Re-defined native fn still has `prototype` | **Must remain `undefined`** |
| `navigator.userAgent` vs request `User-Agent` | **Must match.** Yidun pass rate: <20% → 100% from this alone |
| Node stack frames (`cjs/loader`, `node:internal`) | `Error.prepareStackTrace` filtering **inside the context** |
| Canvas hash | Real `node-canvas` rendering, not a stub |
| Timing acceleration | Real `setTimeout`, not immediate calls |
| `process` visible | Delete the property entirely (not just set to undefined) |

**CRITICAL**: `node:vm` is explicitly **not a security boundary** (per Node docs). For
genuinely untrusted code, use `isolated-vm`.

See `references/environment-simulation-jsvmp.md` + `scripts/env_harness_template.js`.

### K) "Unpack a mini-program (wxapkg / TTPKG)"

```bash
# 1. Locate the package
#    Windows: %USERPROFILE%\Documents\WeChat Files\Applet\<appid>\<version>\__APP__.wxapkg
#    Android: /data/data/com.tencent.mm/MicroMsg/<md5>/appbrand/pkg/

# 2. Inspect the structure
python scripts/wxapkg_unpack.py __APP__.wxapkg --verify

# 3. Unpack
python scripts/wxapkg_unpack.py __APP__.wxapkg -o out/
```

**Expect a counterintuitive result**: you usually get one large `app-service.js` +
`app-config.json`, **not** per-page `wxml`/`wxss` files. Use `wedecode` (needs the main
package too, via `-s`) to reconstruct the source tree.

**Request characteristics** (for replay):

| Field | Value |
|---|---|
| `Referer` | Fixed `https://servicewechat.com/{appid}/{version}/page-frame.html` |
| `User-Agent` | Includes `miniProgram` markers — differs from normal WeChat UA |
| Promise support | Often absent — callbacks only |

**Cloud functions** are the interesting target: `wx.cloud.callFunction` maps to a backend
you can call directly.

See `references/miniprogram-reverse-engineering.md` + `scripts/wxapkg_unpack.py`.

### L) "Analyze a WASM module"

**Do not start by decompiling.** Run triage first:

```bash
python scripts/wasm_triage.py app.wasm
```

It reports: toolchain (Emscripten / wasm-bindgen / AssemblyScript / Rust / TinyGo / Zig /
Blazor), crypto constants present (AES S-box, SHA-256 IV, SM3/SM4, ChaCha20), permuted
base64 tables, and whether DWARF or a name section exists.

**Route selection**:

| Triage result | Route |
|---|---|
| DWARF present | Ghidra + `nneonneo/ghidra-wasm-plugin` — may give original names and types |
| Name section present | `wasm2wat` keeps function names; read the WAT |
| Crypto markers found | **Hook imports + read linear memory.** You likely do not need to decompile |
| Nothing conclusive | Hook imports first; decompile only if you need control flow |

```bash
wasm-objdump -x app.wasm            # structure
wasm2c app.wasm -o app.c            # then gcc -O3 and load in IDA/Ghidra
wasm2js app.wasm -o app.js          # flatten to JS (often fastest)
```

**Critical correction**: `wasm-decompile` belongs to **WABT**, not Binaryen — and it was
**removed from WABT on 2026-06-22** (PR #2769, effective 1.0.42). Pin wabt ≤ 1.0.41 if you
need it. Ghidra has **no native WASM support**.

See `references/wasm-reverse-engineering.md`.

### M) "Reverse a desktop application"

**Triage before anything else.** The single most expensive mistake is loading a
managed-runtime artifact into a disassembler.

```bash
diec ./app        # Detect It Easy: language, compiler, packer, arch, entropy
file ./app
binwalk -e ./app  # is it actually a container?
```

| Finding | Route |
|---|---|
| `.NET` CLR header | dnSpyEx. Run **de4dot** first if obfuscated. **NativeAOT → treat as native** |
| JVM (`CAFEBABE`) | CFR / Vineflower / JADX. **Deobfuscate strings first**, then re-decompile |
| Python frozen | `pyinstxtractor` → decompile `.pyc` (version-gated; 3.9+ often has no decompiler) |
| **Nuitka** | Compiled to native. **No bytecode to recover.** |
| Electron | `@electron/asar extract`; check fuses; check `--remote-debugging-port` |
| Tauri | Webview frontend + **Rust native backend**. No asar. |
| Go | `go version -m ./app` gives dependency versions. `GoReSym`/`redress` for stripped |
| Rust | `rustfilt` to demangle; panic strings survive stripping |
| Native C/C++ | FLIRT/FID → RTTI recovery → **struct recovery** → anchor on imports/strings |

**Do not read a binary front to back.** Anchor on imported APIs matching the behaviour you
care about, string references, and cryptographic constants. Static analysis gives you a
map; dynamic analysis tells you whether the map is lying.

See `references/software-reverse-engineering.md`.

### N) "Reverse a firmware image or IoT device"

**Try the software route first** — it is an order of magnitude less work:

```text
vendor download portal -> OTA interception -> companion app cache -> cloud API
```

Then hardware, in this order of increasing effort:

```text
UART (serial console, often a shell)
  -> SPI flash (flashrom + CH341A + SOIC-8 clip)   <- standard first attempt
  -> JTAG/SWD (OpenOCD; JTAGulator for pin discovery)
  -> glitching (only if secure boot is properly implemented)
```

**Extraction**: `binwalk v3` (Rust rewrite; the v2 fork is EOL at 2025-12-12) **then**
`unblob` for anything missed. **Verify extraction completeness** — filesystem extraction
fails silently far more often than it fails loudly.

**SquashFS is the most common failure point**: vendors use non-standard compression and
modified headers that stock `unsquashfs` rejects. Use **sasquatch**.

**Set the correct load base address in Ghidra** or every reference is wrong. Identify the
RTOS (FreeRTOS / Zephyr / VxWorks / ThreadX) to understand calling conventions.

See `references/firmware-and-hardware-re.md`.

### O) "Reverse an unknown binary file format"

```text
1. Hex dump the first 64 bytes. Look for a magic number.
2. Entropy by region — low-entropy regions are headers or tables.
3. Find TWO samples differing in ONE known field. Diff them. Those bytes are your field.
4. Repeat for each field you can vary.
5. Formalize with Kaitai Struct or an ImHex pattern.
6. Validate against many samples.
```

**Step 3 is the technique that actually works.** It is far faster than staring at hex.

Before reverse-engineering anything, rule out a known serialization format: protobuf
(`protoc --decode_raw`, `blackboxprotobuf`), MessagePack, CBOR, BSON, Avro (schema is
embedded — no RE needed), Thrift, FlatBuffers / Cap'n Proto (need the schema).

See `references/software-reverse-engineering.md` §6 and
`references/protocol-reverse-engineering-advanced.md`.

## Anti-Bot Severity Ladder

| Level | Typical signals | Recommended baseline | Examples |
|---|---|---|---|
| L0 | No active bot stack | requests/httpx + throttling | Internal APIs, small sites |
| L1 | IP/rate checks only | rotating proxies + retries | Public data APIs |
| L2 | TLS/HTTP2 checks | curl_cffi/hrequests/rnet/utls/wreq | Basic Cloudflare, simple WAF, AWS WAF |
| L3 | JS + browser fingerprint | Playwright + stealth patching | Cloudflare JS challenge, Imperva `reese84` |
| L4 | behaviour + challenge loops | Patchright/nodriver/Camoufox + residential/ISP | CF managed challenge, DataDome |
| L5 | enterprise bot manager | full stack + adaptive controls + fallback APIs | Akamai BMP, HUMAN, Kasada, F5 |
| **L6** | **signed-parameter / VM risk engine** | **algorithm reversal or environment simulation; NOT browser automation** | **RiverSecurity, Tencent TCaptcha, GeeTest, Yidun, Shumei, Dingxiang, Tongdun** |
| **L7** | **commercial gate / cost imposition** | **pay, license, or stop — not a technical problem** | **Cloudflare Pay Per Crawl (402), AI Labyrinth** |

**Escalation strategy**:
- L0→L1: proxy rotation when seeing 429 rate limits
- L1→L2: curl_cffi/utls when seeing TLS fingerprint detection (empty body, instant 403)
- L2→L3: real browser when a JS challenge appears
- L3→L4: residential proxies + humanize when CAPTCHA appears repeatedly
- L4→L5: custom fingerprint rotation + behavioural modelling
- L5→L6: **Change paradigm.** Browser automation will not help.
- L6→L7: **Stop escalating.** A 402 is a commercial decision.

**Cost implications**:
- L0–L2: ~$0.001/request (HTTP client, datacenter proxies)
- L3: ~$0.01/request (browser overhead)
- L4: ~$0.10/request (residential proxy)
- L5: ~$1.00/request (CAPTCHA solving, complex fingerprinting)
- L6: high upfront (reverse engineering), near-zero marginal — only works at volume
- L7: whatever the vendor charges

**L6 is a different game.** L0–L5 are about looking human. L6 is about reproducing
cryptography. Do not apply L4 tactics to an L6 target and conclude it is impossible.

**Within L5, the vendor determines the lever.** DataDome scores each request
independently, so IP reputation dominates. HUMAN shares reputation network-wide, so a
burned fingerprint is burned everywhere. Kasada escalates PoW difficulty by session
trust — an economic defence. Akamai is TLS-coherence-first. See
`references/global-anti-bot-vendors.md`.

## Layer Diagnosis Table

When a target blocks you, identify the layer before choosing a fix.

| Symptom | Layer | Fix |
|---|---|---|
| Instant 403, empty body | Transport fingerprint | curl_cffi + `tls_permute_extensions` |
| "Checking your browser" page | JS challenge | Browser path, or solve the challenge |
| Works manually, fails in code | Missing token/cookie | Replay the full request chain |
| Challenge passes, API rejects | Device fingerprint (layer 2) | See `cn-risk-control-ecosystem.md` |
| 202/412 with obfuscated script | RiverSecurity dynamic VM | See `ruishu-river-security.md` |
| 403 with a valid signature | Wrong canonicalization | Compare two near-identical requests |
| Signature accepted once, then rejected | Nonce replay protection | Fresh nonce per request |
| **429 with `x-kpsdk-*` headers** | **Kasada proof of work** | Solve the PoW; do not just retry |
| **Bare 403/429 with no body at all** | Kasada reputation burned | The IP is spent; changing technique will not help |
| **HTTP 200 but wrong content** | **Imperva** 200-disguised block page | Do not trust the status code; validate the payload |
| **HTTP 200 with a poisoned body on one endpoint** | **F5 Shape** transform-200 | Policy is per-endpoint; the homepage being clean means nothing |
| **428 Precondition Required** | Akamai sec-cpt | Forced wait + PoW; handle the second layer |
| **429/403 with no vendor fingerprint at all** | Netacea / Cequence (agentless) | No payload to reverse; the only lever is behaviour |
| **Blocked only after setting a custom UA** | UA contradicts the TLS profile | Check `summary.user_agent` from `fingerprint_probe.py` |
| HTTP 402 / `crawler-*` | Commercial gate | Pay, license, or stop |
| Works for minutes, then dies | Session/token TTL | Implement refresh lifecycle |

**Three status codes that actively lie**: Imperva's 200-disguised block, F5 Shape's
200-with-poisoned-body, and Kasada's body-less rejection. In all three, the status code
tells you the opposite of the truth.

## Verification Checklist (before scaling)

- `scripts/fingerprint_probe.py` output matches a real browser for the same target
- bot detector pages are clean enough (webdriver/CDP leaks reduced)
- accept-language/timezone/proxy region are coherent
- **UA matches the TLS fingerprint** (a mismatch is itself the signal)
- **the TCP stack matches the claimed OS** (a Linux Python client behind a residential
  proxy still presents a Linux TCP stack)
- request cadence resembles real user flows, using a distribution not a constant
- success rate and challenge rate are logged per target and per proxy ASN
- **downstream rejection rate after a successful challenge is tracked** (layer 2)
- session cookies validated before assuming code bugs
- WAF cookies harvested fresh per request
- browser profiles persistent for scheduled tasks
- proxy health checking enabled
- **dependency versions pinned** (a client upgrade can change your fingerprint)
- for L6 targets: reproduction verified against a captured fixture, not just "it returns 200"
- for firmware: extraction completeness verified (file count, total size, expected binaries)
- for binary RE: the load base address is correct before trusting any cross-reference
- for identity separation: no personal credential has touched engagement infrastructure

## References

### Compliance and boundaries

- `references/compliance-and-scope.md` — **authorization line, statutory research exemptions with expiry dates, dual-use reasoning, machine-readable preference signals, stop conditions, agent guidance**
- `references/legal-ethical.md` — **case law (US/EU/CN), Criminal Law Art. 285/286 thresholds, Anti-Unfair Competition Law 2025, DMCA §1201 ninth triennial, risk matrix**
- `references/identity-and-attribution.md` — **four-layer separation (identity/machine/network/behaviour), fingerprint coherence cross-checks, antidetect browser honest assessment**

### Foundations

- `references/http-clients.md` — curl_cffi/hrequests/rnet/primp, impersonation, **the UA/OS trap per profile version**
- `references/browser-automation.md` — Playwright/Patchright/nodriver/Camoufox/DrissionPage selection
- `references/anti-detection.md` — detection surfaces, anti-detect browser ladder, coherence checklist
- `references/tls-http-fingerprinting.md` — **JA3/JA3N/JA4/Akamai H2 fingerprint, three-layer alignment**
- `references/traffic-camouflage.md` — **the camouflage stack layer by layer, GREASE, HTTP/2 SETTINGS, TCP-stack fingerprinting, domain fronting (T1090.004), temporal signals, defender's detection checklist**
- `references/global-anti-bot-vendors.md` — **one-response vendor identification, per-vendor mechanism and difficulty tier, agentless vendors, public benchmark data with its methodological caveats, the 2025–2026 "agent trust" shift and Web Bot Auth**
- `references/anti-bot-bypass.md` — vendor-by-vendor playbooks
- `references/frontier-anti-bot-2026.md` — **Cloudflare AI Labyrinth / Pay Per Crawl / Content Signals, the 402 standard family (x402, AWS WAF Monetize, RSL), Anubis PoW, CDP detection**

### Language ecosystems

- `references/language-ecosystems.md` — **per-language library map (Python/Node/Go/Rust/JVM/.NET/C/C++/Ruby/PHP), capability matrix for browser-TLS impersonation, embeddable JS engines (QuickJS/goja/rquickjs/Wazero), WASM runtimes**

### Scaling and operations

- `references/scraping-frameworks.md` — Scrapy/Crawlee/Colly/Rod, production architecture
- `references/proxy-strategies.md` — proxy types, rotation models, health scoring
- `references/proxy-rotation-strategies.md` — production Clash/Mihomo rotation, failover, geo-matching
- `references/data-extraction.md` — extraction priority, selectors, normalization contract
- `references/tool-alternatives.md` — replacement matrix for every layer

### Authentication and sessions

- `references/authenticated-session-mapping.md` — inject a real session to map a CF-gated SPA API
- `references/automated-login-solver.md` — production login automation
- `references/waf-bypass-techniques.md` — WAF cookie harvesting, dual-cookie strategy

### JavaScript

- `references/js-deobfuscation.md` — **obfuscator identification, option→reversal map, webpack/Vite/sourcemap recovery**
- `references/environment-simulation-jsvmp.md` — **environment-simulation harness, the three node:vm realm facts, JSVMP internals, anti-virtualization**

### Software and binary reverse engineering

- `references/software-reverse-engineering.md` — **triage, managed runtimes (.NET/JVM/Python/Electron/Tauri), Go/Rust, native static+dynamic, packers and VM protectors, installers, document and data formats, serialization formats, game engines (Unity IL2CPP/Unreal/Godot), DRM scope**
- `references/binary-native-reverse-engineering.md` — compiled binary analysis
- `references/wasm-reverse-engineering.md` — **WASM toolchain, WABT removal, runtime hooking, toolchain fingerprints**

### Firmware and hardware

- `references/firmware-and-hardware-re.md` — **acquisition (software routes first, then UART/SPI/JTAG), secure boot and readout protection, extraction (binwalk v3/unblob/FACT/EMBA), filesystem types and SquashFS gotchas, emulation failure modes, RTOS identification, side-channel and glitching, wireless (BLE/Zigbee/Sub-GHz/NFC), automotive CAN/UDS/J1939, DMCA exemptions for hardware research**

### Mobile

- `references/mobile-reverse-engineering.md` — Android/iOS app RE workflow
- `references/mobile-app-reverse-engineering.md` — **full toolchain, jailbreak/root matrix, SSL pinning, Flutter/Hermes**

### Protocols

- `references/protocol-reverse-engineering.md` — WebSocket, gRPC, custom TCP/UDP
- `references/protocol-reverse-engineering-advanced.md` — **protobuf without .proto, gRPC reflection, Kaitai/Wireshark, TLS decryption, mitmproxy internals**

### Chinese risk control

- `references/cn-risk-control-ecosystem.md` — **vendor matrix, layer decision tree, mobile hardening generations**
- `references/ruishu-river-security.md` — **RiverSecurity detection table, generation differences, both routes**
- `references/captcha-bypass.md` — avoidance-first model, CAPTCHA classes, solver integration
- `references/captcha-vendors-cn.md` — **per-vendor parameter breakdown (GeeTest/Aliyun/Tencent/Yidun/Shumei/Dingxiang/Tongdun)**
- `references/signature-parameter-re.md` — **locating and reversing signed parameters, Chinese national crypto (SM), crypto-js traps**
- `references/miniprogram-reverse-engineering.md` — **wxapkg/TTPKG/Alipay, cloud functions, request characteristics**

### Special targets

- `references/gradio-space-reverse-engineering.md` — Gradio/HF Space API patterns
- `references/emerging-trends.md` — **2025→2026 trends, dead/archived tool list, watchlist**

## Scripts

| Script | Purpose |
|---|---|
| `scripts/fingerprint_probe.py` | **Verify your TLS/HTTP fingerprint against a reference before writing bypass code** |
| `scripts/signature_probe.js` | **Locate where a signed parameter is generated (hooks XHR/fetch/cookie/crypto)** |
| `scripts/env_harness_template.js` | **environment-simulation skeleton with the dual-realm toString spoof and stack scrubbing already handled** |
| `scripts/wxapkg_unpack.py` | **Dependency-free wxapkg parser/unpacker with header validation and traversal defense** |
| `scripts/wasm_triage.py` | **WASM triage: toolchain, crypto constants, DWARF, route recommendation** |
| `scripts/camoufox_template.py` | Camoufox browser baseline |
| `scripts/curl_cffi_template.py` | curl_cffi HTTP baseline with profile verification |
| `scripts/session_probe_template.py` | Session validation probe |

All scripts support `--help`; the dependency-bearing ones also support `--check-deps` and
degrade gracefully when their optional dependency is absent.

## When to Escalate vs Stop

Escalate when:
- target is business-critical
- you have assessed actual legal exposure (not just ToS discomfort)
- expected value exceeds infra and maintenance cost
- **you have correctly identified which layer is blocking** — escalating the wrong layer
  wastes weeks
- **you have identified the vendor** — escalating with the wrong technique wastes the
  same weeks

Stop when:
- you face active legal process (cease-and-desist, injunction, criminal inquiry)
- **the defense is a commercial gate (HTTP 402)** — a licensing decision, not a bypass
- technical barriers indicate protected/authenticated resources you cannot access without
  authorization
- an equivalent licensed data source exists at lower total cost
- the marginal cost of reversal exceeds the data's value at your volume
- **the work requires bypassing authentication rather than a bot challenge**

Do not treat Terms of Service as a hard stop. In most jurisdictions, public data scraping
does not constitute "unauthorized access" under criminal computer fraud statutes.
Contractual disputes and criminal liability are different risk categories. Note the
asymmetry: **China's Anti-Unfair Competition Law (2025 revision, effective 2025-10-15) explicitly
targets circumvention or destruction of technical management measures**, making anti-bot evasion legally riskier in China than in
the US or EU. See `references/compliance-and-scope.md` and `references/legal-ethical.md`.

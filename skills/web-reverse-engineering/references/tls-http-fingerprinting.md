# TLS and HTTP Fingerprints (JA3 / JA3N / JA4 / JA4+ / Akamai H2)

The first gate of modern anti-bot protection is often not at the application layer, but in the **TLS handshake fingerprint** and the **HTTP/2 frame fingerprint**. Hitting a Cloudflare/Akamai site with requests gets you blocked before you ever reach the business logic — this is why.

## Why It Is Needed

The TLS handshake characteristics of `requests`, `httpx`, and `aiohttp` (cipher suite order, extension set and order, elliptic curves, ALPN) differ drastically from real browsers, forming a stably identifiable fingerprint. The way around it is not "adding a User-Agent", but **making the handshake itself look like a browser**.

## JA3

**Algorithm**: concatenate the five fields `SSLVersion,Cipher,SSLExtension,EllipticCurve,ECPointFormat` in their **original order**, separated by commas, with fields internally separated by `-`, then take the MD5.

- **GREASE values must be removed**
- **Order sensitive** — this is why it was broken

**Fatal flaw**: **Chrome 109/110 introduced TLS extension order randomization**, so JA3 is no longer stable within the same browser version, producing many false positives.

**Status**: the official implementation `salesforce/ja3` **was archived on 2025-05-01**.

## JA3N

**JA3N = a set-based variant**: it **deduplicates and sorts** the cipher and extension lists before hashing, and is therefore immune to extension order randomization.

**Important limitation**: **JA3N is only a convention of the curl_cffi ecosystem, not a formal standard**. It has no specification document and is defined by the implementer.

**Usage in curl_cffi**: extension order randomization must be explicitly enabled to emulate Chrome's modern behavior:

```python
from curl_cffi import requests

r = requests.get(
    url,
    impersonate="chrome",
    extra_fp={"tls_permute_extensions": True},   # Key: reproduce Chrome 109+ extension order randomization
)
```

## JA4

**Format**: `ja4_a_ja4_b_ja4_c`, three segments separated by `_`.

### ja4_a (10 characters, human readable)

| Position | Meaning |
|---|---|
| 1 | transport type: `t` = TCP, `q` = QUIC, `d` = DTLS |
| 2–3 | version: `13` / `12` / `11` / `10` / `s3` / `s2` / `d1`–`d3` / `00` |
| 4 | SNI: `d` = domain (has SNI), `i` = IP (no SNI) |
| 5–6 | 2-digit cipher count (**after GREASE removal**) |
| 7–8 | 2-digit extension count (**after GREASE removal**) |
| 9–10 | the **first and last alphanumeric characters** of the first ALPN value |

### ja4_b

SHA-256 of the **sorted** cipher list, **truncated to 12 hex characters**. Empty list → `000000000000`.

### ja4_c

SHA-256 of the **sorted** extension type codes (**excluding SNI `0000` and ALPN `0010`**) truncated to 12 characters, then `_` concatenated with the signature algorithms in **original order**.

**Specification example**: `t13d1516h2_8daaf6152771_e5627efa2ab1`

## JA4+ Suite

| Abbreviation | Target |
|---|---|
| JA4 | TLS Client |
| JA4S | TLS Server |
| JA4H | HTTP Client |
| JA4L | Latency (Client) |
| JA4LS | Latency (Server) |
| JA4X | X.509 certificate |
| JA4SSH | SSH |
| JA4T | TCP (Client) |
| JA4TS | TCP (Server) |
| JA4TScan | TCP active scanning |
| JA4D / JA4D6 | DHCP |

**License split (important for commercial use)**:

- **JA4 itself: BSD-3-Clause**
- **All other JA4+ methods: FoxIO License 1.1** (with non-commercial restrictions)

Specification repository: https://github.com/FoxIO-LLC/ja4

## Akamai HTTP/2 Fingerprint

Format: `SETTINGS | WINDOW_UPDATE | PRIORITY | PSEUDO_HEADER_ORDER`

| Browser | Fingerprint |
|---|---|
| Chrome | `1:65536;2:0;4:6291456;6:262144\|15663105\|0\|m,a,s,p` |
| Firefox | `1:65536;4:131072;5:16384\|12517377\|0\|m,p,a,s` |
| Safari | `1:65536;3:1000;4:6291456\|10485760\|0\|m,s,p,a` |

**Meaning of the four segments**:

1. the `id:value` key-value pairs of the **SETTINGS frame** (semicolon separated)
2. the **WINDOW_UPDATE** value
3. **PRIORITY** (mostly 0)
4. **pseudo-header order** (`m` = `:method`, `a` = `:authority`, `s` = `:scheme`, `p` = `:path`)

**Pseudo-header order is a strong characteristic**: Chrome and Firefox are both `m,a,s,p`, while **Safari is `m,s,p,a`**.

## Tools

| Tool | Description |
|---|---|
| **curl_cffi** | the first choice for browser impersonation. `impersonate="chrome"` etc.; `extra_fp` fine-tunes the TLS and H2 layers |
| **tls-client** | a similar implementation with multi-language bindings |
| Cloudflare JA3/JA4 documentation | https://developers.cloudflare.com/bots/additional-configurations/ja3-ja4-fingerprint |
| Cloudflare JA4 signals announcement | https://blog.cloudflare.com/ja4-signals |
| FoxIO JA4 specification | https://github.com/FoxIO-LLC/ja4 |

**curl_cffi caveats**: the available targets for `impersonate` change across versions; the default behavior of extension order randomization may differ from real browsers, so `extra_fp.tls_permute_extensions = True` must be set explicitly. See https://github.com/lexiforest/curl_cffi/issues/529

## Detection Side: How Sites Use These Fingerprints

1. **TLS fingerprint does not match the UA** → immediately judged a script (the cheapest and most effective first gate)
2. **Abnormal H2 pseudo-header order** → same as above
3. **JA4 compared against a known browser version database** → a match is let through, a miss is challenged
4. **The same JA4 appears at high frequency** → correlate with the IP pool for rate limiting

**Corollary**: forging a UA without changing the TLS/H2 fingerprint is **negative value** — the inconsistency itself is a strong signal.

## Three-Layer Fingerprint Alignment Principle

One general principle applicable to both Chinese and Western risk control: **every layer on the request path must be self-consistent**.

| Layer | Items that must be consistent |
|---|---|
| TLS | JA3/JA4, cipher order, extension set, ALPN |
| HTTP/2 | SETTINGS, WINDOW_UPDATE, pseudo-header order |
| HTTP | header order and set, UA, `Accept-Language`, `Accept-Encoding` |
| JS environment | `navigator.userAgent`, `navigator.platform`, `navigator.languages`, timezone |
| Network | IP geolocation, timezone, and language all consistent |
| Device | a plausible combination of `screen`, `devicePixelRatio`, WebGL renderer |

**Inconsistency at any single layer can cause a significant drop in pass rate** — this matters more than any single-point technique.

## Quick Self-Check

```python
# Check whether your own TLS fingerprint looks like a browser
from curl_cffi import requests
r = requests.get("https://tls.browserleaks.com/json", impersonate="chrome")
print(r.json())   # compare ja3_hash / ja4 / akamai_hash
```

Items to compare: `ja3_hash`, `ja3n_hash`, `ja4`, `akamai_hash`, `akamai_text`.

## Sources

- JA4 specification and implementation: https://github.com/FoxIO-LLC/ja4
- JA4 technical details: https://github.com/FoxIO-LLC/ja4/blob/main/technical_details/JA4.md
- JA4H technical details: https://github.com/FoxIO-LLC/ja4/blob/main/technical_details/JA4H.md
- JA4 license FAQ: https://github.com/FoxIO-LLC/ja4/blob/main/License%20FAQ.md
- JA3 official implementation (archived): https://github.com/salesforce/ja3
- curl_cffi FAQ: https://curl-cffi.readthedocs.io/en/latest/faq.html
- curl_cffi extension randomization issue: https://github.com/lexiforest/curl_cffi/issues/529
- Cloudflare JA3/JA4 configuration: https://developers.cloudflare.com/bots/additional-configurations/ja3-ja4-fingerprint
- Cloudflare JA4 signals: https://blog.cloudflare.com/ja4-signals

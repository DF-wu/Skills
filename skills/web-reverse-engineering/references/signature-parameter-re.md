# Signature & Encrypted Parameter RE

The most common task in web reverse engineering is "an endpoint carries one or more encrypted parameters that have to be generated locally". This document gives a systematic method for locating and reproducing them.

## Locating workflow (locate first, then reproduce)

```text
1. Capture traffic and flag every suspicious parameter (irregular long strings, hex, base64, short timestamps, incrementing IDs)
2. Determine how many parameters there are and how they relate (one or several? do they depend on each other?)
3. Search the parameter name globally -> no result means it has been obfuscated (see below)
4. Set an XHR/fetch breakpoint and walk back up the call stack to the generation point
5. Determine the encryption type (see "Algorithm identification")
6. Pick a reproduction route: code extraction / environment simulation / RPC
```

### Four techniques when the parameter name cannot be found

Obfuscated parameter names are the norm (GeeTest, for example, replaces every key parameter). Options:

1. **Step through the stack slowly** — the most primitive but the most reliable
2. **Hand-write an AST pass to restore the obfuscated code**
3. **Locate it by AST memory roaming**
4. **Run it through an online deobfuscator, then reconsider**

Recommended combination: deobfuscate variable names first -> save the JS locally -> enable Local Overrides -> at that point you can search for keywords and debug.

### Breakpoint selection

| Target | Breakpoint location |
|---|---|
| Request parameters | `XMLHttpRequest.prototype.send` / `XMLHttpRequest.prototype.setRequestHeader` / `window.fetch` |
| Cookie generation | the setter of `document.cookie` |
| Fingerprint generation | entry of the function where the characteristic parameter name lives |
| Trajectory-related | mouse / touch event listeners |

```js
// XHR parameter interception: log the full parameters of every request
const XHR_open = XMLHttpRequest.prototype.open;
const XHR_send = XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.open = function (method, url) {
  this.__url = url; this.__method = method;
  return XHR_open.apply(this, arguments);
};
XMLHttpRequest.prototype.send = function (body) {
  console.log('[XHR]', this.__method, this.__url, body);
  return XHR_send.apply(this, arguments);
};
```

## Algorithm identification

### crypto-js signatures

**Important status**: crypto-js is **officially discontinued**. README wording: "Active development of CryptoJS has been discontinued. This library is no longer maintained."

**Module list (usable directly as a fingerprint dictionary)**:

| Category | Module names |
|---|---|
| Core | `core`, `x64-core`, `lib-typedarrays` |
| Digest | `md5`, `sha1`, `sha256`, `sha224`, `sha512`, `sha384`, `sha3`, `ripemd160` |
| HMAC | `hmac-md5`, `hmac-sha1`, `hmac-sha256`, `hmac-sha224`, `hmac-sha512`, `hmac-sha384`, `hmac-sha3`, `hmac-ripemd160` |
| KDF | `pbkdf2`, `evpkdf` |
| Ciphers | `aes`, `tripledes`, `rc4`, `rabbit`, `rabbit-legacy` |
| Formats | `format-openssl`, `format-hex` |
| Encodings | `enc-latin1`, `enc-utf8`, `enc-hex`, `enc-utf16`, `enc-base64` |
| Modes | `mode-cfb`, `mode-ctr`, `mode-ctr-gladman`, `mode-ofb`, `mode-ecb` (**CBC is the default, so there is no standalone module**) |
| Padding | `pad-pkcs7` (default), `pad-ansix923`, `pad-iso10126`, `pad-iso97971`, `pad-zeropadding`, `pad-nopadding` |

**Identifying traits**:

- Call signature `CryptoJS.AES.encrypt(msg, key, {iv, mode: CryptoJS.mode.CBC, padding: CryptoJS.pad.Pkcs7})`
- The ciphertext is a `WordArray`; read `CipherParams.ciphertext`
- **OpenSSL-format ciphertext begins with the ASCII bytes `Salted__` (8 bytes) followed by an 8-byte salt**; the key is derived by **EVPKDF** (192 words / 768 bytes discarded by default)
- Output conversion `.toString(CryptoJS.enc.Utf8)` / `.toString(CryptoJS.enc.Base64)` / `.toString(CryptoJS.enc.Hex)`

**Version traps**:

- **3.2.0 has a CRITICAL BUG; the README explicitly marks it "DO NOT USE THIS VERSION"**
- From 4.0.0 onward, `Math.random()` was replaced by the native crypto random source
- 4.1.0 added a URL-safe base64 variant
- 4.2.0 changed the PBKDF2 default hash and iteration count, and added Blowfish and a custom KDF Hasher

### Chinese national cryptographic standards (SM2 / SM3 / SM4)

```js
const sm2 = require('sm-crypto').sm2
let keypair = sm2.generateKeyPairHex()          // publicKey (130 chars) / privateKey
sm2.compressPublicKeyHex(publicKey)             // compress to 66 chars
const cipherMode = 1                            // 1 = C1C3C2 (default), 0 = C1C2C3
sm2.doEncrypt(msg, publicKey, cipherMode)
sm2.doDecrypt(encryptData, privateKey, cipherMode)

const sm3 = require('sm-crypto').sm3
sm3('abc')                                      // digest
sm3('abc', { key: '<hex or byte array>' })      // HMAC

const sm4 = require('sm-crypto').sm4
sm4.encrypt(msg, key)                           // hex output by default, pkcs#7 by default
sm4.encrypt(msg, key, { padding: 'none', output: 'array' })
sm4.encrypt(msg, key, { mode: 'cbc', iv: '<32 hex>' })
```

**Reverse-engineering identification points (pitfalls the README documents explicitly)**:

- **SM2 decryption automatically prepends the `04` prefix.** If the ciphertext comes from another tool and already contains `04`, **it must be stripped manually before being passed in** — this is a key clue for identifying which tool produced the ciphertext
- The SM2 signature `hash` parameter defaults to `true` (it applies an SM3 digest); pure signing requires `hash: false` explicitly. The default `userId` is `1234567812345678`
- `der: true` enables DER encode/decode; `pointPool` accepts pre-generated elliptic-curve points for speed
- The SM4 key must be 128 bits; passing `pkcs#5` also goes through pkcs#7 padding

### Modified / permuted Base64

**Mechanism**: two cases — (1) a new encoding table is defined directly; (2) the new encoding table is generated dynamically. Both can be decoded equivalently by "recovering the table that was used at encode time".

**Identification and recovery**:

- **Static trait**: a 64-character string constant appears in the source, and its character set is a **permutation** of the RFC 4648 alphabet `ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/` (the URL-safe variant is `+/` -> `-_` with `=` omitted)
- **Dynamic trait**: the table is assembled at runtime from `charCodeAt` / bitwise operations (you must dump it after it is generated)
- **Recovery**: extract the table -> build the inverse mapping -> decode
- **Quick heuristic**: try a standard base64 decode; if you get garbage but the **length is consistent (original length × 3/4)**, an alphabet permutation is highly likely

### RSA public-key extraction

**jsencrypt** is the most common RSA implementation on the web.

- Positioning: "A tiny (18.5 kB gzip), zero-dependency, Javascript library to perform OpenSSL RSA Encryption, Decryption, and Key Generation"
- Usage: `new JSEncrypt()` -> `setPublicKey(pemString)` / `setPrivateKey(pemString)`; **setting the private key derives the public key automatically**
- `encrypt()` returns a base64 string; `decrypt()` returns `false` on failure
- Signing: `signSha256(data)` / `verifySha256(data, signature)`; supported hashes are `md2`, `md5`, `sha1`, `sha224`, `sha256`, `sha384`, `sha512`, `ripemd160`
- OAEP: `encryptOAEP(data)`
- Supported formats: private key PKCS#1 (`-----BEGIN RSA PRIVATE KEY-----`), public key PKCS#8 (`-----BEGIN PUBLIC KEY-----`)
- Under the hood: Tom Wu's jsbn (the core algorithms are unchanged)

**PEM component ↔ jsbn variable mapping table** (compare directly against the in-memory object while reversing):

| PEM component | jsbn variable |
|---|---|
| modulus | `n` |
| public exponent | `e` |
| private exponent | `d` |
| prime1 | `p` |
| prime2 | `q` |
| exponent1 | `dmp1` |
| exponent2 | `dmq1` |
| coefficient | `coeff` |

**Public-key extraction in practice**:

1. grep the source for `BEGIN PUBLIC KEY` / `BEGIN RSA PRIVATE KEY`
2. Hook `JSEncrypt.prototype.setPublicKey` / `setPrivateKey` at runtime and print the arguments
3. The PEM body is base64, so `n` / `e` can be parsed out directly
4. The key commonly arrives from an API response (e.g. `RSAPublicKey` in the JSON returned by `GET Home/Form`)

## Signature structure patterns

| Pattern | Trait | Example |
|---|---|---|
| Pure digest | Fixed-length hex, 32/40/64 characters | `sign = md5(params + salt)` |
| Digest + salt | Same as above, but the salt has to be found | the salt is usually hard-coded or fetched from an API |
| Symmetric encryption | base64 or hex, length grows with the plaintext | AES/DES/SM4 |
| Asymmetric encryption | Fixed length (equal to the key length) | RSA/SM2 |
| Hybrid | **symmetric ciphertext + asymmetrically encrypted key** concatenated | `w = AES(data) + RSA(key)` (GeeTest) |
| Timestamp binding | Changes every time, short time window | `_ts`, `nonce`, `timestamp` |
| Incrementing sequence | Monotonically increasing | `subsid`, `seq` |

**The hybrid pattern dominates Chinese risk control**: GeeTest v3/v4 and Shumei v4 all use this structure. Identification method: split the parameter by length — if the leading segment's length varies with the content and the trailing segment has a fixed length, it is the hybrid pattern.

## Parameter ordering and concatenation pitfalls

In signing algorithms the parameter order is often obfuscated; check:

- Whether keys are sorted lexicographically (`Object.keys(params).sort()`)
- Whether empty values are filtered out
- Whether the URL path and the HTTP method are included
- Whether a timestamp and a random number are included
- Whether special characters are URL-encoded

**Debugging method**: build two requests that differ by exactly one parameter value, compare the signatures, and back out what is being concatenated.

## Timestamp and nonce

| Field | Common handling |
|---|---|
| Timestamp | seconds vs milliseconds; whether it is a string |
| Timezone | GeeTest v4 requires an ISO string in `+08:00` format |
| nonce | length and character set (hex / base64 / digits) |
| Expiry | the server-side validation window is typically 5–30 minutes |

## Choosing a reproduction route

| Route | Fits | Cost | Risk |
|---|---|---|---|
| **Code extraction** | self-contained algorithm, few dependencies | medium | breaks as soon as the site updates |
| **Environment simulation** | the algorithm depends on the browser environment | medium-low | detection points have to be handled |
| **RPC remote call** | complex algorithm, low request volume | low (first time) | low throughput |
| **Pure algorithm rewrite** | needs high throughput and long-term maintenance | high | requires complete understanding |

Decision rule: **ask about the request volume first**. Under 10,000 requests/day -> RPC is enough; over 100,000 -> a pure algorithm is mandatory.

## Sources

- Four techniques for locating GeeTest parameters: https://cloud.tencent.com/developer/article/1971174
- GeeTest deobfuscation and parameter recovery: https://github.com/yanglbme/geetest-crack
- GeeTest's full request chain and the `w` structure: https://www.cnblogs.com/zgq123456/articles/15266990.html
- crypto-js modules and versions: https://github.com/brix/crypto-js
- sm-crypto usage and pitfalls: https://github.com/JuneAndGreen/sm-crypto
- Analysis of modified Base64: https://bbs.kanxue.com/thread-251248.htm
- jsencrypt and the PEM mapping: https://github.com/travist/jsencrypt
- Shumei v4 encryption structure: https://cloud.tencent.com/developer/article/2475504
- Tongdun p1–p9 and the algorithm combination: https://cloud.tencent.com/developer/article/2501583

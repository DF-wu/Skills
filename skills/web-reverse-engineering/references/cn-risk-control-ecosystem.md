# China Risk-Control Landscape Overview

Risk-control strength on the Chinese internet is generally higher than on comparable European and American sites, and its shape differs: European and American sites rely mainly on TLS/fingerprinting, whereas Chinese sites rely mainly on a three-layer combination of **dynamic scripts + device fingerprints + parameter signing**. Understanding this ecosystem is the first step in choosing the right route.

## Vendor matrix

| Vendor | Product/identifier | Core mechanism | Community-flagged difficulty | Verifiable characteristics |
|---|---|---|---|---|
| **RiverSecurity (Ruishu)** | Botgate | dynamic wrapping/verification/obfuscation/tokens, VM + eval | control-flow flattening, WASM, slider trajectory, concurrent environments | `FSSBBIl1UgzbN7N80S`; 202/412 status codes (see `ruishu-river-security.md`) |
| **Aliyun Cloud Shield / Aliyun WAF** | ESA / WAF 3.0 | cookie session tracking + JS challenge + slider | control-flow flattening, WASM, slider trajectory | `acw_tc`, `cdn_sec_tc`, `acw_sc__v2`, `acw_sc__v3`, `ssxmod_itna*`, parameters beginning with `140#`, `227!` prefix + `fireyejs.js` |
| **Tencent** | TCaptcha (Tenyu/Waterproof Wall) | JSVMP device fingerprint + PoW | jsvmp, dynamic JS, concurrent IP requirements, AIGC image library | `tdc.js`, `collect`, `eks`, `ans`, `pow_answer`, `__TENCENT_CHAOS_VM` |
| **NetEase Yidun** | NECaptcha / risk-control SDK | device fingerprint + behavioral trajectory | mixed parameters, concurrent environments | `163` domain, `data`, `fp`, `cb`, `gdxidpyhxdE` |
| **Shumei** | Tianwang / device fingerprint | device fingerprint + content risk control | none (the community considers it the easiest) | `fverify` request, `organization`, `smidV2`, `smDeviceId`, `shumeiBlockBox` |
| **Dingxiang** | Intelligent Passive Verification / ConstID | dynamic JS + environment verification | dynamic JS, many verification environments, many CAPTCHA types | `ac` encrypted parameter, `ak`, `DXCaptcha`, `DXRiskManager` |
| **Tongdun** | device fingerprint / tdCaptcha | Blackbox fingerprint + slider | dynamic JS | `fm.js` + `blackbox`; `tdCaptcha.js` + `p1`~`p9` |
| **GeeTest (Jiyan)** | Sensebot / GeeGuard | trajectory + fingerprint + PoW | none | `geetest` identifier and domains (see `captcha-vendors-cn.md`) |
| **vaptcha** | -- | gesture recognition | gesture recognition | `vaptcha-sdk.js` |

> The difficulty column is the community's own wording (source: https://1997.pro/archives/1713518394359); it is not an official rating and serves only as a rough workload estimate.

### Aliyun: three injection scenarios (verifiable from official docs)

Aliyun's compliance statement splits cookie injection into three **mutually non-overlapping scenarios**, which is far more useful than memorizing cookie names -- it tells you **why** a given cookie appears:

| Scenario | Trigger condition | Injected cookie | Purpose |
|---|---|---|---|
| **One** | CC protection / scan protection is in use and the request cookie **does not contain** `acw_tc` | `acw_tc`, `cdn_sec_tc` | distinguish and count different clients; together with the scan protection and custom frequency rules whose "statistical object is session", determine CC attacks |
| **Two** | the site configures Bot management advanced mode and enables automatic Web SDK integration | `ssxmod_itna`, `ssxmod_itna2`, `ssxmod_itna3` | collect fingerprints (including the HTTP message `host` field, browser height/width, etc.) |
| **Three** | a WAF custom rule or Bot management rule action enables JS verification/slider | **JS verification passed** -> `acw_sc__v2`; **slider passed** -> `acw_sc__v3` | proof of passing verification |

So the semantics are: `acw_tc` = client session tracking; `cdn_sec_tc` = same-class session marker; `acw_sc__v2` = JS challenge credential; `acw_sc__v3` = slider credential. **All of the above is explicitly stated in the official docs, not community inference.**

Additional official operational details (useful for judging session lifetime): after verification passes, traffic is allowed by default within **1800 seconds (30 minutes)**, configurable 5-1800 seconds; in WAF 3.0 the tracking cookie (`acw_tc`) allows configuring the issuance state and `secure`, and **`SameSite` cannot be configured for now**; the slider cookie (`acw_sc__v3`) allows configuring `secure`.

Sources: https://help.aliyun.com/zh/waf/web-application-firewall-3-0/web-application-firewall-3-0-security-compliance-instructions , https://help.aliyun.com/zh/waf/web-application-firewall-3-0/protected-objects-and-protected-object-groups , https://help.aliyun.com/zh/edge-security-acceleration/esa/support/http-header

### The generation algorithm of `acw_sc__v2` (community-reproducible, not official)

Multiple independent sources agree: `acw_sc__v2 = hexXor(unsbox(arg1))`, where `arg1` is **a 40-character hex string supplied by the inline script in the server's 202 response, changing on every page refresh**.

- `unsbox` is a **character rearrangement** (restoring the order according to the fixed 40-element permutation table `[15,35,29,24,33,16,1,38,10,9,19,31,40,27,22,23,25,13,6,11,39,18,20,8,14,21,32,26,2,30,7,4,17,5,3,28,34,37,12,36]`)
- `hexXor` is a **byte-by-byte XOR with a fixed key**, key `3000176000856006061501533003690027800375`
- It finally triggers `reload(arg2)`, and `arg2` is the cookie value that gets written

In the original JS this key appears as the variable `_0x5e8b26`, and the script begins with an environment probe (`while (window["_phantom"] || window["__phantomas"]) {}`) -- **this line shows that it at least detects PhantomJS-class headless environments**.

**This is a fixed algorithm, not a dynamic VM**, so it is the least laborious layer in the Alibaba system. The real difficulties are scenario two (`ssxmod_itna*` fingerprint) and the slider (`acw_sc__v3` trajectory).

Source: https://www.cnblogs.com/wyh0923/p/16590583.html

## Layered decision-making: first determine "which layer is blocking you"

This is where Chinese risk-control reverse engineering most easily goes wrong. **Most failures come from attacking the wrong layer**.

```text
request fails
  |
  |- returns 202 / 412, response body is inline JS   -> RiverSecurity layer (environment simulation / pure algorithm)
  |- returns 200 but the content is a <script> challenge page -> JS challenge layer (acw_sc__v2 class)
  |- returns 403 and the cookie name identifies a vendor -> vendor WAF layer
  |- page is normal but the endpoint returns 403/parameter error -> signed-parameter layer (sign/token/blackbox)
  |- page is normal but the endpoint returns a risk-control code -> device-fingerprint layer (fingerprint must be self-consistent)
  |- everything is normal but it expires after a few minutes -> session/token lifetime layer
```

**Key insight**: Chinese sites often deploy **several layers at once**. For example, after passing the challenge layer on a RiverSecurity generation-6 site, the business endpoints still **independently verify the fingerprint** -- "a short cookie can get past the page, but the data query endpoint verifies the fingerprint" is a phenomenon the community has repeatedly confirmed. **Getting past the first layer does not mean clearing the game**.

## General countermeasures (cross-vendor)

### 1. Environment simulation (bu-huanjing) (mainstream, best cost-performance)

Construct a browser environment in Node that is convincing enough to fool the detection, and run the site's code directly to produce the parameters. See `environment-simulation-jsvmp.md` for details.

Recommended starting point: [`pysunday/sdenv`](https://github.com/pysunday/sdenv) (based on a modified jsdom; the community rates it "the most comfortable, fast and stable").

### 2. Hook + global export

"Pull" the generating function out of its closure and call it in a real or simulated environment.

| Target | Hook point |
|---|---|
| Cookie generation | the setter of `document.cookie` |
| Yidun fingerprint | the setter of `window["gdxidpyhxde"]` |
| Fingerprint generating function | globally search for the characteristic parameter name -> breakpoint -> attach the function to `window` |
| Request parameters | `XMLHttpRequest.prototype.send` / `fetch` |

```js
// Cookie setter hook: locate the generation point
let cookieTmp = '';
Object.defineProperty(document, 'cookie', {
  get() { return cookieTmp; },
  set(v) {
    console.log('[cookie set]', v);
    debugger;              // the call stack here reveals the generating function
    cookieTmp = v;
    return v;
  },
});
```

### 3. Reusing the Webpack loader

For self-executing-function-style obfuscated bundles, there is no need to extract code line by line:

1. Globalize the webpack loader (`__webpack_require__`)
2. Add logging to the loader
3. Pair it with an `env.js` environment simulation
4. Use `main.js` to call `loader.js` and invoke the target module directly

### 4. RPC remote invocation

Do not restore the algorithm locally at all: start a resident browser process, and have local code send parameter requests to the browser over WebSocket, so that the real browser environment computes them and sends them back.

**Applicable**: the algorithm is complex but the request volume is low; or as the first step of "get it running first, optimize later".
**Cost**: low per-machine throughput, and you need to manage a browser pool.

### 5. Trajectory generation

Slider/click-select types need trajectories:

- Bezier curves
- ease-in-out cubic easing
- AI-generated trajectory functions

### 6. UA consistency (most easily overlooked, highest payoff)

**The UA of the JS environment must match the request UA**. A measured report from a Yidun scenario: after the fix, the pass rate rose from <20% to 100%.

## Common failure modes

| Symptom | Real cause | Fix |
|---|---|---|
| After environment simulation, a cookie is produced locally but the request is still rejected | the fingerprint is not self-consistent (`screen`/`devicePixelRatio`/WebGL combination is implausible) | use an environment snapshot collected from a real browser; do not hardcode item by item |
| Parameters are generated correctly but the endpoint returns risk control | the request UA / TLS fingerprint is inconsistent with the JS environment | align all three fingerprint layers |
| Environment simulation reports a missing property | only "breadth" was filled in, not "depth" | modern risk control detects relationships between properties and property descriptors |
| It works locally but stops working the next day | the site's algorithm iterated, or a dynamic value such as `$_ts` changed | do dynamic matching (regex/AST); do not hardcode |
| Selenium/Playwright run directly and get detected | automation-feature detection | do not expect browser automation to bypass this directly; switch to environment simulation or RPC |

## Mobile app hardening (an accompanying problem)

App-side reverse engineering frequently runs into hardening shells, which is a separate front from web risk control.

| Generation | Technical characteristics | Unpacking difficulty | Representative tools |
|---|---|---|---|
| Generation 1: whole-DEX encryption | whole Dex encrypted, dynamically loaded | relatively easy, memory dump | FRIDA-DEXDump, Dexhunter, elf-dump-fix |
| Generation 2: DEX function extraction | methods individually extracted and encrypted, decrypted then executed | restorable (dump the runtime method bodies and backfill the dex) | FART, Youpk, BlackDex, Dex2oatHunter |
| Generation 3: VMP / Dex2C | standalone virtual machine interpretation / semantics-equivalent syntax migration | **Dex2C currently has no way to be restored, only traced and analyzed**; VMP protects the mapping table and can be manually restored | no mature automated tooling |

Verifiable tooling limitations:

- **FART** only provides Android 6.0 and 8.0 images; the original version cannot cope with root detection, while **Fart8** erased the fingerprint and can cope. Because the project is well known, **hardening vendors have already blacklisted FART's features**.
- **frida-fart** requires copying `fart.so`/`fart64.so` into `/data/app` and `chmod 777`; it is started with `spawn`, and `fart()` is executed after entering the Activity. The advanced usage `dump(classname)` can actively dump methods that have never executed (more effective against function-extraction shells). **Drawback: it cannot handle shells with anti-debugging** -- paid hardening always ships anti-debugging, which recognizes the frida signature, leaving it stuck on the splash screen with frida-server dead.
- **BlackDex** is based on a plugin-style idea, running the target app as a plugin inside its own process. **Because it is open source, its signature is obvious and hardening vendors can easily counter it**.

**Shell signature identification**: the fifth generation of the Ijiami shell shows `IJMDal.Data` under `assets`.

> The lists of characteristic `so` filenames per vendor (Ijiami/Bangcle/Legu/Ju'anquan/Yidun/Tongfudun/Nagain) differ between secondary sources and are **unverified**; actual identification should be based on the live `lib/` directory listing and the loading flow.

## Sources

- Community risk-control collection (difficulty/characteristic table): https://1997.pro/archives/1713518394359
- Aliyun cookie injection scenarios (official): https://help.aliyun.com/zh/waf/web-application-firewall-3-0/web-application-firewall-3-0-security-compliance-instructions
- Aliyun protected-object settings (`acw_tc` configurable items): https://help.aliyun.com/zh/waf/web-application-firewall-3-0/protected-objects-and-protected-object-groups
- Aliyun HTTP header example: https://help.aliyun.com/zh/edge-security-acceleration/esa/support/http-header
- `acw_sc__v2` algorithm (Python + JS source, including the `_0x5e8b26` key): https://www.cnblogs.com/wyh0923/p/16590583.html
- RiverSecurity generation 4/5/6 analyses: https://www.cnblogs.com/ikdl/p/16453681.html , https://www.cnblogs.com/ikdl/p/16647423.html , https://www.cnblogs.com/ikdl/p/17778885.html
- RiverSecurity generation 6 environment-simulation field report: https://blog.csdn.net/2401_85468967/article/details/148050084
- Shumei v4 device ID: https://cloud.tencent.com/developer/article/2475504
- Tongdun BlackBox: https://1997.pro/archives/1706068432055
- Tongdun v2 slider p1~p9: https://cloud.tencent.com/developer/article/2501583
- Yidun fp / gdxidpyhxdE: https://blog.csdn.net/weixin_46625757/article/details/145442263
- Yidun slider full parameter set: https://blog.csdn.net/Bushixiana/article/details/149002049
- Dingxiang request chain and parameters: https://www.cnblogs.com/boycelee/p/14270112.html
- Three-generation hardening taxonomy: https://blog.csdn.net/weixin_39190897/article/details/114269713
- Hardening and unpacking in practice: https://juejin.cn/post/7423310754952675379

## Unverified list (verify before citing)

The following items differ between secondary sources or have only a single origin, and **should not be stated as fact**:

1. RiverSecurity's quantified claim of "2^32 algorithms x 2^24 variants x 2^128 keys" -- vendor wording only, with no independent verification
2. The independent JS challenge cookie name and algorithm of Tencent Cloud WAF
3. Dingxiang error codes `-10001` ~ `-10007`
4. The complete field list of Tongdun's official Web SDK
5. The list of hardening characteristic `so` filenames per vendor (Ijiami/Bangcle/Legu/Ju'anquan/Yidun/Tongfudun/Nagain) -- secondary sources contradict each other; actual identification should be based on the live `lib/` directory and the loading flow
6. The complete chain of 360 hardening's `DtcLoader` / `/proc/self/maps` anti-debugging
7. The usage of `gee_guard` as a cookie name or parameter name ("GeeGuard is a device-fingerprint product name" is verified, but "appears as a cookie parameter" is not)
8. Some GeeTest versions pushing key logic down into WASM (AES-CBC + HMAC-SHA256)

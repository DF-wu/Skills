# CAPTCHA and Device-Fingerprint Vendor Deep Dive (GeeTest / Aliyun / Tencent / NetEase / Shumei / Dingxiang / Tongdun)

This document breaks down parameter structures vendor by vendor. **General principle**: first decide whether you are dealing with a "CAPTCHA" or a "device fingerprint" -- the two have different goals. A CAPTCHA must yield a `validate`/`token`; a device fingerprint must produce a stable `deviceId`/`blackbox`.

## GeeTest (Jiyan)

### Generation 3 (v3)

**Endpoint chain**:

| Step | Endpoint | Output |
|---|---|---|
| 1 | `register-slide-official` / `register-slider` / `register-click-official` | `gt` (site-fixed feature code), `challenge` (changes every time) |
| 2 | `gettype.php` | carries `gt`, returns the CAPTCHA type |
| 3 | `get.php` | `c`, `s`, slider image / background image |
| 4 | `ajax.php` | mode (`slide`/`click`); returns `validate` once passed |
| 5 | `validate.php` | server-side second validation |

**w parameter**: generation 3 has **three w values** (two from `get.php` + one from `ajax.php`).

- **Old version**: apart from the final `ajax.php`, w may be an empty string
- **New version**: the three w values are mutually linked, and **any one of them being wrong means `forbidden`**

**w composition**:

```
w = AES(plaintext) + RSA(16-char random string key)
```

The AES plaintext contains `gt`, `challenge`, the user IP, version, `c`, `s`, browser information, and the mouse trajectory. The RSA part is a 16-character random string encrypted with the RSA public key.

**Details**: `h9s9` and the like are fixed parameters; for generation-3 click-select, the AES **iv is `0000000000000000`**.

**Locating trick**: globally search for the signature `"\u0077"` (that is, the Unicode escape of `w`) to get into `slide.X.Y.Z.js` / `click.X.Y.Z.js`.

### Generation 4 (v4)

| Item | Value |
|---|---|
| Site identifier | only `captcha_id` (no `gt`/`challenge`) |
| load endpoint | `gcaptcha4.geetest.com/load` |
| verify endpoint | `gcaptcha4.geetest.com/verify` |
| load returns | `lot_number`, `captcha_type`, `bg`, `slice`, `ypos`, `pow_detail` (`version`/`bits`/`datetime`/`hashfunc`), `payload`, `process_token`, `payload_protocol` |
| verify parameters | `lot_number`, `payload`, `process_token`, `payload_protocol`, `pt`, `w`, `callback` |
| verify returns | `result: success/fail` |

**w structure**:

```
w = hex(AES_CBC(w_data, aes_key)) + hex(RSA_Encrypt(aes_key))
```

**PoW**: perform a hash collision according to `pow_detail.bits` and `hashfunc`, producing `pow_msg` / `pow_sign`.

**Other fields**:

- `device_id` (fixed for the same site)
- `userresponse` (the community gives `setLeft / 1.0059466666666665 + 2`; this is an empirically fitted value and must be calibrated by measurement against the target)
- `passtime`
- **The time format must be an ISO string carrying the `+08:00` timezone**

**JSONP trap**: the response is JSONP, so you must **locate `(` / `)` dynamically to parse it**; you cannot hardcode offsets -- the callback name length varies with the timestamp.

> The claim that some versions push key logic down into WASM (AES-CBC + HMAC-SHA256) comes from the community; this round **found no citable source, so it is unverified**. If you hit a WASM path, see `wasm-reverse-engineering.md`.

### GeeGuard (device fingerprint, not a CAPTCHA)

`gee_guard` / GeeGuard is GeeTest's **device-fingerprint product**, not a CAPTCHA endpoint. Its capability is to locally generate a short-lived trusted-device GeeToken and to **bidirectionally bind** it to the business party's unique business identifier (by signature, valid only for the current business flow).

HarmonyOS SDK permissions: `INTERNET` / `GET_NETWORK_INFO` / `STORE_PERSISTENT_DATA`, optionally `APP_TRACKING_CONSENT` (OAID).

> The usage of `gee_guard` as a cookie name or parameter name is **unverified**; what is verified is only that GeeGuard is a product name.

**Collection surface disclosed in the official privacy policy** (directly usable for inferring the detection dimensions): device information, device network information, device environment information (including jailbreak/debugging/emulator/code-tampering indicators, UA, referer), **user biometric trajectory information** (slide/click/mouse-movement trajectories), timestamp, installer package name.

## Aliyun Cloud Shield / Aliyun WAF

### Cookie system (explicitly stated in official docs)

The official Aliyun compliance statement gives **three injection scenarios**:

| Scenario | Trigger condition | Injected cookie | Purpose |
|---|---|---|---|
| One | CC protection / scan protection is in use and the request cookie does not contain `acw_tc` | `acw_tc`, `cdn_sec_tc` | distinguish and count different clients; together with the protection rule whose "statistical object is session", determine CC attacks |
| Two | the site configures Bot management advanced mode and enables automatic Web SDK integration | `ssxmod_itna`, `ssxmod_itna2`, `ssxmod_itna3` | collect fingerprints (including the HTTP message `host` field, browser height/width, etc.) |
| Three | a WAF custom rule or Bot management rule action enables JS verification / slider | `acw_sc__v2` (JS verification passed), `acw_sc__v3` (slider passed) | proof of passing verification |

**Official details**:

- Action expiry time: after verification passes, traffic is allowed by default within **1800 seconds (30 minutes)**; configurable 5-1800 seconds
- WAF 3.0 protected-object settings: the tracking cookie is `acw_tc`, whose issuance state and `secure` attribute are configurable, and **the `SameSite` attribute cannot be configured for now**; the slider cookie is `acw_sc__v3`, whose `secure` is configurable
- `acw_tc` example value: `2f7b12da17525774695245703ee21f15714874ac9b5788522f6bf6f459`, `path=/; HttpOnly; Max-Age=3600`

**Conclusion mapping**:

- `acw_tc` = client session tracking cookie
- `cdn_sec_tc` = same-class session marker (marks different client sessions, counts how often the same session launches attacks)
- `acw_sc__v2` = JS challenge pass credential
- `acw_sc__v3` = slider verification pass credential

### `acw_sc__v2` generation algorithm (community-reproducible)

```python
def unsbox(arg1):
    box = [15,35,29,24,33,16,1,38,10,9,19,31,40,27,22,23,25,13,6,11,39,18,20,8,
           14,21,32,26,2,30,7,4,17,5,3,28,34,37,12,36]
    res = list(range(0, len(arg1)))
    for i in range(0, len(arg1)):
        j = arg1[i]
        for k in range(0, 40):
            if box[k] == i + 1:
                res[k] = j
    return "".join(res)

def hexXor(arg2):
    box = "3000176000856006061501533003690027800375"
    res = ""
    for i in range(0, 40, 2):
        res += hex(int(arg2[i:i+2], 16) ^ int(box[i:i+2], 16))[2:].zfill(2)
    return res

def get_acw_sc_v2(arg1):
    return hexXor(unsbox(arg1))
```

That is, `acw_sc__v2 = hexXor(unsbox(arg1))`.

- `arg1` is a **40-character hex string that changes dynamically on every refresh** (supplied by the inline script in the 202 response)
- `arg2` is the final cookie value

**Original JS characteristics**: it contains the infinite loop `while (window["_phantom"] || window["__phantomas"]) {}` (aimed at Selenium/Phantomas-class automation) and `var _0x5e8b26 = "3000176000856006061501533003690027800375";`, and finally triggers `reload(arg2)`.

**Countermeasure flow**: use a regex or DOM parsing to pull the inline `arg1` out of the 202 page -> run `unsbox` + `hexXor` locally -> replay while carrying `acw_sc__v2`.

**Two Alibaba-family systems** (community risk-control collection): encrypted parameters beginning with `140#`, and the `227!` prefix + `fireyejs.js`, plus control-flow flattening / WASM / slider trajectory.

## Tencent TCaptcha (Tenyu / Waterproof Wall)

### File inventory (original Kanxue analysis)

| File | Size | Role | Obfuscation level |
|---|---|---|---|
| `TCaptcha.js` | -- | entry point / loader | low |
| `tcaptcha-frame.js` | 207KB | main frame logic | medium (Webpack) |
| `dy-ele.js` | 209KB | slider core logic | medium (Webpack) |
| `tdc.js` | 78KB | device fingerprint collection | extremely high (JSVMP) |

### verify endpoint parameters

| Parameter | Meaning |
|---|---|
| `collect` | TDC-encrypted device fingerprint + trajectory data |
| `tlg` | length of `collect` |
| `eks` | encrypted key information generated by TDC |
| `sess` | session identifier |
| `ans` | slider answer JSON |
| `pow_answer` | PoW result |
| `pow_calc_time` | PoW elapsed time in milliseconds |
| `subsid` | sub-session ID, incrementing |
| `callback` | JSONP callback name, of the form `_aq_191730` |

### JSVMP details

`tdc.js` uses Tencent's in-house `__TENCENT_CHAOS_STACK` / `__TENCENT_CHAOS_VM` custom bytecode interpreter, with the bytecode **inlined as a huge array of tens of thousands of numbers**; all core encryption logic executes inside the VM.

There is also a random variable name storing `eks`, for example `window.KcYVdONjSbHEDgmXanKNEdRPYPMTPdOh`, **which changes on every load** -- this makes hook scripts unstable.

**Common TDC call shapes**:

```js
collect = decodeURIComponent(window.TDC.getData(true));
eks     = window.TDC.getInfo().info;
window.TDC.setData({ ft: "q__7Pf__H" });
```

**PoW**: brute-force search for `md5(nonce + counter) === target`, returning `ans` (the counter) and `duration`.

**Difficulties**: JSVMP + random variable names + a bytecode array of tens of thousands of numbers; the cost of static analysis and code extraction is extremely high.

> Whether Tencent Cloud WAF has an **independent named JS challenge cookie at the same level as Alibaba's `acw_sc__v2`: unverified**. The community often lumps `tdc.js` (which is actually TCaptcha) together with Tencent Cloud WAF; the two should be stated separately.

## NetEase Yidun

### Device-fingerprint query endpoint fields (official docs)

| Field | Type | Description |
|---|---|---|
| `taskId` | String | unique identifier of this query operation |
| `tokenCreationTime` | Number | token creation time (UNIX milliseconds) |
| `device.deviceId` | String | device fingerprint ID |
| `device.sdkType` | Number | 1-Web, 2-Android, 3-iOS, **4-mini program** |
| `checkResult.isTampered` | Number | whether the upload request was tampered with |
| `checkResult.isSimulator` | Number | whether it is an emulator |
| `checkResult.isRooted` | Number | whether Root/jailbroken |
| `checkResult.isMultiRun` | Number | whether multiple instances are running |
| `checkResult.isVpn` / `isProxy` | Number | VPN / proxy |
| `checkResult.isHooked` / `isInjected` / `isDebugged` | Number | hook / injection / debugging |
| `checkResult.isXposed` | Number | Xposed |
| `checkResult.isCloud` / `isSuspectCloud` | Number | cloud phone / suspected cloud phone |
| `checkResult.isRiskRom` / `isVm` / `isModify` / `isModifyApp` | Number | risky ROM / virtual machine / device modification / repackaging |
| `checkResult.isFlash` / `isAutoTouch` / `isControlApp` / `isScript` | Number | one-click reflash / auto-tap / device-farm control / script |
| `checkResult.securityScore` | Number | security score |
| `checkResult.isCydiaSubstrate` / `isM1` / `isSpeedUp` / `isAntiJailbreak` | Number | iOS-side risk items |

**Note**: the official docs title marks this device-fingerprint document as **"discontinued"**, and the integration method may already have migrated. The value of this table lies in **reverse-inferring the detection dimensions**.

### Web-side parameters (community)

- Domain characteristic `163`; parameters `data`, `fp`, `cb` (also `token`, `acToken`)
- The cookie / global property `gdxidpyhxdE` (`window["gdxidpyhxde"]`) is associated with `fp`: **generate the parameter first -> write it into the cookie -> then read the value from the cookie as `fp`**
- Locating: hook the setter of `window["gdxidpyhxde"]`
- `data` = the encrypted slider trajectory array, containing fields such as `atomTraceData` (unencrypted trajectory), `p`, `ext`, `m`
- Trajectory element triple: `[Math.round(dragX < 0 ? 0 : dragX), Math.round(clientY - startY), now() - beginTime]`
- `ext` = `f(token, mouseDownCounts + ',' + traceData.length)`
- The server returning `validate` means verification passed
- Parameter names carry version characteristics; community analyses cover 2.19.1 / 2.27.2 / 2.28.0 / 2.28.5
- **Environment requirement: the UA of the JS environment must match the request UA** (otherwise the pass rate drops noticeably)
- Type values: `7` = sequential click-select, `2` = slider

## Shumei

### v4 device ID generation

| Item | Value |
|---|---|
| Entry file | `fp.min.js` (obfuscated with ob) |
| Request parameters | `organization` (unique identifier of the Shumei product), `data`, `ep` |
| `ep` | `rsaEncrypt(uuid, publicKey)`; `publicKey` is returned by `api.js`; `uuid` is generated by `getUid` (standard UUID v4 form) |
| `data` | **the plaintext data after gzip compression**, then encrypted with **AES-CBC**: key = `priId`, **iv fixed at `0102030405060708`** |
| `priId` | **truncate** the uuid parameter passed in when generating `ep`, then apply standard **MD5** |
| plaintext content | browser environment, encryption parameters, etc.; `smid` is returned by `getLocalsmid()`; `MD5_Encrypt` is standard MD5 (`'smsk_web_' + ...` form) |
| `Protocol` | carries a dynamic DES key |
| `deviceId` form | obtained by prefixing the content returned by the v4 endpoint with `"B"` |
| Cookie | `smidV2` / `smDeviceId`, plus `shumeiBlockBox` |

### Slider

- Endpoints `register` (fetch the image and encryption information), `fverify` (verification; the v2 path is `/v2/fverify`)
- `organization` is an encrypted field
- `rid` is passed in by `register`; the parameters that actually vary number about three, and change mainly with **slide distance, slide time, slide trajectory**
- The encryption algorithm involves **DES-ECB + Zero Padding + Base64**
- `captchaUuid` = `generateTimeFormat()` + 16 random characters
- box-related: `boxId` starts with `'B'` and is 89 characters; `boxData` starts with `'D'` and is about 8K

### Official product capabilities (for understanding the detection surface)

Device fingerprint claimed capabilities: unique device identifier, fake-device detection, machine-operated device tags, suspicious-device tags (able to identify Root, no SIM card, VPN, device reset and twenty-odd other conditions), device attribute tags (50+ dimensions). **Risk environment detection** explicitly includes: detecting proxy servers, **device debugging state and runtime environment**, high-risk software, and identifying device farms, multi-instance apps, and so on.

> Vendor claims such as "duplicate rate as low as one in ten thousand" and "compatible with 32,000+ models" are marketing data and have not been independently verified.

## Dingxiang

### Officially verifiable content

- Product name "Intelligent Passive Verification"
- SDK classes `DXCaptchaView` / `DXCaptchaViewV5`; listeners `DXCaptchaListener` / `DXCaptchaEvent`
- The success callback returns a `token` (used for backend validation)
- **If the token starts with `sl`, it is a degraded token generated because the frontend network is unreachable**
- Parameters: `constID_js` / `constIDServer` / `constID_options` (no configuration needed inside the Android/iOS SDK), `captchaJS`, `keyURL`, `corsBaseURL` (v5.1.3r+)
- Events: `success` / `fail` / `onCaptchaJsLoaded` (v5.1.7r+) / `onCaptchaJsLoadFail`
- Device-fingerprint module class name `DXRiskManager` (the `ConstID` module), plus a `hardId` concept

### Request chain and parameters (community, 2019-2021 analyses, possibly outdated)

| Step | Endpoint | Output |
|---|---|---|
| 1 | `c1` | the `c` parameter (used to compute the device fingerprint) |
| 2 | `a` | image and `token2`; returns `sid`, `y`, `p1`/`p2`/`p3` (scrambled jigsaw webp paths) |
| 3 | `v1` | `token3` |

Parameter table: `ak` (fixed value associated with the AppId), `ac` (encrypted parameter, of the form `492#X8Xn8AQv/Y6pdvgYXXfOuMffR/...`), `aid` (timestamp + random number + 1, presumed nonce), `jsv` (version number, e.g. `1.3.11.98`), `sid`, `de`, `wp`, `s`/`h`/`w`, `_r`, `x`/`y`.

The fingerprint is stored in **multiple places**: cookie, Session Storage, Local Storage.

Failure response example: `{"data":"f8839e00435f2e05f9ed60b3d3c5498554cb367655ec6e7318adefda150437040a74963c","msg":"lid invalid","status":-4}`

> Dingxiang error codes `-10001` ~ `-10007`: **unverified**.

## Tongdun

### Passive (device fingerprint)

- File `fm.js`, parameter **`blackbox`**
- Parameter-name systems `a`/`b`/`c`/`d`... or `h`/`i`/`j`/`k`...
- **Historically the `blackbox` location was in the payload, and it later migrated to headers**
- Global config object `window._fmOpt` (containing `token`, `partner`, `appName`)
- `oO0QQo.mfaId` (possibly `undefined`)

### Slider `p1` ~ `p9` (v2)

| Parameter | Construction |
|---|---|
| `p1` | `blackBox` (`QQoooQ.blackBox`; may also be temporarily hardcoded) |
| `p2` | `blackBox + ^^1^^1^^1` |
| `p3` | `MD5(...)` (constant features are obvious, standard MD5) |
| others | `window._fmOpt.token` / `.partner` / `.appName` / `oO0QQo.mfaId` participate in the construction |

The encryption involves **AES** (iv of the form `Moa14C2uXpe8AUJ5`) and **DES3**.

**The image endpoint and the verification endpoint are the same endpoint, differing only in request parameters.** Verification result fields: `needValidateCode`, `validateToken`.

**Important note**: the community explicitly points out that "this analysis is only one of Tongdun's algorithms -- **it has more than one**" -- Tongdun has multiple parallel algorithms, so you must not assume a single implementation.

### TrustDecision (Tongdun's overseas brand)

Provides a lightweight JS and mobile SDK, claiming to output 70+ device risk labels and to support Web/iOS/Android/mini programs.

> The complete field list of Tongdun's official Web SDK: **unverified**.

## Cross-vendor comparison

| Vendor | Encryption algorithm characteristics | Fixed values/constants | Main difficulty |
|---|---|---|---|
| Alibaba | custom XOR + 40-byte permutation table | `3000176000856006061501533003690027800375` | inline arg1 changes dynamically + anti-automation infinite loop |
| GeeTest generation 3 | AES + RSA concatenation, three linked w values | click-select iv = all zeros | strong linkage of the three w values |
| GeeTest generation 4 | AES-CBC + RSA + PoW | -- | PoW collision + dynamic JSONP parsing |
| Tencent | in-house JSVMP bytecode | -- | bytecode array of tens of thousands of numbers + random variable names |
| Yidun | not fully public | `gdxidpyhxdE` cookie name | mixed parameter versions + UA consistency requirement |
| Shumei | AES-CBC (gzip preprocessing) + RSA + MD5 | iv = `0102030405060708` | relatively the lowest |
| Dingxiang | custom (`ac` of the form `492#...`) | -- | many environment-verification dimensions |
| Tongdun | AES + DES3 + MD5 | iv of the form `Moa14C2uXpe8AUJ5` | multiple parallel algorithms |

## Sources

- GeeTest generation 3 full chain: https://www.cnblogs.com/ikdl/p/17001212.html
- GeeTest generation 3 three linked w values: https://cloud.tencent.com/developer/article/2383906
- GeeTest generation 3/4 click-select and AES iv: https://www.cnblogs.com/ikdl/p/17272966.html
- GeeTest generation 4 w = AES+RSA + PoW: https://blog.csdn.net/weixin_42384784/article/details/160193114
- GeeTest GeeGuard integration guide: https://docs.geetest.com/guard/quick_integration_guide
- GeeTest privacy policy (collection surface): https://www.geetest.com/Private
- Aliyun compliance statement (cookie injection scenarios): https://help.aliyun.com/zh/waf/web-application-firewall-3-0/web-application-firewall-3-0-security-compliance-instructions
- Aliyun WAF 3.0 protected-object settings: https://help.aliyun.com/zh/waf/web-application-firewall-3-0/protected-objects-and-protected-object-groups
- Full `acw_sc__v2` implementation: https://www.cnblogs.com/wyh0923/p/16590583.html
- Tencent TCaptcha file inventory and JSVMP: https://bbs.kanxue.com/thread-290429.htm
- Tencent pure-protocol restoration research: https://github.com/decodecaptcha/TencentCaptchaBreak
- Yidun device-fingerprint field table: https://support.dun.163.com/documents/609099986339037184?docId=624010587874123776
- Shumei v4 device ID: https://cloud.tencent.com/developer/article/2475504
- Shumei slider: https://hyb.life/archives/209
- Dingxiang SDK docs: https://www.dingxiang-inc.com/docs/detail/captcha
- Dingxiang ConstID: https://www.dingxiang-inc.com/docs/detail/const-id
- Dingxiang request-chain analysis: https://www.cnblogs.com/boycelee/p/14270112.html
- Tongdun BlackBox: https://1997.pro/archives/1706068432055
- Tongdun v2 slider p1~p9: https://cloud.tencent.com/developer/article/2501583
- Community risk-control collection: https://1997.pro/archives/1713518394359

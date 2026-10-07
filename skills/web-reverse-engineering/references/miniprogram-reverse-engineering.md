# Mini-Program Reverse Engineering (WeChat / Alipay / Douyin / QuickApp)

Mini-programs are a separate reverse-engineering battlefield: package format, runtime model, and capture feasibility all differ from the Web.

## WeChat Mini-Programs

### The wxapkg file format

> **Empirical correction (important)**: `firstMark` and `lastMark` **each occupy 1 byte, not 2 bytes**. Many circulating documents write both as `Ushort`, and copying that directly leads to `struct.error: unpack requires a buffer of N bytes`. The complete header is **18 bytes**: `>B I I I B I` (1+4+4+4+1+4). The bundled `scripts/wxapkg_unpack.py` in this skill uses the corrected layout and has been empirically verified against a synthetic sample.

| Segment | Field | Type | Notes |
|---|---|---|---|
| header | `firstMark` | **1 byte** | Fixed `0xBE` (190) |
| header | `info` | Ulong (4 bytes) | Purpose unknown, usually 0 |
| header | `indexInfoLength` | Ulong (4 bytes) | Index segment length |
| header | `bodyInfoLength` | Ulong (4 bytes) | Data segment length |
| header | `lastMark` | **1 byte** | Fixed `0xED` (237) |
| header | `fileCount` | Ulong (4 bytes) | Number of files (offset 14) |
| index | `nameLength` | Ulong | Filename length |
| index | `name` | Char[] | Length = `nameLength` |
| index | `offset` | Ulong | File offset within the data segment |
| index | `size` | Ulong | File size |
| data | file data | — | Concatenated end to end |

**Real log example**:

```
Header info: firstMark: 0xbe unknownInfo: 0 infoListLength: 15360
dataLength: 2960164 lastMark: 0xed
fileCount: 375
```

The unpacking tool's first step is validating the `0xBE` / `0xED` magic numbers; a mismatch means it is not a wxapkg or has been encrypted/modified.

**Security note**: the index segment's `name` is **attacker-controlled input**. Parsing must reject `..`, absolute paths, drive letters, and symlink escapes, otherwise unpacking a malicious package will write outside the output directory. `scripts/wxapkg_unpack.py` has this validation built in and has been empirically verified to block `../../pwned.txt`.

### The counterintuitive structure after unpacking

The directory contains **no** `wxml` and **no** scattered `js` — only a few huge files at the root (typically `app-service.js` and `app-config.json`).

**Subpackage trap**: subpackages rely on deduplication, so **you must supply the main package directory when unpacking subpackages** (the tool's `-s` parameter); otherwise the restored wxml is missing components and the wxss is missing variables.

### Toolchain and maintenance status

| Tool | Repository | Language | Maintenance status |
|---|---|---|---|
| **KillWxapkg** | https://github.com/Ackites/KillWxapkg | Go | **Active**. Automatic decryption, unpacking, project-directory restoration, Hook support, repackaging (`-repack`), `-watch`, `-sensitive`; the README lists the mini-program versions supported by Hook (8447 ~ 11275_x64) |
| **wedecode** | https://github.com/biggerstar/wedecode | Node.js | **Active** (GPL-3.0). Supports mini-programs + mini-games + subpackages + plugins; restores JS/WXML/WXSS/WXS/JSON plus media, wasm, workers; ships a visual UI (`wedecode ui`), automatic decryption, and a polyfill mechanism |
| **wux1an/wxapkg** | https://github.com/wux1an/wxapkg | Go + Wails | **Active**. Cross-platform GUI (Windows/macOS), scan + decrypt + unpack + code beautification; CLI subcommands `scan`/`unpack`, 30 threads by default |
| unveilr | Kanxue post | Closed source | **New versions went closed source with subscription pricing**; 2.0 is the last free version in circulation |
| wxappUnpacker | https://github.com/Ryan-Miao/wxappUnpacker | Node.js | Historical version. The README states explicitly "current features are as follows (**subpackage support not yet complete**)" |
| CrackMinApp | https://github.com/Cherrison/CrackMinApp | C# + Node.js | **Effectively discontinued**. The README notes "latest bug fix **2019.10.24**" |
| Sec-Fork/KillWxapkg-2 | https://github.com/Sec-Fork/KillWxapkg-2 | Go | Fork, subset of features (`-restore`/`-pretty`/`-ext`) |

**Conclusion**: the only ones still active in 2024–2026 are **KillWxapkg**, **wedecode**, and **wux1an/wxapkg**.

### Package acquisition paths

| Platform | Path |
|---|---|
| Windows WeChat before 4.0 | `C:\Users\{user}\Documents\WeChat Files\Applet\{AppID}\{number}\__APP__.wxapkg` |
| Android | `/data/data/com.tencent.mm/MicroMsg/{userID}/appbrand/pkg/` (requires root or an emulator) |

**Technique for locating the target package**: capture traffic with Charles / the Nox emulator and locate the corresponding pkg from the request header `referer`.

> The xwechat path after WeChat 4.0 and the usage of `pc_wxapkg_decrypt.exe -wxid ... -in __APP__.wxapkg`: **unverified**.

### Request characteristics (must-read before capturing)

| Characteristic | Value |
|---|---|
| **referer fixed domain** | `servicewechat.com`, format `https://servicewechat.com/{appid}/{version}/page-frame.html`. **The referer of `wx.request` cannot be set** |
| User-Agent (Android) | The **`miniProgram`** marker is appended after the WeChat built-in browser UA |
| User-Agent (iOS) | **Identical to the WeChat built-in browser; cannot be distinguished by UA** |
| Promise style | `wx.request` **does not support** Promise-style calls (the official docs mark `with Promise style call: Not supported`) |
| Package size limit | Over 2MB requires subpackages; when migrating you must carry all subpackages |

**Corollary**: server-side referer restrictions, COS hotlink-protection whitelists, and CDN hotlink protection **must all allow `servicewechat.com`**.

### Cloud functions / Cloud Development calls

**Inside the mini-program**:

```js
wx.cloud.init({ env, traceUser })
wx.cloud.callFunction({ name, data, config })
```

**Server-side HTTP API**:

```
POST https://api.weixin.qq.com/tcb/invokecloudfunction?access_token=...&env=...&name=...
Params: env / name / req_data (or POSTBODY)
Returns: errcode / errmsg / resp_data
```

**Key limitation**: triggering a cloud function via the HTTP API **does not include user information** (you cannot obtain the OpenID, and cannot use APIs that involve user login state); timeout 5s. Error codes include `40014`, `40101`, `41001`, `42001`, `43002`, `44002`, `85088`.

**CloudBase OpenAPI**:

```
POST https://tcb-api.tencentcloudapi.com/api/v2/envs/${envId}/functions/${functionName}:invoke
```

**Cloud Hosting (CloudRun) calls**:

```js
wx.cloud.callContainer({
  config: { env },
  path, method,
  header: { "X-WX-SERVICE": "service-name" }
})
```

Differences from `wx.request`: intranet communication does not consume public-network traffic, only authorized mini-programs/official accounts can access it, there is no need to configure "server domains" in the mini-program console, and the backend can obtain the openid directly. Cross-environment calls need `resourceAppid` / `resourceEnv` (Cloud Development environment sharing).

Cloud Hosting error codes: `102002` request timeout (timeout max 15s), `-601034` no permission, enable Cloud Hosting first, `-606001` request body > 100KB, `-606002` response body > 1MB, `-606003` account in arrears, `-606006` unauthenticated-mode requests not allowed, `-601027` Environment not found, `-601031` service does not exist.

### Capture feasibility (key)

WeChat cloud requests fall into four categories:

| Type | Mechanism | Capturability |
|---|---|---|
| 1 | Calls the `OperateWxData` interface based on WeChat's **Mmtls** protocol, over WeChat's private channel | **Standard capture tools cannot capture it** |
| 2 | Based on **HTTP/2 + authentication**: first obtain encrypted parameters and an auth token through Mmtls `qbase_commit` → `tcbapi_get_service_info`; the request body is encrypted with a key and **compressed with snappy**; the data format is ProtoBuf or JSON; the decryption algorithm is **AES-CBC** | Requires decryption |
| 3 | Unauthenticated HTTP/2 (WeChat Cloud Hosting / cloud gateway, but not inside the mini-program) | Capturable |
| 4 | The WeChat cloud gateway based on **plaintext HTTP** (used by other Apps); capture tools with Socks can capture it | Capturable. The request headers carry **`x-wx-auth-code`** and **`x-wx-call-id`**, both computed from the URL and Body (**the algorithm is in the so layer**) |

**Downgrade capture approach**: trigger an exception via Frida hook to force the HTTP/2 cloud gateway to downgrade to `JSOperateWxData` / Mmtls, so that plaintext can be captured without dealing with AES (community projects target Android WeChat 848/849/850, and the downgrade cloud function targets 848/849).

> wxapkg package type identifiers `APP_V3` / `APP_V4` / `APP_SUBPACKAGE_V2` / `APP_PLUGIN_V1`: **unverified** (though the existence of `__WITHOUT_MULTI_PLUGINCODE__.wxapkg` and `__APP__.wxapkg` is corroborated by sources).

## Alipay Mini-Programs

**Packaging and runtime mechanism**:

- The client downloads an **offline package** from the CDN; it is a **`.tar` file** produced by packaging the original project
- Stored at `/data/data/com.eg.android.AlipayGphone/files/nebulaInstallApps`
- After extraction you get `index.html`, `index.js`, `index.worker.js`
- `index.worker.js` holds all page business logic (corresponding to the developer's `pageName.js`)
- `index.html` / `index.js` correspond to acss and axml (**axml component information and hierarchy are compiled into js** and rendered at runtime)

**Dual-thread model**:

| Thread | Content | Runtime environment |
|---|---|---|
| Render (view) | `index.js` + framework `af-appx.min.js` | WebView |
| Worker (app service) | `index.worker.js` + `af-appx.worker.min.js` | V8 engine |

**Code loading**: Render loads through the WebView's `loadUrl()`, and `af-appx.min.js` is written in dynamically via `writeln()`. You can **hook the `loadUrl` function of the `WVUCWebView` class** to observe loading.

Developer file types: `.axml` (analogous to HTML), `.acss` (analogous to CSS), `.js`.

> The community often refers to Alipay mini-program packages generically as `apkg`; the verifiable carrier is the **`.tar` offline package** delivered by the CDN. **The claim of an "`apkg` extension" is unverified**.

## Douyin Mini-Programs

**Format**: `TPKG` / `ttpkg.js` / `pkg` files, in two categories:

1. Mini-program packages with a plaintext index
2. A mini-game package index variant with a **`JSON{"__ttks":...}`** header

**Tool**: [`XueDugu/ttpkgUnpacker`](https://github.com/XueDugu/ttpkgUnpacker) (Python)

- Fixes plaintext `TPKG` index offset compatibility
- Adds `__ttks` encrypted-index decoding (recovers filenames, offsets, sizes)
- Automatically generates `unpack-report.json` / `unpack-report.md` (tree structure, file statistics, entry files)
- Automatically restores `app.json` and page `.json` files
- Prevents path-escape writes
- Built-in samples: `038d897.ttpkg.js` (plaintext mini-program), `e2670a8.pkg` (plaintext pkg), `8862e65.pkg` (mini-game `__ttks` index)

**Limitations**: some mini-game payloads may still carry business-side obfuscation, so **unpacking does not equal full deobfuscation**; the `ttss` / `ttml` rule-recovery logic remains fairly heuristic.

**Usage**:

```bash
python3 ttpkgUnpacker/main.py xxx.ttpkg.js
python3 -m ttpkgUnpacker <dir>
```

There is also `gitee.com/xipis/ttpkUnpacker` as another implementation.

## QuickApp

| Item | Value |
|---|---|
| Build artifact | **`.rpk`** files (e.g. `com.application.demo.rpk`) |
| Compiler toolchain | `hap-toolkit` (`npm run build` generates `build`/`dist`; the rpk is inside `dist`) |
| Page source files | `.ux` |
| Project configuration | `quickapp.config.js` |
| Local debugging | `npm run server` starts a local HTTP server (default 8000); the phone debugger scans the code to install |
| Device-side installation | Put the rpk into `sdcard/rpks` and run it with the "Platform Preview" build |
| Platform switching | The debugger can switch the runtime platform to `org.hapjs.mockup` |

**Official position (record of the 120th exchange session on the official QuickApp forum)**:

> Q: Can QuickApp rpk files be decompiled?
> A: **No.**

The Huawei QuickApp IDE provides an "Open RPK" feature (menu `File > Open RPK`); this is an **official forward-engineering tool**, not decompilation.

**Conclusion**: the community-verifiable path for QuickApp is "obtain the rpk + run it in the Platform Preview and observe", not static restoration.

## Unverified Items (verify before citing)

1. The wxapkg package type identifiers `APP_V3` / `APP_V4` / `APP_SUBPACKAGE_V2` / `APP_PLUGIN_V1`
2. The xwechat path after WeChat 4.0, and the usage of `pc_wxapkg_decrypt.exe -wxid ... -in __APP__.wxapkg`
3. `wx.getRendererUserAgent` (base library 2.26.3+) and `wx.cloud.CDN`
4. The Alipay mini-program package extension "`apkg`" (community accounts differ)
5. The possibility of static restoration for QuickApp rpk — the official answer is explicitly "No", but that is an **official position** rather than a technical proof; the community also has no publicly reproducible static-restoration approach

## Sources

- wxapkg structure table: https://daijunooo.github.io/2019/01/31/unpack
- wxapkg real log and subpackage `-s`: https://blog.poetries.top/2021/04/20/wx-compile-summary
- unveilr going closed source and the `unpacked 185 files` log: https://bbs.kanxue.com/thread-281804.htm
- Magic-number validation logic: https://blog.csdn.net/gitblog_01107/article/details/159427625
- KillWxapkg: https://github.com/Ackites/KillWxapkg
- wedecode: https://github.com/biggerstar/wedecode
- wux1an/wxapkg: https://github.com/wux1an/wxapkg
- wxappUnpacker (subpackages incomplete): https://github.com/Ryan-Miao/wxappUnpacker
- CrackMinApp (discontinued in 2019): https://github.com/Cherrison/CrackMinApp
- Android package path: https://www.cnblogs.com/tlnshuju/p/19455602
- referer fixed to servicewechat.com: https://cloud.tencent.com/developer/information/servicewechat.com
- Mini-program UA differences: https://zhangzifan.com/wechat-user-agent.html
- wx.request not supporting Promise: https://developers.weixin.qq.com/miniprogram/en/dev/api/network/request/wx.request.html
- Cloud function HTTP API: https://developers.weixin.qq.com/miniprogram/dev/server/API/cloudbase/functions/api_invokecloudfunction.html
- CloudBase OpenAPI: https://docs.cloudbase.net/api-reference/openapi/function
- Cloud Hosting calls: https://docs.cloudbase.net/run/develop/access/mini
- Cloud Hosting error codes: https://developers.weixin.qq.com/minigame/dev/wxcloudrun/src/development/call/faq.html
- Capture feasibility of the four WeChat cloud categories: https://github.com/anrikgwp/RYF5584-AndroidWXCloudFuncHook
- Actively invoking Cloud Hosting APIs with Frida: https://bbs.kanxue.com/thread-284878.htm
- Alipay dual-thread model and hooking loadUrl: https://juejin.cn/post/7137478354042617869
- Alipay offline package mechanism: https://blog.csdn.net/weixin_52381874/article/details/141713311
- Douyin ttpkgUnpacker: https://github.com/XueDugu/ttpkgUnpacker
- Douyin ttpkg Kanxue share: https://bbs.kanxue.com/thread-287249.htm
- QuickApp CLI: https://doc.quickapp.cn/ide/cli.html
- QuickApp toolkit: https://doc.quickapp.cn/framework/toolkit.html
- Official QuickApp "cannot decompile" answer: https://bbs.quickapp.cn/v2/forum/info?id=2011
- Huawei IDE Open RPK: https://developer.huawei.com/consumer/cn/doc/Tools-Guides/ide-rpk-0000001183309176

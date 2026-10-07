# Mobile Application Reverse Engineering

Mobile apps often expose simpler APIs than their web counterparts. The reverse engineering pipeline here is distinct from web scraping but shares the same philosophy: start at the highest layer, descend only when necessary.

> **For the full 2026 toolchain, jailbreak/root availability matrix, and framework-specific paths (Flutter/Hermes), see `mobile-app-reverse-engineering.md`.** This page is the workflow; that page is the reference.

## Decision Tree

```text
Target is a mobile app
  -> Can you intercept HTTPS traffic with standard proxy?
     -> Yes: Map API endpoints, replicate calls (easiest path)
     -> No: SSL pinning is active
        -> Try Frida/objection to bypass pinning
        -> Try ecapture/r0capture (no CA needed)
        -> If that fails, patch APK or use Magisk modules
  -> API calls are signed/encrypted?
     -> Hook crypto functions with Frida to extract keys
     -> Decompile with jadx to find signing logic
  -> Native library (.so) handles security?
     -> Ghidra/radare2 to analyze ARM binary
     -> Frida to hook JNI boundary
  -> App is Flutter?
     -> blutter (arm64 only, no Release builds)
     -> reFlutter for proxy patch (only <= Flutter 3.24.x)
  -> App uses Hermes (React Native)?
     -> hbctool (only HBC 59/62/74/76)
     -> hermes-dec for other versions
  -> App is hardened (packed)?
     -> Identify shell generation, then use the matching unpacker
     -> See the hardening table in cn-risk-control-ecosystem.md
```

## Environment Setup

### Android

```bash
# ADB basics
adb devices
adb shell
adb install app.apk
adb logcat | grep -i "target_app"

# Frida server on device
adb push frida-server /data/local/tmp/
adb shell "chmod 755 /data/local/tmp/frida-server"
adb shell "/data/local/tmp/frida-server &"

# objection (Frida wrapper)
pip install objection
objection -g com.target.app explore
```

**Android 14+ warning**: system CA certificates moved into the **Conscrypt APEX** module. Every classic tutorial that says "push your cert to `/system/etc/security/cacerts` and it works" is now wrong on Android 14+. Use an APEX-aware module (e.g. AlwaysTrustUserCerts) instead.

### iOS

```bash
# Requires jailbroken device, or a Corellium instance
pip install frida-tools
frida-ps -U  # list apps on USB-connected device
frida-ios-dump -u com.target.app -o target.ipa
```

**Jailbreak reality check (2026)**:

| Device / iOS | Public full jailbreak |
|---|---|
| A11 and below, iOS 14–16 | Dopamine (up to iOS 16.6.1) |
| A12–A13, iOS 15–16.6.1 | Dopamine 2 |
| A12–A16, iOS 17.0–18.x | **No public full jailbreak** |
| A17+ / iOS 18+ | **No public full jailbreak** |
| A18 / A19 (iPhone 16/17) | **No public jailbreak, no path** |

Where jailbreak is unavailable: **TrollStore** (permanent app signing via CoreTrust bug, A12–A13 / iOS 14–17) still enables `frida-server` sideloading for many setups. For unjailbreakable devices, the practical path is **frida gadget injection into a repackaged IPA** — requires the IPA to be decrypted first, which itself requires a jailbroken or Corellium device.

## SSL Pinning Bypass

### Escalation order (try in this sequence)

| Order | Method | Notes |
|---|---|---|
| 1 | `objection` | Fastest, handles most cases |
| 2 | `frida-multiple-unpinning` | Broader coverage than objection |
| 3 | `ecapture` (eBPF uprobe) | **Captures TLS plaintext with NO CA installed** — bypasses the entire cert problem |
| 4 | `r0capture` (Frida) | Hooks at the Java/native SSL layer |
| 5 | Static patch + repackage | Last resort; breaks signatures |

`ecapture` is the most under-used option. It hooks the TLS library's read/write at the kernel level via eBPF uprobe, so pinning implementations that validate certificates never see anything wrong — because you are not intercepting at the cert layer at all.

### Method 1: objection (easiest)

```bash
objection -g com.target.app explore
android sslpinning disable
# or
ios sslpinning disable
```

### Method 2: Frida script

```javascript
// Universal SSL pinning bypass
Java.perform(function () {
  var X509TrustManager = Java.use("javax.net.ssl.X509TrustManager");
  var SSLContext = Java.use("javax.net.ssl.SSLContext");

  var TrustManager = Java.registerClass({
    name: "com.target.bypass.TrustManager",
    implements: [X509TrustManager],
    methods: {
      checkClientTrusted: function () {},
      checkServerTrusted: function () {},
      getAcceptedIssuers: function () { return []; }
    }
  });

  var TrustManagers = [TrustManager.$new()];
  var SSLContext_init = SSLContext.init.overload(
    "[Ljavax/net/ssl/KeyManager;", "[Ljavax/net/ssl/TrustManager;", "Ljava/security/SecureRandom;"
  );
  SSLContext_init.implementation = function (km, tm, random) {
    SSLContext_init.call(this, km, TrustManagers, random);
  };
});
```

### Method 3: Patch APK (last resort)

```bash
apktool d app.apk -o app_dir
# Find and patch pinning logic (search for TrustManager, OkHttp, etc.)
apktool b app_dir -o patched.apk
jarsigner -keystore debug.keystore patched.apk alias
```

## Static Analysis

### APK decompilation

| Tool | Strength |
|---|---|
| `jadx` | Best decompiler output; GUI + CLI |
| `apktool` | Resources + smali; needed for repackaging |
| `GDA` | Windows GUI, fast, no JVM |
| `JEB` | Commercial; most capable for obfuscated code |
| `bytecode-viewer` | Aggregates multiple decompilers |
| `frida-dexdump` | **Dumps decrypted DEX from a running app** — essential when the APK is packed |

**Order matters**: if the APK is hardened (packed), static analysis of the on-disk DEX gives you the shell, not the app. Dump the decrypted DEX at runtime first (`frida-dexdump`), then decompile that.

### Key things to find

| Artifact | Search patterns | Tool |
|---|---|---|
| API endpoints | `https://`, `http://`, retrofit annotations | jadx grep |
| API keys | `api_key`, `apikey`, `token`, `secret` | strings / jadx |
| Crypto logic | `Cipher`, `MessageDigest`, `SecretKeySpec` | jadx class tree |
| Native calls | `System.loadLibrary`, `JNI` | jadx + Ghidra |
| Root detection | `su`, `magisk`, `supersu` | grep smali |
| **Signature params** | `sign`, `_sign`, `signature` | jadx + Frida hook |

## Dynamic Analysis with Frida

### Hook specific class/method

```javascript
Java.perform(function () {
  var TargetClass = Java.use("com.target.app.CryptoUtils");
  TargetClass.signRequest.implementation = function (url, body, timestamp) {
    console.log("URL:", url);
    console.log("Body:", body);
    console.log("Timestamp:", timestamp);
    var result = this.signRequest(url, body, timestamp);
    console.log("Signature:", result);
    return result;
  };
});
```

### Dump network requests

```javascript
Java.perform(function () {
  var OkHttpClient = Java.use("okhttp3.OkHttpClient");
  // Hook interceptors or response body
});
```

## Native Library Analysis

When security logic is in `.so` files:

```bash
unzip app.apk lib/* -d libs/
r2 -A libs/arm64-v8a/libtarget.so
# then: ii (imports), iS (sections), afl (functions)
```

Frida hook at JNI boundary:

```javascript
Interceptor.attach(Module.findExportByName(null, "Java_com_target_app_Crypto_nativeSign"), {
  onEnter: function (args) {
    console.log("Native sign called");
    console.log("Arg1:", Memory.readUtf8String(args[1]));
  },
  onLeave: function (retval) {
    console.log("Result:", Memory.readUtf8String(retval));
  }
});
```

**Note**: hardened apps strip exported JNI symbol names. When `findExportByName` returns null, enumerate `Module.enumerateSymbols()` and match by address, or hook `RegisterNatives` to capture the dynamic registration.

## iOS Specific

```bash
frida-ios-dump -u com.target.app -o target.ipa
class-dump -H target.app -o headers/
```

```javascript
// Frida iOS hooking
var hook = ObjC.classes['TargetClass']['- signRequest:'];
Interceptor.attach(hook.implementation, {
  onEnter: function(args) {
    console.log('signRequest called');
  }
});
```

## Framework-Specific Paths

| Framework | Detection | Tool | Constraint |
|---|---|---|---|
| **Flutter** | `libflutter.so` in `lib/` | `blutter` | **arm64 only, no Release binaries** — build from source |
| **Flutter (proxy)** | same | `reFlutter` | Proxy patch only works on **Flutter ≤ 3.24.x** |
| **React Native (Hermes)** | `libhermes.so` | `hbctool` | **Only HBC 59 / 62 / 74 / 76** |
| **React Native (Hermes)** | same | `hermes-dec` | Broader version coverage |
| **Unity** | `libunity.so`, `assets/bin/Data` | `Il2CppDumper` + `Il2CppInspector` | IL2CPP only, not Mono |
| **Cordova/Ionic** | `www/` in assets | Plain unzip | No RE needed |

## Hardening Shells

| Generation | Examples | Approach |
|---|---|---|
| First (whole-DEX encryption) | early Bangcle / Ijiami | `frida-dexdump` after app start |
| Second (extraction shell, function-level) | Bangcle Enterprise, Nagain | Needs function-level dump, not whole-DEX |
| Third (VMP + custom interpreter) | Dingxiang, Kiwi | Native-level analysis; treat as an L6 problem |

For third-generation shells, the cost/benefit is usually bad. Reconsider whether the mobile path is cheaper than the web path for the same data.

## Replicating Mobile API from Desktop

Once you map the API:

1. Extract all required headers (User-Agent, App-Version, OS-Version, etc.)
2. Reproduce auth flow (often device registration → token)
3. Implement signature/token generation (or use Frida to call native code)
4. Use standard HTTP client with mobile headers

```python
from curl_cffi import requests

headers = {
    "User-Agent": "TargetApp/2.1.0 (Android 14; Pixel 7)",
    "X-App-Version": "2.1.0",
    "X-Device-ID": "...",
    "Authorization": "Bearer ...",
    "X-Signature": "...",  # reimplement or intercept from app
}

resp = requests.get("https://api.target.com/v1/feed", headers=headers, impersonate="chrome")
```

**Note**: mobile API endpoints often check the `User-Agent` for mobile-app markers. Using `impersonate="chrome"` gives you a browser TLS fingerprint, which can itself be inconsistent with a mobile UA. Prefer `impersonate="safari_ios"` or a matching mobile profile when the target distinguishes.

## Operational Security

- Use a dedicated test device (don't RE on your daily driver)
- Snapshot/reset the device between sessions
- Some apps detect debuggers, emulators, root; have a bypass strategy ready
- Record the app version — everything you learn breaks on the next update

Mobile RE opens APIs that web scraping cannot reach. It is higher effort but often higher reward.

## Version Quick-Reference

| Tool | Status (2026) |
|---|---|
| LSPosed | Official stopped at v1.9.2 (2023-10-11) → use **JingMatrix/Vector** |
| Magisk | Active |
| Xposed (original) | Archived |
| Frida | Active |
| objection | Active |
| `ptswarm/reFlutter` | **Archived** → use `Impact-I/reFlutter` |
| Stream (iOS capture app) | In App Store |
| Thor | Removed from App Store |

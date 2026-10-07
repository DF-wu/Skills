# Mobile App Reverse Engineering In Depth (Android / iOS / Flutter / Hermes)

Mobile is the extended battlefield of web reverse engineering: when signing logic sinks down into the App, or when you need to reproduce App-only endpoints, you must enter this layer.

## 1. Android Static Analysis

An APK is a zip container holding `classes*.dex` (Dalvik bytecode), `resources.arsc` (binary resource table), `AndroidManifest.xml` (binary XML), and `lib/<abi>/*.so` (native libraries). Static reverse engineering has three layers: DEX→Java decompilation, resource/manifest restoration, and SO-layer disassembly.

| Tool | Repository | Positioning |
|---|---|---|
| **jadx** | https://github.com/skylot/jadx | First choice for DEX→Java decompilation, `v1.5.6` |
| **Apktool** | https://github.com/iBotPeaches/Apktool | Resource and manifest restoration + repackaging, `v3.0.3` |
| GDA | https://github.com/charles2gan/GDA-android-reversing-Tool | Windows native, no JVM dependency; includes malicious-behavior / privacy-leak / vulnerability detection |
| JEB Decompiler | https://www.pnfsoftware.com/jeb/changelog | Commercial. Continuously adds dexdec optimizers, **unflattener** (control-flow-flattening restoration), an MCP server, and the VIBRE AI assistant |
| **Frida** | https://github.com/frida/frida | Dynamic instrumentation, `17.22.2` |
| **unidbg** | https://github.com/zhkl0228/unidbg | **Emulated execution of Android `.so`** (ARM32/ARM64), backends unicorn/dynarmic/KVM; supports JNI calls, syscall emulation, inline hook |
| MT Manager | Official forum https://bbs.binmt.cc | Edit dex/resources directly on the phone, closed source |
| SimpleHook | https://github.com/littleWhiteDuck/SimpleHook | Xposed module, graphical configuration of hook return values/parameters, logs encryption and decryption calls; supports both Java and Smali rule styles |

**Standard workflow**:

```bash
apktool d app.apk            # restore resources and manifest
jadx -d out app.apk          # decompile DEX
frida -U -f pkg -l script.js # dynamic verification
```

**The value of unidbg**: when the encryption/verification logic lives inside `libxxx.so`, use unidbg to invoke the JNI function directly (construct an `AndroidEmulator`, `module.callFunction`), **avoiding real-device environment dependencies**, and run it offline in batches.

## 2. Root and Hook Frameworks

**Principle**: Xposed replaces `app_process` and injects into Zygote to hijack method calls at the ART layer; Magisk takes over `init` through `magiskinit` and mounts overlayfs to achieve systemless modification; Zygisk runs native code inside the Zygote process, bypassing some detection.

| Project | Repository | Status |
|---|---|---|
| Magisk | https://github.com/topjohnwu/Magisk | Active, `v30.7`, includes Android 16 QPR2 sepolicy and Zygisk support |
| KernelSU | https://github.com/tiann/KernelSU | Active (kernel-level root, requires GKI) |
| APatch | https://github.com/bmax121/APatch | Active (kernel patch + inline hook) |
| LSPosed (official) | https://github.com/LSPosed/LSPosed | **Releases stopped at `v1.9.2` (2023-10-11)**; the community widely reports that the official build fails on Android 15/16 |
| **LSPosed (JingMatrix/Vector)** | https://github.com/JingMatrix/Vector | **Active; this fork is what you should actually use**. The README states support for Android 8.1 ~ 16 and requires Magisk 26.0+ with Zygisk |
| LSPatch | https://github.com/LSPosed/LSPatch | **Archived** |
| rovo89 Xposed family | https://github.com/rovo89/Xposed | **All archived** |
| Zygisk module template | https://github.com/topjohnwu/zygisk-module-sample | Archived; active replacement https://github.com/snake-4/Zygisk-Assistant |

**Key warning**: official LSPosed's "supports Android 8.1~14" is a **2023 statement**. In 2026 you must go by the fork's statement.

## 3. iOS Jailbreak and Reverse Engineering

### Jailbreak tools

| Tool | Source | Coverage |
|---|---|---|
| **Dopamine** | https://github.com/opa334/Dopamine | Extremely active. rootless semi-untethered. 3.0 introduced the Titan PPL/SPTM bypass; supports iOS 15.0–17.3.1 (arm64e), 15.0–18.7.1 (arm64/A12-A13), 26.0–26.0.1 (A12/A13) |
| palera1n | https://github.com/palera1n/palera1n | Active. A8–A11 and T2, iOS/iPadOS/tvOS 15.0+ |
| **TrollStore** | https://github.com/opa334/TrollStore | Exploits AMFI/CoreTrust signature-verification flaws to achieve **permanent-signature sideloading without a kernel exploit**. Supports 14.0b2–16.6.1, 16.7 RC, 17.0; **16.7.x (except RC) and 17.0.1+ will never be supported** |
| checkra1n | https://checkra.in/ | **De facto discontinued** (no formal announcement). iPhone 5s–X (checkm8) |
| unc0ver | https://unc0ver.dev/ | De facto discontinued, iOS 11.0–14.8 |
| Taurine / XinaA15 | https://github.com/Odyssey-Team/Taurine | Discontinued |

**Current-state assessment**: the only new public complete jailbreak in 2025–2026 is **Dopamine 3.0**. **A14+ on iOS 17.4+, and A18/A19 (iPhone 16/17), currently have no public complete jailbreak**.

**Scam identification**: the Fugu18/Fugu19 family are scams (Linus Henze's Fugu stopped at Fugu15); kfd is only a kernel read/write primitive, not a complete jailbreak; MacDirtyCow was fixed in 15.7.2/16.2; CVE-2025-24203 (mdc0/dirtyZero) supports UI-level customization only.

### Reverse engineering and decryption tools

| Tool | Source | Status |
|---|---|---|
| **ipsw** | https://github.com/blacktop/ipsw | Extremely active. Firmware download/unpacking, dyld shared cache extraction, kernelcache analysis, one-shot generation of Frida and symbolicated artifacts |
| Hopper | https://www.hopperapp.com/ | Active (commercial). Built-in MCP server since 6.0 |
| IDA Pro | https://hex-rays.com/ida-pro | Active (version statements conflict, see below) |
| Ghidra | https://github.com/NationalSecurityAgency/ghidra | Active |
| objection | https://github.com/sensepost/objection | Active. Both iOS + Android |
| SSL Kill Switch 3 | https://github.com/NyaMisty/ssl-kill-switch3 | Dormant but usable (provides rootful and rootless debs) |
| frida-ios-dump | https://github.com/AloneMonkey/frida-ios-dump | Repo alive but **discontinued (2020-06)**. Active alternatives: `incogbyte/frida-ios-dump-ng`, `jwalker/frida-ios-dump-modern`, `aadog/fd-back` |
| class-dump | https://github.com/nygard/class-dump | Not archived but **stopped in 2019** |
| dsdump | https://github.com/DerekSelander/dsdump | **Archived; the author wrote "don't use this tool" in the commit message** |
| Corellium | https://www.corellium.com/ | **Not enterprise-only**. Solo is the student EDU version ($3/device-hour); uses the CHARM hypervisor for ARM-on-ARM virtualization and provides 1-click jailbroken virtual iOS |

> **IDA version statement conflict**: two verification paths reached inconsistent conclusions (one says the latest stable is 9.3sp2 with 9.4 still Beta; the other says 9.4/9.4sp1 has been released). **Go by the version actually visible in your My Hex-Rays customer portal.**

### iOS traffic-capture apps

- **Stream — real, still listed**: https://apps.apple.com/us/app/stream-network-debug-tool/id1312141691 . Network Extension + installing a CA certificate decrypts HTTPS, supports HAR import/export
- **Thor — real but delisted**: original App Store id 1210562295. AppleCensorship monitors 175 storefronts, **0 available**, last listed record 2022-02-11. Its functional successor is Hodor (https://apps.apple.com/us/app/hodor-http-s-packet-sniffer/id1608857736 )

## 4. SSL Pinning Bypass

Pinning is implemented at three layers, corresponding to three kinds of bypass:

| Layer | Implementation | Bypass |
|---|---|---|
| System level | Network Security Configuration (`<pin-set>`, Android 7+) | Modify the NSC, or install the proxy CA into the system store |
| App level | TrustManager override / OkHttp `CertificatePinner` | Runtime-hook the Java-layer verification |
| Native layer | BoringSSL `SSL_CTX_set_custom_verify` / `ssl_verify_peer_cert` (Flutter, hardening SDKs) | Hook the native layer, or patch the binary |

### Technique list

| Technique | Tool/source |
|---|---|
| Generic Frida script | `frida-multiple-unpinning` https://codeshare.frida.re/@akabe1/frida-multiple-unpinning/ (included in OWASP MASTG-TOOL-0140) |
| One-click hook + proxy rewriting | https://github.com/httptoolkit/frida-interception-and-unpinning (active) |
| objection | `android sslpinning disable` / `ios sslpinning disable` |
| Xposed modules | JustTrustMe (https://github.com/Fuzion24/JustTrustMe), JustTrustMePro, TrustMeAlready (**archived**; active branch `mobile46/TrustMeAlready`) |
| Static repackaging | Apktool + `res/xml/network_security_config.xml`: edit `<trust-anchors>` to add the user CA, delete `<pin-set>`, repackage and re-sign |
| Hash/certificate replacement | `grep -ri "sha256\|sha1" ./smali` and replace with the proxy CA hash; `find ./assets -type f \( -iname *.cer -o -iname *.crt \)` to replace certificate files; or replace the `.jks`/`.bks` truststore |
| **Pure capture (no CA needed)** | `r0capture` (https://github.com/r0ysue/r0capture, Frida hooks `SSL_read`/`SSL_write` across the whole chain), `ecapture` (https://github.com/gojue/ecapture, **eBPF uprobe captures TLS plaintext directly, no CA certificate installation required**) |

**Layered decision**: try `objection` first → if that fails, move to `frida-multiple-unpinning` → if that still fails, check whether it is native pinning (`strings lib*.so | grep -i "ssl_verify\|pinning\|sha256/"`); if so, go with ecapture/r0capture or a static patch → for Flutter see section 6.

## 5. Capture Environment and Certificate Trust

**Core facts (they decide success or failure)**:

1. **From Android 7.0 (API 24), apps no longer trust user/admin-installed CAs by default**, only the system store
2. **From Android 14, system root certificates are provided by the Conscrypt APEX**, read at runtime from `/apex/com.android.conscrypt/cacerts` with priority, falling back to `/system/etc/security/cacerts` only when missing

**Corollary**: all tutorials of the "modify `/system/etc/security/cacerts`" kind **necessarily fail** on Android 14+ devices with an updated Conscrypt; you must use a solution that supports APEX.

| Solution | Repository | Notes |
|---|---|---|
| **AlwaysTrustUserCerts** | https://github.com/NVISOsecurity/AlwaysTrustUserCerts | Active. Magisk/KernelSU/KernelSU Next; **handles both the `/system` and `/apex/com.android.conscrypt/cacerts` paths**, covering Android 7–16 |
| MoveCertificate | https://github.com/ys1231/MoveCertificate | Android 7–16, Magisk v20.4+/KernelSU/APatch |
| Manual injection | — | `nsenter --mount=/proc/$PID/ns/mnt -- /bin/mount --bind /system/etc/security/cacerts /apex/com.android.conscrypt/cacerts` |

**Capture tools**:

| Tool | Source | Status |
|---|---|---|
| mitmproxy | https://github.com/mitmproxy/mitmproxy | Active, `v12.2.3` |
| Reqable (formerly HttpCanary) | https://reqable.com/en-US | **Issue-tracking repository only, not open source**; has an official MCP server |
| Charles | https://www.charlesproxy.com | Commercial |
| PCAPdroid | https://github.com/emanuele-f/PCAPdroid | **Root-free** VpnService capture; paired with `PCAPdroid-mitm` to feed traffic into mitmproxy for decryption |

**Recommended chain**: install Magisk + AlwaysTrustUserCerts on a real device → install the proxy CA as a user certificate and reboot → `mitmproxy --mode wireguard` (bypasses system proxy restrictions) or PCAPdroid as a VpnService → if needed, PCAPdroid-mitm forwards to mitmproxy.

> **Official note**: Android apps often bypass the system HTTP proxy settings, so you must switch to WireGuard, Local Capture, or Transparent mode.

## 6. Flutter Reverse Engineering

**Mechanism**: Flutter release builds AOT-compile Dart code into `libapp.so`, whose content is a **Dart VM snapshot**: it contains the object pool, class information (**ordered layout, no random access**), and the native code address of each method. `libflutter.so` is the engine itself.

**Difficulties**: the Dart snapshot format has no official documentation and changes with every version; AOT code's calling convention differs from the standard ARM64 ABI (register allocation and integer encoding both differ), so standard disassemblers produce poor readability.

| Tool | Repository | Status and limitations |
|---|---|---|
| **blutter** | https://github.com/worawit/blutter | Active. `python3 blutter.py path/to/app/lib/arm64-v8a out_dir`, produces `asm/*` (symbolicated disassembly), `blutter_frida.js`, `objs.txt`, `pp.txt` (every Dart object in the object pool). **Limitations**: only Android arm64 `libapp.so`, only newer Dart versions, **no support for obfuscated apps or iOS binaries**; no GitHub Release |
| **reFlutter** | https://github.com/Impact-I/reFlutter | Active. `pip3 install reflutter`. repack mode replaces the engine to route through a proxy; dump mode `-p` outputs `dump.dart` (JSONL). Supports Shorebird; engines are indexed by snapshot hash in `enginehash.csv`; the `frida-ssl.js` runtime bypass requires a non-stripped engine. **The original repo ptswarm/reFlutter is archived** |
| Generic pinning bypass | https://github.com/vichhka-git/universal-flutter-ssl-pinning | Uses PyGhidra to statically locate BoringSSL and auto-generate Frida/Renef scripts |
| OWASP technique | https://mas.owasp.org/MASTG/techniques/android/MASTG-TECH-0112 | Official technique page, lists the four major snapshot difficulties |

**Hands-on**:

```bash
unzip app.apk 'lib/arm64-v8a/*'
python3 blutter.py path/to/app/lib/arm64-v8a out_dir
grep -i "api\|token" out_dir/pp.txt        # find strings in the object pool
# locate functions in asm/* and hook them with blutter_frida.js
```

**Limitation warning**: reFlutter's "hard-coded proxy IP" approach **only applies to Flutter 3.24.x and earlier**; newer versions must rely on `frida-ssl.js` or a static patch.

## 7. React Native / Hermes Reverse Engineering

**Mechanism**: Hermes has been the default JS engine since RN 0.70, precompiling JS into Hermes bytecode (`.hbc`) at build time and placing it at `assets/index.android.bundle`. **The HBC format carries an integer version number and is strictly validated at runtime** (a mismatch reports "Wrong bytecode version. Expected 96 but got 98" and crashes), so tools must be adapted version by version.

| Tool | Repository | Status and limitations |
|---|---|---|
| **hermes-dec** | https://github.com/P1sec/hermes-dec | Active. `hbc-file-parser` / `hbc-disassembler` / `hbc-decompiler`; 0.1.7 fixes decoding for **bytecode ≥ 97** |
| hbctool | https://github.com/bongtrop/hbctool | Semi-active. `hbctool disasm` / `hbctool asm` (**can write back**). **Key limitation: only supports HBC versions 59 / 62 / 74 / 76** |
| hermes_rs | https://github.com/Pilfer/hermes_rs | Active (Rust disassembler/assembler) |
| hermes-decomp | https://github.com/SymbioticSec/hermes-decomp | Narrow niche |

**Hands-on**:

```bash
unzip app.apk assets/index.android.bundle
# read the first 8 bytes magic: c6 1f bc 03 c1 03 19 1f is the Hermes signature, and take the version number
hermes-dec hbc-decompiler index.android.bundle out.js
```

**Warning**: hbctool's supported-version table has not been comprehensively updated since it was established in 2021, and is most likely inapplicable on RN 0.7x/0.8x — **go by the actual HBC version number; do not assume it works**.

## 8. Android App Hardening Shells (accompanying issue)

| Generation | Technical characteristics | Unpacking difficulty | Representative tools |
|---|---|---|---|
| Gen 1: whole-DEX encryption | Whole-DEX encryption, dynamic loading | Relatively easy, memory dump | FRIDA-DEXDump, Dexhunter, elf-dump-fix |
| Gen 2: DEX function extraction | Methods individually extracted and encrypted, decrypted at execution | Recoverable (dump runtime method bodies and backfill the dex) | FART, Youpk, BlackDex, Dex2oatHunter |
| Gen 3: VMP / Dex2C | Independent virtual machine interpretation / semantically equivalent syntax migration | **Dex2C currently has no way to be restored, only traced and analyzed**; VMP protects the mapping table and can be manually restored | No mature automated tools |

**Tool limitations (read first)**:

- **FART** only provides Android 6.0 and 8.0 images; the original version cannot cope with root detection, and **Fart8** erased the fingerprints. Because the project is well known, **hardening vendors have already blacklisted FART signatures**
- **frida-fart** requires copying `fart.so`/`fart64.so` into `/data/app` and `chmod 777`; start with `spawn` and execute `fart()` after entering the Activity. Advanced usage `dump(classname)` can actively dump methods that have never executed. **Downside: cannot handle shells with anti-debugging** — paid hardening always includes anti-debugging and will recognize frida signatures
- **BlackDex** is based on a plugin-ization approach. **Because it is open source, its signature is obvious and hardening vendors can easily counter it**
- **FRIDA-DEXDump** brute-force searches complete dex files for the `dex035` magic; header-erased dex is handled via signature matching

**Shell signature identification**: the 5th-generation Ijiami shell shows `IJMDal.Data` under `assets`.

> Vendor signature `so` filename lists (Ijiami / Bangcle / Legu / JuSecurity / Yidun / Tongfudun / Nagain) differ between secondary sources and are **unverified**; actual identification should be based on the on-site `lib/` directory listing and the loading flow.

## Version and Maintenance Status Quick Reference

**Active**: jadx 1.5.6 · Apktool 3.0.3 · Frida 17.22.2 · JEB 5.47 · Ghidra 12.1.4 · unidbg 0.9.9 · Magisk 30.7 · KernelSU · APatch · JingMatrix/Vector · blutter · reFlutter · hermes-dec 0.1.7 · hermes_rs · ipsw · Hopper 6.6.0 · Dopamine 3.0.10 · palera1n 2.4 · TrollStore 2.1.1 · PCAPdroid · ecapture · r0capture · AlwaysTrustUserCerts

**Semi-stalled**: hbctool (stale version-support table) · SSL Kill Switch 3 (2023-11) · SimpleHook (closed-source distribution)

**Archived or de facto discontinued**: rovo89/Xposed family · LSPosed/LSPatch · ptswarm/reFlutter · ViRb3/TrustMeAlready · DerekSelander/dsdump · official LSPosed builds (2023-10) · checkra1n · unc0ver · Taurine · XinaA15 · class-dump (stopped in 2019) · frida-ios-dump (stopped in 2020)

## Sources

- jadx: https://github.com/skylot/jadx
- Apktool: https://github.com/iBotPeaches/Apktool
- JEB changelog: https://www.pnfsoftware.com/jeb/changelog
- unidbg: https://github.com/zhkl0228/unidbg
- Magisk: https://github.com/topjohnwu/Magisk
- KernelSU: https://github.com/tiann/KernelSU
- APatch: https://github.com/bmax121/APatch
- LSPosed: https://github.com/LSPosed/LSPosed
- JingMatrix/Vector: https://github.com/JingMatrix/Vector
- Dopamine: https://github.com/opa334/Dopamine
- palera1n: https://github.com/palera1n/palera1n
- TrollStore: https://github.com/opa334/TrollStore
- iOS 26 jailbreak timeline: https://www.techspot.com/news/113408-jailbreak-ios-26-finally-here-326-days-after.html
- ipsw: https://github.com/blacktop/ipsw
- Stream App Store: https://apps.apple.com/us/app/stream-network-debug-tool/id1312141691
- Thor delisting monitoring: https://applecensorship.com/app-store-monitor/app/1210562295
- frida-multiple-unpinning: https://codeshare.frida.re/@akabe1/frida-multiple-unpinning/
- MASTG-TOOL-0140: https://mas.owasp.org/MASTG/tools/android/MASTG-TOOL-0140/
- frida-interception-and-unpinning: https://github.com/httptoolkit/frida-interception-and-unpinning
- MASTG-TECH-0012 (NSC bypass): https://mas.owasp.org/MASTG/techniques/android/MASTG-TECH-0012
- ecapture: https://github.com/gojue/ecapture
- r0capture: https://github.com/r0ysue/r0capture
- Android CA change announcement: https://android-developers.googleblog.com/2016/07/changes-to-trusted-certificate.html
- Android security configuration: https://developer.android.com/privacy-and-security/security-config
- Conscrypt APEX capture: https://blog.nviso.eu/2025/06/05/intercepting-traffic-on-android-with-mainline-and-conscrypt/
- AlwaysTrustUserCerts: https://github.com/NVISOsecurity/AlwaysTrustUserCerts
- MoveCertificate: https://github.com/ys1231/MoveCertificate
- PCAPdroid: https://github.com/emanuele-f/PCAPdroid
- blutter: https://github.com/worawit/blutter
- reFlutter: https://github.com/Impact-I/reFlutter
- MASTG-TECH-0112 (Flutter): https://mas.owasp.org/MASTG/techniques/android/MASTG-TECH-0112
- hermes-dec: https://github.com/P1sec/hermes-dec
- hbctool: https://github.com/bongtrop/hbctool
- Hardening three-generation division: https://blog.csdn.net/weixin_39190897/article/details/114269713
- Hardening and unpacking hands-on: https://juejin.cn/post/7423310754952675379
- FRIDA-DEXDump: https://github.com/hluwa/FRIDA-DEXDump
- BlackDex: https://github.com/CodingGay/BlackDex

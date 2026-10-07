# 移动端 App 逆向深度（Android / iOS / Flutter / Hermes）

移动端是 Web 逆向的延伸战场：当签名逻辑下沉到 App，或需要复现 App 独有接口时，必须进入这一层。

## 一、Android 静态分析

APK 是 zip 容器，含 `classes*.dex`（Dalvik 字节码）、`resources.arsc`（二进制资源表）、`AndroidManifest.xml`（二进制 XML）与 `lib/<abi>/*.so`（原生库）。静态逆向分三层：DEX→Java 反编译、资源/清单还原、SO 层反汇编。

| 工具 | 仓库 | 定位 |
|---|---|---|
| **jadx** | https://github.com/skylot/jadx | DEX→Java 反编译首选，`v1.5.6` |
| **Apktool** | https://github.com/iBotPeaches/Apktool | 资源与清单还原 + 重打包，`v3.0.3` |
| GDA | https://github.com/charles2gan/GDA-android-reversing-Tool | Windows 原生、不依赖 JVM；含恶意行为/隐私泄露/漏洞检测 |
| JEB Decompiler | https://www.pnfsoftware.com/jeb/changelog | 商业。持续加 dexdec 优化器、**unflattener**（控制流平坦化还原）、MCP server、VIBRE AI 助手 |
| **Frida** | https://github.com/frida/frida | 动态插桩，`17.22.2` |
| **unidbg** | https://github.com/zhkl0228/unidbg | **模拟执行 Android `.so`**（ARM32/ARM64），后端 unicorn/dynarmic/KVM；支持 JNI 调用、syscall 模拟、inline hook |
| MT 管理器 | 官方论坛 https://bbs.binmt.cc | 手机上直接改 dex/资源，闭源 |
| SimpleHook | https://github.com/littleWhiteDuck/SimpleHook | Xposed 模块，图形化配置 hook 返回值/参数、记录加解密调用；支持 Java 与 Smali 两种规则写法 |

**标准流程**：

```bash
apktool d app.apk            # 还原资源与清单
jadx -d out app.apk          # 反编译 DEX
frida -U -f pkg -l script.js # 动态验证
```

**unidbg 的价值**：加密/校验逻辑在 `libxxx.so` 里时，用 unidbg 直接拉起 JNI 函数（构造 `AndroidEmulator`、`module.callFunction`），**避免真机环境依赖**，可离线批量跑。

## 二、Root 与 Hook 框架

**原理**：Xposed 通过替换 `app_process` 与注入 Zygote，在 ART 层劫持方法调用；Magisk 通过 `magiskinit` 接管 `init` 并挂载 overlayfs 实现 systemless 修改；Zygisk 在 Zygote 进程内运行原生代码，绕过部分检测。

| 项目 | 仓库 | 状态 |
|---|---|---|
| Magisk | https://github.com/topjohnwu/Magisk | 活跃，`v30.7`，含 Android 16 QPR2 sepolicy 与 Zygisk 支持 |
| KernelSU | https://github.com/tiann/KernelSU | 活跃（内核级 root，需 GKI） |
| APatch | https://github.com/bmax121/APatch | 活跃（内核 patch + inline hook） |
| LSPosed（官方） | https://github.com/LSPosed/LSPosed | **发布停在 `v1.9.2`（2023-10-11）**；社区普遍报告官方构建在 Android 15/16 上失效 |
| **LSPosed（JingMatrix/Vector）** | https://github.com/JingMatrix/Vector | **活跃，实际应使用此 fork**。README 口径支持 Android 8.1 ~ 16，需 Magisk 26.0+ 与 Zygisk |
| LSPatch | https://github.com/LSPosed/LSPatch | **已归档** |
| rovo89 Xposed 系 | https://github.com/rovo89/Xposed | **全部已归档** |
| Zygisk 模块模板 | https://github.com/topjohnwu/zygisk-module-sample | 已归档；活跃替代 https://github.com/snake-4/Zygisk-Assistant |

**关键警告**：官方 LSPosed 的「支持 Android 8.1~14」是 **2023 年口径**。2026 年必须按 fork 口径执行。

## 三、iOS 越狱与逆向

### 越狱工具

| 工具 | 来源 | 支持面 |
|---|---|---|
| **Dopamine** | https://github.com/opa334/Dopamine | 极活跃。rootless 半不完美。3.0 引入 Titan PPL/SPTM bypass；支持 iOS 15.0–17.3.1（arm64e）、15.0–18.7.1（arm64/A12-A13）、26.0–26.0.1（A12/A13） |
| palera1n | https://github.com/palera1n/palera1n | 活跃。A8–A11 与 T2，iOS/iPadOS/tvOS 15.0+ |
| **TrollStore** | https://github.com/opa334/TrollStore | AMFI/CoreTrust 签名校验缺陷实现**永久签名侧载，不需内核漏洞**。支持 14.0b2–16.6.1、16.7 RC、17.0；**16.7.x（除 RC）与 17.0.1+ 永不支持** |
| checkra1n | https://checkra.in/ | **事实停更**（无正式公告）。iPhone 5s–X（checkm8） |
| unc0ver | https://unc0ver.dev/ | 事实停更，iOS 11.0–14.8 |
| Taurine / XinaA15 | https://github.com/Odyssey-Team/Taurine | 停更 |

**现状评估**：2025–2026 唯一新的公开完整越狱是 **Dopamine 3.0**。**A14+ 在 iOS 17.4+、以及 A18/A19（iPhone 16/17）目前无公开完整越狱**。

**陷阱识别**：Fugu18/Fugu19 系骗局（Linus Henze 的 Fugu 止于 Fugu15）；kfd 只是内核读写原语而非完整越狱；MacDirtyCow 已修于 15.7.2/16.2；CVE-2025-24203（mdc0/dirtyZero）仅支持 UI 级定制。

### 逆向与解密工具

| 工具 | 来源 | 状态 |
|---|---|---|
| **ipsw** | https://github.com/blacktop/ipsw | 极活跃。固件下载/解包、dyld shared cache 抽取、kernelcache 分析、一键产出 Frida 与符号化产物 |
| Hopper | https://www.hopperapp.com/ | 活跃（商业）。6.0 起内置 MCP server |
| IDA Pro | https://hex-rays.com/ida-pro | 活跃（版本口径存在冲突，见下） |
| Ghidra | https://github.com/NationalSecurityAgency/ghidra | 活跃 |
| objection | https://github.com/sensepost/objection | 活跃。iOS + Android 双端 |
| SSL Kill Switch 3 | https://github.com/NyaMisty/ssl-kill-switch3 | 沉寂但可用（提供 rootful 与 rootless deb） |
| frida-ios-dump | https://github.com/AloneMonkey/frida-ios-dump | 仓库存活但**停更（2020-06）**。活跃替代：`incogbyte/frida-ios-dump-ng`、`jwalker/frida-ios-dump-modern`、`aadog/fd-back` |
| class-dump | https://github.com/nygard/class-dump | 未归档但**停于 2019** |
| dsdump | https://github.com/DerekSelander/dsdump | **已归档，作者在提交信息里写 "don't use this tool"** |
| Corellium | https://www.corellium.com/ | **非仅限企业**。Solo 为学生 EDU 版（$3/设备小时）；基于 CHARM hypervisor 做 ARM-on-ARM 虚拟化，提供 1-click 越狱虚拟 iOS |

> **IDA 版本口径冲突**：两路核实结论不一致（一说最新稳定为 9.3sp2、9.4 仍 Beta；一说 9.4/9.4sp1 已发布）。**以 My Hex-Rays 客户门户实际可见版本为准。**

### iOS 抓包 App

- **Stream — 真实、在架**：https://apps.apple.com/us/app/stream-network-debug-tool/id1312141691 。Network Extension + 安装 CA 证书解 HTTPS，支持 HAR 导入导出
- **Thor — 真实但已下架**：原 App Store id 1210562295。AppleCensorship 监控 175 个店面，**0 个可用**，最后在架记录 2022-02-11。功能后继为 Hodor（https://apps.apple.com/us/app/hodor-http-s-packet-sniffer/id1608857736 ）

## 四、SSL Pinning 绕过

Pinning 分三层实现，对应三类绕过：

| 层 | 实现 | 绕过 |
|---|---|---|
| 系统级 | Network Security Configuration（`<pin-set>`，Android 7+） | 改 NSC 或把代理 CA 装进系统库 |
| 应用层 | TrustManager 覆写 / OkHttp `CertificatePinner` | 运行时 hook Java 层校验 |
| 原生层 | BoringSSL `SSL_CTX_set_custom_verify` / `ssl_verify_peer_cert`（Flutter、加固 SDK） | hook 原生层或改二进制 |

### 手段清单

| 手段 | 工具/来源 |
|---|---|
| 通用 Frida 脚本 | `frida-multiple-unpinning` https://codeshare.frida.re/@akabe1/frida-multiple-unpinning/ （OWASP MASTG-TOOL-0140 收录） |
| 一键 hook + 代理改写 | https://github.com/httptoolkit/frida-interception-and-unpinning （活跃） |
| objection | `android sslpinning disable` / `ios sslpinning disable` |
| Xposed 模块 | JustTrustMe（https://github.com/Fuzion24/JustTrustMe）、JustTrustMePro、TrustMeAlready（**已归档**，活跃分支 `mobile46/TrustMeAlready`） |
| 静态改包 | Apktool + `res/xml/network_security_config.xml`：改 `<trust-anchors>` 加入用户 CA、删除 `<pin-set>`，重打包重签名 |
| 哈希/证书替换 | `grep -ri "sha256\|sha1" ./smali` 替换为代理 CA 哈希；`find ./assets -type f \( -iname *.cer -o -iname *.crt \)` 替换证书文件；或替换 `.jks`/`.bks` truststore |
| **纯抓包（免 CA）** | `r0capture`（https://github.com/r0ysue/r0capture，Frida hook `SSL_read`/`SSL_write` 全链路）、`ecapture`（https://github.com/gojue/ecapture，**eBPF uprobe 直接抓 TLS 明文，无需安装 CA 证书**） |

**分层决策**：先试 `objection` → 不行上 `frida-multiple-unpinning` → 再不行检查是否原生 pinning（`strings lib*.so | grep -i "ssl_verify\|pinning\|sha256/"`），是则走 ecapture/r0capture 或静态 patch → Flutter 见第六节。

## 五、抓包环境与证书信任

**核心事实（决定成败）**：

1. **Android 7.0（API 24）起，应用默认不再信任用户/管理员安装的 CA**，只信任系统库
2. **Android 14 起系统根证书改由 Conscrypt APEX 提供**，运行时优先读取 `/apex/com.android.conscrypt/cacerts`，仅在缺失时回退 `/system/etc/security/cacerts`

**推论**：所有「改 `/system/etc/security/cacerts`」类教程在 Android 14+ 且 Conscrypt 已更新的设备上**必然失效**，必须用支持 APEX 的方案。

| 方案 | 仓库 | 说明 |
|---|---|---|
| **AlwaysTrustUserCerts** | https://github.com/NVISOsecurity/AlwaysTrustUserCerts | 活跃。Magisk/KernelSU/KernelSU Next；**处理 `/system` 与 `/apex/com.android.conscrypt/cacerts` 双路径**，覆盖 Android 7–16 |
| MoveCertificate | https://github.com/ys1231/MoveCertificate | Android 7–16，Magisk v20.4+/KernelSU/APatch |
| 手动注入 | — | `nsenter --mount=/proc/$PID/ns/mnt -- /bin/mount --bind /system/etc/security/cacerts /apex/com.android.conscrypt/cacerts` |

**抓包工具**：

| 工具 | 来源 | 状态 |
|---|---|---|
| mitmproxy | https://github.com/mitmproxy/mitmproxy | 活跃，`v12.2.3` |
| Reqable（原 HttpCanary） | https://reqable.com/en-US | **仅 issue 跟踪仓库，不开源**；有官方 MCP server |
| Charles | https://www.charlesproxy.com | 商业 |
| PCAPdroid | https://github.com/emanuele-f/PCAPdroid | **免 root** 的 VpnService 抓包；配套 `PCAPdroid-mitm` 把流量导入 mitmproxy 解密 |

**推荐链路**：真机装 Magisk + AlwaysTrustUserCerts → 装代理 CA 为用户证书并重启 → `mitmproxy --mode wireguard`（绕开系统代理限制）或 PCAPdroid 起 VpnService → 必要时 PCAPdroid-mitm 转发到 mitmproxy。

> **官方提示**：Android 应用常绕过系统 HTTP 代理设置，必须改用 WireGuard、Local Capture 或 Transparent 模式。

## 六、Flutter 逆向

**机制**：Flutter release 构建把 Dart 代码 AOT 编译进 `libapp.so`，其内容是一个 **Dart VM snapshot**：含对象池、类信息（**顺序布局，无法随机访问**）、各方法的原生代码地址。`libflutter.so` 是引擎本身。

**难点**：Dart snapshot 格式无正式文档且逐版本变化；AOT 代码的调用约定与标准 ARM64 ABI 不同（寄存器分配、整数编码均异），标准反汇编器产出可读性差。

| 工具 | 仓库 | 状态与限制 |
|---|---|---|
| **blutter** | https://github.com/worawit/blutter | 活跃。`python3 blutter.py path/to/app/lib/arm64-v8a out_dir`，产出 `asm/*`（带符号反汇编）、`blutter_frida.js`、`objs.txt`、`pp.txt`（对象池全量 Dart 对象）。**限制**：仅 Android arm64 的 `libapp.so`、仅较新 Dart 版本、**对混淆应用与 iOS 二进制不支持**；无 GitHub Release |
| **reFlutter** | https://github.com/Impact-I/reFlutter | 活跃。`pip3 install reflutter`。repack 模式替换引擎以走代理；dump 模式 `-p` 输出 `dump.dart`（JSONL）。支持 Shorebird；引擎按 snapshot hash 索引于 `enginehash.csv`；`frida-ssl.js` 运行时绕过需未 strip 的引擎。**原仓库 ptswarm/reFlutter 已归档** |
| 通用 pinning 绕过 | https://github.com/vichhka-git/universal-flutter-ssl-pinning | 用 PyGhidra 静态定位 BoringSSL 并自动生成 Frida/Renef 脚本 |
| OWASP 技法 | https://mas.owasp.org/MASTG/techniques/android/MASTG-TECH-0112 | 官方技法页，列出 snapshot 四大难点 |

**实操**：

```bash
unzip app.apk 'lib/arm64-v8a/*'
python3 blutter.py path/to/app/lib/arm64-v8a out_dir
grep -i "api\|token" out_dir/pp.txt        # 在对象池里找字符串
# 在 asm/* 定位函数并用 blutter_frida.js 挂钩
```

**限制警告**：reFlutter 的「硬编码代理 IP」方案**仅适用于 Flutter 3.24.x 及更早**，新版本需依赖 `frida-ssl.js` 或静态 patch。

## 七、React Native / Hermes 逆向

**机制**：Hermes 自 RN 0.70 起为默认 JS 引擎，构建期把 JS 提前编译为 Hermes 字节码（`.hbc`），放在 `assets/index.android.bundle`。**HBC 格式带整数版本号，运行时严格校验**（不匹配报 "Wrong bytecode version. Expected 96 but got 98" 并崩溃），因此工具必须逐版本适配。

| 工具 | 仓库 | 状态与限制 |
|---|---|---|
| **hermes-dec** | https://github.com/P1sec/hermes-dec | 活跃。`hbc-file-parser` / `hbc-disassembler` / `hbc-decompiler`；0.1.7 修复 **bytecode ≥ 97** 的解码 |
| hbctool | https://github.com/bongtrop/hbctool | 半活跃。`hbctool disasm` / `hbctool asm`（**可回写**）。**关键限制：仅支持 HBC 版本 59 / 62 / 74 / 76** |
| hermes_rs | https://github.com/Pilfer/hermes_rs | 活跃（Rust 反汇编/汇编） |
| hermes-decomp | https://github.com/SymbioticSec/hermes-decomp | 生态位窄 |

**实操**：

```bash
unzip app.apk assets/index.android.bundle
# 读前 8 字节 magic：c6 1f bc 03 c1 03 19 1f 为 Hermes 标识，并取版本号
hermes-dec hbc-decompiler index.android.bundle out.js
```

**警告**：hbctool 的支持版本表自 2021 年建立后未全面跟进，在 RN 0.7x/0.8x 上大概率不适用——**以实际 HBC 版本号为准，不要假定可用**。

## 八、Android 加固壳（伴随问题）

| 代际 | 技术特点 | 脱壳难度 | 代表工具 |
|---|---|---|---|
| 一代：DEX 整体加密 | Dex 整体加密，动态加载 | 较易，内存 dump | FRIDA-DEXDump、Dexhunter、elf-dump-fix |
| 二代：DEX 函数抽取 | 方法单独抽取加密，解密执行 | 可还原（dump 运行时方法体回填 dex） | FART、Youpk、BlackDex、Dex2oatHunter |
| 三代：VMP / Dex2C | 独立虚拟机解释执行 / 语义等价语法迁移 | **Dex2C 目前无办法还原，只能跟踪分析**；VMP 保护映射表，可人工还原 | 无成熟自动化工具 |

**工具局限（务必先读）**：

- **FART** 仅提供 Android 6.0 与 8.0 镜像；原始版无法应对 root 检测，**Fart8** 抹除了指纹。因项目知名，**加固厂商已将 FART 特征加入黑名单**
- **frida-fart** 需把 `fart.so`/`fart64.so` 拷到 `/data/app` 并 `chmod 777`；以 `spawn` 启动，进 Activity 后执行 `fart()`。高级用法 `dump(classname)` 可主动 dump 未执行过的方法。**缺点：无法处理带反调试的壳**——付费版加固必带反调试，会识别 frida 特征
- **BlackDex** 基于插件化思路。**因开源，特征明显，加固厂商易对抗**
- **FRIDA-DEXDump** 完整 dex 暴力搜索 `dex035` 魔数；抹头 dex 通过特征匹配

**壳特征识别**：爱加密 5 代壳在 `assets` 下可见 `IJMDal.Data`。

> 各厂商特征 so 文件名清单（爱加密/梆梆/乐固/聚安全/易盾/通付盾/娜迦）在二手来源间存在出入，**属未核实**，实际识别应以现场 `lib/` 目录列表与加载流程为准。

## 版本与维护状态速查

**活跃**：jadx 1.5.6 · Apktool 3.0.3 · Frida 17.22.2 · JEB 5.47 · Ghidra 12.1.4 · unidbg 0.9.9 · Magisk 30.7 · KernelSU · APatch · JingMatrix/Vector · blutter · reFlutter · hermes-dec 0.1.7 · hermes_rs · ipsw · Hopper 6.6.0 · Dopamine 3.0.10 · palera1n 2.4 · TrollStore 2.1.1 · PCAPdroid · ecapture · r0capture · AlwaysTrustUserCerts

**半停滞**：hbctool（版本支持表陈旧）· SSL Kill Switch 3（2023-11）· SimpleHook（闭源分发）

**已归档或事实停更**：rovo89/Xposed 系 · LSPosed/LSPatch · ptswarm/reFlutter · ViRb3/TrustMeAlready · DerekSelander/dsdump · LSPosed 官方构建（2023-10）· checkra1n · unc0ver · Taurine · XinaA15 · class-dump（停于 2019）· frida-ios-dump（停于 2020）

## 来源

- jadx：https://github.com/skylot/jadx
- Apktool：https://github.com/iBotPeaches/Apktool
- JEB changelog：https://www.pnfsoftware.com/jeb/changelog
- unidbg：https://github.com/zhkl0228/unidbg
- Magisk：https://github.com/topjohnwu/Magisk
- KernelSU：https://github.com/tiann/KernelSU
- APatch：https://github.com/bmax121/APatch
- LSPosed：https://github.com/LSPosed/LSPosed
- JingMatrix/Vector：https://github.com/JingMatrix/Vector
- Dopamine：https://github.com/opa334/Dopamine
- palera1n：https://github.com/palera1n/palera1n
- TrollStore：https://github.com/opa334/TrollStore
- iOS 26 越狱时间线：https://www.techspot.com/news/113408-jailbreak-ios-26-finally-here-326-days-after.html
- ipsw：https://github.com/blacktop/ipsw
- Stream App Store：https://apps.apple.com/us/app/stream-network-debug-tool/id1312141691
- Thor 下架监控：https://applecensorship.com/app-store-monitor/app/1210562295
- frida-multiple-unpinning：https://codeshare.frida.re/@akabe1/frida-multiple-unpinning/
- MASTG-TOOL-0140：https://mas.owasp.org/MASTG/tools/android/MASTG-TOOL-0140/
- frida-interception-and-unpinning：https://github.com/httptoolkit/frida-interception-and-unpinning
- MASTG-TECH-0012（NSC 绕过）：https://mas.owasp.org/MASTG/techniques/android/MASTG-TECH-0012
- ecapture：https://github.com/gojue/ecapture
- r0capture：https://github.com/r0ysue/r0capture
- Android CA 变更公告：https://android-developers.googleblog.com/2016/07/changes-to-trusted-certificate.html
- Android 安全配置：https://developer.android.com/privacy-and-security/security-config
- Conscrypt APEX 抓包：https://blog.nviso.eu/2025/06/05/intercepting-traffic-on-android-with-mainline-and-conscrypt/
- AlwaysTrustUserCerts：https://github.com/NVISOsecurity/AlwaysTrustUserCerts
- MoveCertificate：https://github.com/ys1231/MoveCertificate
- PCAPdroid：https://github.com/emanuele-f/PCAPdroid
- blutter：https://github.com/worawit/blutter
- reFlutter：https://github.com/Impact-I/reFlutter
- MASTG-TECH-0112（Flutter）：https://mas.owasp.org/MASTG/techniques/android/MASTG-TECH-0112
- hermes-dec：https://github.com/P1sec/hermes-dec
- hbctool：https://github.com/bongtrop/hbctool
- 加固三代划分：https://blog.csdn.net/weixin_39190897/article/details/114269713
- 加固与脱壳实操：https://juejin.cn/post/7423310754952675379
- FRIDA-DEXDump：https://github.com/hluwa/FRIDA-DEXDump
- BlackDex：https://github.com/CodingGay/BlackDex

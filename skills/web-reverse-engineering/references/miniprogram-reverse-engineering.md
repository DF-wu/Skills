# 小程序逆向（WeChat / Alipay / Douyin / QuickApp）

小程序是独立的逆向战场：包格式、运行模型、抓包可行性都与 Web 不同。

## 微信小程序

### wxapkg 文件格式

| 段 | 字段 | 类型 | 说明 |
|---|---|---|---|
| header | `firstMark` | Ushort | 固定 `0xBE`（190） |
| header | `info` | Ulong | 作用未知，通常为 0 |
| header | `indexInfoLength` | Ulong | 索引段长度 |
| header | `bodyInfoLength` | Ulong | 数据段长度 |
| header | `lastMark` | Ushort | 固定 `0xED`（237） |
| header | `fileCount` | Ulong | 文件数目 |
| index | `nameLength` | Ulong | 文件名长度 |
| index | `name` | Char[] | 长度 = `nameLength` |
| index | `offset` | Ulong | 文件在数据段偏移 |
| index | `size` | Ulong | 文件大小 |
| data | 文件数据 | — | 首尾相接 |

**实际日志示例**：

```
Header info: firstMark: 0xbe unknownInfo: 0 infoListLength: 15360
dataLength: 2960164 lastMark: 0xed
fileCount: 375
```

解包工具第一步校验 `0xBE` / `0xED` 魔数，对不上即判定非 wxapkg 或已被加密改造。

### 解包后的反直觉结构

目录里**没有** `wxml`，也**没有**分散的 `js`，只有几个巨大文件在根目录（典型为 `app-service.js`、`app-config.json`）。

**分包陷阱**：分包依赖去重，**解分包时必须提供主包目录**（工具 `-s` 参数），否则还原的 wxml 缺组件、wxss 缺变量。

### 工具链与维护状态

| 工具 | 仓库 | 语言 | 维护状态 |
|---|---|---|---|
| **KillWxapkg** | https://github.com/Ackites/KillWxapkg | Go | **活跃**。自动解密、解包、还原工程目录、支持 Hook、重新打包（`-repack`）、`-watch`、`-sensitive`；README 列出 Hook 支持的小程序版本（8447 ~ 11275_x64） |
| **wedecode** | https://github.com/biggerstar/wedecode | Node.js | **活跃**（GPL-3.0）。支持小程序 + 小游戏 + 分包 + 插件；还原 JS/WXML/WXSS/WXS/JSON 及媒体、wasm、workers；带可视化 UI（`wedecode ui`）、自动解密、polyfill 机制 |
| **wux1an/wxapkg** | https://github.com/wux1an/wxapkg | Go + Wails | **活跃**。跨平台 GUI（Windows/macOS），扫描 + 解密 + 解包 + 代码美化；CLI 子命令 `scan`/`unpack`，默认 30 线程 |
| unveilr | 看雪帖 | 闭源 | **新版转闭源、订阅制收费**；2.0 为流传的最后一版免费版本 |
| wxappUnpacker | https://github.com/Ryan-Miao/wxappUnpacker | Node.js | 历史版本。README 明确「当前功能如下（**分包功能尚未完成**）」 |
| CrackMinApp | https://github.com/Cherrison/CrackMinApp | C# + Node.js | **已实质停更**。README 标注「Bug 最新修复时间 **2019.10.24**」 |
| Sec-Fork/KillWxapkg-2 | https://github.com/Sec-Fork/KillWxapkg-2 | Go | Fork，功能子集（`-restore`/`-pretty`/`-ext`） |

**结论**：2024–2026 年仍活跃的只有 **KillWxapkg**、**wedecode**、**wux1an/wxapkg** 三个。

### 包获取路径

| 平台 | 路径 |
|---|---|
| Windows 微信 4.0 之前 | `C:\Users\{user}\Documents\WeChat Files\Applet\{AppID}\{数字}\__APP__.wxapkg` |
| Android | `/data/data/com.tencent.mm/MicroMsg/{用户ID}/appbrand/pkg/`（需 root 或模拟器） |

**定位目标包技巧**：用 Charles / 夜神模拟器抓包，根据请求头 `referer` 定位对应 pkg。

> 微信 4.0 之后的 xwechat 路径与 `pc_wxapkg_decrypt.exe -wxid ... -in __APP__.wxapkg` 用法：**未核实**。

### 请求特征（抓包前必读）

| 特征 | 值 |
|---|---|
| **referer 固定域名** | `servicewechat.com`，格式 `https://servicewechat.com/{appid}/{version}/page-frame.html`。**`wx.request` 的 referer 不可设置** |
| User-Agent（Android） | 微信内置浏览器 UA 后追加 **`miniProgram`** 标识 |
| User-Agent（iOS） | **与微信内置浏览器一致，无法用 UA 区分** |
| Promise 风格 | `wx.request` **不支持** Promise 风格调用（官方文档标注 `with Promise style call: Not supported`） |
| 包大小限制 | 超过 2MB 需分包；迁移时需带齐所有分包 |

**推论**：服务端接口的 referer 限制、COS 防盗链白名单、CDN 防盗链都**必须放行 `servicewechat.com`**。

### 云函数 / 云开发调用

**小程序内**：

```js
wx.cloud.init({ env, traceUser })
wx.cloud.callFunction({ name, data, config })
```

**服务端 HTTP API**：

```
POST https://api.weixin.qq.com/tcb/invokecloudfunction?access_token=...&env=...&name=...
参数：env / name / req_data（或 POSTBODY）
返回：errcode / errmsg / resp_data
```

**关键限制**：HTTP API 途径触发云函数**不包含用户信息**（无法获取 OpenID，无法使用涉及用户登录态的 API）；超时 5s。错误码含 `40014`、`40101`、`41001`、`42001`、`43002`、`44002`、`85088`。

**CloudBase OpenAPI**：

```
POST https://tcb-api.tencentcloudapi.com/api/v2/envs/${envId}/functions/${functionName}:invoke
```

**云托管调用**：

```js
wx.cloud.callContainer({
  config: { env },
  path, method,
  header: { "X-WX-SERVICE": "服务名" }
})
```

与 `wx.request` 的区别：内网通信不耗公网流量、仅授权小程序/公众号可访问、无需在小程序后台配置「服务器域名」、后端可直接获取 openid。跨环境需 `resourceAppid` / `resourceEnv`（云开发环境共享）。

云托管错误码：`102002` 请求超时（timeout 最大 15s）、`-601034` 没有权限请先开通云托管、`-606001` 请求包 > 100KB、`-606002` 响应包 > 1MB、`-606003` 账号欠费、`-606006` 不允许未登录模式请求、`-601027` Environment not found、`-601031` 服务不存在。

### 抓包可行性（关键）

微信云请求分四类：

| 类型 | 机制 | 可抓性 |
|---|---|---|
| 1 | 基于微信 **Mmtls** 协议调用 `OperateWxData` 接口，走微信私有链路 | **标准抓包软件抓不到** |
| 2 | 基于 **HTTP/2 + 鉴权**：先通过 Mmtls 的 `qbase_commit` → `tcbapi_get_service_info` 拿到加密参数与鉴权 Token；请求体用 key 加密并**用 snappy 压缩**；数据格式为 ProtoBuf 或 JSON；解密算法为 **AES-CBC** | 需解密 |
| 3 | 不鉴权的 HTTP/2（微信云托管/云网关，但不在小程序内） | 可抓 |
| 4 | 基于 **HTTP 明文**的微信云网关（用于其他 App），带 Socks 的抓包软件可抓到 | 可抓。请求头附 **`x-wx-auth-code`** 与 **`x-wx-call-id`**，二者由 URL 与 Body 计算得出（**算法在 so 层**） |

**降级抓包思路**：通过 Frida hook 触发异常，强制把 HTTP/2 云网关降级为 `JSOperateWxData` / Mmtls，从而无需处理 AES 即可抓明文（社区项目适配安卓微信 848/849/850，降级云函数适配 848/849）。

> wxapkg 包类型标识 `APP_V3` / `APP_V4` / `APP_SUBPACKAGE_V2` / `APP_PLUGIN_V1`：**未核实**（但 `__WITHOUT_MULTI_PLUGINCODE__.wxapkg` 与 `__APP__.wxapkg` 的存在可由来源佐证）。

## 支付宝小程序

**打包与运行机制**：

- 客户端从 CDN 下载**离线包**，是将原项目打包后的一个 **`.tar` 文件**
- 存放于 `/data/data/com.eg.android.AlipayGphone/files/nebulaInstallApps`
- 解压后得到 `index.html`、`index.js`、`index.worker.js`
- `index.worker.js` 为所有页面业务逻辑（对应开发者写的 `pageName.js`）
- `index.html` / `index.js` 对应 acss 与 axml（**axml 组件信息与层次结构被编译成 js**，运行时渲染）

**双线程模型**：

| 线程 | 内容 | 运行环境 |
|---|---|---|
| Render（视图） | `index.js` + 框架 `af-appx.min.js` | WebView |
| Worker（应用服务） | `index.worker.js` + `af-appx.worker.min.js` | V8 引擎 |

**代码加载**：Render 通过 WebView 的 `loadUrl()` 加载，`af-appx.min.js` 通过 `writeln()` 动态写入。可 **hook `WVUCWebView` 类的 `loadUrl` 函数**观察加载。

开发者文件类型：`.axml`（对标 HTML）、`.acss`（对标 CSS）、`.js`。

> 社区常把支付宝小程序包通称为 `apkg`；可核实的载体是 CDN 下发的 **`.tar` 离线包**。**「`apkg` 后缀」这一说法未核实**。

## 抖音小程序

**格式**：`TPKG` / `ttpkg.js` / `pkg` 文件，分两类：

1. 明文索引的小程序包
2. 带 **`JSON{"__ttks":...}`** 头部的小游戏包索引变体

**工具**：[`XueDugu/ttpkgUnpacker`](https://github.com/XueDugu/ttpkgUnpacker)（Python）

- 修复明文 `TPKG` 索引偏移兼容
- 新增 `__ttks` 加密索引解码（可恢复文件名、偏移、大小）
- 自动生成 `unpack-report.json` / `unpack-report.md`（树状结构、文件统计、入口文件）
- 自动恢复 `app.json` 与页面 `.json`
- 防止路径逃逸写出
- 内置样本：`038d897.ttpkg.js`（明文小程序）、`e2670a8.pkg`（明文 pkg）、`8862e65.pkg`（小游戏 `__ttks` 索引）

**局限**：部分小游戏 payload 仍可能带业务侧混淆，**解包不等于完全反混淆**；`ttss` / `ttml` 规则恢复逻辑仍偏启发式。

**用法**：

```bash
python3 ttpkgUnpacker/main.py xxx.ttpkg.js
python3 -m ttpkgUnpacker <dir>
```

另有 `gitee.com/xipis/ttpkUnpacker` 为另一实现。

## 快应用 QuickApp

| 项 | 值 |
|---|---|
| 打包产物 | **`.rpk`** 文件（如 `com.application.demo.rpk`） |
| 编译工具 | `hap-toolkit`（`npm run build` 生成 `build`/`dist`，`dist` 内为 rpk） |
| 页面源文件 | `.ux` |
| 项目配置 | `quickapp.config.js` |
| 本地调试 | `npm run server` 起本地 HTTP 服务器（默认 8000），手机调试器扫码安装 |
| 设备侧安装 | 把 rpk 放到 `sdcard/rpks` 后用「平台预览版」运行 |
| 平台切换 | 调试器可切换运行平台至 `org.hapjs.mockup` |

**官方立场（快应用官方论坛第 120 期交流记录）**：

> 问：快应用 rpk 可以反编译么？
> 答：**不可以**。

华为快应用 IDE 提供「打开 RPK」功能（菜单 `文件 > 打开 RPK`），属**官方正向工具**，不是反编译。

**结论**：快应用的社区可核实路径是「获取 rpk + 平台预览版运行观察」，而非静态还原。

## 来源

- wxapkg 结构表：https://daijunooo.github.io/2019/01/31/unpack
- wxapkg 真实日志与分包 `-s`：https://blog.poetries.top/2021/04/20/wx-compile-summary
- unveilr 闭源与 `unpacked 185 files` 日志：https://bbs.kanxue.com/thread-281804.htm
- 魔数校验逻辑：https://blog.csdn.net/gitblog_01107/article/details/159427625
- KillWxapkg：https://github.com/Ackites/KillWxapkg
- wedecode：https://github.com/biggerstar/wedecode
- wux1an/wxapkg：https://github.com/wux1an/wxapkg
- wxappUnpacker（分包未完成）：https://github.com/Ryan-Miao/wxappUnpacker
- CrackMinApp（2019 停更）：https://github.com/Cherrison/CrackMinApp
- Android 包路径：https://www.cnblogs.com/tlnshuju/p/19455602
- referer 固定 servicewechat.com：https://cloud.tencent.com/developer/information/servicewechat.com
- 小程序 UA 差异：https://zhangzifan.com/wechat-user-agent.html
- wx.request 不支持 Promise：https://developers.weixin.qq.com/miniprogram/en/dev/api/network/request/wx.request.html
- 云函数 HTTP API：https://developers.weixin.qq.com/miniprogram/dev/server/API/cloudbase/functions/api_invokecloudfunction.html
- CloudBase OpenAPI：https://docs.cloudbase.net/api-reference/openapi/function
- 云托管调用：https://docs.cloudbase.net/run/develop/access/mini
- 云托管错误码：https://developers.weixin.qq.com/minigame/dev/wxcloudrun/src/development/call/faq.html
- 微信云四类抓包可行性：https://github.com/anrikgwp/RYF5584-AndroidWXCloudFuncHook
- Frida 主动调用云托管 API：https://bbs.kanxue.com/thread-284878.htm
- 支付宝双线程与 hook loadUrl：https://juejin.cn/post/7137478354042617869
- 支付宝离线包机制：https://blog.csdn.net/weixin_52381874/article/details/141713311
- 抖音 ttpkgUnpacker：https://github.com/XueDugu/ttpkgUnpacker
- 抖音 ttpkg 看雪分享：https://bbs.kanxue.com/thread-287249.htm
- 快应用 CLI：https://doc.quickapp.cn/ide/cli.html
- 快应用 toolkit：https://doc.quickapp.cn/framework/toolkit.html
- 快应用官方「不可反编译」答复：https://bbs.quickapp.cn/v2/forum/info?id=2011
- 华为 IDE 打开 RPK：https://developer.huawei.com/consumer/cn/doc/Tools-Guides/ide-rpk-0000001183309176

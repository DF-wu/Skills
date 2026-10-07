# 验证码与设备指纹厂商专项（GeeTest / Aliyun / Tencent / NetEase / Shumei / Dingxiang / Tongdun）

本文按厂商逐一拆解参数结构。**通用原则**：先判断是「验证码」还是「设备指纹」，两者目标不同——验证码要拿到 `validate`/`token`，设备指纹要产出稳定的 `deviceId`/`blackbox`。

## 极验 GeeTest

### 三代（v3）

**接口链**：

| 步骤 | 接口 | 产出 |
|---|---|---|
| 1 | `register-slide-official` / `register-slider` / `register-click-official` | `gt`（站点固定特征码）、`challenge`（每次变化） |
| 2 | `gettype.php` | 携带 `gt`，返回验证码类型 |
| 3 | `get.php` | `c`、`s`、滑块图/底图 |
| 4 | `ajax.php` | 模式（`slide`/`click`）；通过后返回 `validate` |
| 5 | `validate.php` | 服务端二次校验 |

**w 参数**：三代有**三个 w**（`get.php` 两次 + `ajax.php` 一次）。

- **旧版**：除最后一个 `ajax.php` 外，w 可为空字符串
- **新版**：三个 w 相互关联，**任一错误即 `forbidden`**

**w 构成**：

```
w = AES(明文) + RSA(16 位随机字符串密钥)
```

AES 明文含 `gt`、`challenge`、用户 IP、版本、`c`、`s`、浏览器信息、鼠标轨迹。RSA 部分为 16 位随机字符串经 RSA 公钥加密。

**细节**：`h9s9` 等为固定参数；三代点选类 AES 的 **iv 为 `0000000000000000`**。

**定位技巧**：全局搜索特征码 `"\u0077"`（即 `w` 的 Unicode 转义），进入 `slide.X.Y.Z.js` / `click.X.Y.Z.js`。

### 四代（v4）

| 项 | 值 |
|---|---|
| 站点标识 | 仅 `captcha_id`（无 `gt`/`challenge`） |
| load 接口 | `gcaptcha4.geetest.com/load` |
| verify 接口 | `gcaptcha4.geetest.com/verify` |
| load 返回 | `lot_number`、`captcha_type`、`bg`、`slice`、`ypos`、`pow_detail`（`version`/`bits`/`datetime`/`hashfunc`）、`payload`、`process_token`、`payload_protocol` |
| verify 参数 | `lot_number`、`payload`、`process_token`、`payload_protocol`、`pt`、`w`、`callback` |
| verify 返回 | `result: success/fail` |

**w 结构**：

```
w = hex(AES_CBC(w_data, aes_key)) + hex(RSA_Encrypt(aes_key))
```

**PoW**：按 `pow_detail.bits` 与 `hashfunc` 做哈希碰撞，产出 `pow_msg` / `pow_sign`。

**其他字段**：

- `device_id`（同站点固定）
- `userresponse`（社区给出 `setLeft / 1.0059466666666665 + 2`，属经验拟合值，需按目标实测校准）
- `passtime`
- **时间格式必须为带 `+08:00` 时区的 ISO 字符串**

**JSONP 陷阱**：响应为 JSONP，需**动态定位 `(` / `)` 解析**，不能硬编码偏移——callback 名长度随时间戳变化。

> 部分版本关键逻辑下沉 WASM（AES-CBC + HMAC-SHA256）的说法来自社区，本轮**未定位到可引用来源，属未核实**。若遇 WASM 路径，见 `wasm-reverse-engineering.md`。

### GeeGuard（设备指纹，非验证码）

`gee_guard` / GeeGuard 是极验的**设备指纹产品**，不是验证码接口。能力为本地生成短期可信设备 GeeToken，并与业务方业务唯一标识**双向绑定**（通过签名，仅对当前业务流程有效）。

鸿蒙版 SDK 权限：`INTERNET` / `GET_NETWORK_INFO` / `STORE_PERSISTENT_DATA`，可选 `APP_TRACKING_CONSENT`（OAID）。

> `gee_guard` 作为 Cookie 名或参数名出现的用法**未核实**；已核实的只是 GeeGuard 为产品名。

**官方隐私政策披露的采集面**（可直接用于判断检测维度）：设备信息、设备网络信息、设备环境信息（含越狱/调试/模拟器/代码篡改标识、UA、referer）、**用户生物轨迹信息**（滑动/点击/鼠标移动轨迹）、时间戳、安装包名。

## 阿里云盾 / 阿里 WAF

### Cookie 体系（官方文档明示）

阿里云官方合规声明给出**三种植入场景**：

| 场景 | 触发条件 | 植入 Cookie | 用途 |
|---|---|---|---|
| 一 | 使用 CC 防护/扫描防护且请求 Cookie 不含 `acw_tc` | `acw_tc`、`cdn_sec_tc` | 区分统计不同客户端；配合「统计对象为 session」的防护规则判断 CC 攻击 |
| 二 | 站点配置 Bot 管理高级模式并开启自动集成 Web SDK | `ssxmod_itna`、`ssxmod_itna2`、`ssxmod_itna3` | 收集指纹（含 HTTP 报文 `host` 字段、浏览器高度宽度等） |
| 三 | WAF 自定义规则或 Bot 管理规则动作开启 JS 校验 / 滑块 | `acw_sc__v2`（JS 校验通过）、`acw_sc__v3`（滑块通过） | 验证通过凭证 |

**官方细节**：

- 处置动作过期时间：验证通过后默认 **1800 秒（30 分钟）**内放行，可配 5–1800 秒
- WAF 3.0 防护对象设置：跟踪 cookie 即 `acw_tc`，可配置下发状态与 `secure` 属性，**`SameSite` 属性暂不支持配置**；滑块 cookie 即 `acw_sc__v3`，可配置 `secure`
- `acw_tc` 示例值：`2f7b12da17525774695245703ee21f15714874ac9b5788522f6bf6f459`，`path=/; HttpOnly; Max-Age=3600`

**结论对照**：

- `acw_tc` = 客户端会话跟踪 Cookie
- `cdn_sec_tc` = 同类会话标记（标记不同客户端会话、统计同一会话发起攻击频率）
- `acw_sc__v2` = JS 挑战通过凭证
- `acw_sc__v3` = 滑块验证通过凭证

### `acw_sc__v2` 生成算法（社区可复现）

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

即 `acw_sc__v2 = hexXor(unsbox(arg1))`。

- `arg1` 是 **40 位 hex 字符串，每次刷新动态变化**（由 202 响应内联脚本给出）
- `arg2` 即最终 Cookie 值

**JS 原版特征**：含 `while (window["_phantom"] || window["__phantomas"]) {}` 死循环（针对 Selenium/Phantomas 类自动化）与 `var _0x5e8b26 = "3000176000856006061501533003690027800375";`，最终触发 `reload(arg2)`。

**对抗流程**：正则或 DOM 解析取出 202 页面内联 `arg1` → 本地执行 `unsbox` + `hexXor` → 携带 `acw_sc__v2` 重放。

**阿里系两套体系**（社区风控集合）：`140#` 开头加密参数 与 `227!` 开头 + `fireyejs.js`，另有控制流平坦化 / WASM / 滑块轨迹。

## 腾讯 TCaptcha（天御 / 防水墙）

### 文件清单（看雪原创分析）

| 文件 | 大小 | 作用 | 混淆程度 |
|---|---|---|---|
| `TCaptcha.js` | — | 入口/加载器 | 低 |
| `tcaptcha-frame.js` | 207KB | 主框架逻辑 | 中（Webpack） |
| `dy-ele.js` | 209KB | 滑块核心逻辑 | 中（Webpack） |
| `tdc.js` | 78KB | 设备指纹采集 | 极高（JSVMP） |

### verify 接口参数

| 参数 | 含义 |
|---|---|
| `collect` | TDC 加密的设备指纹 + 轨迹数据 |
| `tlg` | `collect` 长度 |
| `eks` | TDC 生成的加密密钥信息 |
| `sess` | 会话标识 |
| `ans` | 滑块答案 JSON |
| `pow_answer` | PoW 结果 |
| `pow_calc_time` | PoW 耗时毫秒 |
| `subsid` | 子会话 ID，递增 |
| `callback` | JSONP 回调名，形如 `_aq_191730` |

### JSVMP 细节

`tdc.js` 使用腾讯自研 `__TENCENT_CHAOS_STACK` / `__TENCENT_CHAOS_VM` 自定义字节码解释器，字节码以**数万个数字的大数组内联**，核心加密逻辑全部在 VM 内执行。

另有随机变量名存储 `eks`，如 `window.KcYVdONjSbHEDgmXanKNEdRPYPMTPdOh`，**每次加载变化**——使 hook 脚本不稳定。

**TDC 常用调用形态**：

```js
collect = decodeURIComponent(window.TDC.getData(true));
eks     = window.TDC.getInfo().info;
window.TDC.setData({ ft: "q__7Pf__H" });
```

**PoW**：暴力搜索 `md5(nonce + counter) === target`，返回 `ans`（counter）与 `duration`。

**难点**：JSVMP + 随机变量名 + 数万数字字节码数组，静态分析与扣代码成本极高。

> 腾讯云 WAF 是否存在与阿里 `acw_sc__v2` 同级别的**独立具名 JS 挑战 Cookie：未核实**。社区常把 `tdc.js`（实为 TCaptcha）与腾讯云 WAF 混为一谈，二者应分开陈述。

## 网易易盾

### 设备指纹查询接口字段（官方文档）

| 字段 | 类型 | 说明 |
|---|---|---|
| `taskId` | String | 本次查询操作唯一标识 |
| `tokenCreationTime` | Number | token 生成时间（UNIX 毫秒） |
| `device.deviceId` | String | 设备指纹 ID |
| `device.sdkType` | Number | 1-Web，2-Android，3-iOS，**4-小程序** |
| `checkResult.isTampered` | Number | 上传请求是否被篡改 |
| `checkResult.isSimulator` | Number | 是否模拟器 |
| `checkResult.isRooted` | Number | 是否 Root/越狱 |
| `checkResult.isMultiRun` | Number | 是否多开 |
| `checkResult.isVpn` / `isProxy` | Number | VPN / 代理 |
| `checkResult.isHooked` / `isInjected` / `isDebugged` | Number | hook / 注入 / 调试 |
| `checkResult.isXposed` | Number | Xposed |
| `checkResult.isCloud` / `isSuspectCloud` | Number | 云手机 / 疑似云手机 |
| `checkResult.isRiskRom` / `isVm` / `isModify` / `isModifyApp` | Number | 风险 ROM / 虚拟机 / 改机 / 改包 |
| `checkResult.isFlash` / `isAutoTouch` / `isControlApp` / `isScript` | Number | 一键刷机 / 自动点击 / 群控 / 脚本 |
| `checkResult.securityScore` | Number | 安全评分 |
| `checkResult.isCydiaSubstrate` / `isM1` / `isSpeedUp` / `isAntiJailbreak` | Number | iOS 侧风险项 |

**注意**：官方文档标题标注该设备指纹文档为**「已下线」**，接入方式可能已迁移。此表的价值在于**反推检测维度**。

### Web 侧参数（社区）

- 域名特征 `163`；参数 `data`、`fp`、`cb`（另有 `token`、`acToken`）
- Cookie / 全局属性 `gdxidpyhxdE`（`window["gdxidpyhxde"]`）与 `fp` 关联：**先生成参数 → 写入 cookie → 再从 cookie 取值作为 `fp`**
- 定位：hook `window["gdxidpyhxde"]` 的 setter
- `data` = 加密后的滑动轨迹数组，含 `atomTraceData`（未加密轨迹）、`p`、`ext`、`m` 等字段
- 轨迹元素三元组：`[Math.round(dragX < 0 ? 0 : dragX), Math.round(clientY - startY), now() - beginTime]`
- `ext` = `f(token, mouseDownCounts + ',' + traceData.length)`
- 服务端返回 `validate` 即验证通过
- 参数名带版本特征，社区分析覆盖 2.19.1 / 2.27.2 / 2.28.0 / 2.28.5
- **环境要求：JS 环境的 UA 与请求 UA 必须一致**（否则通过率显著下降）
- 类型值：`7` = 顺序点选，`2` = 滑块

## 数美 shumei

### v4 设备 ID 生成

| 项 | 值 |
|---|---|
| 入口文件 | `fp.min.js`（经 ob 混淆） |
| 请求参数 | `organization`（数美产品唯一标识）、`data`、`ep` |
| `ep` | `rsaEncrypt(uuid, publicKey)`；`publicKey` 由 `api.js` 返回；`uuid` 由 `getUid` 生成（标准 UUID v4 形态） |
| `data` | **gzip 压缩后的明文数据**，再用 **AES-CBC** 加密：key = `priId`，**iv 固定为 `0102030405060708`** |
| `priId` | 对生成 `ep` 时传入的 uuid 参数**截取**后做标准 **MD5** |
| 明文内容 | 浏览器环境、加密参数等；`smid` 由 `getLocalsmid()` 返回；`MD5_Encrypt` 为标准 MD5（`'smsk_web_' + ...` 形态） |
| `Protocol` | 携带动态 DES key |
| `deviceId` 形态 | 由 v4 接口返回内容前拼接 `"B"` 得到 |
| Cookie | `smidV2` / `smDeviceId`，另有 `shumeiBlockBox` |

### 滑块

- 接口 `register`（获取图片与加密信息）、`fverify`（验证，v2 路径 `/v2/fverify`）
- `organization` 为加密字段
- `rid` 由 `register` 传递，实际变化参数约三位，主要随**滑动距离、滑动时间、滑动轨迹**变化
- 加密算法涉及 **DES-ECB + Zero Padding + Base64**
- `captchaUuid` = `generateTimeFormat()` + 16 位随机
- box 相关：`boxId` 以 `'B'` 开头、89 字符；`boxData` 以 `'D'` 开头、约 8K

### 官方产品能力（用于理解检测面）

设备指纹声称能力：设备唯一标识、虚假设备识别、机器操控设备标签、设备可疑标签（可识别 Root、无 SIM 卡、VPN、设备重置等二十余种）、设备属性标签（50+ 维度）。**风险环境识别**明确包含：检测代理服务器、**设备调试状态与运行环境**、高危软件，识别设备农场、多开 APP 等。

> 厂商宣称的「重码率低至万分之一」「适配 3.2 万+ 型号」等为营销数据，未经独立核实。

## 顶象 dingxiang

### 官方可核实内容

- 产品名「智能无感验证」
- SDK 类 `DXCaptchaView` / `DXCaptchaViewV5`；监听器 `DXCaptchaListener` / `DXCaptchaEvent`
- 验证成功回调返回 `token`（用于后端校验）
- **若 token 以 `sl` 开头，则为前端网络不通生成的降级 token**
- 参数：`constID_js` / `constIDServer` / `constID_options`（Android/iOS SDK 内无需配置）、`captchaJS`、`keyURL`、`corsBaseURL`（v5.1.3r+）
- 事件：`success` / `fail` / `onCaptchaJsLoaded`（v5.1.7r+）/ `onCaptchaJsLoadFail`
- 设备指纹模块类名 `DXRiskManager`（`ConstID` 模块），另有 `hardId` 概念

### 请求链与参数（社区，2019–2021 分析，可能过时）

| 步骤 | 接口 | 产出 |
|---|---|---|
| 1 | `c1` | `c` 参数（用于计算设备指纹） |
| 2 | `a` | 图片与 `token2`；返回 `sid`、`y`、`p1`/`p2`/`p3`（乱序拼图 webp 路径） |
| 3 | `v1` | `token3` |

参数表：`ak`（AppId 关联固定值）、`ac`（加密参数，形如 `492#X8Xn8AQv/Y6pdvgYXXfOuMffR/...`）、`aid`（时间戳 + 随机数 + 1，推测 nonce）、`jsv`（版本号，如 `1.3.11.98`）、`sid`、`de`、`wp`、`s`/`h`/`w`、`_r`、`x`/`y`。

指纹存储在 cookie、Session Storage、Local Storage **多处**。

失败响应示例：`{"data":"f8839e00435f2e05f9ed60b3d3c5498554cb367655ec6e7318adefda150437040a74963c","msg":"lid invalid","status":-4}`

> 顶象错误码 `-10001` ~ `-10007`：**未核实**。

## 同盾

### 无感（设备指纹）

- 文件 `fm.js`，参数 **`blackbox`**
- 参数名体系 `a`/`b`/`c`/`d`… 或 `h`/`i`/`j`/`k`…
- **`blackbox` 位置历史上在 payload，后迁移到 headers**
- 全局配置对象 `window._fmOpt`（含 `token`、`partner`、`appName`）
- `oO0QQo.mfaId`（可能为 `undefined`）

### 滑块 `p1` ~ `p9`（v2）

| 参数 | 构造 |
|---|---|
| `p1` | `blackBox`（`QQoooQ.blackBox`，也可暂时写死） |
| `p2` | `blackBox + ^^1^^1^^1` |
| `p3` | `MD5(...)`（常数特征明显，标准 MD5） |
| 其他 | `window._fmOpt.token` / `.partner` / `.appName` / `oO0QQo.mfaId` 参与构造 |

加密涉及 **AES**（iv 形如 `Moa14C2uXpe8AUJ5`）与 **DES3**。

**图片接口与验证接口为同一接口，仅请求参数不同。** 验证结果字段：`needValidateCode`、`validateToken`。

**重要提示**：社区明确指出「这个分析只是同盾其中一份算法，**它不止一份算法**」——同盾存在多套并行算法，不可假定单一实现。

### TrustDecision（同盾出海品牌）

提供轻量级 JS 与移动端 SDK，声称输出 70+ 项设备风险标签，支持 Web/iOS/Android/小程序。

> 同盾官方 Web SDK 完整字段清单：**未核实**。

## 横向对比

| 厂商 | 加密算法特征 | 固定值/常量 | 主要难点 |
|---|---|---|---|
| 阿里 | 自定义异或 + 40 字节置换表 | `3000176000856006061501533003690027800375` | 内联 arg1 动态变化 + 反自动化死循环 |
| 极验三代 | AES + RSA 拼接，三个 w 关联 | 点选类 iv = 全零 | 三 w 强关联 |
| 极验四代 | AES-CBC + RSA + PoW | — | PoW 碰撞 + JSONP 动态解析 |
| 腾讯 | 自研 JSVMP 字节码 | — | 数万数字字节码数组 + 随机变量名 |
| 易盾 | 未完全公开 | `gdxidpyhxdE` cookie 名 | 参数版本杂 + UA 一致性要求 |
| 数美 | AES-CBC（gzip 预处理）+ RSA + MD5 | iv = `0102030405060708` | 相对最低 |
| 顶象 | 自定义（`ac` 形如 `492#...`） | — | 环境校验维度多 |
| 同盾 | AES + DES3 + MD5 | iv 形如 `Moa14C2uXpe8AUJ5` | 多套并行算法 |

## 来源

- 极验三代全链：https://www.cnblogs.com/ikdl/p/17001212.html
- 极验三代三 w 关联：https://cloud.tencent.com/developer/article/2383906
- 极验三/四代点选与 AES iv：https://www.cnblogs.com/ikdl/p/17272966.html
- 极验四代 w = AES+RSA + PoW：https://blog.csdn.net/weixin_42384784/article/details/160193114
- 极验 GeeGuard 集成指南：https://docs.geetest.com/guard/quick_integration_guide
- 极验隐私政策（采集面）：https://www.geetest.com/Private
- 阿里云合规声明（Cookie 植入场景）：https://help.aliyun.com/zh/waf/web-application-firewall-3-0/web-application-firewall-3-0-security-compliance-instructions
- 阿里 WAF 3.0 防护对象设置：https://help.aliyun.com/zh/waf/web-application-firewall-3-0/protected-objects-and-protected-object-groups
- `acw_sc__v2` 完整实现：https://www.cnblogs.com/wyh0923/p/16590583.html
- 腾讯 TCaptcha 文件清单与 JSVMP：https://bbs.kanxue.com/thread-290429.htm
- 腾讯纯协议还原研究：https://github.com/decodecaptcha/TencentCaptchaBreak
- 易盾设备指纹字段表：https://support.dun.163.com/documents/609099986339037184?docId=624010587874123776
- 数美 v4 设备 ID：https://cloud.tencent.com/developer/article/2475504
- 数美滑块：https://hyb.life/archives/209
- 顶象 SDK 文档：https://www.dingxiang-inc.com/docs/detail/captcha
- 顶象 ConstID：https://www.dingxiang-inc.com/docs/detail/const-id
- 顶象请求链分析：https://www.cnblogs.com/boycelee/p/14270112.html
- 同盾 BlackBox：https://1997.pro/archives/1706068432055
- 同盾 v2 滑块 p1~p9：https://cloud.tencent.com/developer/article/2501583
- 社区风控集合：https://1997.pro/archives/1713518394359

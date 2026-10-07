# 签名与加密参数逆向（Signature & Encrypted Parameter RE）

Web 逆向中最常见的任务是「接口有一个/多个加密参数，需要本地生成」。本文给出系统化定位与复现方法。

## 定位流程（先定位，再复现）

```text
1. 抓包，标记所有可疑参数（无规律长串、hex、base64、短时间戳、递增 ID）
2. 判断参数数量与关联性（一个还是多个？是否互相依赖？）
3. 全局搜索参数名 → 若无结果，说明被混淆（见下）
4. 打 XHR/fetch 断点，回溯调用栈找到生成点
5. 判断加密类型（见「算法识别」）
6. 选择复现路线：扣代码 / 补环境 / RPC
```

### 搜索不到参数名时的四种手段

参数名被混淆是常态（如极验对每个关键参数都做了替换）。可选：

1. **堆栈慢慢调试**——最原始但最可靠
2. **手写 AST 还原混淆代码**
3. **通过 AST 内存漫游定位**
4. **拿在线工具解混淆后再考虑**

推荐组合：先变量名去混淆 → 把 JS 存本地 → 开启本地替换（Local Overrides）→ 此时就能搜关键词和调试了。

### 断点选择

| 目标 | 断点位置 |
|---|---|
| 请求参数 | `XMLHttpRequest.prototype.send` / `XMLHttpRequest.prototype.setRequestHeader` / `window.fetch` |
| Cookie 生成 | `document.cookie` 的 setter |
| 指纹生成 | 特征参数名所在函数的入口 |
| 轨迹相关 | 鼠标/触摸事件监听器 |

```js
// XHR 参数拦截：打印每次请求的完整参数
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

## 算法识别

### crypto-js 特征

**重要状态**：crypto-js 已**停止维护**。README 原文："Active development of CryptoJS has been discontinued. This library is no longer maintained."

**模块清单（可直接作指纹字典）**：

| 类别 | 模块名 |
|---|---|
| 核心 | `core`、`x64-core`、`lib-typedarrays` |
| 摘要 | `md5`、`sha1`、`sha256`、`sha224`、`sha512`、`sha384`、`sha3`、`ripemd160` |
| HMAC | `hmac-md5`、`hmac-sha1`、`hmac-sha256`、`hmac-sha224`、`hmac-sha512`、`hmac-sha384`、`hmac-sha3`、`hmac-ripemd160` |
| KDF | `pbkdf2`、`evpkdf` |
| 密码 | `aes`、`tripledes`、`rc4`、`rabbit`、`rabbit-legacy` |
| 格式 | `format-openssl`、`format-hex` |
| 编码 | `enc-latin1`、`enc-utf8`、`enc-hex`、`enc-utf16`、`enc-base64` |
| 模式 | `mode-cfb`、`mode-ctr`、`mode-ctr-gladman`、`mode-ofb`、`mode-ecb`（**CBC 是默认，故无独立模块**） |
| 填充 | `pad-pkcs7`（默认）、`pad-ansix923`、`pad-iso10126`、`pad-iso97971`、`pad-zeropadding`、`pad-nopadding` |

**识别特征**：

- 调用签名 `CryptoJS.AES.encrypt(msg, key, {iv, mode: CryptoJS.mode.CBC, padding: CryptoJS.pad.Pkcs7})`
- 密文是 `WordArray`，取 `CipherParams.ciphertext`
- **OpenSSL 格式密文以 ASCII `Salted__`（8 字节）开头 + 8 字节 salt**；密钥由 **EVPKDF** 派生（默认丢弃 192 words / 768 字节）
- 输出转换 `.toString(CryptoJS.enc.Utf8)` / `.toString(CryptoJS.enc.Base64)` / `.toString(CryptoJS.enc.Hex)`

**版本陷阱**：

- **3.2.0 有 CRITICAL BUG，README 明确标注 "DO NOT USE THIS VERSION"**
- 4.0.0 起 `Math.random()` 被原生 crypto 随机数替换
- 4.1.0 新增 URL-safe base64 变体
- 4.2.0 变更 PBKDF2 默认哈希与迭代次数，新增 Blowfish 与自定义 KDF Hasher

### 国密 SM2 / SM3 / SM4

```js
const sm2 = require('sm-crypto').sm2
let keypair = sm2.generateKeyPairHex()          // publicKey(130位) / privateKey
sm2.compressPublicKeyHex(publicKey)             // 压缩到 66 位
const cipherMode = 1                            // 1 = C1C3C2（默认），0 = C1C2C3
sm2.doEncrypt(msg, publicKey, cipherMode)
sm2.doDecrypt(encryptData, privateKey, cipherMode)

const sm3 = require('sm-crypto').sm3
sm3('abc')                                      // 杂凑
sm3('abc', { key: '<hex 或字节数组>' })          // HMAC

const sm4 = require('sm-crypto').sm4
sm4.encrypt(msg, key)                           // 默认输出 hex，默认 pkcs#7
sm4.encrypt(msg, key, { padding: 'none', output: 'array' })
sm4.encrypt(msg, key, { mode: 'cbc', iv: '<32 hex>' })
```

**逆向识别要点（README 明确记载的坑）**：

- **SM2 密文解密时会自动补 `04` 前缀**。若密文来自其它工具且已含 `04`，**必须手动去除再传入**——这是判定「密文来源工具」的关键线索
- SM2 签名 `hash` 参数默认 `true`（做 SM3 杂凑）；纯签名需显式 `hash: false`。默认 `userId` 为 `1234567812345678`
- `der: true` 启用 DER 编解码；`pointPool` 可传入预生成椭圆曲线点加速
- SM4 key 必须 128 位；传 `pkcs#5` 也会走 pkcs#7 填充

### 魔改 Base64

**机制**：分两种情况——① 直接定义新编码 table；② 动态生成新编码 table。两种情况均可通过「还原出编码时使用的 table」来等价解码。

**识别与还原**：

- **静态特征**：源码中出现 64 字符长字符串常量，且字符集为 RFC 4648 字母表 `ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/` 的**置换**（URL-safe 变体为 `+/` → `-_` 且省略 `=`）
- **动态特征**：table 由 `charCodeAt` / 位运算在运行时拼装（需在生成后 dump）
- **还原**：提取 table → 构建反向映射 → 解码
- **快速启发式**：尝试标准 base64 解码，若得到乱码但**长度合规（原长 × 3/4）**，则高度可疑为字母表置换

### RSA 公钥提取

**jsencrypt** 是 Web 端最常见的 RSA 实现。

- 定位："A tiny (18.5 kB gzip), zero-dependency, Javascript library to perform OpenSSL RSA Encryption, Decryption, and Key Generation"
- 调用：`new JSEncrypt()` → `setPublicKey(pemString)` / `setPrivateKey(pemString)`；**设私钥时公钥会自动派生**
- `encrypt()` 返回 base64 字符串；`decrypt()` 失败返回 `false`
- 签名：`signSha256(data)` / `verifySha256(data, signature)`；支持哈希 `md2`、`md5`、`sha1`、`sha224`、`sha256`、`sha384`、`sha512`、`ripemd160`
- OAEP：`encryptOAEP(data)`
- 支持格式：私钥 PKCS#1（`-----BEGIN RSA PRIVATE KEY-----`）、公钥 PKCS#8（`-----BEGIN PUBLIC KEY-----`）
- 底层：Tom Wu 的 jsbn（核心算法未改动）

**PEM 组件 ↔ jsbn 变量映射表**（逆向时直接对照内存对象）：

| PEM 组件 | jsbn 变量 |
|---|---|
| modulus | `n` |
| public exponent | `e` |
| private exponent | `d` |
| prime1 | `p` |
| prime2 | `q` |
| exponent1 | `dmp1` |
| exponent2 | `dmq1` |
| coefficient | `coeff` |

**公钥提取实操**：

1. 源码中 grep `BEGIN PUBLIC KEY` / `BEGIN RSA PRIVATE KEY`
2. 运行时 Hook `JSEncrypt.prototype.setPublicKey` / `setPrivateKey` 打印入参
3. PEM 为 base64，可直接解析出 `n` / `e`
4. 密钥来源常见于接口返回（如 `GET Home/Form` 返回 JSON 中的 `RSAPublicKey`）

## 签名结构模式

| 模式 | 特征 | 示例 |
|---|---|---|
| 纯摘要 | 定长 hex，32/40/64 字符 | `sign = md5(params + salt)` |
| 摘要 + 盐 | 同上但需找 salt | salt 常硬编码或从接口取 |
| 对称加密 | base64 或 hex，长度随明文增长 | AES/DES/SM4 |
| 非对称加密 | 长度固定（等于密钥长度） | RSA/SM2 |
| 混合 | **对称密文 + 非对称加密的密钥**拼接 | `w = AES(data) + RSA(key)`（极验） |
| 时间戳绑定 | 每次变化，短时间窗口 | `_ts`、`nonce`、`timestamp` |
| 递增序列 | 单调递增 | `subsid`、`seq` |

**混合模式是中文风控的主流**：极验三代/四代、数美 v4 都是这个结构。识别方法：把参数按长度切分，若前段长度随内容变化、后段长度固定，则为混合模式。

## 参数排序与拼接陷阱

签名算法中参数顺序常被混淆，需注意：

- 是否按 key 字典序排序（`Object.keys(params).sort()`）
- 是否过滤空值
- 是否包含 URL 路径与 HTTP method
- 是否包含时间戳与随机数
- 是否对特殊字符做 URL 编码

**调试方法**：构造两组仅差一个参数值的请求，对比签名差异，可反推拼接内容。

## 时间戳与 nonce

| 字段 | 常见处理 |
|---|---|
| 时间戳 | 秒 vs 毫秒；是否为字符串 |
| 时区 | 极验四代要求 `+08:00` 格式的 ISO 字符串 |
| nonce | 长度与字符集（hex / base64 / 数字） |
| 过期 | 服务端校验窗口常为 5–30 分钟 |

## 复现路线选择

| 路线 | 适用 | 成本 | 风险 |
|---|---|---|---|
| **扣代码** | 算法独立、依赖少 | 中 | 站点更新即失效 |
| **补环境** | 算法依赖浏览器环境 | 中低 | 需处理检测点 |
| **RPC 远程调用** | 算法复杂、请求量低 | 低（首次） | 吞吐低 |
| **纯算法重写** | 需高吞吐、长期维护 | 高 | 需完整理解 |

决策依据：**先问请求量**。日均 < 1 万次 → RPC 足够；> 10 万次 → 必须纯算法。

## 来源

- 极验参数定位四手段：https://cloud.tencent.com/developer/article/1971174
- 极验反混淆与参数还原：https://github.com/yanglbme/geetest-crack
- 极验完整请求链与 w 结构：https://www.cnblogs.com/zgq123456/articles/15266990.html
- crypto-js 模块与版本：https://github.com/brix/crypto-js
- sm-crypto 用法与陷阱：https://github.com/JuneAndGreen/sm-crypto
- 魔改 Base64 分析：https://bbs.kanxue.com/thread-251248.htm
- jsencrypt 与 PEM 映射：https://github.com/travist/jsencrypt
- 数美 v4 加密结构：https://cloud.tencent.com/developer/article/2475504
- 同盾 p1~p9 与算法组合：https://cloud.tencent.com/developer/article/2501583

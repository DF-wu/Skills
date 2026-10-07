# TLS 与 HTTP 指纹（JA3 / JA3N / JA4 / JA4+ / Akamai H2）

现代反爬的第一道门往往不在应用层，而在 **TLS 握手指纹**与 **HTTP/2 帧指纹**。用 requests 打一个 Cloudflare/Akamai 站点，会在到达业务逻辑前就被拦下——原因就在这里。

## 为什么需要它

`requests`、`httpx`、`aiohttp` 的 TLS 握手特征（cipher suite 顺序、扩展集合与顺序、椭圆曲线、ALPN）与真实浏览器差异极大，形成可稳定识别的指纹。绕过方式不是「加 User-Agent」，而是**让握手本身像浏览器**。

## JA3

**算法**：把 `SSLVersion,Cipher,SSLExtension,EllipticCurve,ECPointFormat` 五个字段按**原顺序**拼接，逗号分隔，字段内用 `-` 分隔，再取 MD5。

- **GREASE 值必须移除**
- **顺序敏感**——这是它被攻破的原因

**致命缺陷**：**Chrome 109/110 引入 TLS 扩展顺序随机化**，使 JA3 在同一浏览器版本内不再稳定，产生大量假阳性。

**状态**：官方实现 `salesforce/ja3` **已于 2025-05-01 归档**。

## JA3N

**JA3N = 集合版变体**：把 cipher 与 extension 列表**去重排序**后再哈希，因此对扩展顺序随机化免疫。

**重要限定**：**JA3N 只是 curl_cffi 生态的约定，不是正式标准**。它没有规范文档，由实现方定义。

**curl_cffi 中使用**：需要显式开启扩展顺序随机化才能模拟 Chrome 的现代行为：

```python
from curl_cffi import requests

r = requests.get(
    url,
    impersonate="chrome",
    extra_fp={"tls_permute_extensions": True},   # 关键：复现 Chrome 109+ 的扩展顺序随机化
)
```

## JA4

**格式**：`ja4_a_ja4_b_ja4_c`，三段用 `_` 分隔。

### ja4_a（10 字符，人类可读）

| 位置 | 含义 |
|---|---|
| 1 | 传输类型：`t` = TCP，`q` = QUIC，`d` = DTLS |
| 2–3 | 版本：`13` / `12` / `11` / `10` / `s3` / `s2` / `d1`–`d3` / `00` |
| 4 | SNI：`d` = domain（有 SNI），`i` = IP（无 SNI） |
| 5–6 | 2 位 cipher 数量（**去 GREASE 后**） |
| 7–8 | 2 位 extension 数量（**去 GREASE 后**） |
| 9–10 | 第一个 ALPN 值的**首尾字母数字字符** |

### ja4_b

**排序后**的 cipher 列表取 SHA-256，**截断为 12 位 hex**。空列表 → `000000000000`。

### ja4_c

**排序后**的 extension 类型码（**排除 SNI `0000` 与 ALPN `0010`**）取 SHA-256 截断 12 位，然后 `_` 拼接**原始顺序**的 signature algorithms。

**规范示例**：`t13d1516h2_8daaf6152771_e5627efa2ab1`

## JA4+ 套件

| 简称 | 对象 |
|---|---|
| JA4 | TLS Client |
| JA4S | TLS Server |
| JA4H | HTTP Client |
| JA4L | Latency（Client） |
| JA4LS | Latency（Server） |
| JA4X | X.509 证书 |
| JA4SSH | SSH |
| JA4T | TCP（Client） |
| JA4TS | TCP（Server） |
| JA4TScan | TCP 主动扫描 |
| JA4D / JA4D6 | DHCP |

**许可分裂（重要，商用需注意）**：

- **JA4 本身：BSD-3-Clause**
- **其余 JA4+ 方法：FoxIO License 1.1**（含非商业限制）

规范仓库：https://github.com/FoxIO-LLC/ja4

## Akamai HTTP/2 指纹

格式：`SETTINGS | WINDOW_UPDATE | PRIORITY | PSEUDO_HEADER_ORDER`

| 浏览器 | 指纹 |
|---|---|
| Chrome | `1:65536;2:0;4:6291456;6:262144\|15663105\|0\|m,a,s,p` |
| Firefox | `1:65536;4:131072;5:16384\|12517377\|0\|m,p,a,s` |
| Safari | `1:65536;3:1000;4:6291456\|10485760\|0\|m,s,p,a` |

**四段含义**：

1. **SETTINGS 帧**的 `id:value` 键值对（分号分隔）
2. **WINDOW_UPDATE** 值
3. **PRIORITY**（多为 0）
4. **伪头顺序**（`m` = `:method`，`a` = `:authority`，`s` = `:scheme`，`p` = `:path`）

**伪头顺序是强特征**：Chrome 与 Firefox 都是 `m,a,s,p`，**Safari 是 `m,s,p,a`**。

## 工具

| 工具 | 说明 |
|---|---|
| **curl_cffi** | 浏览器 impersonate 的首选。`impersonate="chrome"` 等；`extra_fp` 可微调 TLS 与 H2 层 |
| **tls-client** | 同类实现，多语言绑定 |
| Cloudflare JA3/JA4 文档 | https://developers.cloudflare.com/bots/additional-configurations/ja3-ja4-fingerprint |
| Cloudflare JA4 signals 公告 | https://blog.cloudflare.com/ja4-signals |
| FoxIO JA4 规范 | https://github.com/FoxIO-LLC/ja4 |

**curl_cffi 注意事项**：`impersonate` 的可用目标随版本变化；扩展顺序随机化的默认行为与真实浏览器可能不同，需显式 `extra_fp.tls_permute_extensions = True`。参见 https://github.com/lexiforest/curl_cffi/issues/529

## 检测侧：站点怎么用这些指纹

1. **TLS 指纹不匹配 UA** → 直接判定为脚本（最廉价、最有效的第一道门）
2. **H2 伪头顺序异常** → 同上
3. **JA4 与已知浏览器版本库比对** → 命中即放行，未命中即挑战
4. **同一 JA4 高频出现** → 关联 IP 池做速率限制

**推论**：伪造 UA 而不改 TLS/H2 指纹，是**负收益**——不一致本身就是强信号。

## 三层指纹对齐原则

中文与欧美风控都适用的一条总原则：**请求链路上所有层必须自洽**。

| 层 | 需一致的项 |
|---|---|
| TLS | JA3/JA4、cipher 顺序、扩展集合、ALPN |
| HTTP/2 | SETTINGS、WINDOW_UPDATE、伪头顺序 |
| HTTP | Header 顺序与集合、UA、`Accept-Language`、`Accept-Encoding` |
| JS 环境 | `navigator.userAgent`、`navigator.platform`、`navigator.languages`、时区 |
| 网络 | IP 归属地、时区、语言三者一致 |
| 设备 | `screen`、`devicePixelRatio`、WebGL renderer 组合合理 |

**任意一层不一致，都可能导致通过率显著下降**——这比任何单点技术都重要。

## 快速自检

```python
# 检查自己的 TLS 指纹是否像浏览器
from curl_cffi import requests
r = requests.get("https://tls.browserleaks.com/json", impersonate="chrome")
print(r.json())   # 对比 ja3_hash / ja4 / akamai_hash
```

对照项：`ja3_hash`、`ja3n_hash`、`ja4`、`akamai_hash`、`akamai_text`。

## 来源

- JA4 规范与实现：https://github.com/FoxIO-LLC/ja4
- JA4 技术细节：https://github.com/FoxIO-LLC/ja4/blob/main/technical_details/JA4.md
- JA4H 技术细节：https://github.com/FoxIO-LLC/ja4/blob/main/technical_details/JA4H.md
- JA4 许可 FAQ：https://github.com/FoxIO-LLC/ja4/blob/main/License%20FAQ.md
- JA3 官方实现（已归档）：https://github.com/salesforce/ja3
- curl_cffi FAQ：https://curl-cffi.readthedocs.io/en/latest/faq.html
- curl_cffi 扩展随机化 issue：https://github.com/lexiforest/curl_cffi/issues/529
- Cloudflare JA3/JA4 配置：https://developers.cloudflare.com/bots/additional-configurations/ja3-ja4-fingerprint
- Cloudflare JA4 signals：https://blog.cloudflare.com/ja4-signals

# Traffic Camouflage and Protocol Mimicry

How clients make their traffic indistinguishable from ordinary traffic — and how
defenders detect the attempts. Both directions are covered, because neither is
understandable without the other.

**Framing**: this is the mechanism layer of anti-detection. It is what
[`anti-detection.md`](anti-detection.md) applies and what
[`tls-http-fingerprinting.md`](tls-http-fingerprinting.md) measures. Understanding it is
necessary for two legitimate purposes: building clients that behave honestly like the
real thing (interoperability, testing), and detecting clients that are lying (defence).
Authorization governs which applies — see
[`compliance-and-scope.md`](compliance-and-scope.md).

---

## 1. The camouflage stack

Camouflage is layered. A client is only as convincing as its weakest layer, because a
detector only needs one contradiction.

| Layer | What is observable | What camouflage means |
|---|---|---|
| **Application** | HTTP headers, header order, cookies, request cadence | Match a real client's header set, order, and values exactly |
| **Protocol** | HTTP/2 SETTINGS, pseudo-header order, priority frames | Reproduce the real stack's negotiation parameters |
| **Presentation** | TLS ClientHello: cipher list, extension list, order, GREASE, ALPN | Reproduce the real browser's ClientHello byte-for-byte |
| **Transport** | TCP options, window size, initial TTL, timestamps | Match the claimed OS's TCP stack |
| **Network** | Source IP, ASN, geolocation, RTT | Egress coherent with the claimed identity |
| **Temporal** | Request timing, session duration, inter-arrival distribution | Behaviour that resembles a human or a real client |
| **Payload** | Content itself | Legitimate-looking requests, not a scraping pattern |

**The critical property is coherence, not strength.** A perfect TLS fingerprint on a
datacenter IP with machine-gun request timing is less convincing than a mediocre
fingerprint on a residential IP with human pacing. Detectors weight the contradictions,
not the individual values.

---

## 2. TLS layer

The TLS ClientHello is the highest-value fingerprint because it is sent before any
application data and cannot be rewritten by a proxy (unless the proxy terminates TLS).

What is fingerprinted:

| Element | Notes |
|---|---|
| Cipher suite list and order | Strong signal; order matters for JA3 |
| Extension list and order | Strongest single signal on modern browsers |
| **GREASE values** (RFC 8701) | Chrome sends random GREASE values; a client that omits them is instantly non-Chrome |
| Elliptic curves and point formats | |
| ALPN | `h2`, `http/1.1` |
| Signature algorithms | |
| Supported versions | |
| **Extension order randomization** | Chrome 109+ randomizes; a fixed order is detectable |
| Record layer version, compression | |

The fingerprint schemes:

- **JA3** — order-sensitive hash of version, ciphers, extensions, curves, formats
- **JA3N** — same, but with order normalized (a curl_cffi ecosystem convention, not a
  formal standard)
- **JA4** — modern replacement, more structured, order-insensitive in the parts that
  should be. `t13d1516h2_<cipher hash>_<extension hash>` style.
- **Akamai fingerprint** — includes HTTP/2 SETTINGS alongside the TLS parameters

The practical point about JA3: **once extension randomization is enabled, JA3 changes on
every request.** Measured with curl_cffi:

| run | JA3 | JA4 |
|---|---|---|
| 1 | `0ba99caf26b07a146f0cb49cb7431976` | `t13d1516h2_8daaf6152771_806a8c22fdea` |
| 2 | `6988ac858ec7f28b6700dcd048f8e3e6` | `t13d1516h2_8daaf6152771_806a8c22fdea` |

So do not diff JA3 against a stored reference when permutation is on — the difference is
correct behaviour. Use JA4 for baselines.

**Approach**: do not hand-craft a ClientHello. Use a client that replays a real one
(curl_cffi, `utls`, `rquest`, `wreq`, `bogdanfinn/tls-client`), and verify the result
with `scripts/fingerprint_probe.py`.

---

## 3. HTTP layer

Headers are the second-highest-value signal, and the one most often botched.

| Property | Why it matters |
|---|---|
| **Header set** | A browser sends a specific set. Missing `sec-ch-ua` on a claimed Chrome is a tell. |
| **Header order** | Real browsers send in a consistent order. Alphabetical order is a script tell. |
| **`sec-ch-ua`, `sec-ch-ua-mobile`, `sec-ch-ua-platform`** | Must agree with the UA string |
| **`Sec-Fetch-Site`, `Sec-Fetch-Mode`, `Sec-Fetch-Dest`, `Sec-Fetch-User`** | Browsers always send these; scripts almost never do |
| **`Accept-Language`** | Must match the session's claimed locale, and the order should be a plausible browser order |
| **`Accept-Encoding`** | `gzip, deflate, br, zstd` on modern Chrome; missing `zstd` on Chrome 123+ is a tell |
| **`Connection`, `Upgrade-Insecure-Requests`** | Presence/absence patterns |
| **Cookie order** | Browsers send cookies in a defined order; a script that sorts them is detectable |
| **`Referer` chain** | A request with no referer to an authenticated endpoint is suspicious |

HTTP/2 adds a parallel set:

- SETTINGS frame values (initial window size, max concurrent streams, header table size)
- Window update behaviour
- Pseudo-header order (`:method`, `:authority`, `:scheme`, `:path`)
- Whether priority frames are sent
- Stream ID patterns

Akamai's fingerprint includes HTTP/2 SETTINGS precisely because it is hard to fake
without an actual HTTP/2 stack.

---

## 4. Transport and network layer

Below TLS, the TCP/IP stack itself is fingerprinted:

| Element | Observable via |
|---|---|
| Initial TTL | Default differs per OS (Linux 64, Windows 128, macOS 64) |
| TCP window size | OS and version specific |
| TCP options and order | MSS, SACK, timestamps, window scale |
| IP ID behaviour | Sequential vs random per OS |
| MTU / MSS | Path and OS |
| RTT | Geographic distance to the claimed egress |

Tools: `p0f`, `p0f3`, nmap OS detection, and any middlebox doing passive OS
fingerprinting.

**The consequence most people miss**: a client can present a perfect Chrome TLS
fingerprint and still be identified by its TCP stack. A Python client on Linux behind a
residential proxy presents a Linux TCP stack while claiming Windows. On targets that do
passive OS fingerprinting, this is the contradiction.

---

## 5. Protocol mimicry

Beyond fingerprint matching, some clients disguise the protocol itself. Worth
understanding in both directions.

### Domain fronting

The technique: use one domain in the TLS SNI field and a different domain in the HTTP
Host header. If both are served from the same CDN, the CDN routes on the Host header
after terminating TLS.

```text
TLS SNI:    front.example        <- what a network observer sees
HTTP Host:  real.example         <- where the CDN actually routes it
```

- MITRE ATT&CK **T1090.004**.
- Classic implementations: Tor's `meek` plugin (originally through Google App Engine),
  and the domain-fronting technique in the original blocking-resistant communication
  paper.
- CDNs have largely closed this by validating SNI against Host. Google suspended the
  `meek-reflect.appspot.com` reflection server.
- Variant: **"domainless" fronting** — leave the SNI blank, in case the CDN ignores
  blank SNI.
- 2025 research found residual edge cases, e.g. fronting through core Google domains to
  reach Cloud Run instances.

**Why it is in a RE document**: it explains why a captured request may not reveal its
true destination, and it explains why a network capture of a client can be misleading.
For the defender, the detection is straightforward and reliable: **SNI/Host mismatch plus
a CDN certificate** is a high-confidence signal.

### Protocol masquerading

Making one protocol look like another on the wire:

- Tunnel inside HTTP(S) — most common, since it survives most filtering
- Tunnel inside DNS (DoH/DoT blur the boundary)
- Tunnel inside WebSocket — looks like a long-lived HTTP connection
- Tunnel inside a CDN's allowed traffic
- Padding to fixed block sizes to defeat length analysis
- Traffic shaping to match a target profile's packet size/timing distribution

**Detection side**: the giveaways are usually statistical, not structural. Packet size
distributions, inter-arrival timing, and byte-count symmetry that does not match the
protocol being claimed. A "normal HTTPS session" with perfectly regular packet sizes and
no request/response asymmetry is not normal HTTPS.

---

## 6. Temporal layer

Timing is the layer that survives every fingerprint fix.

| Signal | What looks human | What looks automated |
|---|---|---|
| Inter-request interval | Variable, log-normal-ish | Constant, or uniform random |
| Session duration | Minutes, with idle gaps | Seconds, or hours with no gaps |
| Diurnal pattern | Follows the claimed timezone's waking hours | Uniform around the clock |
| Request ordering | Non-linear, backtracking | Sequential pagination in perfect order |
| Response-time reaction | Slows down on error, backs off | Fixed retry interval |
| Think time before actions | Present | Absent |
| Concurrency | Low and bursty | High and sustained |

**Constant intervals are the single most common automated tell.** `time.sleep(1)` between
requests produces a distribution no human session produces. Use a distribution, not a
constant.

---

## 7. Coherence: the actual goal

The engineering discipline that makes all of the above work:

```text
1. Record a real client's complete profile (TLS + HTTP + headers + timing).
2. Replay it exactly. Do not hand-tune individual values.
3. Verify every layer against an echo endpoint.
4. Cross-check the layers against each other.
5. Only then vary anything.
```

Cross-checks that matter, in order of how often they catch people:

1. **UA vs TLS fingerprint** — the most common failure. `impersonate="chrome"` in
   curl_cffi reports a **macOS** UA; overriding it with a Windows string creates this
   contradiction. See [`http-clients.md`](http-clients.md).
2. **UA vs `sec-ch-ua-platform` vs `navigator.platform`** — three places claiming an OS.
3. **Header order vs a real browser's order.**
4. **Missing `Sec-Fetch-*` headers** on a request claiming to be a browser navigation.
5. **TCP stack vs claimed OS.**
6. **Timezone vs IP geolocation.**
7. **`Accept-Language` vs session locale vs content language requested.**

---

## 8. Detecting camouflage (defender's view)

If you are on the other side — testing whether a client is what it claims — the checklist
is the inverse of the above:

1. **Compare the TLS fingerprint to the claimed UA's real fingerprint.** Mismatch is
   decisive.
2. **Check for GREASE.** A "Chrome" ClientHello with no GREASE is not Chrome.
3. **Check `Sec-Fetch-*` presence.** Browser navigation always includes them.
4. **Check header order** against a recorded real browser.
5. **Check the TCP stack** against the claimed OS.
6. **Analyse request timing distribution.** Constant intervals, or a distribution that
   does not match human behaviour.
7. **Look at the session shape.** A session that only ever requests API endpoints and
   never loads assets is not a browsing session.
8. **Correlate the IP.** ASN type, geolocation coherence, and whether the IP's history is
   consistent with the claimed identity.
9. **Check for consistency across sessions.** The same rare font list, the same WebGL
   renderer string, the same canvas hash appearing across supposedly different devices
   is the giveaway for a batch of synthetic profiles.

The last point is the important one for defenders: **individual spoofing is much harder
to detect than batch spoofing.** A single well-built synthetic client may be
indistinguishable. A thousand of them, generated from one template, share a distribution
that no real population has.

---

## 9. Anti-patterns

- Hand-crafting a ClientHello instead of replaying a real one.
- Setting a UA without checking the TLS fingerprint.
- Alphabetical or inconsistent header order.
- Omitting `Sec-Fetch-*` on a claimed browser navigation.
- Fixed `time.sleep()` intervals.
- Randomizing fingerprint values per request — random values are themselves a signal, and
  real devices are stable.
- Fixing one layer and assuming the others are fine.
- Assuming a proxy changes the TLS fingerprint (it does not, unless it terminates TLS).
- Assuming a proxy changes the TCP stack fingerprint (it usually does not).
- Building all profiles from one template, then shipping the identical rare values
  everywhere.

---

## 10. Relationship to other documents

- Measuring your own fingerprint: [`tls-http-fingerprinting.md`](tls-http-fingerprinting.md),
  `scripts/fingerprint_probe.py`
- Client implementations per language: [`http-clients.md`](http-clients.md),
  [`language-ecosystems.md`](language-ecosystems.md)
- Browser-level runtime spoofing: [`anti-detection.md`](anti-detection.md),
  [`browser-automation.md`](browser-automation.md)
- Environment simulation for JS challenges: [`environment-simulation-jsvmp.md`](environment-simulation-jsvmp.md)
- Identity separation: [`identity-and-attribution.md`](identity-and-attribution.md)
- Vendor-specific detection: [`global-anti-bot-vendors.md`](global-anti-bot-vendors.md)
- Authorization: [`compliance-and-scope.md`](compliance-and-scope.md)

---

## 中文摘要

**伪装的本质是分层一致，不是单层强度。** 一个完美 TLS 指纹配数据中心 IP 配机枪式请求节奏，比一个平庸指纹配住宅 IP 配人类节奏更容易被识别。检测方加权的是**矛盾**，不是单个数值。

**分层可观测面**：应用层（HTTP 头集合/顺序/值、Cookie 顺序）→ 协议层（HTTP/2 SETTINGS、伪头顺序）→ 表示层（TLS ClientHello：密码套件、扩展列表与**顺序**、**GREASE**、ALPN）→ 传输层（TCP 选项、窗口大小、初始 TTL）→ 网络层（IP、ASN、地理、RTT）→ 时间层（请求节奏、会话时长、到达间隔分布）→ 载荷层。

**TLS 层**：ClientHello 价值最高，因为在应用数据之前发出且代理无法改写（除非终止 TLS）。**GREASE**（RFC 8701）是关键——Chrome 发送随机 GREASE 值，缺少它的客户端立刻暴露。**Chrome 109+ 随机化扩展顺序**，固定顺序可被检测。指纹方案：JA3（顺序敏感）、JA3N（curl_cffi 生态约定，**非正式标准**）、**JA4**（现代替代）、Akamai fingerprint（含 HTTP/2 SETTINGS）。**实测要点：开启扩展随机化后 JA3 每次请求都变**（见正文实测表），所以不要拿存储的 JA3 参考值做 diff——差异是正确行为；基线比较用 JA4。

**HTTP 层**：浏览器发送**特定集合与特定顺序**的头。**`Sec-Fetch-*` 系列**是浏览器导航必发、脚本几乎从不发的头，是最高信噪比的检查点之一。`sec-ch-ua*` 必须与 UA 一致。Chrome 123+ 的 `Accept-Encoding` 应含 `zstd`。Cookie 顺序由浏览器定义，脚本排序即暴露。

**传输层（最常被忽略）**：TCP/IP 栈本身被指纹化——初始 TTL（Linux 64 / Windows 128）、窗口大小、TCP 选项顺序、IP ID 行为。**一个 Python 客户端在 Linux 上经住宅代理，呈现 Linux TCP 栈却声称 Windows**，在被动 OS 指纹识别面前直接矛盾。

**协议伪装**：
- **域名前置**（MITRE **T1090.004**）：TLS SNI 用一个域名、HTTP Host 用另一个，同一 CDN 上按 Host 路由。Tor 的 `meek` 插件是经典实现；Google 已停用 `meek-reflect.appspot.com` 反射服务器。变体"无域名前置"留空 SNI。**检测极可靠：SNI/Host 不匹配 + CDN 证书 = 高置信信号。**
- 隧道化：套在 HTTPS/DNS/WebSocket 内；填充到固定块大小以对抗长度分析；整形以匹配目标流量分布。**检测方靠统计特征而非结构特征**——包长分布、到达间隔、字节对称性与所声称协议不符。

**时间层**：**恒定间隔是最常见的自动化特征**——`time.sleep(1)` 产生的分布没有任何真实人类会话会产生。要用分布，不要用常量。

**一致性是真正的目标**：录制真实客户端的完整画像（TLS + HTTP + 头 + 时序）→ 原样重放 → 逐层用回显端点验证 → 层间交叉校验。最常见的七类矛盾见正文，第一位是 **UA 与 TLS 指纹不符**（curl_cffi 的 `impersonate="chrome"` 上报 **macOS** UA，覆盖成 Windows 就制造了这个矛盾）。

**防御方视角**：对声称的 UA 比对真实 TLS 指纹（决定性）→ 查 GREASE → 查 `Sec-Fetch-*` → 查头顺序 → 查 TCP 栈 → 分析请求间隔分布 → 看会话形状（只请求 API 从不加载资源的不叫浏览会话）→ 关联 IP 历史 → **跨会话一致性**。

**最后一点对防御方最重要**：**单体伪装远比批量伪装难检测**。一个精心构造的合成客户端可能无法区分；一千个由同一模板生成、共享真实群体不可能有的分布，才是真正的暴露点。

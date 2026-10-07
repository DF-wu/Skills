# 2026 反爬前沿与对抗（Cloudflare / Anubis / 检测侧）

2025–2026 年反爬格局出现三个新变量：**AI 爬虫专用陷阱**、**付费爬取协议**、**工作量证明门槛**。本文覆盖它们与检测侧现状。

## 一、Cloudflare 三件套

### AI Labyrinth（2025-03-19）

**机制**：给被识别为 AI 爬虫的请求返回**由 AI 生成的虚假页面**，页面内嵌**隐藏的诱饵链接**（人不可见，爬虫会跟进），把爬虫引入无限循环。

| 项 | 值 |
|---|---|
| 上线时间 | 2025-03-19 |
| 可用层级 | **opt-in，含 Free 计划** |
| 内容生成 | Workers AI |
| 内容存储 | R2 |
| 页面标记 | `noindex`（避免污染搜索索引） |
| 事件名 | `AI Labyrinth Served`、`AI Labyrinth Crawls` |

**对抗要点**：检测页面是否 `noindex`、是否存在不可见链接（`display:none` / 尺寸 0 / 移出视口 / 与背景同色）。命中即应丢弃并标记该来源不可信。

来源：https://blog.cloudflare.com/ai-labyrinth

### Pay Per Crawl（2025-07-01 私有 beta → 已 GA）

**机制**：让内容方对爬取**收费或拒绝**，通过 HTTP **402 Payment Required** 表达。

| 项 | 值 |
|---|---|
| 上线 | 2025-07-01 私测；**2025-08-27** AI Audit 更名 AI Crawl Control 并 GA，同时引入自定义 HTTP 402 响应（付费计划） |
| 支付方 | Stripe（merchant-of-record） |
| 三种策略 | allow / charge / block |
| 价格头 | `crawler-price`、`crawler-exact-price`、`crawler-max-price`、`crawler-charged`、`crawler-error` |
| 协议规则 | `crawler-exact-price` 与 `crawler-max-price` **一次请求只允许其一**；同时出现或同时缺席均回 402 |
| 身份验证 | **Web Bot Auth**（HTTP message signatures）；2026-04-17 起支付头必须纳入 `signature-input` 签名组件 |
| 发现 API | `GET https://crawlers-api.ai-audit.cfdata.org/charged_zones` |
| 免费路径 | `/robots.txt`、`/sitemap.xml`、`/security.txt`、`/.well-known/security.txt`、`/crawlers.json` |
| 路由顺序 | 支付决策运行在既有 WAF / 限流 / bot management 策略**之后** |
| 计费语义 | 成功响应带 `crawler-charged` 标明实际计费额；**错误响应不计费** |

**对抗要点**：收到 **402** 不应盲目重试——这是显式的商业拒绝信号。检查 `crawler-*` 头判断是否已被计费。

**已形成的事实标准族**（不再是单一厂商行为）：

| 方案 | 时间 | 形态 |
|---|---|---|
| **Cloudflare Pay Per Crawl** | 2025-07 → GA 2025-08-27 | 402 + `crawler-*` 头；Stripe 结算 |
| **x402 Foundation** | 2025-09-23（Cloudflare + Coinbase 联合发起） | 402 + 机器可读支付要求 `PAYMENT-REQUIRED`；客户端用 `PAYMENT-SIGNATURE` 重试；网络无关（EVM/Solana）；**facilitator** 负责验证与结算 |
| **AWS WAF AI Traffic Monetization** | 2026-06 | Bot Control 新增 **Monetize** 动作；未付请求收 402 + 清单（每请求价格 USDC、可接受网络 **Base 与 Solana**、收款地址、许可条款），**格式即 x402**；付款后边缘签发作用域受限的访问 token |
| **Content Signals** | 2025-09-24 | robots.txt 扩展，CC0 |
| **RSL (Really Simple Licensing)** | — | 写在 robots.txt 中的 XML 许可标准，由 RSL Collective 管理；**与 CDN 无关**，联盟制 |

Cloudflare 方数据点：其网络上站点**每天发出超过 10 亿个 HTTP 402 响应码**给 bot、crawler 与 agent。法律状态：x402 目前是**技术开放标准**，尚非被监管认可的支付系统。

来源：https://blog.cloudflare.com/introducing-pay-per-crawl 、https://developers.cloudflare.com/ai-crawl-control/changelog 、https://developers.cloudflare.com/ai-crawl-control/features/pay-per-crawl/what-is-pay-per-crawl 、https://www.cloudflare.com/press/press-releases/2025/cloudflare-and-coinbase-will-launch-x402-foundation 、https://aws.amazon.com/about-aws/whats-new/2026/06/aws-waf-ai-traffic-monetization

### Content Signals Policy（2025-09-24）

**机制**：在 `robots.txt` 中以机器可读方式表达三种用途偏好：

| 信号 | 含义 |
|---|---|
| `search` | 允许用于搜索引擎索引 |
| `ai-input` | 允许作为 AI 推理输入 |
| `ai-train` | 允许用于 AI 训练 |

| 项 | 值 |
|---|---|
| 许可 | **CC0**（可自由采用） |
| 法律框架 | EU DSM Directive Art. 4 的**权利保留**表达方式 |
| 后续 | 出现 `use=reference` 等扩展 |
| 与 Turnstile 的关系 | **无关**——Turnstile 是挑战机制，Content Signals 是偏好声明 |

**重要区分**：Content Signals **不是技术强制**，是偏好声明；是否遵守取决于爬虫方。它与 DSM Art. 4(3) 的「机器可读权利保留」在功能上对齐。

来源：https://blog.cloudflare.com/content-signals-policy

### Super Bot Fight Mode 的执行顺序

**关键事实**：Super Bot Fight Mode 在**自定义 WAF 规则之后**执行。因此对特定路径设置 **`Skip` 动作**可以跳过 SBFM 检查。这是配置层的事实，用于理解防护顺序。

## 二、Anubis（工作量证明门槛）

**项目**：https://github.com/techaroHQ/anubis （MIT，Go 编写的反向代理）

**机制**：Hashcash 风格 SHA-256 PoW。难度 `d` → 工作量 `W = 16^d`。

| 项 | 值 |
|---|---|
| **默认难度** | **5**（约 1,048,576 次哈希） |
| 浏览器 JS 速率 | 约 0.5 MH/s |
| 原生 Go 速率 | 约 50 MH/s |
| 通过凭证 | JWT + `*-anubis-auth` cookie，约 2 周有效 |
| 付费加速 | Thoth（付费 reputation 插件） |

**设计意图**：让 AI 爬虫的**成本**高于收益，而不是阻止访问。人类浏览器只需几百毫秒。

**历史事件**：

- **CVE-2025-24369**：客户端可传入 `difficulty=0` 绕过。修复 commit `e09d0226a628f04b1d80fd83bee777894a45cd02`
- **2025-08-15 Codeberg 事件**：AI 爬虫解出了 PoW，导致类似 DoS 的负载
- **2026 转向**：改用**内存困难的 Argon2id（通过 WebAssembly）**，使 GPU/ASIC 加速收益降低

**对抗路径**：

1. 用原生代码（Go/Rust）解 PoW——速度约为浏览器 JS 的 100 倍，难度 5 只需毫秒级
2. 复用 `*-anubis-auth` cookie（约 2 周有效期）
3. 若目标是 Thoth 保护站点，PoW 成本由 reputation 决定，纯算力收益下降

来源：https://github.com/techaroHQ/anubis 、https://anubis.techaro.lol/docs/design/how-anubis-works/ 、https://anubis.techaro.lol/blog/2026/anubis-wasm/ 、https://nvd.nist.gov/vuln/detail/CVE-2025-24369 、https://theregister.com/2025/08/15/codeberg_beset_by_ai_bots/ 、https://lock.cmpxchg8b.com/anubis.html

## 三、检测侧现状

### 检测工具

| 工具 | 来源 | 检查点 |
|---|---|---|
| **CreepJS** | https://github.com/abrahamjuliot/creepjs | 综合指纹与一致性 |
| FingerprintJS | https://github.com/fingerprintjs/fingerprintjs | 商业指纹 |
| BotD | https://github.com/fingerprintjs/BotD | 自动化信号 |
| **brotector** | https://github.com/ttlns/brotector | `navigator.webdriver`、**CDP `Runtime.enable` / `Console.enable`**、`window.cdc_*`、`isTrusted === false`、`__pwInitScripts`、堆栈签名；`?crash=false` 可关闭 |
| rebrowser-bot-detector | https://github.com/rebrowser/rebrowser-bot-detector | CDP 泄漏检测 |
| Are You Headless | https://arh.antoinevastel.com/bots/areyouheadless | 基础 headless 检测 |
| **fpscanner** | https://github.com/antoinevastel/fpscanner | 指纹一致性扫描 |
| **bot.incolumitas.com** | https://bot.incolumitas.com | `behavioralClassificationScore`（0 = bot，1 = human），在 1.5/4/7/10/15 秒更新 |
| BrowserScan / PixelScan | https://browserscan.net / https://pixelscan.net | 综合一致性 |
| detect-headless | https://github.com/infosimples/detect-headless | 经典 headless 信号集 |

### 最强信号：CDP `Runtime.enable`

**当前最强的自动化检测信号是 CDP `Runtime.enable` 的副作用**——Playwright/Puppeteer 调用它会改变 console 序列化行为，可被检测。

**历史演变**：

- 经典手法是 `Error.stack` 特征，**现已被 V8 补丁击败**（DataDome 与 Castle 的研究）
- `Page.createIsolatedWorld` 可缓解 CDP 检测

参考：https://rebrowser.net/blog/how-to-fix-runtime-enable-cdp-detection... 、https://datadome.co/threat-research/how-new-headless-chrome-the-cdp-signal-are-impacting-bot-detection 、https://blog.castle.io/why-a-classic-cdp-bot-detection-signal-suddenly-stopped-working-and-nobody-noticed

### 其他常见信号

| 信号 | 说明 |
|---|---|
| `window.chrome` 缺失 | Chromium 系特征对象 |
| `navigator.plugins` 为空 | 真实浏览器有插件 |
| Permissions API 不一致 | `Notification.permission` 与 `navigator.permissions.query` 结果矛盾 |
| WebGL renderer 为 SwiftShader / Mesa | 软件渲染 = 无 GPU = 疑似服务器 |
| `outerHeight` / `outerWidth` === 0 | 无窗口 |
| `document.hasFocus()` === false | 无焦点 |
| `navigator.languages` 缺失 | 真实浏览器必有 |
| 时区与 IP 不匹配 | 交叉校验 |

## 四、反检测浏览器阶梯

**按有效性排序**（社区共识）：

| 层级 | 方案 | 许可 | 说明 |
|---|---|---|---|
| 1（最强） | **Camoufox** | MPL-2.0 | Firefox fork，在 **C++ 层**修改指纹，JS 层不可见 |
| 2 | **Patchright** | Apache-2.0 | Chromium only，**Playwright 的直接替代**（drop-in） |
| 2 | **nodriver** | AGPL-3.0 | Chrome DevTools 协议直连，不用 WebDriver |
| 3 | rebrowser-patches | MIT | 修补 Playwright/Puppeteer 的 CDP 泄漏 |
| 4（最弱） | JS 注入型 stealth 插件 | 各异 | 在 JS 层打补丁，易被 native 检测识破 |

**其他可选**：SeleniumBase UC/CDP 模式、botasaurus（+driver）、pydoll、DrissionPage、zendriver、Scrapling。

**已死方案**：**undetected-chromedriver 实际上已停止维护**（PyPI 3.5.5，2024-02-17 最后发布）。不要在新项目中使用。

| 项目 | 仓库 |
|---|---|
| Camoufox | https://github.com/daijro/camoufox |
| Patchright | https://github.com/Kaliiiiiiiiii-Vinyzu/patchright |
| nodriver | https://github.com/ultrafunkamsterdam/nodriver |
| rebrowser-patches | https://github.com/rebrowser/rebrowser-patches |
| SeleniumBase | https://github.com/seleniumbase/SeleniumBase |
| botasaurus | https://github.com/omkarcloud/botasaurus |
| pydoll | https://github.com/autoscrape-labs/pydoll |
| DrissionPage | https://github.com/g1879/DrissionPage |
| zendriver | https://github.com/cdpdriver/zendriver |
| Scrapling | https://github.com/D4Vinci/Scrapling |

## 五、reCAPTCHA v3 评分

| 项 | 值 |
|---|---|
| 评分范围 | 0.0–1.0 |
| 默认阈值 | 0.5 |
| 免费额度 | 10,000 次评估/月 |
| 超出后 | $8/月 至 100,000 次 |
| siteverify 返回字段 | `success`、`score`、`action`、`challenge_ts`、`hostname`、`error-codes` |

**两个关键点**：

1. **必须校验 `action`**——否则攻击者可把低价值页面的 token 重放到高价值接口（这是官方文档明确要求的）
2. **staging 环境评分不可靠**——评分模型从真实流量学习，测试环境的分数无参考价值

来源：https://developers.google.com/recaptcha/docs/v3 、https://cloud.google.com/recaptcha/pricing

## 六、2026 格局判断

**技术趋势**：

1. **门槛从「识别」转向「成本」**——Anubis 用 PoW 让爬取变贵，Pay Per Crawl / x402 / AWS WAF Monetize 让爬取变成付费谈判。这类机制**不是可「绕过」的检测**，而是经济博弈
2. **AI 爬虫专用对抗**——AI Labyrinth 说明防护方开始区分「AI 训练爬虫」与「传统爬虫」，并对其投喂污染数据
3. **PoW 向内存困难算法演进**——Argon2id + WASM 让算力优势被削弱
4. **协议级偏好声明**——Content Signals 把 robots.txt 从「协议」变成「法律权利保留的表达」，与 DSM Art. 4(3) 对齐
5. **身份层标准化**——Web Bot Auth（RFC 9421 + Ed25519）让「合法 agent」可以自证身份，从而把「未知 agent」默认当作可疑。这是 2026 年最重要的结构性变化：**验证从「你是不是人类」转向「你有没有签名」**

**实务建议**：

- 遇到 402 → 停止重试，评估商业授权。**402 已有事实标准族（Cloudflare / x402 / AWS WAF Monetize），不是孤例**
- 遇到 PoW → 用原生实现解，不要用浏览器 JS
- 遇到 AI Labyrinth 特征 → 丢弃页面并标记
- 遇到 `ai-train`/`ai-input` 信号被保留 → 法律层面需重新评估，不只是技术问题
- 遇到 `Signature` / `Signature-Input` / `Signature-Agent` → 这是 **Web Bot Auth**，是身份声明而非挑战；没有签名的 agent 会被默认归类为可疑

## 来源

- AI Labyrinth：https://blog.cloudflare.com/ai-labyrinth
- Pay Per Crawl：https://blog.cloudflare.com/introducing-pay-per-crawl
- Pay Per Crawl 协议细节：https://developers.cloudflare.com/ai-crawl-control/features/pay-per-crawl/what-is-pay-per-crawl
- AI Crawl Control 变更记录：https://developers.cloudflare.com/ai-crawl-control/changelog
- x402 Foundation（Cloudflare + Coinbase）：https://www.cloudflare.com/press/press-releases/2025/cloudflare-and-coinbase-will-launch-x402-foundation
- AWS WAF AI Traffic Monetization：https://aws.amazon.com/about-aws/whats-new/2026/06/aws-waf-ai-traffic-monetization
- Web Bot Auth：https://developers.cloudflare.com/bots/reference/bot-verification/web-bot-auth
- Cloudflare Verified Bots with cryptography：https://blog.cloudflare.com/verified-bots-with-cryptography
- Content Signals Policy：https://blog.cloudflare.com/content-signals-policy
- Anubis：https://github.com/techaroHQ/anubis
- Anubis 工作原理：https://anubis.techaro.lol/docs/design/how-anubis-works/
- Anubis WASM/Argon2id：https://anubis.techaro.lol/blog/2026/anubis-wasm/
- CVE-2025-24369：https://nvd.nist.gov/vuln/detail/CVE-2025-24369
- Codeberg 事件：https://theregister.com/2025/08/15/codeberg_beset_by_ai_bots/
- Anubis 分析：https://lock.cmpxchg8b.com/anubis.html
- brotector：https://github.com/ttlns/brotector
- rebrowser-bot-detector：https://github.com/rebrowser/rebrowser-bot-detector
- CDP Runtime.enable 检测：https://rebrowser.net/blog/how-to-fix-runtime-enable-cdp-detection...
- DataDome CDP 研究：https://datadome.co/threat-research/how-new-headless-chrome-the-cdp-signal-are-impacting-bot-detection
- Castle CDP 研究：https://blog.castle.io/why-a-classic-cdp-bot-detection-signal-suddenly-stopped-working-and-nobody-noticed
- bot.incolumitas.com：https://bot.incolumitas.com
- fpscanner：https://github.com/antoinevastel/fpscanner
- Camoufox：https://github.com/daijro/camoufox
- Patchright：https://github.com/Kaliiiiiiiiii-Vinyzu/patchright
- nodriver：https://github.com/ultrafunkamsterdam/nodriver
- rebrowser-patches：https://github.com/rebrowser/rebrowser-patches
- reCAPTCHA v3：https://developers.google.com/recaptcha/docs/v3
- reCAPTCHA 定价：https://cloud.google.com/recaptcha/pricing

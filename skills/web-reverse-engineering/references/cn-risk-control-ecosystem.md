# 中文风控生态总览（China Risk-Control Landscape）

中文互联网的风控强度普遍高于欧美同类站点，且形态不同：欧美以 TLS/指纹为主，中文站点以**动态脚本 + 设备指纹 + 参数签名**三层组合为主。理解这个生态是选择正确路线的第一步。

## 厂商矩阵

| 厂商 | 产品/标识 | 核心机制 | 社区标注难点 | 可核实特征 |
|---|---|---|---|---|
| **瑞数 RiverSecurity** | Botgate | 动态封装/验证/混淆/令牌，VM + eval | 控制流平坦化、WASM、滑块轨迹、并发环境 | `FSSBBIl1UgzbN7N80S`；202/412 状态码（见 `ruishu-river-security.md`） |
| **阿里云盾 / 阿里 WAF** | ESA / WAF 3.0 | Cookie 会话跟踪 + JS 挑战 + 滑块 | 控制流平坦化、WASM、滑块轨迹 | `acw_tc`、`cdn_sec_tc`、`acw_sc__v2`、`acw_sc__v3`、`ssxmod_itna*`、`140#` 开头参数、`227!` 开头 + `fireyejs.js` |
| **腾讯** | TCaptcha（天御/防水墙） | JSVMP 设备指纹 + PoW | jsvmp、动态 JS、并发 IP 要求、AIGC 图库 | `tdc.js`、`collect`、`eks`、`ans`、`pow_answer`、`__TENCENT_CHAOS_VM` |
| **网易易盾** | NECaptcha / 风控 SDK | 设备指纹 + 行为轨迹 | 参数杂、并发环境 | `163` 域名、`data`、`fp`、`cb`、`gdxidpyhxdE` |
| **数美 shumei** | 天网 / 设备指纹 | 设备指纹 + 内容风控 | 无（社区认为最易） | `fverify` 请求、`organization`、`smidV2`、`smDeviceId`、`shumeiBlockBox` |
| **顶象 dingxiang** | 智能无感验证 / ConstID | 动态 JS + 环境校验 | 动态 JS、检验环境多、验证码类型多 | `ac` 加密参数、`ak`、`DXCaptcha`、`DXRiskManager` |
| **同盾** | 设备指纹 / tdCaptcha | Blackbox 指纹 + 滑块 | 动态 JS | `fm.js` + `blackbox`；`tdCaptcha.js` + `p1`~`p9` |
| **极验 GeeTest** | Sensebot / GeeGuard | 轨迹 + 指纹 + PoW | 无 | `geetest` 标识及域名（见 `captcha-vendors-cn.md`） |
| **vaptcha** | — | 手势识别 | 手势识别 | `vaptcha-sdk.js` |

> 难点列为社区口径（来源：https://1997.pro/archives/1713518394359），非官方评级，仅作工作量预估参考。

## 分层决策：先判断「哪一层在拦你」

这是中文风控逆向最容易走错的地方。**多数失败源于攻错了层**。

```text
请求失败
  │
  ├─ 返回 202 / 412，响应体是内联 JS        → 瑞数层（补环境 / 纯算法）
  ├─ 返回 200 但内容是 <script> 挑战页       → JS 挑战层（acw_sc__v2 类）
  ├─ 返回 403 且 Cookie 名可辨识厂商         → 厂商 WAF 层
  ├─ 页面正常但接口 403/参数错误             → 签名参数层（sign/token/blackbox）
  ├─ 页面正常但接口返回风控码                → 设备指纹层（需指纹自洽）
  └─ 全部正常但几分钟后失效                  → 会话/令牌生命周期层
```

**关键认知**：中文站点常**同时**部署多层。例如瑞数 6 代站点在通过挑战层后，业务接口还会**独立校验指纹**——「短 cookie 可过页面，但数据查询接口会校验指纹」是社区反复验证的现象。**通过第一层不等于通关**。

## 通用对抗手段（跨厂商）

### 1. 补环境（主流、性价比最高）

在 Node 中构造足以骗过检测的浏览器环境，直接运行站点代码产出参数。详见 `environment-simulation-jsvmp.md`。

推荐起点：[`pysunday/sdenv`](https://github.com/pysunday/sdenv)（基于改版 jsdom，社区评价「最舒服、又快又稳」）。

### 2. Hook + 全局导出

把生成函数从闭包中「提」出来，在真实或模拟环境中调用。

| 目标 | Hook 点 |
|---|---|
| Cookie 生成 | `document.cookie` 的 setter |
| 易盾指纹 | `window["gdxidpyhxde"]` 的 setter |
| 指纹生成函数 | 全局搜索特征参数名 → 断点 → 把函数挂到 `window` |
| 请求参数 | `XMLHttpRequest.prototype.send` / `fetch` |

```js
// Cookie setter hook：定位生成点
let cookieTmp = '';
Object.defineProperty(document, 'cookie', {
  get() { return cookieTmp; },
  set(v) {
    console.log('[cookie set]', v);
    debugger;              // 在此看调用栈即可定位生成函数
    cookieTmp = v;
    return v;
  },
});
```

### 3. Webpack 加载器复用

对自执行函数形态的混淆包，不必逐行扣代码：

1. 把 webpack 加载器（`__webpack_require__`）全局化
2. 给加载器加日志打印
3. 配 `env.js` 补环境
4. 用 `main.js` 调 `loader.js`，直接调用目标模块

### 4. RPC 远程调用

本地完全不还原算法，起一个浏览器常驻进程，本地代码通过 WebSocket 把参数需求发给浏览器，由真实浏览器环境计算后回传。

**适用**：算法复杂但请求量不高；或作为「先跑通再优化」的第一步。
**代价**：单机吞吐低，需管理浏览器池。

### 5. 轨迹生成

滑块/点选类需要轨迹：

- 贝塞尔曲线
- ease-in-out cubic 缓动
- AI 生成轨迹函数

### 6. UA 一致性（最易忽略、收益最高）

**JS 环境的 UA 必须与请求 UA 一致**。易盾场景实测报告：修正后通过率从 <20% 提升到 100%。

## 常见失败模式

| 症状 | 真实原因 | 修正 |
|---|---|---|
| 补环境后本地能出 cookie，但请求仍被拒 | 指纹不自洽（`screen`/`devicePixelRatio`/WebGL 组合不合理） | 用真实浏览器采集的环境快照，不要逐项硬编码 |
| 参数生成正确但接口返回风控 | 请求 UA / TLS 指纹与 JS 环境不一致 | 三层指纹对齐 |
| 补环境时报错缺失某属性 | 只补了「广度」没补「深度」 | 现代风控检测属性间关联性与属性描述符 |
| 本地跑通后隔天失效 | 站点算法迭代或 `$_ts` 类动态值变化 | 做动态匹配（正则/AST），不要写死 |
| Selenium/Playwright 直跑被识别 | 自动化特征检测 | 不要指望浏览器自动化直接绕过；改用补环境或 RPC |

## 移动端加固（伴随问题）

App 侧逆向常遇到加固壳，与 Web 风控是两条战线。

| 代际 | 技术特点 | 脱壳难度 | 代表工具 |
|---|---|---|---|
| 一代：DEX 整体加密 | Dex 整体加密，动态加载 | 较易，内存 dump | FRIDA-DEXDump、Dexhunter、elf-dump-fix |
| 二代：DEX 函数抽取 | 方法单独抽取加密，解密执行 | 可还原（dump 运行时方法体回填 dex） | FART、Youpk、BlackDex、Dex2oatHunter |
| 三代：VMP / Dex2C | 独立虚拟机解释执行 / 语义等价语法迁移 | **Dex2C 目前无办法还原，只能跟踪分析**；VMP 保护映射表，可人工还原 | 无成熟自动化工具 |

可核实的工具局限：

- **FART** 仅提供 Android 6.0 与 8.0 镜像；原始版无法应对 root 检测，**Fart8** 抹除了指纹可应对。因项目知名，**加固厂商已将 FART 特征加入黑名单**。
- **frida-fart** 需把 `fart.so`/`fart64.so` 拷到 `/data/app` 并 `chmod 777`；以 `spawn` 启动，进 Activity 后执行 `fart()`。高级用法 `dump(classname)` 可主动 dump 未执行过的方法（对函数抽取壳更有效）。**缺点：无法处理带反调试的壳**——付费版加固必带反调试，会识别 frida 特征，卡在启动界面且 frida-server 挂掉。
- **BlackDex** 基于插件化思路，把目标 App 当插件运行到自己进程中。**因开源，特征明显，加固厂商易对抗**。

**壳特征识别**：爱加密 5 代壳在 `assets` 下可见 `IJMDal.Data`。

> 各厂商特征 so 文件名清单（爱加密/梆梆/乐固/聚安全/易盾/通付盾/娜迦）在二手来源间存在出入，**属未核实**，实际识别应以现场 `lib/` 目录列表与加载流程为准。

## 来源

- 社区风控集合（难点/特征表）：https://1997.pro/archives/1713518394359
- 瑞数 4/5/6 代分析：https://www.cnblogs.com/ikdl/p/16453681.html 、https://www.cnblogs.com/ikdl/p/16647423.html 、https://www.cnblogs.com/ikdl/p/17778885.html
- 瑞数 6 补环境实战：https://blog.csdn.net/2401_85468967/article/details/148050084
- 数美 v4 设备 ID：https://cloud.tencent.com/developer/article/2475504
- 同盾 BlackBox：https://1997.pro/archives/1706068432055
- 同盾 v2 滑块 p1~p9：https://cloud.tencent.com/developer/article/2501583
- 易盾 fp / gdxidpyhxdE：https://blog.csdn.net/weixin_46625757/article/details/145442263
- 易盾滑块全参数：https://blog.csdn.net/Bushixiana/article/details/149002049
- 顶象请求链与参数：https://www.cnblogs.com/boycelee/p/14270112.html
- 加固三代划分：https://blog.csdn.net/weixin_39190897/article/details/114269713
- 加固与脱壳实操：https://juejin.cn/post/7423310754952675379

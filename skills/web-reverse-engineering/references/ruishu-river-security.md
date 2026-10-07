# 瑞数信息 RiverSecurity / Botgate 逆向专项

瑞数是中文互联网最强的动态防护之一，也是唯一需要「按站独立复现」的体系。它不靠指纹判定，而靠**动态变换**：同一段保护逻辑每次下发都不同，静态特征无法复用。

## 判别：先确认目标是不是瑞数

| 信号 | 值 | 说明 |
|---|---|---|
| 首次无 Cookie 请求状态码 | `202` | 3 代、4 代 |
| 首次无 Cookie 请求状态码 | `412` | 5 代及以后 |
| 响应体特征 | 内联自执行脚本 + `<meta>` 引用外链 JS | 形如 `c.FxJzG50F.dfe1675.js` |
| Cookie 名 | `FSSBBIl1UgzbN7N80S` / `FSSBBIl1UgzbN7N80T` | 两位数字为 HTTP 默认端口 |
| Cookie 名 | `FSSBBIl1UgzbN7N443T` | `443` = HTTPS 默认端口 |
| Cookie 名（5 代非标） | `vsKWUwn3HsfIO` / `WvY7XhIMu0fGT` | 5 代不再带端口号 |
| URL 后缀参数 | `MmEwMD=4xxxxx` | 4 代 |
| URL 后缀参数 | `bX3Xf9nD=5xxxxx` | 5 代 |

**命名规律**：`80` = HTTP 默认端口，`443` = HTTPS 默认端口。**Cookie 值第一位数字即瑞数代际**。

**两段式流程**：首次请求返回 202/412 → 单独请求一个 JS 文件 → 携带 JS 生成的 Cookie 重新请求页面 → 200。

## 代际差异

| 代际 | 入口特征 | 状态码 | 特殊点 |
|---|---|---|---|
| 3 代 | `_$aW = _$c6_$l6();` | 202 | `_$c6` 实为 `eval`，`_$l6()` 实为 `call` |
| 4 代 | `ret = _$DG.call(_$6a, _$YK);` | 202 | **有「生成假 Cookie」步骤** |
| 5 代 | `ret = _$Yg.call(_$kc, _$mH);` / `_$ap = _$j5.call(_$_T, _$gp);` | 412 | 无假 Cookie 步骤；Cookie 名不带端口 |
| 6 代 | 同上变体 | 412 | Cookie 长达 173 位；由 128 位数组转化 |

## 6 代内部结构（可核实要点）

- 最终 Cookie 由 **128 位数组**转化而来
- 其中 4 位数组由 `_$Zb` 生成「0–255 的随机数」
- `_$hM` 方法使用一个 **256 位数组** `_$yx._$4y`（该值可直接固定）
- 时间戳处理产出 `[1695610803, 1695611070, 394, -901278768]` 形式的 4 值，转 16 位数组后做位异或
- 核心代码位于 **VM 虚拟机**中，由 202/412 响应页面 `meta` 引用的外链 JS 加载，`eval` 激活
- `$_ts` 是动态值，需正则或 AST 动态匹配后替换

## 两条路线

### 路线 A：补环境（主流、维护成本低）

在 Node 中构造足以骗过瑞数检测的浏览器环境，直接运行站点 VM 代码产出 Cookie。

推荐栈：[`pysunday/sdenv`](https://github.com/pysunday/sdenv)（BSD-3-Clause，npm `sdenv`，Node ≥ 20.19.5，依赖 `node-gyp`）。其核心是 `sdenv-jsdom`——一个针对瑞数 jsdom 检测点做过修改的 jsdom fork。作者声明：**固定随机数 + 配合 `sdenv-extend` 部分插件后，瑞数 VMP 在 sdenv 中生成的 cookie 可与浏览器一致**。

同作者配套项目：

| 项目 | 作用 |
|---|---|
| [`sdenv-jsdom`](https://github.com/pysunday/sdenv-jsdom) | 专用 jsdom（fork 并改检测点） |
| [`sdenv-extend`](https://github.com/pysunday/sdenv-extend) | Node 与浏览器共用的环境扩展 |
| [`rs-reverse`](https://github.com/pysunday/rs-reverse) | 瑞数 VMP 纯算法逆向 |

同类公开补环境项目：`NodeSandbox`、`qxVm`、`boda_jsEnv`、`catvm`。与「瑞数 + cookie 一致性」直接对应的是 sdenv 系列。

**注意**：sdenv 作者声明主要针对瑞数 VMP 场景开发，不保证对其它反爬产品稳定可用。

### 路线 B：纯算法还原（成本高、无环境依赖）

[`pysunday/rs-reverse`](https://github.com/pysunday/rs-reverse) 提供四个子命令：

```bash
# 1. 生成动态代码：传入含 $_ts.nsd 与 $_ts.cd 的文本，或直接给 URL
npx rs-reverse makecode
npx rs-reverse makecode -u https://target/path

# 2. 生成 cookie（内部先跑 makecode，再跑还原算法）
npx rs-reverse makecookie
node main.js makecookie -j ./path/to/main.js -f ./path/to/ts.json

# 3. 两步请求版本（第一次请求带 cookie 进第二次请求）
npx rs-reverse makecode-high -u https://target/path

# 4. 调试/演示用：直接求值表达式
npx rs-reverse exec -c 'gv.cp2'
npx rs-reverse exec -c 'ascii2string(gv.keys)'
```

关键细节：
- `-j` 指定外层虚拟机代码文件，`-f` 指定 `ts.json` 配置文件
- 若目标网站存在**额外 debugger 版本**且 `basearr` 未做适配，需确认 `-f` 对应配置含 `hasDebug` 配置项，不存在可手动添加或用 `makecode` 自动生成
- `makecode-high` 需避免连续执行，会触发风控报错
- 纯算法还原需按控制流编号（如 742/744/772 号控制流）逐步跟进

## 检测点与对抗要点

瑞数 6 代从「广度检测」转向「深度验证」——更关注**属性间关联性**与**运行时行为特征**（含属性描述符检测强化）。仅补齐 `window`/`document`/`navigator`/`screen` 的广度已不够。

| 检测点 | 表现 | 对抗 |
|---|---|---|
| 自动化框架 | `l` 函数内 `while (window["_phantom"] || window["__phantomas"]) {}` 死循环 | 补环境时置 `undefined`；或用 sdenv 类框架 |
| 属性描述符 | 检测 getter/setter 是否为原生实现 | 用 `Object.defineProperty` 时保留原生描述符特征 |
| 属性关联性 | 跨对象交叉验证（如 `screen.width` 与 `devicePixelRatio` 的合理组合） | 采用真实浏览器采集的环境快照，而非逐项硬编码 |
| 指纹校验 | Cookie 长度与 `window.localStorage` 中 canvas 等指纹值相关 | **短 cookie 可过页面，但数据查询接口会校验指纹** —— 必须让指纹自洽 |
| Selenium/Playwright 直跑 | 社区报告「完全绕不过去，都被检测了」 | 不要指望浏览器自动化直接绕过 |

## 关键难点（现实评估）

1. 代码在 VM + `eval` 中运行，静态搜索不到关键逻辑
2. **每个站点算法独立，无通用脚本**——社区共识是「一个站一套脚本」
3. 控制流编号 + 动态 `$_ts` 使纯算法还原维护成本极高
4. 版本迭代快（4→5→6 代，且存在非标版本）

**厂商口径提示**：瑞数研发总监曾称「算法共有 2^32 种、每种 2^24 种变形、配合 2^128 密钥组合」。此为**公司方口径，无独立第三方复现，属未核实**。不要把它当作技术规格使用。

## 来源

- 瑞数 4 代分析：https://www.cnblogs.com/ikdl/p/16453681.html
- 瑞数 5 代分析：https://www.cnblogs.com/ikdl/p/16647423.html
- 瑞数 6 代分析：https://www.cnblogs.com/ikdl/p/17778885.html
- 瑞数 6 代补环境：https://blog.csdn.net/2301_80198695/article/details/146923013
- 瑞数 6 代 + 补环境实战：https://blog.csdn.net/2401_85468967/article/details/148050084
- 绕过瑞数 6 构造正向代理：https://flowerwind.github.io/2023/12/11/从条件竞争到绕过瑞数6反爬构造正向代理漫游内网-md
- 厂商官网：https://www.riversecurity.com
- 四项核心技术（转载 51CTO 采访）：https://developer.aliyun.com/article/187801

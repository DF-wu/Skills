# 补环境与 JSVMP 还原（Environment Simulation & JSVMP Analysis）

中文风控的核心障碍有两类：**补环境**（代码依赖浏览器环境）与 **JSVMP**（代码被编译成自定义字节码）。本文分别处理。

## 第一部分：补环境

### 概念

风控 JS 需要浏览器对象才能运行。补环境 = 在 Node 中构造足够的浏览器环境，直接运行站点代码产出参数。相比逐行扣代码，**维护成本低得多**——站点更新后通常无需改代码。

### 运行载体

| 方案 | 来源 | 要点 |
|---|---|---|
| Node `vm` | https://nodejs.org/api/vm.html | `vm.createContext()` 模拟 window 全局；`vm.Script` / `runInContext` / `runInNewContext`。**官方明示：`node:vm` 不是安全机制，不可用于运行不受信任代码** |
| jsdom | https://github.com/jsdom/jsdom | `getInternalVMContext()` 把 jsdom window 变成 vm 可用的真上下文 |
| happy-dom | https://github.com/capricorn86/happy-dom | 更快的 DOM 实现，TypeScript |
| isolated-vm | https://github.com/laverdet/isolated-vm | 真隔离 V8 isolate，REstringer / webcrack 用它跑 unsafe 模块 |
| node-canvas | https://github.com/Automattic/node-canvas | 补 Canvas 指纹必需 |

> `vm2` 的维护状态**未核实**（社区长期传闻有逃逸漏洞）。建议以 `isolated-vm` 作为替代。

### 需要补的对象清单

```
window / self / global
document（含 documentElement.getAttribute）
navigator（含 userAgent、plugins、mimeTypes、属性描述符）
location
localStorage / sessionStorage
screen
history
crypto
XMLHttpRequest / fetch
canvas / WebGL
external
performance
chrome
iframe.contentWindow
```

### 环境检测对抗（重点）

#### `Function.prototype.toString` native code 检测

这是最主流的检测手段。标准对抗实现：

```js
const $toString = Function.toString;
const myFunction_toString_symbol = Symbol('('.concat('', ')'));
const myToString = function myToString() {
  return (typeof this === 'function' && this[myFunction_toString_symbol]) || $toString.call(this);
};
const set_native = function (func, key, value) {
  Object.defineProperty(func, key, { enumerable: false, configurable: true, writable: true, value });
};
delete Function.prototype['toString'];
set_native(Function.prototype, 'toString', myToString);
set_native(Function.prototype.toString, myFunction_toString_symbol, 'function toString() { [native code] }');
```

**关键细节（极易被忽略）**：重定义 native 函数后，**其 `prototype` 必须保持 `undefined`**。

社区实测对比显示：`qxVm` 处理正确（native 函数 `prototype === undefined`），而自写框架常错误地给出函数 prototype。**检测方正是靠这一点抓补环境。**

#### 其他检测点与对策

| 检测点 | 对策 |
|---|---|
| `Symbol.toStringTag` / `Symbol.toPrimitive` | `Object.defineProperty(obj, Symbol.toStringTag, {value: 'External'})` |
| `Object.getOwnPropertyNames` / `Object.keys` 原型链枚举 | 精确控制自有属性集合（如某站要求只返回 `['length','name']`） |
| 属性描述符检测 | `Object.defineProperty` 显式设定 `enumerable` / `configurable` / `writable` |
| `Object.freeze()` 检测 | 模拟完毕后对 `window` / `navigator` 调 `Object.freeze()`（浏览器中它们本就是不可变的） |
| 异常堆栈特征 | Node 特征串 `/modules/cjs/loader`；对策：重写 `String.prototype.indexOf` 令其返回 -1 |
| `process` 全局检测 | 删除 `global.process`（并 `delete __dirname` / `__filename`） |
| Canvas / WebGL 指纹 | 需 `node-canvas` 真实绘制；注意 .jpg/.png、quality、属性差异，且同条件多次绘制须一致 |
| iframe `contentWindow` 检测 | 需模拟 iframe 上下文 |
| 自动化痕迹 | 部分站点有 20+ 项自动化属性检测点 |

#### 代理吐环境

对 `document` / `navigator` / `location` 挂 `Proxy` 打印访问轨迹，逐步补齐（`self` / `window` 通常无需挂代理）。

```js
function proxyEnv(obj, name) {
  return new Proxy(obj, {
    get(target, prop) {
      console.log(`[env] ${name}.${String(prop)}`);
      return target[prop];
    },
    set(target, prop, value) {
      console.log(`[env] set ${name}.${String(prop)} =`, value);
      target[prop] = value;
      return true;
    },
  });
}
```

### 补环境框架

| 框架 | 仓库 | 备注 |
|---|---|---|
| **sdenv** | https://github.com/pysunday/sdenv | 「完美过瑞数 vmp 理论通杀」；社区评价「最舒服、又快又稳」；基于改版 jsdom |
| v_jstools | https://github.com/cilame/v_jstools | Chrome 扩展式补环境/调试，含 AST 处理与 WASM 支持 |
| Fchrome | https://github.com/jiyulany/Fchrome | 定制 Chromium，环境自吐 |
| qxVm | https://github.com/ylw00/qxVm | 纯 JS 补环境框架，基于 `node16` + `vm2`；**DOM 操作不全** |
| boda_jsEnv | https://github.com/xuxiaobo-bobo/boda_jsEnv | — |
| 聚合仓 | https://github.com/hybjpjx/all_vm2_vm_node_sandbox | 汇总 CatVm2、HaHaVM、NodeSandbox、ZGYD、boda_jsEnv、qxVm、sdenv 等 |
| rs-reverse | https://github.com/pysunday/rs-reverse | sdenv 的灵感来源，瑞数纯算法 |

**社区评价**：`catvm` / `CatVm2` 环境缺失多且不更新；`node-sandbox`（魔改 Node）作者已弃坑。

> **重要限制**：部分「补环境框架」实际是**模拟环境框架**——修改了 jsdom 易被检测的地方，可直接运行站点 JS 出结果，但**不能「吐环境」**（只有部分对象和函数可监听打印日志，如 cookie、eval）。若需要完整的访问轨迹导出，仍需自行挂 `Proxy`。

### 补环境实战检查清单

- [ ] `navigator.userAgent` 与请求 UA 一致
- [ ] `screen` 与 `devicePixelRatio` 组合合理
- [ ] native 函数重定义后 `prototype === undefined`
- [ ] `Object.getOwnPropertyNames` 返回值符合浏览器
- [ ] `Object.freeze()` 已应用于 `window` / `navigator`
- [ ] 异常堆栈中无 Node 特征串
- [ ] `global.process` 已删除
- [ ] Canvas 同条件多次绘制结果一致
- [ ] 属性描述符（`enumerable` / `configurable` / `writable`）显式设定

## 第二部分：JSVMP

### 机制

自定义字节码 + 解释器循环。典型结构：

```
VMContext    寄存器 / 栈 / 字节码指针
VMInit       初始化
VMExit       退出
Dispatcher   主循环 while + switch(opcode)
Handler      每 opcode 的处理函数
```

执行模型：`opcode = bytecode[PC++]`，操作数从字节码流或常量池取，结果压栈/写寄存器。

**溯源**：概念源自 匡开圆（西北大学 2015 级硕士）2018 年学位论文《基于 WebAssembly 的 JavaScript 代码虚拟化保护方法研究与实现》及国家专利《一种基于前端字节码技术的 JavaScript 虚拟化保护方法》。

**官方立场（obfuscator.io 原文）**：

> "No automated deobfuscator online services currently exist for VM-obfuscated code — each obfuscation compiles code into custom bytecode with a unique virtual machine, making universal tooling impossible."

即 **JSVMP 无通用自动还原方案，必须逐样本处理**。这是本领域最重要的一条现实约束。

### 代表性实现

| 项目 | 仓库 | 说明 |
|---|---|---|
| cy_jsvmp | https://github.com/2833844911/cy_jsvmp | Babel AST + 自定义栈式 VM；**每次混淆动态生成 opcode 映射**；偏 ES5 |
| facelessJsvmp | https://github.com/Alanhays/facelessJsvmp | JSVMP 保护实现 |
| jsvmp | https://github.com/baishuijianjia/jsvmp | 栈式 JS VM，Babel AST + 字节码编译 + 沙箱执行 |
| obfuscator.io VM | https://obfuscator.io | 商业 Pro，见 `js-deobfuscation.md` 的 `vm*` 选项 |

**真实世界样本**：瑞数 vmp（4/5/6）、抖音 X-Bogus / abogus、腾讯 `tdc.js`（`__TENCENT_CHAOS_VM`）。

### 反虚拟化方法

1. **插桩 opcode + PC 追踪**：在 Dispatcher 的 `switch` 前打印 `(PC, opcode, 栈/寄存器快照)`，重建执行轨迹
2. **AST 恢复 `switch-case`**：把 handler 还原为按 opcode 编号的可读分支，再做逐 opcode AST 重写
3. **源码级插桩**：在 HTTP 层重写响应，注入插桩代码，避免改动手工脱壳产物
4. **PC 递增陷阱（高频踩坑）**：`opFunc.apply(undefined, args)` 与 `opFunc(...args)` 在 `PC += ++PC` 类表达式下语义不同——前者得 3，后者（先 `var v = ++PC; PC += v`）得 4。这是判定实现细节的关键线索
5. **`ret` opcode 的 undefined 歧义**：返回值为 `undefined` 时无法区分「正常返回」与「VM 退出」
6. **`opcode[++PC]` 加载器抽象**：把取指封装为独立函数，便于统一替换为日志版
7. **规模现实**：社区案例记载需跑完 **88 万条指令**才退出 VM——纯单步追踪不可行，必须做**收敛采样 + 关键路径回溯**

### 插桩/追踪工具

| 工具 | 仓库 | 能力 |
|---|---|---|
| v_jstools | https://github.com/cilame/v_jstools | Chrome 扩展：JS 调试、Hook、AST 处理、WASM 支持 |
| hello_js_reverse_skill | https://github.com/WhiteNightShadow/hello_js_reverse_skill | AI 驱动逆向 Skill；含 `hook_jsvmp_interpreter`（proxy / transparent 双模式）、`instrumentation(action='install'\|'log'\|'stop'\|'reload')`、`inject_hook_preset`（xhr/fetch/crypto/websocket/debugger_bypass/cookie/runtime_probe）、`network_capture`、`get_request_initiator`、`intercept_request` |

> 专用反虚拟化工具（`dexvm` / `vmp` 类）**未核实**——未找到可验证仓库。

### 与补环境的关系

JSVMP 常与补环境组合出现：VM 代码运行后仍需浏览器环境。实践顺序是：

1. 先用补环境让 VM 代码跑通（能出结果即算成功）
2. 若需理解算法，再做 opcode 级插桩追踪
3. 若只需结果，**停在步骤 1 即可**——不要为了「理解」而做无收益的 opcode 还原

## 来源

- 补环境原理与检测点：https://github.com/AlienwareHe/awesome-reverse/blob/main/js/browser-env-fix.md
- 携某 testab 补环境实战：https://cloud.tencent.com/developer/article/2446185
- native 函数 prototype 必须 undefined：http://program.robinjia.cc/page/5
- 补环境框架对比：https://www.cnblogs.com/kanadeblisst/p/18177803
- 多个开源补环境框架测试：https://juejin.cn/post/7366082235243741221
- sdenv：https://github.com/pysunday/sdenv
- Node vm 文档（非安全机制声明）：https://nodejs.org/api/vm.html
- JSVMP 无通用工具（obfuscator.io 官方立场）：https://obfuscator.io
- cy_jsvmp：https://github.com/2833844911/cy_jsvmp
- JSVMP 插桩辅助补环境：https://cloud.tencent.com/developer/article/2446185
- 腾讯 `__TENCENT_CHAOS_VM`：https://bbs.kanxue.com/thread-290429.htm

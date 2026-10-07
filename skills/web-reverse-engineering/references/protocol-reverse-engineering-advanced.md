# 协议逆向进阶（protobuf / gRPC / 自定义二进制 / MQTT / TLS 解密）

当目标不用 HTTP+JSON 时，需要协议层能力。本文覆盖现代协议逆向的完整工具链。

## 一、protobuf

**wire format 是 TLV**：`(field_number << 3) | wire_type` 作 key，四种 wire type 决定 value 编码（varint / length-delimited / 32bit / 64bit）。

**关键难点**：**类型信息不在报文里**（双方靠 `.proto` 约定）。无 `.proto` 时需做**启发式推断**：按 key 拆字段 → 用长度字段试探嵌套消息 → 输出可读树 → 人工修正 typedef。

| 工具 | 仓库 | 机制 |
|---|---|---|
| protobuf-inspector | https://github.com/mildsunrise/protobuf-inspector | 纯 Python，按 wire format 逐字段试探解码输出缩进树，支持外挂回调脚本补类型提示。**无 GitHub Release** |
| **pbtk** | https://github.com/marin-m/pbtk | 三件套：无 `.proto` 启发式反序列化、**从抓包/二进制反推 `.proto` 定义**、配套 GUI |
| **blackboxprotobuf** | https://github.com/nccgroup/blackboxprotobuf | `decode_message` 返回 `(dict, typedef)`，typedef 可回灌 `encode_message` **实现无 .proto 改包**；自带 `mitmproxy/` 插件（`bbpb.py`）与 `burp/` 扩展 |

**blackboxprotobuf 的改包能力是核心价值**——能解也能重新编码，意味着可以在代理里实时修改 protobuf 请求。

## 二、gRPC

| 工具 | 仓库 | 机制 |
|---|---|---|
| **grpcurl** | https://github.com/fullstorydev/grpcurl | 默认走 **server reflection**，无 `.proto` 即可 `list`/`describe`/`call`；也可 `-protoset` 走离线描述符；支持 TLS/mTLS 与明文 |
| grpcui | https://github.com/fullstorydev/grpcui | 把 gRPC 方法渲染为浏览器表单，同样依赖 reflection |
| mitmproxy-grpc | https://github.com/aarnaut/mitmproxy-grpc | 给 mitmproxy 补 gRPC 支持 |
| Nope-Proxy | https://github.com/summitt/Nope-Proxy | Burp 的 TCP/UDP 非 HTTP 代理扩展，覆盖 WebSocket 与自定义二进制 |

### Server Reflection 语义

- 服务名 `grpc.reflection.v1.ServerReflection`（旧版 `grpc.reflection.v1alpha` 仍被广泛兼容）
- 只有一条双向流 RPC `ServerReflectionInfo`
- 请求/响应按 oneof 匹配：`file_by_filename` / `file_containing_symbol` / `file_containing_extension` / `list_services` / `all_extension_numbers_of_type`

**实用价值**：若目标开启了 reflection，**整个 API 面直接暴露**，无需任何逆向。

```bash
grpcurl -plaintext host:port list
grpcurl -plaintext host:port describe svc.Service
grpcurl -plaintext -d '{"id": 1}' host:port svc.Service/Method
```

### gRPC-Web 帧格式

来源：https://raw.githubusercontent.com/grpc/grpc/master/doc/PROTOCOL-WEB.md

| 项 | 规则 |
|---|---|
| 帧结构 | 1 字节标志 + 4 字节**大端**长度 + 载荷 |
| trailer 帧 | **标志最高位 `0x80`** 标记；其正文是 HTTP/1 风格 header block（**不经 HTTP trailer 传输**） |
| base64 模式 | `application/grpc-web-text` 走 base64，且 **base64 padding 不与帧边界对齐，必须流式解码** |
| 流结束 | 以 EOF 结束，而非 HTTP/2 的 END_STREAM |

实现仓库：https://github.com/grpc/grpc-web

### mitmproxy 的 HTTP/2 能力边界

基于 hyper-h2：

- 忽略 PRIORITY 帧
- 不支持 push promise
- **不支持 h2c 明文**

**推论**：gRPC 抓包 = HTTP/2 抓包 + protobuf content view；明文 gRPC 需 TLS/ALPN 协商出 h2。

**protobuf 支持的真相**：mitmproxy 的 protobuf 支持是**内置 content view，不是独立 addon**。Python 侧仅在 `mitmproxy/contentviews/_api.py` 注册 `protobuf_definitions` 选项，**真正解析实现在 Rust 仓库** https://github.com/mitmproxy/mitmproxy_rs 。自 mitmproxy 12 起提供交互式 Protobuf / gRPC content view。

**Burp 侧**：官方 BApp「Protobuf Decoder」https://portswigger.net/bappstore/bd8c70d3f1b74679b2a9fed03d36e81a ，源码 https://github.com/PortSwigger/protobuf-decoder ，**最后更新 2021-08-04，依赖 Jython 2.7——已非活跃维护件**。应以 blackboxprotobuf 的 mitmproxy 插件为主。

## 三、自定义二进制协议

两条路线：

1. **描述式解析**：用声明式 DSL 描述字段结构并编译成多语言 parser，在真实报文上迭代校正
2. **自动推断**：从 pcap 做消息对齐 → 字段切分 → 类型推断 → 状态机重建

| 工具 | 来源 | 机制 |
|---|---|---|
| **Kaitai Struct** | https://github.com/kaitai-io/kaitai_struct | `.ksy` 声明式描述，编译到 C++/C#/Go/Java/JS/Lua/Nim/Perl/PHP/Python/Ruby/Rust |
| **Kaitai Web IDE** | https://ide.kaitai.io/ | hex 视图与解析对象树联动；右键 `.ksy` 即生成 parser；文件只落在浏览器本地存储；支持 `-webide-representation`、`-webide-parse-mode: eager` |
| 010 Editor Binary Templates | https://www.sweetscape.com/010editor/repository/templates/ | 类 C 语法模板驱动解析，适合长度前缀与变长数组 |
| **Wireshark Lua dissector** | https://www.wireshark.org/docs/wsdg_html_chunked/wsluarm.html | `Proto`/`ProtoField` 声明字段，`dissector(buffer, pinfo, tree)` 回调；须命中 `DissectorTable` 或用户 "Decode As"；TCP 流重组需注册 `tcp.port` 并开 desegment |
| Netzob | https://github.com/netzob/netzob | pcap → 消息对齐 → 字段切分 → 类型推断 → **FSM 推断**，并可反向生成 fuzzer。**release 停在 2.0.0（2023-01）** |

### Kaitai 快速示例

```yaml
meta:
  id: my_protocol
  endian: le
seq:
  - id: magic
    contents: [0xAA, 0xBB]
  - id: length
    type: u4
  - id: payload
    size: length
  - id: crc
    type: u2
```

生成 parser：`ksc -t python my_protocol.ksy`。

### 自动协议逆向的学术工具出处

| 工具 | 出处 |
|---|---|
| Discoverer | 2007 USENIX Security，动态二进制分析 + 影子执行推断报文格式 |
| FieldHunter | 2015/2016，字段抽取 + 类型推断。**第三方部分复现** https://github.com/vs-uulm/fieldhunter （**非原作者实现**） |
| NEMESYS | USENIX WOOT 2018，从单条消息内在结构推断字段边界并提出 Format Match Score |
| NETPLIER | NDSS 2021，把关键词识别建模为概率推断 |
| 综述 | Kleber/Maile/Kargl, IEEE COMST 2019, DOI 10.1109/COMST.2018.2867544 |

> **注意**：Discoverer 与 FieldHunter 的**官方开源实现均未找到**；`vs-uulm/fieldhunter` 仅为第三方部分复现，不等价于论文实现。

## 四、MQTT / CoAP / WebSocket

### 内置 dissector（最省力）

| 协议 | Wireshark 字段名 | 覆盖版本 | 默认端口 |
|---|---|---|---|
| MQTT | `mqtt` | 1.12.0–4.6.9 | 1883 / 8883 |
| CoAP | `coap` | 1.6.0–4.6.9 | 5683 / 5684 |

- 非标端口用 **Decode As**
- CoAP 支持 Block1/Block2 重组与 OSCORE 选项
- MQTT 解析 v5 属性
- **`https://wiki.wireshark.org/MQTT` 与 `/CoAP` 均已 404**，应以 Display Filter Reference 为权威入口：https://www.wireshark.org/docs/dfref/m/mqtt.html 、https://www.wireshark.org/docs/dfref/c/coap.html

### 客户端工具

| 工具 | 仓库 | 状态 |
|---|---|---|
| **MQTTX** | https://github.com/emqx/MQTTX | 活跃。桌面/Web/CLI 三形态，**CLI 可脚本化 pub/sub，适合造流量** |
| MQTT Explorer | https://github.com/thomasnordquist/MQTT-Explorer | 仓库仍在更新但 **release 停在 v0.3.5（2019-07）** |
| websocat | https://github.com/vi/websocat | 活跃。命令行 WebSocket 客户端/服务端/代理，**stdin/stdout 双向管道便于手工重放帧** |

### mitmproxy 的 WebSocket 能力

基于 wsproto：

- **不支持客户端/服务端消息重放**
- PING/PONG 不写入 flow
- `flow.websocket` 模型自 v6 起
- 插件用 `websocket_message` 钩子 + `WebSocketMessage` 对象
- 控制台有 "WebSocket Messages" 标签页

**Chrome DevTools**：Network 面板选中 WS 连接 → Messages 标签页，列 Data/Length/Time，二进制帧显示 opcode 名与编号。

## 五、TLS 解密

**核心事实**：现代 TLS 使用 PFS（临时密钥交换），**服务器私钥无法解密已捕获流量**。可行路径只有两条：

1. 从客户端 TLS 库导出会话密钥（keylog），交给 Wireshark
2. 中间人代理（mitmproxy/Charles/Burp）主动重协商

### SSLKEYLOGFILE 机制

进程启动时读取该环境变量，把 (Pre)-Master Secret 及 TLS 1.3 traffic secret 按 **NSS Key Log Format** 追加写入指定文件。

| 项 | 值 |
|---|---|
| 支持方 | Firefox、Chrome/Chromium（自 2014 年 BoringSSL 起内置，另有 `--ssl-key-log-file=<path>` 参数） |
| **不支持方** | **Safari 与 Windows SChannel 不遵循该变量** |
| 生效条件 | 浏览器必须**完全退出再重启** |
| 原始规范 | https://nss-crypto.org/reference/security/nss/legacy/key_log_format/index.html |
| **已标准化为 RFC 9850** | https://www.rfc-editor.org/rfc/rfc9850.html （Informational，2026-07） |
| OpenSSL | ≥ 3.4 原生读取 `SSLKEYLOGFILE`，此前必须由应用自行注册 keylog 回调 |

**标签**：`CLIENT_RANDOM`、`CLIENT_HANDSHAKE_TRAFFIC_SECRET`、`SERVER_HANDSHAKE_TRAFFIC_SECRET`、`CLIENT_TRAFFIC_SECRET_0`、`SERVER_TRAFFIC_SECRET_0`、`EXPORTER_SECRET`、`ECH_SECRET`、`ECH_CONFIG`。

**Wireshark 用法**：

```
Preferences → Protocols → TLS → (Pre)-Master-Secret log filename   # 内部选项 tls.keylog_file
editcap --inject-secrets tls,keys.txt in.pcap out.pcapng            # 固化进 pcapng 的 Decryption Secrets Block
```

**mitmproxy 集成**：

```bash
SSLKEYLOGFILE="$PWD/.mitmproxy/sslkeylogfile.txt" mitmproxy
# 若不想污染同 shell 下的浏览器，改用 MITMPROXY_SSLKEYLOGFILE
```

官方页：https://docs.mitmproxy.org/stable/howto/wireshark-tls/

### Frida 挂钩 `SSL_write` / `SSL_read`

**原理**：`SSL_write` 入参 buffer 是加密前明文，`SSL_read` 出参 buffer 是解密后明文，挂钩即得明文；要密钥则改挂钩 `SSL_CTX_set_keylog_callback` / BoringSSL `ssl_log_secret`。

| 项目 | 仓库 |
|---|---|
| ssl_logger | https://github.com/google/ssl_logger |
| **friTap** | https://github.com/fkie-cad/friTap — 活跃。覆盖 OpenSSL/BoringSSL/SChannel，输出明文抓包或 NSS keylog；含实验性内存扫描、RC4、Telegram/MTProto 解析、**Android arm64 去符号兜底**（靠 keylog 标签字符串定位 `ssl_log_secret`） |
| frida-sslkeylog | https://github.com/saleemrashid/frida-sslkeylog |
| Android SSL_read/write Hook | https://github.com/fanxs-t/Android-SSL_read-write-Hook |
| iOS TLS Keylogger | https://github.com/jankais3r/Frida-iOS-15-TLS-Keylogger |

**关键限制**：**静态链接的 BoringSSL（Flutter、Chromium、多数加固 App）无导出符号**，`Module.findExportByName` 失效，需按字节特征或偏移扫描。

## 六、mitmproxy 进阶

### addon 模型

扩展点是 **addon**——实现特定方法名的 Python 对象，注册到模块级 `addons` 列表即被加载。

**HTTP 钩子按调用时机**：

```
requestheaders   → 请求头读完、body 尚空
request          → 完整请求已读
responseheaders
response
error / http_connect
```

每个钩子收到可原地修改的 `mitmproxy.http.HTTPFlow`（如 `flow.response.text = ...` / `flow.response.content = b'...'`）。

### 实时重载（重要）

`-s path/to/script.py` 加载的脚本会被监视文件修改时间，改动后约 **1 秒内自动卸载旧模块、重新导入并注册**，**无需重启代理、不丢失其它 addon 与在途 flow 状态**。

- `configure` / `running` / 导入期抛错 → 记入事件日志并保留旧版本未注册
- 事件处理器内抛错 → 只记日志，不卸载 addon
- **新增脚本文件仍需重启**

### 已核实的选项与命令

| 项 | 源码位置 | 说明 |
|---|---|---|
| `connection_strategy` | `mitmproxy/addons/proxyserver.py` | 默认 `eager`，可选 `lazy` |
| `map_local` | `mitmproxy/addons/maplocal.py` | 把请求映射到本地文件/目录 |
| `map_remote` | `mitmproxy/addons/mapremote.py` | 把请求映射到远端主机 |
| HAR 导出 | `mitmproxy/addons/savehar.py`；`save.har` 命令 + `hardump` 选项 | 读取 HAR 支持 `mitmproxy -r example.har` |
| `tls_passthrough` | `examples/contrib/tls_passthrough.py` | **这是 contrib 示例脚本，不是内置 CLI 选项**，需 `-s` 加载 |

> **常见误区**：`tls_passthrough` 被广泛误传为内置选项，实际是 contrib 示例。照搬旧教程直接写 `--set tls_passthrough=true` 会报未知选项。

### 代理模式

| 模式 | 用途 |
|---|---|
| Regular | 显式 HTTP(S) 代理（默认推荐） |
| Local Capture | `--mode local[:进程名\|:PID]`，抓本机进程 |
| **WireGuard** | `--mode wireguard[@addr:port]`，起 VPN 服务端，抓外部设备或单个 Android App |
| Reverse | `reverse:SPEC`，置于服务器前 |
| Transparent | 网络层引流，客户端把代理机设为默认网关 |
| Upstream | `upstream:SPEC`，链式代理 |
| SOCKS | SOCKS5 服务端 |
| DNS | 可脚本化 DNS 服务端 |

### API 逆向辅助

**mitmproxy2swagger**（https://github.com/alufers/mitmproxy2swagger ）可从流量自动反推 OpenAPI/Swagger 定义。

## 来源

- pbtk：https://github.com/marin-m/pbtk
- blackboxprotobuf：https://github.com/nccgroup/blackboxprotobuf
- protobuf-inspector：https://github.com/mildsunrise/protobuf-inspector
- grpcurl：https://github.com/fullstorydev/grpcurl
- grpcui：https://github.com/fullstorydev/grpcui
- gRPC reflection 文档：https://grpc.github.io/grpc/core/md_doc_server-reflection.html
- gRPC reflection 指南：https://grpc.io/docs/guides/reflection/
- gRPC-Web 规范：https://raw.githubusercontent.com/grpc/grpc/master/doc/PROTOCOL-WEB.md
- grpc-web：https://github.com/grpc/grpc-web
- Kaitai Struct：https://github.com/kaitai-io/kaitai_struct
- Kaitai Web IDE：https://ide.kaitai.io/
- 010 Editor 模板库：https://www.sweetscape.com/010editor/repository/templates/
- Wireshark Lua dissector：https://www.wireshark.org/docs/wsdg_html_chunked/wsluarm.html
- Wireshark MQTT 字段参考：https://www.wireshark.org/docs/dfref/m/mqtt.html
- Wireshark CoAP 字段参考：https://www.wireshark.org/docs/dfref/c/coap.html
- Netzob：https://github.com/netzob/netzob
- NETPLIER：https://www.ndss-symposium.org/wp-content/uploads/ndss2021_4A-5_24531_paper.pdf
- NEMESYS：https://www.usenix.org/conference/woot18/presentation/kleber
- Discoverer：https://www.usenix.org/conference/16th-usenix-security-symposium/discoverer-automatic-protocol-reverse-engineering-network
- MQTTX：https://github.com/emqx/MQTTX
- websocat：https://github.com/vi/websocat
- NSS Key Log Format：https://nss-crypto.org/reference/security/nss/legacy/key_log_format/index.html
- RFC 9850：https://www.rfc-editor.org/rfc/rfc9850.html
- Wireshark TLS：https://wiki.wireshark.org/TLS
- mitmproxy + Wireshark：https://docs.mitmproxy.org/stable/howto/wireshark-tls/
- friTap：https://github.com/fkie-cad/friTap
- mitmproxy addons：https://docs.mitmproxy.org/stable/addons/overview
- mitmproxy events：https://docs.mitmproxy.org/stable/api/events.html
- mitmproxy modes：https://docs.mitmproxy.org/stable/concepts/modes
- mitmproxy2swagger：https://github.com/alufers/mitmproxy2swagger
- PortSwigger protobuf-decoder：https://github.com/PortSwigger/protobuf-decoder

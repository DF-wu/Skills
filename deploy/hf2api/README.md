# hf2api

HuggingFace Spaces 語音服務 — **兩種使用方式**，選你需要的。

| 方式                    | 說明                                                     | 需要              |
| ----------------------- | -------------------------------------------------------- | ----------------- |
| **Skill（直接）**       | 讀 skill 檔 → curl/Python 直接打 HF Space。零依賴。      | `curl`, `python3` |
| **Wrapper（本地 API）** | Docker 容器提供 OpenAI 相容 localhost API，經 VPN 出口。 | Docker, VPN 憑證  |

> **Skills 安裝路徑**: `npx skills add DF-wu/Skills --skill qwen3-asr-tts-hf2api`

---

## 這份設定的位置

Skill 檔、程式碼（`src/`）與這份部署設定現在都在同一個 repo：

| 內容 | 路徑 |
| ---- | ---- |
| Skill 本體 + 程式碼 | `skills/qwen3-asr-tts-hf2api/`、`skills/vits-tts-hf2api/` |
| 部署設定（本目錄） | `deploy/hf2api/` |

原本 skill 在 `DF-wu/TreasureBox`、程式碼在私有 `DF-wu/hf2api` 的雙 repo 架構已於
2026-08-19 合併到 `DF-wu/Skills`，不再需要跨 repo 同步。

`docker-compose.yml` 的 volume 已改指 `../../skills/<name>`，請從本目錄執行 compose。

---

## 方式一：Skill 直接使用（推薦給 Agent）

Agent 讀 skill 檔就能直接用 curl/Python 呼叫 HF Space。不需要 Docker、不需要 VPN、不需要啟動任何服務。

| Skill          | 安裝                                                    | 功能                      |
| -------------- | ------------------------------------------------------- | ------------------------- |
| `qwen3-asr-tts-hf2api` | `npx skills add DF-wu/Skills --skill qwen3-asr-tts-hf2api` | TTS 49 聲線 + ASR 31 語言 |
| `vits-tts-hf2api`  | `npx skills add DF-wu/Skills --skill vits-tts-hf2api`  | 800+ 角色 TTS + VA 查詢   |

Skill 內含：copy-paste bash/Python functions、完整聲線/VA 對照表、curl 一鍵範例。

---

## 方式二：Wrapper 本地 API（OpenAI 相容）

Docker 部署，提供 `localhost:8820` / `localhost:8830` OpenAI 相容端點。

### 部署模式

| 模式           | Compose 檔                             | gluetun              | 適用                  |
| -------------- | -------------------------------------- | -------------------- | --------------------- |
| **Standalone** | `docker-compose.yml`                   | 自帶 gluetun 容器    | 獨立機器，有 VPN 憑證 |
| **Production** | `myServices/hf2api/docker-compose.yml` | 共用 `gluetun-proxy` | axolotl，已有 gluetun |

### 快速開始

```bash
git clone https://github.com/DF-wu/Skills.git && cd Skills/deploy/hf2api

# Standalone（自帶 VPN）
cp .env.example .env && docker compose up -d

# Production（共用 gluetun-proxy, axolotl）
cd myServices/hf2api && docker compose up -d
```

> volume 已改指 `../../skills/<name>`，所以必須在 `deploy/hf2api/` 底下執行 compose。

### 服務

| 服務         | Port | 功能                      | 上游                           | 限制          |
| ------------ | ---- | ------------------------- | ------------------------------ | ------------- |
| qwen3-asr-tts-hf2api | 8820 | TTS 49 聲線 + ASR 31 語言 | Qwen3 HF Spaces                | GPU timeout   |
| vits-tts-hf2api  | 8830 | 800+ 角色 TTS             | 多上游 retry chain（見下表）   | 500/100 chars |

### VITS 上游 API 差異

| Upstream | API 類型 | `session_hash` | Speaker 格式 | Response 格式 |
|----------|---------|---------------|-------------|--------------|
| `ikechan8370/vits-uma-genshin-honkai` | REST `POST /api/generate/` | **不需要** | Gradio dropdown 字串 | `data[1]` = `{"name":"/tmp/x.wav"}` → `GET /file={name}` |
| `AHJoong/vits-uma-genshin-honkai` | REST `POST /api/generate/` | **必須** | 同上 | 同上 |
| `OldSecond/vits-uma-genshin-honkai` | REST `POST /api/generate/` | **必須** | 同上 | 同上 |
| `zomehwh/vits-uma-genshin-honkai`（WS 備援） | WebSocket `/queue/join` | WS protocol | 同上 | base64 inline WAV |

**Retry 順序**：ikechan8370 → AHJoong → OldSecond → zomehwh WS（最後手段）

- AHJoong / OldSecond 是 **新版 Gradio 3.50+**，需在 payload 加 `session_hash` 欄位
- 僅 retriable error（timeout / 5xx / connection）才重試到下一個上游
- 4xx / bad format → 立即 502，不 fallback

### Speaker：必須用 Gradio dropdown 精確字串

- ✅ `"神里绫华（龟龟）"` `"甘雨（椰羊）"` `"派蒙"`
- ❌ 整數 ID（SPEAKERS dict 的數值 ≠ Gradio dropdown index）
- ❌ 繁簡體差異（绫 ≠ 綾）
- `resolve_speaker_gradio()` 自動把簡稱對應到 dropdown 全名
- REST 現在全部傳字串（舊版傳整數 ID 已棄用）

### Language：Gradio dropdown 值

| API Key | Gradio 字串 |
|---------|------------|
| `"zh"` | `"中文"` |
| `"ja"` | `"日语"`（**不是** `"日本語"`） |
| `"mix"` | `"中日混合（中文用[ZH][ZH]包裹起来，日文用[JA][JA]包裹起来）"`

### API

```
POST /v1/audio/speech           # TTS
POST /v1/audio/transcriptions   # ASR（qwen3 only）
GET  /v1/models                 # 模型列表
GET  /health                    # 健康檢查
```

---

## 目錄結構

```
Skills/
├── deploy/hf2api/
│   ├── docker-compose.yml      # Standalone（自帶 gluetun）
│   ├── .env.example            # 環境變數
│   ├── README.md               ← 本檔案
│   ├── requirements.md         # 系統需求
│   └── CHANGELOG.md            # 開發記錄
└── skills/
    ├── qwen3-asr-tts-hf2api/   # SKILL.md + src/（Qwen3 原始碼）
    └── vits-tts-hf2api/        # SKILL.md + src/（VITS，REST→WS fallback）
```

Production compose 仍在 `myServices/hf2api/`（另一個 repo）。

---

## 安全性

- **Wrapper 預設開放**：`API_KEY` 未設定時無認證。僅綁定 `127.0.0.1` 不暴露外部。
- **VPN 必經**：所有上游流量經 gluetun，本機 IP 不暴露給 HF Space。
- **無日誌**：Wrapper 不記錄 prompt 或音訊內容。
- **Skill 直連**：curl/Python 直接呼叫 HF Space，不經過任何中介。IP 依你的網路環境。

---

## 已知限制

1. VITS REST 上游 500 chars / WS 備援 100 chars。Fallback 時文字截斷。
2. Qwen3: `speed` 參數上游不支援。
3. 輸出固定 WAV。
4. VITS 卡芙卡 zh 上游 bug → 用 `ja`（`"日语"`）。
5. Cold start: HF Space 閒置後首次請求 20-60s。
6. `zomehwh/vits-models-genshin-bh3`（per-character models）目前上游不可用（Space sleeping）。

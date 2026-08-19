# hf2api — 2026-05-28 Hardening & ikechan Integration

## Docker Hardening

- **Dockerfiles**: Created `qwen3-asr-tts-hf2api/Dockerfile` and `vits-tts-hf2api/Dockerfile` using `python:3.13-alpine` with pre-installed deps (`pip install .` at build time), non-root user (UID 1001), tini init, and healthcheck
- **docker-compose.yml**: Switched from `image: python:3.13-alpine` with runtime `pip install` to `build:` context using local Dockerfiles. Removed volume mounts and inline command scripts. Added healthchecks to both API containers. Fixed TZ default to Asia/Taipei.
- **.dockerignore**: Created to exclude tests, skills, docs, and cache files from build context
- **Dead dep removed**: `aiofiles` was listed in both `pyproject.toml` files but never imported — removed
- **cleanup**: Deleted `speakers.py.bak` backup file, renamed `requirment.md` → `requirements.md`
- **config**: `MAX_TEXT_LENGTH` now env-configurable (`os.getenv`), `FALLBACK_MAX_TEXT_LENGTH` added

## VITS Dual-Upstream (ikechan8370 primary)

- **New primary upstream**: `ikechan8370/vits-uma-genshin-honkai` — uses REST API (`/api/generate/`) instead of WebSocket, text limit 500 chars (up from 100), auto-detected GPU support
- **Fallback upstream**: `zomehwh/vits-uma-genshin-honkai` — original WebSocket, 100 char limit
- **rest_client.py**: New REST API client for ikechan8370's Gradio 3.x `/api/generate/` endpoint
- **tts.py**: Try REST API first (with integer speaker ID), fall back to WebSocket (with string speaker name). Fallback auto-truncates text to 100 chars if needed.
- **config.py**: `BASE_URL` → ikechan8370, `FALLBACK_BASE_URL` → zomehwh, `MAX_TEXT_LENGTH` → 500

## Documentation

- **README.md**: Comprehensive rewrite — architecture, quick start, API endpoints, env vars, skill files, known limitations
- **requirements.md**: Full system requirements document
- **Skills**: Both skill files rewritten with standard YAML frontmatter (`name`, `description` as primary trigger), compact API docs, curl examples, error codes

## Verification

- `docker compose build`: Both images build successfully (~70MB each, down from 149MB ghcr.io)
- `docker compose config`: All 3 services parse correctly
- curl present in both images, healthcheck ports correct
- python config defaults verified in containers

---

# hf2api — 2026-05-28 Debug & Fix Log

## 背景

TreasureBox 的 `qwen3-asr-tts-hf2api` 與 `vits-tts-hf2api` 兩個 skill 的程式碼存在於此目錄，
但 Docker image 尚未建置、容器未啟動。本次將兩者建置、啟動、測試、並修復三個上游 bug。

測試環境：axolotl，兩個 container 皆以 `--network=container:gluetun-proxy` 掛在現有 gluetun VPN 上，
而非 docker-compose.yml 中定義的獨立 gluetun（避免 VPN 憑證重複設定）。

---

## 服務狀態

### qwen3-asr-tts-hf2api (port 8820, inside gluetun-proxy)

- **狀態：正常運作**
- 上游 HF Space: https://qwen-qwen3-tts-demo.hf.space
- 48 voices, 12 languages (TTS) + 32 languages (ASR)
- 無需修改，開箱即用
- 測試結果：Vivian, Serena, Chelsie, Cherry, Moon 五個聲線全部成功生成音檔

### vits-tts-hf2api (port 8830, inside gluetun-proxy)

- **狀態：正常運作（經三個修復）**
- 上游 HF Space: https://zomehwh-vits-uma-genshin-honkai.hf.space
- 500+ anime/game character voices (Genshin, HSR, HI3, Uma Musume, etc.)
- 測試結果：神里綾華(ja)、雷電將軍(mix)、胡桃(zh)、甘雨(zh)、熒(zh) 成功
- 已知限制：卡芙卡(zh) 在 HF Space 上本身回傳 error:null，與 wrapper 無關

---

## 修復內容

### Fix 1: Language Mapping

**檔案：** vits-tts-hf2api/vits_tts_hf2api/speakers.py

**問題：** `LANGUAGES` dict 的值與 Gradio Space 的 dropdown 選項不一致：

- `ja` 原本對應 `日本語` → 應為 `日语`
- `mix` 原本對應 `Mix` → 應為 `中日混合（中文用[ZH][ZH]包裹起来，日文用[JA][JA]包裹起来）`
- `zh` 正確（`中文`），無需修改

### Fix 2: Speaker Name Resolution

**檔案：** vits-tts-hf2api/vits_tts_hf2api/speakers.py

**問題：**
1. 舊版 `resolve_speaker()` 回傳 integer ID，但 Gradio 3.x WebSocket API 的 dropdown
   參數必須是字串值（下拉選單的實際選項文字），而非 index
2. `SPEAKERS` dict 中的簡化名稱（如 `神里绫华`）與 Gradio dropdown 的實際值
   （如 `神里绫华（龟龟）`）不同

**修復：**
1. 從 Gradio Space 的 `/config` endpoint 抓取 component 13（speaker dropdown）的完整
   804 個選項，存入 `GRADIO_SPEAKER_CHOICES` 列表
2. 新增 `_build_gradio_name_map()` 函數：對每個 SPEAKERS key，在 GRADIO_SPEAKER_CHOICES
   中做 prefix match（如 `神里绫华` → `神里绫华（龟龟）`）
3. 新增 `resolve_speaker_gradio(name)` 函數，多層 fallback：
   - 直接比對 GRADIO_SPEAKER_CHOICES（精確）
   - 查 GRADIO_NAME_MAP（prefix match）
   - 查 SPEAKER_ALIASES → GRADIO_NAME_MAP
   - case-insensitive 搜尋
   - prefix match（len >= 2）
   - substring match

### Fix 3: Result Parsing (base64 decode)

**檔案：** vits-tts-hf2api/vits_tts_hf2api/tts.py

**問題：**
1. 舊版將 WS 回傳的 `result[0]` 當作檔案路徑，透過 `/file=` endpoint 下載
2. 實際上 HF Space 回傳的格式是：
   - `result[0]`: `"生成成功!"` (success message)
   - `result[1]`: `"data:audio/wav;base64,..."` (base64 data URI)
   - `result[2]`: `"生成耗时 X.XX s"` (timing)
3. `/file=` download 回傳 500（檔案不存在或 session 過期）

**修復：** 優先嘗試從 `result[1]` 解析 base64 data URI；fallback 才走舊式 file download。

### Fix 4: Language Value Resolution

**檔案：** vits-tts-hf2api/vits_tts_hf2api/tts.py

**問題：** 舊版只檢查 `if language not in speakers.LANGUAGES` 確認 key 存在，
但未取 dict 的 **value**，導致 `"ja"` 直接被送到 Gradio 而非 `"日语"`。

**修復：**
```
language_key = body.get("language", config.DEFAULT_LANGUAGE)
language = speakers.LANGUAGES.get(language_key,
    speakers.LANGUAGES.get(config.DEFAULT_LANGUAGE, "中文"))
```

---

## 部署方式

### Build

```
cd /home/df/workspace/hf2api
docker compose build qwen3-asr-tts-hf2api
docker compose build vits-tts-hf2api
```

### Run

```
docker run -d --name qwen3-asr-tts-hf2api \
  --network=container:gluetun-proxy \
  -e TTS_BASE_URL='https://qwen-qwen3-tts-demo.hf.space' \
  -e ASR_BASE_URL='https://qwen-qwen3-asr.hf.space' \
  -e PORT=8820 -e TZ=Asia/Taipei \
  hf2api-qwen3-asr-tts-hf2api

docker run -d --name vits-tts-hf2api \
  --network=container:gluetun-proxy \
  -e BASE_URL='https://zomehwh-vits-uma-genshin-honkai.hf.space' \
  -e PORT=8830 -e TZ=Asia/Taipei \
  hf2api-vits-tts-hf2api
```

### API 呼叫範例

從 host 端可用 localhost 或 gluetun 容器內部 IP 存取。

qwen3 TTS:
```
curl -X POST http://localhost:8820/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{"input":"你好","voice":"vivian","language":"zh"}' \
  -o output.wav
```

vits TTS (whispered tone):
```
curl -X POST http://localhost:8830/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{"input":"テスト","voice":"神里绫华","language":"ja",
       "noise_scale":0.3,"noise_scale_w":0.668,"length_scale":1.4}' \
  -o output.wav
```

qwen3 ASR:
```
curl -X POST http://localhost:8820/v1/audio/transcriptions \
  -F file=@audio.wav
```

### VITS Whisper 參數指南

| 參數 | 範圍 | 預設 | 悄悄話建議 | 說明 |
|------|------|------|-----------|------|
| noise_scale | 0.1–1.0 | 0.6 | **0.3** | 越低越平穩／冷淡 |
| noise_scale_w | 0.1–1.0 | 0.668 | 0.668 | 音素長度變化 |
| length_scale | 0.1–2.0 | 1.2 | **1.4** | 越高越慢／輕聲 |

---

## 已知問題

1. **卡芙卡 (zh) 無法合成**：HF Space 本身對該 speaker+language 組合回傳 error:null
2. **部分 Qwen3 聲線不穩定**：Chelsea、Luna 等少數聲線會回 TTS upstream error: null，重試或換聲線即可
3. **docker-compose.yml 中的獨立 gluetun 未使用**：目前共用 gluetun-proxy，若要改用獨立 VPN 需設定 VPN_PROVIDER、WG_PRIVATE_KEY 等環境變數
4. **ASR 未測試**：qwen3-asr-tts-hf2api 的 transcription endpoint 尚未實測
5. **gluetun-proxy IP 可能變動**：restart 後內部 IP 可能改變，需更新呼叫端

---

## 測試音檔

所有測試生成的 .wav 檔在 `/tmp/tts_output/`：

| 檔案 | 大小 | 內容 |
|------|------|------|
| qwen3_vivian_1.wav | 311KB | Vivian：「DF，夜深了…」 |
| qwen3_serena_2.wav | 331KB | Serena：「偷偷跟你說…」 |
| qwen3_chelsie_2.wav | 331KB | Chelsie |
| qwen3_cherry_2.wav | 289KB | Cherry |
| qwen3_moon_2.wav | 376KB | Moon |
| vits_ayaka_final.wav | 240KB | 神里綾華 (ja, whisper) |
| vits_raiden_final.wav | 63KB | 雷電將軍 (mix, whisper) |
| vits_胡桃_zh.wav | 150KB | 胡桃 (zh, whisper) |
| vits_甘雨_zh.wav | 178KB | 甘雨 (zh, whisper) |
| vits_荧_zh.wav | 166KB | 熒 (zh, whisper) |

---

## 檔案結構

```
/home/df/workspace/hf2api/
├── CHANGELOG.md          ← 本檔案
├── docker-compose.yml    ← 原始 compose（定義獨立 gluetun，未使用）
├── qwen3-asr-tts-hf2api/         ← qwen3-asr-tts-hf2api 原始碼（無修改）
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── qwen3_asr_tts_hf2api/
└── vits-tts-hf2api/          ← vits-tts-hf2api 原始碼（已修改三處）
    ├── Dockerfile
    ├── pyproject.toml
    ├── vits_tts_hf2api/
    │   ├── speakers.py   ← Fix 1, Fix 2
    │   ├── tts.py        ← Fix 3, Fix 4
    │   ├── ws_client.py  ← 未修改
    │   └── config.py
    └── speakers.py.bak   ← 原始備份
```

---

## 除錯腳本

以下腳本留存於 `/tmp/` 供參考：

- `debug_vits.py` — 第一版 WS debug（用 speaker 字串成功）
- `debug_vits2.py` — 測試 index vs string vs full name
- `debug_vits3.py` — 使用 resolve_speaker_gradio 的完整 WS 測試
- `debug_kafka.py` — 卡芙卡特定測試（確認是 upstream 問題）
- `debug_result.py` — 分析 Gradio 回傳的 result 格式
- `extract_gradio_choices.py` — 從 Gradio config 拉取 804 個 speaker 選項
- `build_gradio_map.py` — 建立 simplified name 到 Gradio full name 的 mapping

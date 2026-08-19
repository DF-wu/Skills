import os

TTS_BASE_URL = os.getenv("TTS_BASE_URL", "https://qwen-qwen3-tts-demo.hf.space")
ASR_BASE_URL = os.getenv("ASR_BASE_URL", "https://qwen-qwen3-asr.hf.space")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "80"))
API_KEY = os.getenv("API_KEY")
DEFAULT_VOICE = os.getenv("DEFAULT_VOICE", "cherry")
DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "auto")
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "300"))
USER_AGENT = "Mozilla/5.0 AppleWebKit/537.36 Chrome/143 Safari/537"

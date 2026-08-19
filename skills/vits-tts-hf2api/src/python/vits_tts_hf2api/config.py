import os

BASE_URL = os.getenv("BASE_URL", "https://ikechan8370-vits-uma-genshin-honkai.hf.space")


def _parse_backup_urls():
    csv = os.getenv("BACKUP_REST_URLS", "")
    if csv:
        return [u.strip() for u in csv.split(",") if u.strip()]
    urls = []
    for i in range(1, 10):
        u = os.getenv(f"BACKUP_REST_URL_{i}", "")
        if u:
            urls.append(u)
    if urls:
        return urls
    return [
        "https://AHJoong-vits-uma-genshin-honkai.hf.space",
        "https://OldSecond-vits-uma-genshin-honkai.hf.space",
    ]


BACKUP_REST_URLS = _parse_backup_urls()
# FALLBACK_WS_URL: WebSocket fallback (replaces FALLBACK_BASE_URL)
FALLBACK_BASE_URL = os.getenv(
    "FALLBACK_BASE_URL", "https://zomehwh-vits-uma-genshin-honkai.hf.space"
)
FALLBACK_WS_URL = os.getenv("FALLBACK_WS_URL", FALLBACK_BASE_URL)
# VITS_MODELS_URL: per-character model Space
VITS_MODELS_URL = os.getenv(
    "VITS_MODELS_URL", "https://zomehwh-vits-models-genshin-bh3.hf.space"
)
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "80"))
API_KEY = os.getenv("API_KEY")  # None = open access
DEFAULT_SPEAKER = os.getenv("DEFAULT_SPEAKER", "日语神里绫华（早见沙织）")
# Default to "ja", NOT "mix": mix-mode requires explicit [ZH]...[ZH] / [JA]...[JA]
# markers around each segment. Raw text under mix returns a 556-byte empty WAV.
# The default speaker is a JP voice, so "ja" is the safe pairing.
DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "ja")
DEFAULT_NOISE_SCALE = float(os.getenv("DEFAULT_NOISE_SCALE", "0.6"))
DEFAULT_NOISE_SCALE_W = float(os.getenv("DEFAULT_NOISE_SCALE_W", "0.668"))
DEFAULT_LENGTH_SCALE = float(os.getenv("DEFAULT_LENGTH_SCALE", "1.2"))
FN_INDEX = int(os.getenv("FN_INDEX", "0"))
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "120"))
USER_AGENT = "Mozilla/5.0 AppleWebKit/537.36 Chrome/143 Safari/537"
MAX_TEXT_LENGTH = int(os.getenv("MAX_TEXT_LENGTH", "500"))
FALLBACK_MAX_TEXT_LENGTH = int(os.getenv("FALLBACK_MAX_TEXT_LENGTH", "100"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
RETRY_DELAY = float(os.getenv("RETRY_DELAY", "1.0"))

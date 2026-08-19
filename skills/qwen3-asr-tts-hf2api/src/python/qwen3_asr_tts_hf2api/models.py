from . import config

# === Qwen3-TTS voices ===
# Key: short lowercase ID → Value: Gradio display name (must match HF Space VOICE_OPTIONS keys)
TTS_VOICES = {
    "cherry": "Cherry / 芊悦",
    "serena": "Serena / 苏瑶",
    "ethan": "Ethan / 晨煦",
    "chelsie": "Chelsie / 千雪",
    "momo": "Momo / 茉兔",
    "vivian": "Vivian / 十三",
    "moon": "Moon / 月白",
    "maia": "Maia / 四月",
    "kai": "Kai / 凯",
    "nofish": "Nofish / 不吃鱼",
    "bella": "Bella / 萌宝",
    "jennifer": "Jennifer / 詹妮弗",
    "ryan": "Ryan / 甜茶",
    "katerina": "Katerina / 卡捷琳娜",
    "aiden": "Aiden / 艾登",
    "bodega": "Bodega / 西班牙语-博德加",
    "alek": "Alek / 俄语-阿列克",
    "dolce": "Dolce / 意大利语-多尔切",
    "sohee": "Sohee / 韩语-素熙",
    "onoanna": "Ono Anna / 日语-小野杏",
    "lenn": "Lenn / 德语-莱恩",
    "sonrisa": "Sonrisa / 西班牙语拉美-索尼莎",
    "emilien": "Emilien / 法语-埃米尔安",
    "andre": "Andre / 葡萄牙语欧-安德雷",
    "radiogol": "Radio Gol / 葡萄牙语巴-拉迪奥·戈尔",
    "eldric": "Eldric Sage / 精品百人-沧明子",
    "mia": "Mia / 精品百人-乖小妹",
    "mochi": "Mochi / 精品百人-沙小弥",
    "bellona": "Bellona / 精品百人-燕铮莺",
    "vincent": "Vincent / 精品百人-田叔",
    "bunny": "Bunny / 精品百人-萌小姬",
    "neil": "Neil / 精品百人-阿闻",
    "elias": "Elias / 墨讲师",
    "arthur": "Arthur / 精品百人-徐大爷",
    "nini": "Nini / 精品百人-邻家妹妹",
    "ebona": "Ebona / 精品百人-诡婆婆",
    "seren": "Seren / 精品百人-小婉",
    "pip": "Pip / 精品百人-调皮小新",
    "stella": "Stella / 精品百人-美少女阿月",
    "li": "Li / 南京-老李",
    "marcus": "Marcus / 陕西-秦川",
    "roy": "Roy / 闽南-阿杰",
    "peter": "Peter / 天津-李彼得",
    "eric": "Eric / 四川-程川",
    "rocky": "Rocky / 粤语-阿强",
    "kiki": "Kiki / 粤语-阿清",
    "sunny": "Sunny / 四川-晴儿",
    "jada": "Jada / 上海-阿珍",
    "dylan": "Dylan / 北京-晓东",
}

# === Qwen3-TTS languages ===
# Key → exact Gradio dropdown string (must match HF Space LANGUAGE_OPTIONS)
TTS_LANGUAGES = {
    "auto": "Auto / 自动",
    "zh": "Chinese / 中文",
    "en": "English / 英文",
    "ja": "Japanese / 日语",
    "ko": "Korean / 韩语",
    "de": "German / 德语",
    "fr": "French / 法语",
    "ru": "Russian / 俄语",
    "pt": "Portuguese / 葡萄牙语",
    "es": "Spanish / 西班牙语",
    "it": "Italian / 意大利语",
}

# === Qwen3-ASR languages ===
# Key → exact Gradio dropdown string (must match HF Space lang_choices)
# HF Space uses title-cased English names + "Auto"
ASR_LANGUAGES = {
    "auto": "Auto",
    "zh": "Chinese",
    "yue": "Cantonese",
    "en": "English",
    "ar": "Arabic",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "pt": "Portuguese",
    "id": "Indonesian",
    "it": "Italian",
    "ko": "Korean",
    "ru": "Russian",
    "th": "Thai",
    "vi": "Vietnamese",
    "ja": "Japanese",
    "tr": "Turkish",
    "hi": "Hindi",
    "ms": "Malay",
    "nl": "Dutch",
    "sv": "Swedish",
    "da": "Danish",
    "fi": "Finnish",
    "pl": "Polish",
    "cs": "Czech",
    "fil": "Filipino",
    "fa": "Persian",
    "el": "Greek",
    "ro": "Romanian",
    "hu": "Hungarian",
    "mk": "Macedonian",
}

VOICE_ALIASES = {
    "alloy": "vivian",
    "echo": "ethan",
    "fable": "momo",
    "onyx": "kai",
    "nova": "chelsie",
    "shimmer": "serena",
}


def resolve_voice(voice_id: str) -> str:
    lowered = voice_id.lower()
    if lowered in TTS_VOICES:
        return TTS_VOICES[lowered]
    if lowered in VOICE_ALIASES:
        real_key = VOICE_ALIASES[lowered]
        return TTS_VOICES.get(
            real_key, TTS_VOICES.get(config.DEFAULT_VOICE, config.DEFAULT_VOICE)
        )
    return TTS_VOICES.get(config.DEFAULT_VOICE, config.DEFAULT_VOICE)


def resolve_language(lang_id: str, target: str = "tts") -> str:
    lowered = lang_id.lower()
    mapping = TTS_LANGUAGES if target == "tts" else ASR_LANGUAGES
    if lowered in mapping:
        return mapping[lowered]
    return mapping.get(config.DEFAULT_LANGUAGE, config.DEFAULT_LANGUAGE)

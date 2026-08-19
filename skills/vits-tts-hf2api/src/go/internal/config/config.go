package config

import "time"

// Upstream HuggingFace Spaces. Order matters — this is the retry chain.
//
//   PrimaryURL    : ikechan8370 — fastest, no session_hash needed
//   BackupURL1    : AHJoong     — requires session_hash (422 otherwise)
//   BackupURL2    : OldSecond   — requires session_hash; occasionally cold
//   WSFallbackURL : zomehwh     — WebSocket only (REST blocked by queue auth)
//
// All four serve the same 804-speaker model with identical Gradio dropdowns.
const (
	PrimaryURL    = "https://ikechan8370-vits-uma-genshin-honkai.hf.space"
	BackupURL1    = "https://AHJoong-vits-uma-genshin-honkai.hf.space"
	BackupURL2    = "https://OldSecond-vits-uma-genshin-honkai.hf.space"
	WSFallbackURL = "wss://zomehwh-vits-uma-genshin-honkai.hf.space"

	DefaultTimeout = 120 * time.Second
)

// Config carries every CLI flag value. main.go builds this from pflag.
type Config struct {
	Text           string
	Speaker        string
	Language       string
	Output         string
	NoiseScale     float64
	NoiseScaleW    float64
	LengthScale    float64
	Speed          float64
	URL            string
	Timeout        time.Duration
	Whisper        bool
	ListSpeakers   bool
	SearchSpeakers string
	ListLanguages  bool
	Quiet          bool
}

// NewConfig returns the documented defaults. Language defaults to "ja" (NOT
// "mix") because the default speaker is a JP voice and mix-mode requires
// explicit [ZH]...[ZH] / [JA]...[JA] markers — raw text under mix produces a
// degenerate 556-byte empty WAV.
func NewConfig() *Config {
	return &Config{
		Speaker:     "日语神里绫华（早见沙织）",
		Language:    "ja",
		NoiseScale:  0.6,
		NoiseScaleW: 0.668,
		LengthScale: 1.2,
		Timeout:     DefaultTimeout,
	}
}

// Package speaker holds the upstream speaker dropdown choices and alias map.
//
// The canonical speaker list lives in references/vits_speakers.json at the
// project root. update_speakers.py rewrites BOTH that file and the embedded
// copy below so they never drift. The binary is fully self-contained — no
// runtime file dependency.
package speaker

import (
	_ "embed"
	"encoding/json"
)

//go:embed vits_speakers.json
var rawSpeakers []byte

// UpstreamChoices is the exact Gradio dropdown choices list from upstream.
// Order is preserved from the JSON (which mirrors upstream order).
var UpstreamChoices []string

// SpeakerAliases maps alias → exact Gradio dropdown string.
// Aliases include auto-generated short names (e.g. "甘雨" → "日语甘雨（上田丽奈）")
// and the hard-coded romaji map in update_speakers.py (e.g. "ayaka" → ...).
var SpeakerAliases map[string]string

func init() {
	var ref struct {
		Choices []string          `json:"choices"`
		Aliases map[string]string `json:"aliases"`
	}
	if err := json.Unmarshal(rawSpeakers, &ref); err != nil {
		panic("speaker: failed to parse embedded vits_speakers.json: " + err.Error())
	}
	UpstreamChoices = ref.Choices
	SpeakerAliases = ref.Aliases
	if SpeakerAliases == nil {
		SpeakerAliases = make(map[string]string)
	}
}

// Languages maps short keys to the Gradio dropdown string expected by the API.
// IMPORTANT: the JP value is `日语` (CN simplified), NOT `日本語` — upstream
// uses simplified Chinese for the language dropdown labels.
var Languages = map[string]string{
	"zh":  "中文",
	"ja":  "日语",
	"mix": "中日混合（中文用[ZH][ZH]包裹起来，日文用[JA][JA]包裹起来）",
}

// LanguageKeysSorted gives a stable, sorted iteration order for --list-languages.
var LanguageKeysSorted = []string{"zh", "ja", "mix"}

const (
	// DefaultSpeaker matches the Python package default (config.DEFAULT_SPEAKER)
	// and the SKILL.md documented default. Pick a JP voice because the mix /
	// 日语 default language pairs naturally with a JP seiyuu voice.
	DefaultSpeaker  = "日语神里绫华（早见沙织）"
	DefaultLanguage = "ja"

	DefaultNoiseScale  = 0.6
	DefaultNoiseScaleW = 0.668
	DefaultLengthScale = 1.2

	// MaxTextLength is the REST upstream limit (rune-counted, not bytes).
	// 500 chars is a soft client-side cap that matches upstream Gradio Spaces.
	MaxTextLength = 500
	// FallbackMaxTextLength is the WS upstream (zomehwh) limit.
	FallbackMaxTextLength = 100

	DefaultTimeout = 120
)

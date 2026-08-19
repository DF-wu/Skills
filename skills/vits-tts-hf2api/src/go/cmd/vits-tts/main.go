// vits-tts — single-binary CLI for the VITS uma-genshin-honkai TTS API.
//
//	./vits-tts "おはよう、旅人さん"                              # default speaker, mix lang
//	./vits-tts "こんにちは" -s ayaka -l ja                      # alias + JP
//	./vits-tts "你好旅行者" -s 派蒙 -l zh -o out.wav              # CN
//	./vits-tts --list-speakers | grep 日语 | head               # discovery
//
// See SKILL.md for the full speaker catalog, gotchas, and the upstream API
// behavior. See README.md for maintainer notes.
package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"unicode/utf8"

	"github.com/DF-wu/hf2api/vits-tts-hf2api/internal/client"
	"github.com/DF-wu/hf2api/vits-tts-hf2api/internal/config"
	"github.com/DF-wu/hf2api/vits-tts-hf2api/internal/speaker"
	"github.com/spf13/pflag"
)

const version = "0.3.0"

func main() {
	cfg := config.NewConfig()

	var (
		text           = pflag.StringP("text", "t", "", "Text to synthesize")
		speakerName    = pflag.StringP("speaker", "s", cfg.Speaker, "Speaker name or alias (see --list-speakers)")
		lang           = pflag.StringP("language", "l", cfg.Language, "Language: zh, ja, mix (or pass the Gradio value directly)")
		output         = pflag.StringP("output", "o", "", "Output WAV file path (default: derived from text)")
		noiseScale     = pflag.Float64("noise-scale", cfg.NoiseScale, "Noise scale 0.1–1.0")
		noiseScaleW    = pflag.Float64("noise-scale-w", cfg.NoiseScaleW, "Noise scale w 0.1–1.0")
		lengthScale    = pflag.Float64("length-scale", cfg.LengthScale, "Length scale 0.1–2.0 (inverse of speed)")
		speed          = pflag.Float64("speed", 0, "Speed override (length_scale = 1.0 / speed)")
		urlOverride    = pflag.String("url", "", "Override upstream base URL (skips retry chain)")
		timeout        = pflag.Duration("timeout", cfg.Timeout, "Per-request timeout (e.g. 30s, 2m)")
		whisper        = pflag.Bool("whisper", false, "Whisper preset: noise=0.3, length=1.4")
		listSpeakers   = pflag.Bool("list-speakers", false, "Print every speaker (sorted) and exit")
		searchSpeakers = pflag.String("search-speakers", "", "Print speakers matching substring (name or alias) and exit")
		listLangs      = pflag.Bool("list-languages", false, "Print supported languages and exit")
		quiet          = pflag.BoolP("quiet", "q", false, "Suppress info messages on stderr")
		showVersion    = pflag.Bool("version", false, "Print version and exit")
	)
	pflag.Parse()

	if *showVersion {
		fmt.Println(version)
		return
	}

	args := pflag.Args()
	if *text == "" && len(args) > 0 {
		*text = args[0]
	}

	if *listSpeakers {
		for _, s := range speaker.ListSpeakers() {
			fmt.Println(s)
		}
		return
	}
	if *searchSpeakers != "" {
		hits := speaker.SearchSpeakers(*searchSpeakers)
		for _, s := range hits {
			fmt.Println(s)
		}
		if len(hits) == 0 {
			fmt.Fprintf(os.Stderr, "No speakers match %q. Try --list-speakers for the full list.\n", *searchSpeakers)
			os.Exit(2)
		}
		return
	}
	if *listLangs {
		for _, k := range speaker.LanguageKeysSorted {
			fmt.Printf("%s\t%s\n", k, speaker.Languages[k])
		}
		return
	}

	if *text == "" {
		fmt.Fprintln(os.Stderr, "Error: no text provided (use positional arg or --text/-t)")
		pflag.Usage()
		os.Exit(1)
	}

	if *whisper {
		*noiseScale = 0.3
		*lengthScale = 1.4
	}
	if *speed > 0 {
		*lengthScale = 1.0 / *speed
	}

	displayLang := speaker.ResolveLanguage(*lang)
	res := speaker.ResolveSpeakerDetailed(*speakerName)
	if res.Resolved == "" {
		fmt.Fprintf(os.Stderr, "Error: unknown speaker %q\n", *speakerName)
		fmt.Fprintln(os.Stderr, "Try: ./vits-tts --search-speakers <substring>")
		os.Exit(1)
	}
	displaySpeaker := res.Resolved

	rawLen := utf8.RuneCountInString(*text)
	textVal := truncateRunes(*text, speaker.MaxTextLength)
	truncated := rawLen > speaker.MaxTextLength

	out := *output
	if out == "" {
		out = deriveOutput(textVal)
	}
	if abs, err := filepath.Abs(out); err == nil {
		out = abs
	}

	// mix language is silent-buggy without [ZH]/[JA] markers (returns 556-byte empty WAV).
	if (*lang == "mix" || displayLang == speaker.Languages["mix"]) &&
		!strings.Contains(textVal, "[ZH]") && !strings.Contains(textVal, "[JA]") {
		fmt.Fprintln(os.Stderr, "Warning: language=mix needs [ZH]...[ZH] / [JA]...[JA] markers around each segment.")
		fmt.Fprintln(os.Stderr, "  Without them upstream returns a 556-byte empty WAV. Use -l zh or -l ja for plain text.")
	}

	if !*quiet {
		fmt.Fprintf(os.Stderr, "Speaker: %s", displaySpeaker)
		if res.Kind != "exact" && res.Kind != "default" {
			fmt.Fprintf(os.Stderr, "  (resolved %q via %s match)", *speakerName, res.Kind)
		}
		fmt.Fprintln(os.Stderr)
		fmt.Fprintf(os.Stderr, "Language: %s\n", displayLang)
		fmt.Fprintf(os.Stderr, "Output: %s\n", out)
		if truncated {
			fmt.Fprintf(os.Stderr, "Warning: text truncated from %d to %d runes (REST limit)\n", rawLen, speaker.MaxTextLength)
		} else {
			fmt.Fprintf(os.Stderr, "Text length: %d runes\n", utf8.RuneCountInString(textVal))
		}
	}

	data := []any{
		textVal,
		displayLang,
		displaySpeaker,
		*noiseScale,
		*noiseScaleW,
		*lengthScale,
	}

	var audio []byte
	var err error
	var fromWS bool
	var logs []client.AttemptLog

	if *urlOverride != "" {
		// User picked a specific upstream. Honor the protocol they chose:
		//   wss:// or ws://  → WebSocket only
		//   anything else    → REST only (no auto-WS fallback to a possibly-unrelated host)
		if strings.HasPrefix(*urlOverride, "ws://") || strings.HasPrefix(*urlOverride, "wss://") {
			audio, err = client.CallGradioWS(*urlOverride, data, *timeout)
			fromWS = err == nil
		} else {
			audio, err = client.CallGradioREST(*urlOverride, data, *timeout, client.RandomSessionHash())
		}
	} else {
		audio, fromWS, logs = client.CallWithRetry(data, *timeout)
		if audio == nil {
			err = fmt.Errorf("all upstreams failed")
		}
	}

	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		for _, l := range logs {
			kind := "REST"
			if l.IsWS {
				kind = "WS  "
			}
			if l.Err != nil {
				fmt.Fprintf(os.Stderr, "  attempt %s %s → %v\n", kind, l.URL, l.Err)
			}
		}
		// Known gotcha: JP-only voices reject Chinese text with HTTP 500 across
		// all four upstreams. Surface a hint so the agent doesn't retry blindly.
		if strings.HasPrefix(displaySpeaker, "日语") && displayLang == speaker.Languages["zh"] {
			fmt.Fprintln(os.Stderr, "Hint: speaker is a JP-only voice (prefix \"日语\") but language=zh. Try -l ja, or use the matching CN speaker (drop \"日语\" prefix).")
		}
		os.Exit(1)
	}

	if err := os.WriteFile(out, audio, 0o644); err != nil {
		fmt.Fprintf(os.Stderr, "Error writing output: %v\n", err)
		os.Exit(1)
	}

	if client.IsLikelyEmptyWAV(audio) {
		fmt.Fprintf(os.Stderr, "Warning: output is only %d bytes — upstream likely returned an empty WAV.\n", len(audio))
		fmt.Fprintln(os.Stderr, "  Common cause: language=mix without [ZH]/[JA] markers, or a speaker that doesn't support the chosen language.")
	}

	if !*quiet {
		via := "REST"
		if fromWS {
			via = "WebSocket fallback"
		}
		fmt.Fprintf(os.Stderr, "Synthesized via %s\n", via)
		fmt.Fprintf(os.Stderr, "Wrote %d bytes to %s\n", len(audio), out)
	}
}

// deriveOutput builds a filename from the first 20 alphanumeric/CJK runes of
// the input. Punctuation and whitespace collapse to `_`. CJK passes through.
func deriveOutput(text string) string {
	if text == "" {
		return "vits_output.wav"
	}
	var sb strings.Builder
	count := 0
	for _, r := range text {
		if count >= 20 {
			break
		}
		switch {
		case r >= 'a' && r <= 'z',
			r >= 'A' && r <= 'Z',
			r >= '0' && r <= '9',
			r > 127:
			sb.WriteRune(r)
		default:
			sb.WriteRune('_')
		}
		count++
	}
	return sb.String() + ".wav"
}

func truncateRunes(s string, n int) string {
	runes := []rune(s)
	if len(runes) <= n {
		return s
	}
	return string(runes[:n])
}

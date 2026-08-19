package client

import (
	"errors"
	"net"
	"net/url"
	"strings"
	"syscall"
	"time"

	"github.com/DF-wu/hf2api/vits-tts-hf2api/internal/config"
	"github.com/DF-wu/hf2api/vits-tts-hf2api/internal/speaker"
)

type retryableError interface {
	IsRetryable() bool
}

func isRetryable(err error) bool {
	if err == nil {
		return false
	}
	if errors.Is(err, ErrTimeout) {
		return true
	}
	if r, ok := err.(retryableError); ok {
		return r.IsRetryable()
	}
	var netErr net.Error
	if errors.As(err, &netErr) {
		return true
	}
	var urlErr *url.Error
	if errors.As(err, &urlErr) {
		return true
	}
	var errno syscall.Errno
	if errors.As(err, &errno) {
		return true
	}
	msg := strings.ToLower(err.Error())
	return strings.Contains(msg, "connection refused") ||
		strings.Contains(msg, "no such host") ||
		strings.Contains(msg, "tls handshake timeout") ||
		strings.Contains(msg, "i/o timeout") ||
		strings.Contains(msg, "broken pipe") ||
		strings.Contains(msg, "reset by peer") ||
		strings.Contains(msg, "empty response")
}

// AttemptLog captures one call in the retry chain so the CLI can show what happened.
type AttemptLog struct {
	URL   string
	IsWS  bool
	Err   error
}

// CallWithRetry walks the upstream chain:
//
//	ikechan8370   REST, no session_hash
//	AHJoong       REST, session_hash required
//	OldSecond     REST, session_hash required
//	zomehwh       WebSocket, 100-char limit
//
// Returns the WAV bytes, a bool indicating WS path, and the per-attempt log.
// Only retriable errors fall through; 4xx and bad-format errors abort.
func CallWithRetry(data []any, timeout time.Duration) ([]byte, bool, []AttemptLog) {
	urls := []struct {
		url       string
		needsHash bool
		isWS      bool
	}{
		{config.PrimaryURL, false, false},
		{config.BackupURL1, true, false},
		{config.BackupURL2, true, false},
		{config.WSFallbackURL, false, true},
	}

	var logs []AttemptLog
	for i, u := range urls {
		callData := make([]any, len(data))
		copy(callData, data)

		// WS upstream has a 100-char limit on the public Space.
		if u.isWS {
			if text, ok := callData[0].(string); ok {
				runes := []rune(text)
				if len(runes) > speaker.FallbackMaxTextLength {
					callData[0] = string(runes[:speaker.FallbackMaxTextLength])
				}
			}
		}

		var audio []byte
		var err error
		if u.isWS {
			audio, err = CallGradioWS(u.url, callData, timeout)
		} else {
			hash := ""
			if u.needsHash {
				hash = RandomSessionHash()
			}
			audio, err = CallGradioREST(u.url, callData, timeout, hash)
		}

		logs = append(logs, AttemptLog{URL: u.url, IsWS: u.isWS, Err: err})

		if err == nil {
			return audio, u.isWS, logs
		}

		// Non-retriable: the upstream said "no" definitively (4xx, bad format,
		// generation error). Don't try the others — they would likely say the
		// same. The one exception: if this is the primary (ikechan8370) and the
		// error is HTTP 422 specifically, AHJoong might still accept it once we
		// add session_hash. Allow fall-through in that one case.
		if !isRetryable(err) && !(i == 0 && strings.Contains(err.Error(), "422")) {
			return nil, false, logs
		}

		if i == len(urls)-1 {
			return nil, false, logs
		}
	}

	return nil, false, logs
}

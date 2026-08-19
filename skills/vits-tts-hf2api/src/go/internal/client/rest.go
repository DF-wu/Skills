package client

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"
)

var (
	ErrTimeout   = errors.New("request timed out")
	ErrHTTP      = errors.New("HTTP error")
	ErrBadFormat = errors.New("bad response format")
	ErrGenerate  = errors.New("generation failed")
)

type generatePayload struct {
	FnIndex     int    `json:"fn_index"`
	Data        []any  `json:"data"`
	SessionHash string `json:"session_hash,omitempty"`
}

type generateResponse struct {
	Data []any `json:"data"`
}

// HTTPStatusError carries the HTTP status code so the retry layer can decide
// whether to fall through (5xx, 429) or fail fast (4xx).
type HTTPStatusError struct {
	StatusCode int
}

func (e *HTTPStatusError) Error() string {
	return fmt.Sprintf("HTTP error: status %d", e.StatusCode)
}

func (e *HTTPStatusError) IsRetryable() bool {
	return e.StatusCode >= 500 || e.StatusCode == 429
}

// CallGradioREST POSTs to {baseURL}/api/generate/ with fn_index:0, then
// downloads the returned WAV. ikechan8370 accepts an empty session_hash;
// AHJoong and OldSecond return 422 if it's missing — so always pass one
// when the caller knows the upstream needs it.
func CallGradioREST(baseURL string, data []any, timeout time.Duration, sessionHash string) ([]byte, error) {
	client := &http.Client{Timeout: timeout}

	u, err := url.Parse(strings.TrimSuffix(baseURL, "/"))
	if err != nil {
		return nil, err
	}

	payload := generatePayload{
		FnIndex:     0,
		Data:        data,
		SessionHash: sessionHash,
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}

	apiURL := u.String() + "/api/generate/"
	req, err := http.NewRequest(http.MethodPost, apiURL, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := client.Do(req)
	if err != nil {
		if isTimeout(err) {
			return nil, ErrTimeout
		}
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 500 || resp.StatusCode == 429 {
		return nil, &HTTPStatusError{StatusCode: resp.StatusCode}
	}
	if resp.StatusCode >= 400 {
		// 4xx → non-retriable. Surface the body so callers see why.
		snippet, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		return nil, fmt.Errorf("HTTP %d (non-retriable): %s", resp.StatusCode, strings.TrimSpace(string(snippet)))
	}

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}

	// Some Gradio Spaces return an empty body when waking up. Treat as retriable.
	if len(bytes.TrimSpace(respBody)) == 0 {
		return nil, &HTTPStatusError{StatusCode: 503}
	}

	var genResp generateResponse
	if err := json.Unmarshal(respBody, &genResp); err != nil {
		return nil, fmt.Errorf("%w: %v (body: %s)", ErrBadFormat, err, truncate(string(respBody), 200))
	}

	if len(genResp.Data) < 2 {
		return nil, fmt.Errorf("%w: data array has %d elements", ErrBadFormat, len(genResp.Data))
	}

	// data[0] is the human-readable status. "生成成功!" on success.
	if msg, ok := genResp.Data[0].(string); ok && msg != "" {
		if strings.Contains(msg, "error") || strings.Contains(msg, "Error") || strings.Contains(msg, "失败") || strings.Contains(msg, "失敗") {
			return nil, fmt.Errorf("%w: %s", ErrGenerate, msg)
		}
	}

	// data[1] is either:
	//   {"name": "/tmp/xxx.wav", "data": null, "is_file": true} — most upstreams
	//   "/tmp/xxx.wav"                                           — some older Spaces
	var filePath string
	switch v := genResp.Data[1].(type) {
	case map[string]any:
		if name, ok := v["name"].(string); ok {
			filePath = name
		} else if p, ok := v["path"].(string); ok {
			filePath = p
		}
	case string:
		filePath = v
	default:
		return nil, fmt.Errorf("%w: data[1] is %T, want map or string", ErrBadFormat, v)
	}
	if filePath == "" {
		return nil, fmt.Errorf("%w: empty file path in response", ErrBadFormat)
	}

	fileURL := u.String() + "/file=" + url.QueryEscape(filePath)
	fileReq, err := http.NewRequest(http.MethodGet, fileURL, nil)
	if err != nil {
		return nil, err
	}

	fileResp, err := client.Do(fileReq)
	if err != nil {
		if isTimeout(err) {
			return nil, ErrTimeout
		}
		return nil, err
	}
	defer fileResp.Body.Close()

	if fileResp.StatusCode != http.StatusOK {
		return nil, &HTTPStatusError{StatusCode: fileResp.StatusCode}
	}

	wav, err := io.ReadAll(fileResp.Body)
	if err != nil {
		return nil, err
	}
	if !isWAV(wav) {
		return nil, fmt.Errorf("%w: downloaded file is not WAV (got %d bytes, header=%q)", ErrBadFormat, len(wav), truncate(string(wav), 32))
	}
	return wav, nil
}

func isWAV(b []byte) bool {
	return len(b) > 12 && bytes.Equal(b[:4], []byte("RIFF")) && bytes.Equal(b[8:12], []byte("WAVE"))
}

// IsLikelyEmptyWAV returns true if the file is a syntactically valid WAV header
// but holds essentially no PCM data. The classic failure mode is a 556-byte WAV
// returned by upstream when mix-language text lacks [ZH]/[JA] markers, or when
// the synthesis silently fails. 2 KB is well below any legitimate speech sample.
func IsLikelyEmptyWAV(b []byte) bool {
	return isWAV(b) && len(b) < 2048
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "..."
}

// isTimeout uses typed checks instead of error string matching.
func isTimeout(err error) bool {
	if err == nil {
		return false
	}
	if errors.Is(err, context.DeadlineExceeded) {
		return true
	}
	var ne net.Error
	if errors.As(err, &ne) && ne.Timeout() {
		return true
	}
	// Net/http surfaces "Client.Timeout exceeded" as a plain error; fall back to string match for that one case.
	return strings.Contains(err.Error(), "Client.Timeout")
}

package client

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"math/rand"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/coder/websocket"
)

type wsMessage struct {
	Msg     string   `json:"msg"`
	Output  wsOutput `json:"output"`
	Success bool     `json:"success"`
}

type wsOutput struct {
	Data []any `json:"data"`
}

type wsHashPayload struct {
	SessionHash string `json:"session_hash"`
	FnIndex     int    `json:"fn_index"`
}

type wsDataPayload struct {
	FnIndex     int    `json:"fn_index"`
	Data        []any  `json:"data"`
	SessionHash string `json:"session_hash"`
}

// CallGradioWS runs the Gradio 3.x queue protocol against {baseURL}/queue/join.
//
// Protocol:
//
//	server: {"msg":"send_hash"}
//	client: {"session_hash":<11 chars>, "fn_index":0}
//	server: {"msg":"estimation",...}  -- one or more; ignore
//	server: {"msg":"send_data"}
//	client: {"data":[...], "fn_index":0, "session_hash":<same>}
//	server: {"msg":"process_starts"}  -- ignore
//	server: {"msg":"process_completed", "output":{"data":[...]}}
//
// output.data[1] is "data:audio/wav;base64,..." on the public zomehwh Space.
// Some forks return a {"name":"/tmp/...wav"} dict instead; we handle both.
func CallGradioWS(baseURL string, data []any, timeout time.Duration) ([]byte, error) {
	wsURL := toWSURL(baseURL)
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	c, _, err := websocket.Dial(ctx, wsURL, &websocket.DialOptions{
		HTTPHeader: http.Header{
			"User-Agent": {"Mozilla/5.0 AppleWebKit/537.36 Chrome/143 Safari/537"},
		},
	})
	if err != nil {
		if isTimeout(err) {
			return nil, ErrTimeout
		}
		return nil, err
	}
	defer c.CloseNow()
	c.SetReadLimit(8 << 20) // 8 MB — estimation messages can include large speaker lists

	sessionHash := RandomSessionHash()

	// Wait for send_hash
	for {
		var msg wsMessage
		if err := wsReadJSON(ctx, c, &msg); err != nil {
			return nil, err
		}
		if msg.Msg == "send_hash" {
			if err := wsWriteJSON(ctx, c, wsHashPayload{SessionHash: sessionHash, FnIndex: 0}); err != nil {
				return nil, err
			}
			break
		}
	}

	// Wait for send_data
	for {
		var msg wsMessage
		if err := wsReadJSON(ctx, c, &msg); err != nil {
			return nil, err
		}
		switch msg.Msg {
		case "send_data":
			if err := wsWriteJSON(ctx, c, wsDataPayload{
				FnIndex:     0,
				Data:        data,
				SessionHash: sessionHash,
			}); err != nil {
				return nil, err
			}
			goto waitCompletion
		case "estimation", "process_starts":
			continue
		case "queue_full":
			return nil, fmt.Errorf("%w: queue_full", ErrGenerate)
		}
	}

waitCompletion:
	for {
		var msg wsMessage
		if err := wsReadJSON(ctx, c, &msg); err != nil {
			return nil, err
		}
		switch msg.Msg {
		case "process_completed":
			return extractAudio(ctx, toHTTPURL(baseURL), msg.Output.Data, timeout)
		case "process_starts", "estimation", "progress":
			continue
		case "queue_full":
			return nil, fmt.Errorf("%w: queue_full", ErrGenerate)
		case "error":
			return nil, fmt.Errorf("%w: ws error message", ErrGenerate)
		}
	}
}

func toWSURL(base string) string {
	base = strings.TrimSuffix(base, "/")
	base = strings.Replace(base, "https://", "wss://", 1)
	base = strings.Replace(base, "http://", "ws://", 1)
	return base + "/queue/join"
}

func toHTTPURL(base string) string {
	base = strings.TrimSuffix(base, "/")
	if strings.HasPrefix(base, "wss://") {
		return strings.Replace(base, "wss://", "https://", 1)
	}
	if strings.HasPrefix(base, "ws://") {
		return strings.Replace(base, "ws://", "http://", 1)
	}
	return base
}

func wsReadJSON(ctx context.Context, c *websocket.Conn, v any) error {
	typ, r, err := c.Reader(ctx)
	if err != nil {
		return err
	}
	if typ != websocket.MessageText {
		_, _ = io.Copy(io.Discard, r)
		return fmt.Errorf("expected text message, got %d", typ)
	}
	return json.NewDecoder(r).Decode(v)
}

func wsWriteJSON(ctx context.Context, c *websocket.Conn, v any) error {
	w, err := c.Writer(ctx, websocket.MessageText)
	if err != nil {
		return err
	}
	if err := json.NewEncoder(w).Encode(v); err != nil {
		return err
	}
	return w.Close()
}

func extractAudio(ctx context.Context, httpBase string, data []any, timeout time.Duration) ([]byte, error) {
	if len(data) < 2 {
		return nil, fmt.Errorf("%w: ws output data has %d elements", ErrBadFormat, len(data))
	}

	// Most common: "data:audio/wav;base64,...."
	if s, ok := data[1].(string); ok && strings.HasPrefix(s, "data:") {
		parts := strings.SplitN(s, ",", 2)
		if len(parts) != 2 {
			return nil, fmt.Errorf("%w: malformed data URI", ErrBadFormat)
		}
		audio, err := base64.StdEncoding.DecodeString(parts[1])
		if err != nil {
			return nil, fmt.Errorf("%w: base64 decode: %v", ErrBadFormat, err)
		}
		if !isWAV(audio) {
			return nil, fmt.Errorf("%w: WS payload is not WAV (%d bytes)", ErrBadFormat, len(audio))
		}
		return audio, nil
	}

	// Fork format: {"name":"/tmp/xxx.wav","data":null}
	m, ok := data[1].(map[string]any)
	if !ok {
		return nil, fmt.Errorf("%w: ws data[1] is %T", ErrBadFormat, data[1])
	}

	if fileData, ok := m["data"].(string); ok && fileData != "" {
		// Some forks inline the WAV in `data` as raw base64.
		raw := fileData
		if i := strings.Index(raw, ","); i >= 0 && strings.HasPrefix(raw, "data:") {
			raw = raw[i+1:]
		}
		audio, err := base64.StdEncoding.DecodeString(raw)
		if err != nil {
			return nil, fmt.Errorf("%w: base64 decode (m.data): %v", ErrBadFormat, err)
		}
		if !isWAV(audio) {
			return nil, fmt.Errorf("%w: ws fork payload not WAV", ErrBadFormat)
		}
		return audio, nil
	}

	filePath, ok := m["name"].(string)
	if !ok || filePath == "" {
		if p, ok := m["path"].(string); ok {
			filePath = p
		}
	}
	if filePath == "" {
		return nil, fmt.Errorf("%w: no name/path in ws data[1]", ErrBadFormat)
	}

	client := &http.Client{Timeout: timeout}
	fileURL := httpBase + "/file=" + url.QueryEscape(filePath)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, fileURL, nil)
	if err != nil {
		return nil, err
	}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("%w: ws file status %d", ErrHTTP, resp.StatusCode)
	}
	buf := new(bytes.Buffer)
	if _, err := io.Copy(buf, resp.Body); err != nil {
		return nil, err
	}
	out := buf.Bytes()
	if !isWAV(out) {
		return nil, fmt.Errorf("%w: ws file fetch is not WAV", ErrBadFormat)
	}
	return out, nil
}

// RandomSessionHash generates an 11-char lowercase+digit token. Gradio uses it
// to correlate queue messages with the eventual completion event.
func RandomSessionHash() string {
	const charset = "abcdefghijklmnopqrstuvwxyz0123456789"
	b := make([]byte, 11)
	for i := range b {
		b[i] = charset[rand.Intn(len(charset))]
	}
	return string(b)
}

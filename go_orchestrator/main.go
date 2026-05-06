// ORC Go Orchestrator — concurrent AI task execution
// Exposes a small HTTP API that the Python frontend can call.
// Each /orchestrate request fans out to multiple AI provider calls
// concurrently using goroutines, then merges the results.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"os"
	"strings"
	"sync"
	"time"
)

// ── Types ─────────────────────────────────────────────────────────────────────

type OrchestrateRequest struct {
	Tasks   []Task `json:"tasks"`
	Timeout int    `json:"timeout_seconds"` // 0 → default 30s
}

type Task struct {
	ID       string            `json:"id"`
	Provider string            `json:"provider"` // "groq" | "alphafold" | "uniprot"
	Payload  map[string]string `json:"payload"`
}

type TaskResult struct {
	ID      string          `json:"id"`
	OK      bool            `json:"ok"`
	Data    json.RawMessage `json:"data,omitempty"`
	Error   string          `json:"error,omitempty"`
	Elapsed float64         `json:"elapsed_ms"`
}

type OrchestrateResponse struct {
	Results []TaskResult `json:"results"`
	Total   float64      `json:"total_ms"`
}

// ── Handlers ──────────────────────────────────────────────────────────────────

func healthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	fmt.Fprintln(w, `{"status":"ok","service":"orc-go-orchestrator"}`)
}

func orchestrateHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "POST only", http.StatusMethodNotAllowed)
		return
	}

	var req OrchestrateRequest
	body, err := io.ReadAll(io.LimitReader(r.Body, 1<<20))
	if err != nil || json.Unmarshal(body, &req) != nil {
		http.Error(w, `{"error":"invalid request body"}`, http.StatusBadRequest)
		return
	}

	timeout := time.Duration(req.Timeout) * time.Second
	if timeout <= 0 {
		timeout = 30 * time.Second
	}
	ctx, cancel := context.WithTimeout(r.Context(), timeout)
	defer cancel()

	start   := time.Now()
	results := make([]TaskResult, len(req.Tasks))
	var wg sync.WaitGroup

	for i, task := range req.Tasks {
		wg.Add(1)
		go func(idx int, t Task) {
			defer wg.Done()
			results[idx] = runTask(ctx, t)
		}(i, task)
	}

	wg.Wait()

	resp := OrchestrateResponse{
		Results: results,
		Total:   float64(time.Since(start).Milliseconds()),
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(resp)
}

// ── Task runners ──────────────────────────────────────────────────────────────

func runTask(ctx context.Context, t Task) TaskResult {
	start := time.Now()
	result := TaskResult{ID: t.ID}

	var data json.RawMessage
	var taskErr error

	switch strings.ToLower(t.Provider) {
	case "groq":
		data, taskErr = runGroqTask(ctx, t.Payload)
	case "alphafold":
		data, taskErr = runAlphaFoldTask(ctx, t.Payload)
	case "uniprot":
		data, taskErr = runUniProtTask(ctx, t.Payload)
	case "echo":
		// Useful for testing
		b, _ := json.Marshal(t.Payload)
		data = json.RawMessage(b)
	default:
		taskErr = fmt.Errorf("unknown provider: %s", t.Provider)
	}

	result.Elapsed = float64(time.Since(start).Milliseconds())
	if taskErr != nil {
		result.OK    = false
		result.Error = taskErr.Error()
	} else {
		result.OK   = true
		result.Data = data
	}
	return result
}

func runGroqTask(ctx context.Context, payload map[string]string) (json.RawMessage, error) {
	apiKey := payload["api_key"]
	if apiKey == "" {
		apiKey = os.Getenv("GROQ_API_KEY")
	}
	if apiKey == "" {
		return nil, fmt.Errorf("GROQ_API_KEY not set")
	}

	model := payload["model"]
	if model == "" {
		model = "llama-3.3-70b-versatile"
	}
	message := payload["message"]
	if message == "" {
		return nil, fmt.Errorf("payload.message is required")
	}

	reqBody := map[string]any{
		"model": model,
		"messages": []map[string]string{
			{"role": "user", "content": message},
		},
		"max_tokens": 512,
	}
	bodyBytes, _ := json.Marshal(reqBody)

	httpReq, _ := http.NewRequestWithContext(
		ctx, http.MethodPost,
		"https://api.groq.com/openai/v1/chat/completions",
		strings.NewReader(string(bodyBytes)),
	)
	httpReq.Header.Set("Authorization", "Bearer "+apiKey)
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(httpReq)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("groq API %d: %s", resp.StatusCode, string(raw[:min(len(raw), 120)]))
	}
	return json.RawMessage(raw), nil
}

func runAlphaFoldTask(ctx context.Context, payload map[string]string) (json.RawMessage, error) {
	uid := strings.TrimSpace(strings.ToUpper(payload["uniprot_id"]))
	if uid == "" {
		return nil, fmt.Errorf("payload.uniprot_id is required")
	}
	url := fmt.Sprintf("https://alphafold.ebi.ac.uk/api/prediction/%s", uid)
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	req.Header.Set("Accept", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(resp.Body)
	if resp.StatusCode == http.StatusNotFound {
		return nil, fmt.Errorf("no AlphaFold entry for %s", uid)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("alphafold API %d", resp.StatusCode)
	}
	return json.RawMessage(raw), nil
}

func runUniProtTask(ctx context.Context, payload map[string]string) (json.RawMessage, error) {
	query := payload["query"]
	if query == "" {
		return nil, fmt.Errorf("payload.query is required")
	}
	apiURL := fmt.Sprintf(
		"https://rest.uniprot.org/uniprotkb/search?query=%s&format=json&size=5",
		url.QueryEscape(query),
	)
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, apiURL, nil)
	req.Header.Set("Accept", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("uniprot API %d", resp.StatusCode)
	}
	return json.RawMessage(raw), nil
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

// ── Main ──────────────────────────────────────────────────────────────────────

func main() {
	port := os.Getenv("ORC_GO_PORT")
	if port == "" {
		port = "8765"
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/health",      healthHandler)
	mux.HandleFunc("/orchestrate", orchestrateHandler)

	log.Printf("ORC Go Orchestrator listening on :%s", port)
	if err := http.ListenAndServe(":"+port, mux); err != nil {
		log.Fatalf("server error: %v", err)
	}
}

# ORC Go Orchestrator

Concurrent AI task microservice. Uses goroutines to fan out requests to multiple
providers (Groq, AlphaFold EBI, UniProt) simultaneously and merge results.

## Build & Run

```bash
cd go_orchestrator
go build -o go_orchestrator .
./go_orchestrator          # default port 8765
ORC_GO_PORT=9000 ./go_orchestrator
```

## API

### GET /health
Returns `{"status":"ok","service":"orc-go-orchestrator"}`.

### POST /orchestrate

Fan-out request body:
```json
{
  "tasks": [
    {"id": "t1", "provider": "alphafold", "payload": {"uniprot_id": "P04637"}},
    {"id": "t2", "provider": "uniprot",   "payload": {"query": "BRCA2 human"}},
    {"id": "t3", "provider": "groq",      "payload": {"message": "Summarise p53.", "api_key": ""}}
  ],
  "timeout_seconds": 30
}
```

Response:
```json
{
  "results": [
    {"id": "t1", "ok": true, "data": {...}, "elapsed_ms": 312},
    {"id": "t2", "ok": true, "data": {...}, "elapsed_ms": 198},
    {"id": "t3", "ok": true, "data": {...}, "elapsed_ms": 850}
  ],
  "total_ms": 851
}
```

All tasks run concurrently; total time ≈ slowest task.

## Providers

| provider   | required payload keys     |
|------------|--------------------------|
| `groq`     | `message` (+ optional `model`, `api_key`) |
| `alphafold`| `uniprot_id`             |
| `uniprot`  | `query`                  |
| `echo`     | any (returns payload as-is, for testing) |

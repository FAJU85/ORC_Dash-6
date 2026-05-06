"""
Thin Python client for the ORC Go Orchestrator microservice.
The Go service runs on localhost:8765 (ORC_GO_PORT env var).
If the service is not running, all calls degrade gracefully with an error string.
"""

import os
import requests

_BASE = f"http://localhost:{os.environ.get('ORC_GO_PORT', '8765')}"
_TIMEOUT = 35


def _url(path: str) -> str:
    return _BASE + path


def is_available() -> bool:
    """Return True if the Go orchestrator is reachable."""
    try:
        r = requests.get(_url("/health"), timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def orchestrate(tasks: list[dict], timeout_seconds: int = 30) -> tuple[list[dict] | None, str | None]:
    """
    Fan out tasks to the Go orchestrator and return results.

    Each task dict must have:
        id       : str  — arbitrary identifier
        provider : str  — "groq" | "alphafold" | "uniprot" | "echo"
        payload  : dict[str, str]

    Returns (results, error_string).  results is a list of TaskResult dicts:
        id, ok, data, error, elapsed_ms
    """
    try:
        resp = requests.post(
            _url("/orchestrate"),
            json={"tasks": tasks, "timeout_seconds": timeout_seconds},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        body = resp.json()
        return body.get("results", []), None
    except requests.ConnectionError:
        return None, "Go orchestrator not running — start it with: cd go_orchestrator && ./go_orchestrator"
    except requests.Timeout:
        return None, "Go orchestrator timed out"
    except Exception as exc:
        return None, f"Orchestrator error: {exc}"


def alphafold_and_uniprot_parallel(
    uniprot_id: str,
    query: str | None = None,
) -> tuple[dict, str | None]:
    """
    Fetch AlphaFold prediction and optionally a UniProt search in parallel.
    Returns a merged dict: {"alphafold": [...], "uniprot": {...}}
    """
    tasks = [{"id": "af", "provider": "alphafold", "payload": {"uniprot_id": uniprot_id}}]
    if query:
        tasks.append({"id": "up", "provider": "uniprot", "payload": {"query": query}})

    results, err = orchestrate(tasks)
    if err:
        return {}, err

    merged: dict = {}
    for r in results:
        if r["ok"]:
            merged[r["id"]] = r.get("data")
        else:
            merged[r["id"] + "_error"] = r.get("error", "unknown error")
    return merged, None

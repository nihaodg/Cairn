from fastapi import APIRouter, HTTPException
import subprocess
import time

from cairn.server.db import get_conn
from cairn.server.models import ApiKeyEntry, ApiKeys, Settings, WorkerConfig, WorkerConfigs, WorkerTestRequest, WorkerTestResult

router = APIRouter(tags=["settings"])


@router.get("/settings", response_model=Settings)
def get_settings():
    with get_conn() as conn:
        row = conn.execute("SELECT intent_timeout, reason_timeout FROM settings WHERE rowid = 1").fetchone()
        return Settings(intent_timeout=row["intent_timeout"], reason_timeout=row["reason_timeout"])


@router.put("/settings", response_model=Settings)
def update_settings(body: Settings):
    with get_conn() as conn:
        conn.execute(
            "UPDATE settings SET intent_timeout = ?, reason_timeout = ? WHERE rowid = 1",
            (body.intent_timeout, body.reason_timeout),
        )
        return body


@router.get("/settings/api-keys", response_model=ApiKeys)
def get_api_keys():
    providers = ["anthropic", "openai"]
    result = {}
    with get_conn() as conn:
        for provider in providers:
            row = conn.execute(
                "SELECT api_key, base_url, model FROM api_keys WHERE provider = ?",
                (provider,),
            ).fetchone()
            if row:
                result[provider] = ApiKeyEntry(
                    provider=provider,
                    api_key=row["api_key"],
                    base_url=row["base_url"],
                    model=row["model"],
                )
            else:
                result[provider] = ApiKeyEntry(provider=provider)
    return ApiKeys(**result)


@router.put("/settings/api-keys", response_model=ApiKeys)
def update_api_keys(body: ApiKeys):
    with get_conn() as conn:
        for provider, entry in body.model_dump().items():
            conn.execute(
                "INSERT OR REPLACE INTO api_keys (provider, api_key, base_url, model) VALUES (?, ?, ?, ?)",
                (provider, entry["api_key"], entry["base_url"], entry["model"]),
            )
    return body


@router.get("/settings/workers", response_model=WorkerConfigs)
def get_worker_configs():
    workers = ["claude_code", "codex", "pi"]
    types = {"claude_code": "claudecode", "codex": "codex", "pi": "pi"}
    result = {}
    with get_conn() as conn:
        for name in workers:
            row = conn.execute(
                "SELECT type, api_key, base_url, model FROM worker_configs WHERE name = ?",
                (name,),
            ).fetchone()
            if row:
                result[name] = WorkerConfig(
                    name=name,
                    type=row["type"],
                    api_key=row["api_key"],
                    base_url=row["base_url"],
                    model=row["model"],
                )
            else:
                result[name] = WorkerConfig(name=name, type=types[name])
    return WorkerConfigs(**result)


@router.put("/settings/workers", response_model=WorkerConfigs)
def update_worker_configs(body: WorkerConfigs):
    with get_conn() as conn:
        for name, config in body.model_dump().items():
            conn.execute(
                "INSERT OR REPLACE INTO worker_configs (name, type, api_key, base_url, model) VALUES (?, ?, ?, ?, ?)",
                (name, config["type"], config["api_key"], config["base_url"], config["model"]),
            )
    return body


@router.post("/settings/workers/test", response_model=WorkerTestResult)
def test_worker_config(body: WorkerTestRequest):
    if not body.api_key:
        return WorkerTestResult(success=False, message="API Key is required")
    if not body.base_url:
        return WorkerTestResult(success=False, message="Base URL is required")
    if not body.model:
        return WorkerTestResult(success=False, message="Model is required")

    cmd = _build_healthcheck_cmd(body.type, body.api_key, body.base_url, body.model)
    started = time.perf_counter()
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        latency_ms = int((time.perf_counter() - started) * 1000)
        if result.returncode == 0:
            return WorkerTestResult(success=True, message="Connection successful", latency_ms=latency_ms)
        else:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            if not stderr:
                stderr = result.stdout.decode("utf-8", errors="replace").strip()
            return WorkerTestResult(success=False, message=stderr[:500] if stderr else "Request failed")
    except subprocess.TimeoutExpired:
        return WorkerTestResult(success=False, message="Request timeout (30s)")
    except Exception as exc:
        return WorkerTestResult(success=False, message=str(exc))


def _build_healthcheck_cmd(worker_type: str, api_key: str, base_url: str, model: str) -> list[str]:
    if worker_type == "claudecode":
        return [
            "curl", "-sS", "--fail", "-o", "/dev/null",
            "-H", f"Authorization: Bearer {api_key}",
            "-H", "anthropic-version: 2023-06-01",
            "-H", "content-type: application/json",
            "-d", f'{{"model":"{model}","max_tokens":10,"messages":[{{"role":"user","content":"ping"}}]}}',
            f"{base_url.rstrip('/')}/v1/messages",
        ]
    elif worker_type == "codex":
        return [
            "curl", "-sS", "--fail", "-o", "/dev/null",
            "-H", f"Authorization: Bearer {api_key}",
            "-H", "content-type: application/json",
            "-d", f'{{"model":"{model}","input":"ping","stream":false}}',
            f"{base_url.rstrip('/')}/responses",
        ]
    elif worker_type == "pi":
        return [
            "curl", "-sS", "--fail", "-o", "/dev/null",
            "-H", f"Authorization: Bearer {api_key}",
            "-H", "content-type: application/json",
            "-d", f'{{"model":"{model}","messages":[{{"role":"user","content":"ping"}}]}}',
            f"{base_url.rstrip('/')}/chat/completions",
        ]
    else:
        raise HTTPException(400, f"Unknown worker type: {worker_type}")

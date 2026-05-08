from fastapi import APIRouter

from cairn.server.db import get_conn
from cairn.server.models import ApiKeyEntry, ApiKeys, Settings, WorkerConfig, WorkerConfigs

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

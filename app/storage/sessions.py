from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.core.config import Settings


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RunRecord:
    session_id: str
    run_id: str
    status: str
    request: Dict[str, Any]
    response: Dict[str, Any] = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)
    error: Optional[Dict[str, Any]] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


def ensure_dirs(settings: Settings) -> str:
    base = os.path.join(settings.data_dir, "sessions")
    os.makedirs(base, exist_ok=True)
    return base


def make_session_id() -> str:
    return datetime.utcnow().strftime("s%Y%m%d_%H%M%S_%f")


def make_run_id() -> str:
    return datetime.utcnow().strftime("r%Y%m%d_%H%M%S_%f")


def _record_to_json(rec: RunRecord) -> Dict[str, Any]:
    return {
        "session_id": rec.session_id,
        "run_id": rec.run_id,
        "status": rec.status,
        "request": rec.request,
        "response": rec.response,
        "logs": rec.logs,
        "error": rec.error,
        "created_at": rec.created_at,
        "updated_at": rec.updated_at,
        "started_at": rec.started_at,
        "finished_at": rec.finished_at,
    }


def _normalize_run_doc(doc: Dict[str, Any], *, saved_path: str | None = None) -> Dict[str, Any]:
    normalized = dict(doc)
    normalized.setdefault("status", "completed" if normalized.get("response") else "failed")
    normalized.setdefault("request", {})
    normalized.setdefault("response", {})
    normalized.setdefault("logs", [])
    normalized.setdefault("error", None)
    normalized.setdefault("created_at", None)
    normalized.setdefault("updated_at", None)
    normalized.setdefault("started_at", None)
    normalized.setdefault("finished_at", None)
    normalized.setdefault("saved_path", saved_path or "")
    return normalized


def save_run(settings: Settings, rec: RunRecord) -> str:
    base = ensure_dirs(settings)
    sess_dir = os.path.join(base, rec.session_id)
    os.makedirs(sess_dir, exist_ok=True)

    path = os.path.join(sess_dir, f"{rec.run_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_record_to_json(rec), f, ensure_ascii=False, indent=2)
    return path


def load_run(settings: Settings, session_id: str, run_id: str) -> Optional[Dict[str, Any]]:
    base = ensure_dirs(settings)
    path = os.path.join(base, session_id, f"{run_id}.json")
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return _normalize_run_doc(json.load(f), saved_path=path)


def load_latest_run(settings: Settings, session_id: str) -> Optional[Dict[str, Any]]:
    base = ensure_dirs(settings)
    sess_dir = os.path.join(base, session_id)
    if not os.path.isdir(sess_dir):
        return None
    files = sorted(x for x in os.listdir(sess_dir) if x.endswith(".json"))
    if not files:
        return None
    path = os.path.join(sess_dir, files[-1])
    with open(path, "r", encoding="utf-8") as f:
        return _normalize_run_doc(json.load(f), saved_path=path)


def load_run_by_id(settings: Settings, run_id: str) -> Optional[Dict[str, Any]]:
    base = ensure_dirs(settings)
    if not os.path.isdir(base):
        return None

    for session_id in sorted(os.listdir(base), reverse=True):
        path = os.path.join(base, session_id, f"{run_id}.json")
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            return _normalize_run_doc(json.load(f), saved_path=path)
    return None


def list_runs(settings: Settings, *, statuses: Optional[set[str]] = None) -> list[Dict[str, Any]]:
    base = ensure_dirs(settings)
    if not os.path.isdir(base):
        return []

    records: list[Dict[str, Any]] = []
    for session_id in sorted(os.listdir(base)):
        sess_dir = os.path.join(base, session_id)
        if not os.path.isdir(sess_dir):
            continue
        for name in sorted(os.listdir(sess_dir)):
            if not name.endswith(".json"):
                continue
            path = os.path.join(sess_dir, name)
            with open(path, "r", encoding="utf-8") as f:
                record = _normalize_run_doc(json.load(f), saved_path=path)
            if statuses is not None and record["status"] not in statuses:
                continue
            records.append(record)
    return records


def list_pending_runs(settings: Settings) -> list[Dict[str, Any]]:
    records = list_runs(settings, statuses={"queued", "running"})
    return [record for record in records if not record.get("finished_at")]

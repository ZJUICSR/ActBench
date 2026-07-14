"""Raw training artifact recorder for ActBench runs."""

from __future__ import annotations

import contextvars
import hashlib
import json
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

_CURRENT_RECORDER: contextvars.ContextVar[Optional["TrainingArtifactRecorder"]] = (
    contextvars.ContextVar("claweval_training_artifact_recorder", default=None)
)


def get_current_recorder() -> Optional["TrainingArtifactRecorder"]:
    return _CURRENT_RECORDER.get()


def activate_recorder(recorder: Optional["TrainingArtifactRecorder"]):
    return _CURRENT_RECORDER.set(recorder)


def reset_recorder(token) -> None:
    _CURRENT_RECORDER.reset(token)


def record_model_call(
    *,
    role: str,
    model: str,
    request_payload: Dict[str, Any],
    response: Any = None,
    usage: Optional[Dict[str, Any]] = None,
    duration_seconds: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> Optional[Path]:
    recorder = get_current_recorder()
    if recorder is None:
        return None
    return recorder.record_model_call(
        role=role,
        model=model,
        request_payload=request_payload,
        response=response,
        usage=usage,
        duration_seconds=duration_seconds,
        metadata=metadata,
        error=error,
    )


def atomic_write_json(path: str | Path, data: Any) -> Path:
    """Atomically write JSON to ``path`` with a same-directory temp file."""

    final_path = Path(path)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, ensure_ascii=False, default=str)
    tmp_path = final_path.with_name(
        f".{final_path.name}.{os.getpid()}.{threading.get_ident()}.{time.time_ns()}.tmp"
    )
    try:
        tmp_path.write_text(payload, encoding="utf-8")
        os.replace(tmp_path, final_path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    return final_path


def artifact_file_info(path: str | Path) -> Dict[str, Any]:
    """Return stable integrity metadata for an artifact file."""

    artifact_path = Path(path)
    stat = artifact_path.stat()
    return {
        "size_bytes": stat.st_size,
        "sha256": _sha256_file(artifact_path),
    }


class TrainingArtifactRecorder:
    """Writes raw, non-redacted artifacts for later red-team model training."""

    schema_version = "training_artifacts.v1"

    def __init__(
        self,
        *,
        root: Path,
        run_kind: str,
        run_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.root = root
        self.run_kind = run_kind
        self.run_id = run_id
        self.metadata = metadata or {}
        self.model_call_count = 0
        self.model_calls: list[Dict[str, Any]] = []
        self.created_at = time.time()
        self._lock = threading.RLock()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "model_calls").mkdir(parents=True, exist_ok=True)
        (self.root / "runs").mkdir(parents=True, exist_ok=True)
        self.write_manifest()

    def write_manifest(self, extra: Optional[Dict[str, Any]] = None) -> Path:
        with self._lock:
            payload = {
                "schema_version": self.schema_version,
                "run_kind": self.run_kind,
                "run_id": self.run_id,
                "created_at": self.created_at,
                "updated_at": time.time(),
                "raw_retention_policy": "raw_unredacted",
                "metadata": self.metadata,
                "model_calls": self.model_calls,
            }
            if extra:
                payload.update(extra)
            return self.write_json("manifest.json", payload)

    def write_json(self, relative_path: str | Path, data: Any) -> Path:
        with self._lock:
            return atomic_write_json(self.root / relative_path, data)

    def write_text(self, relative_path: str | Path, text: str) -> Path:
        with self._lock:
            path = self.root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", errors="replace")
            return path

    def run_dir(self, run_key: str) -> Path:
        safe_key = safe_artifact_name(run_key)
        path = self.root / "runs" / safe_key
        path.mkdir(parents=True, exist_ok=True)
        return path

    def snapshot_directory(self, source: str | Path, relative_dest: str | Path) -> Dict[str, Any]:
        with self._lock:
            source_path = Path(source)
            dest_root = self.root / relative_dest
            manifest: Dict[str, Any] = {
                "source": str(source_path),
                "destination": str(dest_root),
                "created_at": time.time(),
                "files": [],
                "errors": [],
            }
            if not source_path.exists():
                manifest["missing"] = True
                self.write_json(Path(relative_dest) / "files_manifest.json", manifest)
                return manifest

            if dest_root.exists():
                shutil.rmtree(dest_root)
            dest_root.mkdir(parents=True, exist_ok=True)

            for path in sorted(source_path.rglob("*")):
                try:
                    rel = path.relative_to(source_path)
                except ValueError:
                    continue
                dest = dest_root / rel
                try:
                    if path.is_dir():
                        dest.mkdir(parents=True, exist_ok=True)
                        continue
                    if not path.is_file():
                        continue
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, dest)
                    stat = path.stat()
                    manifest["files"].append(
                        {
                            "path": str(rel),
                            "size": stat.st_size,
                            "sha256": _sha256_file(path),
                            "mtime": stat.st_mtime,
                        }
                    )
                except OSError as exc:
                    manifest["errors"].append({"path": str(rel), "error": str(exc)})

            self.write_json(Path(relative_dest) / "files_manifest.json", manifest)
            return manifest

    def record_api_context(
        self,
        *,
        run_key: str,
        api_endpoints: Optional[Dict[str, Any]] = None,
        api_audit: Optional[Dict[str, Any]] = None,
        fixture_overrides: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._lock:
            base = Path("runs") / safe_artifact_name(run_key) / "api"
            self.write_json(base / "endpoints.json", api_endpoints or {})
            self.write_json(base / "audit.json", api_audit or {})
            self.write_json(
                base / "fixture_overrides.json",
                {k: str(v) for k, v in (fixture_overrides or {}).items()},
            )
            for service, fixture_path in (fixture_overrides or {}).items():
                source = Path(str(fixture_path))
                if source.exists() and source.is_file():
                    dest = self.root / base / "fixtures" / f"{safe_artifact_name(str(service))}.json"
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, dest)
            for service, endpoint in (api_endpoints or {}).items():
                if not isinstance(endpoint, dict):
                    continue
                log_path = endpoint.get("log")
                if not log_path:
                    continue
                source = Path(str(log_path))
                if source.exists():
                    dest = self.root / base / "logs" / f"{safe_artifact_name(str(service))}.log"
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, dest)

    def record_model_call(
        self,
        *,
        role: str,
        model: str,
        request_payload: Dict[str, Any],
        response: Any = None,
        usage: Optional[Dict[str, Any]] = None,
        duration_seconds: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> Path:
        with self._lock:
            self.model_call_count += 1
            index = self.model_call_count
            safe_role = safe_artifact_name(role or "unknown")
            rel_path = Path("model_calls") / f"{index:06d}_{safe_role}.json"
            payload = {
                "index": index,
                "role": role or "unknown",
                "model": model,
                "request": request_payload,
                "response": response,
                "usage": usage or {},
                "duration_seconds": duration_seconds,
                "metadata": metadata or {},
                "error": error,
                "timestamp": time.time(),
            }
            path = self.write_json(rel_path, payload)
            self.model_calls.append(
                {
                    "index": index,
                    "role": role or "unknown",
                    "model": model,
                    "path": str(rel_path),
                    "error": error,
                    "metadata": metadata or {},
                }
            )
            self.write_manifest()
            return path


def safe_artifact_name(value: str) -> str:
    text = str(value or "unknown").strip().replace("\\", "_").replace("/", "_")
    safe = "".join(ch if ch.isalnum() or ch in "._=-" else "_" for ch in text)
    return safe[:160] or "unknown"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

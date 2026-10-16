"""Raw training artifact recorder for ActBench runs."""

from __future__ import annotations

import contextvars
import hashlib
import json
import os
import re
import shutil
import stat
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
    """Keep benchmark evidence while replacing known runtime credentials."""

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
        self._secrets: set[str] = set()
        for name, value in os.environ.items():
            if re.search(r"(?:^|_)(?:API_KEY|TOKEN|SECRET|PASSWORD|AUTH_TOKEN)$", name, re.I):
                self.register_secret(value)
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
                "raw_retention_policy": "runtime_credentials_redacted",
                "metadata": self.metadata,
                "model_calls": self.model_calls,
            }
            if extra:
                payload.update(extra)
            return self.write_json("manifest.json", payload)

    def write_json(self, relative_path: str | Path, data: Any) -> Path:
        with self._lock:
            return atomic_write_json(self.root / relative_path, self.redact_value(data))

    def write_text(self, relative_path: str | Path, text: str) -> Path:
        with self._lock:
            path = self.root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self.redact_text(text), encoding="utf-8", errors="replace")
            return path

    def register_secret(self, value: str) -> None:
        """Register an exact controller/provider credential, never a task pattern."""
        if value:
            with self._lock:
                self._secrets.add(value)

    def redact_text(self, value: str) -> str:
        with self._lock:
            secrets = sorted(self._secrets, key=len, reverse=True)
        for secret in secrets:
            value = value.replace(secret, "[REDACTED]")
        return value

    def redact_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.redact_text(value)
        if isinstance(value, dict):
            return {
                self.redact_text(key) if isinstance(key, str) else key: self.redact_value(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [self.redact_value(item) for item in value]
        if value is None or isinstance(value, (int, float, bool)):
            return value
        return self.redact_text(str(value))

    def _copy_evidence(self, source_file, target_file, size: int) -> Dict[str, Any]:
        # Read only the size observed at open: a still-running agent must not
        # extend collection indefinitely by appending to a file during capture.
        secrets = sorted((value.encode("utf-8") for value in self._secrets), key=len, reverse=True)
        pattern = re.compile(b"|".join(re.escape(value) for value in secrets)) if secrets else None
        overlap = max(map(len, secrets), default=1) - 1
        pending = b""
        remaining = size
        digest = hashlib.sha256()
        written = 0
        redacted = False
        while True:
            chunk = source_file.read(min(1024 * 1024, remaining)) if remaining else b""
            remaining -= len(chunk)
            pending += chunk
            final = not chunk or remaining == 0
            cutoff = len(pending) if final else max(0, len(pending) - overlap)
            pieces = []
            position = 0
            if pattern:
                for match in pattern.finditer(pending):
                    if match.start() >= cutoff:
                        break
                    pieces.extend((pending[position : match.start()], b"[REDACTED]"))
                    position = match.end()
                    redacted = True
            consumed = max(cutoff, position)
            pieces.append(pending[position:consumed])
            output = b"".join(pieces)
            target_file.write(output)
            digest.update(output)
            written += len(output)
            pending = pending[consumed:]
            if final:
                break
        return {"size": written, "sha256": digest.hexdigest(), "redacted": redacted}

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
                "symlinks": [],
                "errors": [],
            }
            if not source_path.exists():
                manifest["missing"] = True
                self.write_json(Path(relative_dest) / "files_manifest.json", manifest)
                return manifest

            if dest_root.exists():
                shutil.rmtree(dest_root)
            dest_root.mkdir(parents=True, exist_ok=True)

            # Agent-controlled links must never make the host recorder read
            # outside the mounted workspace. Record links as metadata only.
            # Directory FDs and O_NOFOLLOW also protect against replacements
            # while a service container is still alive during collection.
            def walk_error(exc):
                manifest["errors"].append({"path": str(exc.filename), "error": str(exc)})

            for directory, dirs, files, dir_fd in os.fwalk(
                source_path, follow_symlinks=False, onerror=walk_error
            ):
                dirs.sort()
                relative_dir = Path(directory).relative_to(source_path)
                (dest_root / relative_dir).mkdir(parents=True, exist_ok=True)
                for name in sorted(dirs + files):
                    rel = relative_dir / name
                    dest = dest_root / rel
                    try:
                        info = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
                        if stat.S_ISLNK(info.st_mode):
                            manifest["symlinks"].append(
                                {"path": str(rel), "target": os.readlink(name, dir_fd=dir_fd)}
                            )
                            continue
                        if not stat.S_ISREG(info.st_mode):
                            continue
                        fd = os.open(
                            name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd
                        )
                        with os.fdopen(fd, "rb") as source_file:
                            info = os.fstat(source_file.fileno())
                            if not stat.S_ISREG(info.st_mode):
                                continue
                            with dest.open("wb") as target_file:
                                captured = self._copy_evidence(
                                    source_file, target_file, info.st_size
                                )
                            after = os.fstat(source_file.fileno())
                        dest.chmod(stat.S_IMODE(info.st_mode))
                        os.utime(dest, ns=(info.st_atime_ns, info.st_mtime_ns))
                        manifest["files"].append(
                            {
                                "path": str(rel),
                                **captured,
                                "source_size": info.st_size,
                                "source_changed": (
                                    info.st_size != after.st_size
                                    or info.st_mtime_ns != after.st_mtime_ns
                                ),
                                "mtime": info.st_mtime,
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
                    dest = (
                        self.root / base / "fixtures" / f"{safe_artifact_name(str(service))}.json"
                    )
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with source.open("rb") as source_file, dest.open("wb") as target_file:
                        self._copy_evidence(
                            source_file, target_file, os.fstat(source_file.fileno()).st_size
                        )
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
                    with source.open("rb") as source_file, dest.open("wb") as target_file:
                        self._copy_evidence(
                            source_file, target_file, os.fstat(source_file.fileno()).st_size
                        )

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

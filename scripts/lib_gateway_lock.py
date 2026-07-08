"""Lightweight registry of in-use OpenClaw agent ids (gateway occupancy).

ClawEval's OpenClaw gateway hosts a small number of concurrent agents. Each
workload binds an ``agent_id`` (for example ``bench-<model>``). Two runs that
pick the same agent id can overwrite each other's agent definition, workspace,
and session transcripts, so this module records live occupancy.

Each registration is a JSON lock file under
``/tmp/claweval/gateway_locks/<agent_id>.json`` carrying the owning pid plus
context (scene/risk/model/command). A registration whose pid is no longer alive
is *stale* and is silently reclaimed, so a crashed run never wedges the slot.

Design notes:
- Keyed by agent_id because that — not the TCP port — is the real isolation
  unit. Dynamic mock-API port allocation already avoids port clashes.
- Best-effort: registration never raises on bookkeeping I/O errors. Only an
  explicit *live conflict* raises (GatewayLockConflict), and only when the
  caller asks to acquire a slot already held by a live pid.
- No external deps; safe to import from benchmark runners and status tools.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("gateway_lock")

LOCK_DIR = Path(os.environ.get("CLAWEVAL_GATEWAY_LOCK_DIR", "/tmp/claweval/gateway_locks"))


class GatewayLockConflict(RuntimeError):
    """Raised when an agent_id slot is already held by a live process."""

    def __init__(self, agent_id: str, holder: Dict[str, Any]):
        self.agent_id = agent_id
        self.holder = holder
        super().__init__(
            f"gateway agent slot '{agent_id}' is already held by pid "
            f"{holder.get('pid')} ({holder.get('role', '?')} "
            f"scene={holder.get('scene', '?')} risk={holder.get('risk', '?')}). "
            f"Use a distinct agent id, or wait for that run to finish."
        )


def _lock_path(agent_id: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in str(agent_id))
    return LOCK_DIR / f"{safe}.json"


def _pid_alive(pid: Any) -> bool:
    try:
        pid_int = int(pid)
    except (TypeError, ValueError):
        return False
    if pid_int <= 0:
        return False
    try:
        os.kill(pid_int, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Exists but owned by another user — treat as alive (slot is taken).
        return True
    except OSError:
        return False
    return True


def _read_lock(path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def read_holder(agent_id: str) -> Optional[Dict[str, Any]]:
    """Return the live holder of agent_id, or None if free or stale.

    A stale lock (dead pid) is removed as a side effect so the slot frees up.
    """
    path = _lock_path(agent_id)
    if not path.exists():
        return None
    holder = _read_lock(path)
    if holder is None:
        # Unparseable lock: treat as stale and clear it.
        _safe_unlink(path)
        return None
    if _pid_alive(holder.get("pid")):
        return holder
    _safe_unlink(path)
    return None


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def acquire(
    agent_id: str,
    *,
    role: str = "",
    scene: str = "",
    risk: str = "",
    model: str = "",
    worker_id: Any = None,
    command: str = "",
    pid: Optional[int] = None,
) -> Path:
    """Claim the agent_id slot for this process.

    Raises GatewayLockConflict if a live process already holds it. A stale
    (dead-pid) lock is reclaimed. Returns the lock file path; pass it to
    release(), or call release(agent_id).
    """
    holder = read_holder(agent_id)
    if holder is not None and int(holder.get("pid", -1) or -1) != int(pid or os.getpid()):
        raise GatewayLockConflict(agent_id, holder)
    record = {
        "agent_id": agent_id,
        "pid": int(pid or os.getpid()),
        "role": role,
        "scene": scene,
        "risk": risk,
        "model": model,
        "worker_id": worker_id,
        "command": command,
        "started_at": time.time(),
    }
    path = _lock_path(agent_id)
    try:
        LOCK_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    except OSError as exc:
        # Bookkeeping must never break a real run.
        logger.warning("Could not write gateway lock for %s: %s", agent_id, exc)
    return path


def release(agent_id: str, *, pid: Optional[int] = None) -> None:
    """Release the slot if held by this pid (or an unspecified/own pid)."""
    path = _lock_path(agent_id)
    holder = _read_lock(path)
    if holder is None:
        _safe_unlink(path)
        return
    owner = int(holder.get("pid", -1) or -1)
    if owner == int(pid or os.getpid()) or not _pid_alive(owner):
        _safe_unlink(path)


def list_active(reap_stale: bool = True) -> List[Dict[str, Any]]:
    """Return all live registrations, newest first.

    Stale (dead-pid) locks are removed when reap_stale is True.
    """
    active: List[Dict[str, Any]] = []
    if not LOCK_DIR.exists():
        return active
    for path in sorted(LOCK_DIR.glob("*.json")):
        holder = _read_lock(path)
        if holder is None:
            if reap_stale:
                _safe_unlink(path)
            continue
        if _pid_alive(holder.get("pid")):
            holder["_elapsed_seconds"] = max(0.0, time.time() - float(holder.get("started_at", 0) or 0))
            active.append(holder)
        elif reap_stale:
            _safe_unlink(path)
    active.sort(key=lambda h: float(h.get("started_at", 0) or 0), reverse=True)
    return active

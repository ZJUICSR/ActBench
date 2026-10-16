from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
from concurrent.futures import ThreadPoolExecutor
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib_training_artifacts import TrainingArtifactRecorder
from benchmark.ui import _next_run_id


def test_run_ids_reserve_distinct_workspaces_across_processes(tmp_path):
    run_root = tmp_path / "runs"
    first = _next_run_id(run_root)
    assert (run_root / first).is_dir()
    code = (
        "from pathlib import Path; from benchmark.ui import _next_run_id; "
        "import sys; print(_next_run_id(Path(sys.argv[1])))"
    )
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "scripts")}
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(
            pool.map(
                lambda _: subprocess.check_output(
                    [sys.executable, "-c", code, str(run_root)], env=env, text=True
                ).strip(),
                range(16),
            )
        )
    assert len({first, *ids}) == 17
    assert all((run_root / value).is_dir() for value in ids)


def test_known_credentials_are_redacted_in_json_text_model_calls_and_api_copies(
    tmp_path, monkeypatch
):
    secret = "synthetic-provider-private-value"
    monkeypatch.setenv("TEST_API_KEY", secret)
    recorder = TrainingArtifactRecorder(root=tmp_path / "artifacts", run_kind="test", run_id="keys")
    recorder.write_json("native.json", {secret: {"response": secret, "fixture": "sk-fake-task"}})
    recorder.write_text("stderr.txt", secret)
    recorder.record_model_call(role="judge", model="test", request_payload={"prompt": secret})
    fixture = tmp_path / "fixture.json"
    fixture.write_text(json.dumps({"data": secret, "fixture": "sk-fake-task"}))
    log = tmp_path / "api.log"
    log.write_text(secret)
    recorder.record_api_context(
        run_key="attempt",
        api_endpoints={"mock": {"log": str(log)}},
        fixture_overrides={"mock": fixture},
    )

    for path in recorder.root.rglob("*"):
        if path.is_file():
            assert secret.encode() not in path.read_bytes(), path
    native = json.loads((recorder.root / "native.json").read_text())
    assert native["[REDACTED]"] == {"response": "[REDACTED]", "fixture": "sk-fake-task"}
    assert "sk-fake-task" in (recorder.root / "runs/attempt/api/fixtures/mock.json").read_text()
    assert json.loads((recorder.root / "manifest.json").read_text())["raw_retention_policy"] == (
        "runtime_credentials_redacted"
    )


def test_snapshot_redacts_credentials_across_binary_chunk_boundaries(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    recorder = TrainingArtifactRecorder(
        root=tmp_path / "artifacts", run_kind="test", run_id="binary"
    )
    recorder.register_secret("private-credential")
    recorder.register_secret("private-credential-longer")
    content = (
        b"\xff\x00" + b"a" * (1024 * 1024 - 8) + b"private-credential-longer" + b"sk-fake-task"
    )
    (workspace / "binary.dat").write_bytes(content)

    manifest = recorder.snapshot_directory(workspace, "after")

    captured = (recorder.root / "after/binary.dat").read_bytes()
    assert captured == content.replace(b"private-credential-longer", b"[REDACTED]")
    assert manifest["files"][0]["redacted"] is True
    assert manifest["files"][0]["size"] == len(captured)
    assert manifest["files"][0]["sha256"] == hashlib.sha256(captured).hexdigest()
    assert manifest["files"][0]["source_size"] == len(content)


def test_snapshot_stops_at_opened_size_when_a_service_keeps_appending(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    growing = workspace / "growing.log"
    growing.write_bytes(b"initial evidence")
    inode = growing.stat().st_ino
    original_fstat = os.fstat
    appended = False

    def append_after_stat(fd):
        nonlocal appended
        info = original_fstat(fd)
        if info.st_ino == inode and not appended:
            with growing.open("ab") as target:
                target.write(b"later writes")
            appended = True
        return info

    monkeypatch.setattr(os, "fstat", append_after_stat)
    recorder = TrainingArtifactRecorder(
        root=tmp_path / "artifacts", run_kind="test", run_id="growth"
    )
    manifest = recorder.snapshot_directory(workspace, "after")

    assert (recorder.root / "after/growing.log").read_bytes() == b"initial evidence"
    assert manifest["files"][0]["source_changed"] is True


def test_workspace_snapshot_records_links_without_copying_their_targets(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    regular = workspace / "nested" / "run.sh"
    regular.parent.mkdir()
    regular.write_text("echo task\n")
    regular.chmod(0o750)
    (workspace / "empty").mkdir()
    host_secret = tmp_path / "controller-only.txt"
    host_secret.write_text("host-only sentinel")
    (workspace / "host-file").symlink_to(host_secret)
    (workspace / "host-dir").symlink_to(tmp_path)
    (workspace / "dangling").symlink_to(tmp_path / "missing")
    (workspace / "internal").symlink_to("nested/run.sh")
    os.mkfifo(workspace / "pipe")
    recorder = TrainingArtifactRecorder(
        root=tmp_path / "artifacts", run_kind="test", run_id="snapshot"
    )

    manifest = recorder.snapshot_directory(workspace, "after")

    snapshot = recorder.root / "after"
    assert (snapshot / "nested/run.sh").read_bytes() == regular.read_bytes()
    assert (snapshot / "nested/run.sh").stat().st_mode & 0o777 == 0o750
    assert (snapshot / "empty").is_dir()
    assert {link["path"] for link in manifest["symlinks"]} == {
        "host-file",
        "host-dir",
        "dangling",
        "internal",
    }
    assert [row["path"] for row in manifest["files"]] == ["nested/run.sh"]
    assert manifest["files"][0]["sha256"] == hashlib.sha256(regular.read_bytes()).hexdigest()
    assert manifest["errors"] == []
    for name in ["host-file", "host-dir", "dangling", "internal", "pipe"]:
        assert not (snapshot / name).exists()
        assert not (snapshot / name).is_symlink()
    assert json.loads((snapshot / "files_manifest.json").read_text()) == manifest


def test_workspace_snapshot_rejects_a_file_replaced_by_a_link_while_copying(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "swapped.txt"
    target.write_text("task data")
    host_secret = tmp_path / "controller-only.txt"
    host_secret.write_text("host-only sentinel")
    recorder = TrainingArtifactRecorder(root=tmp_path / "artifacts", run_kind="test", run_id="swap")
    original_open = os.open

    def replace_before_open(path, flags, *args, **kwargs):
        if path == "swapped.txt" and kwargs.get("dir_fd") is not None:
            target.unlink()
            target.symlink_to(host_secret)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", replace_before_open)
    manifest = recorder.snapshot_directory(workspace, "after")

    assert not (recorder.root / "after/swapped.txt").exists()
    assert manifest["files"] == []
    assert manifest["errors"][0]["path"] == "swapped.txt"

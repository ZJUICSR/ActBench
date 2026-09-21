from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib_training_artifacts import TrainingArtifactRecorder


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

from deeptrap import __version__
from deeptrap.cli import main
from deeptrap.paths import skills_dir, tasks_dir


def test_bundled_resources_are_available() -> None:
    assert (tasks_dir() / "task_B9_T01" / "task.yaml").is_file()
    assert (skills_dir() / "mock_apis" / "taskboard_api" / "SKILL.md").is_file()


def test_cli_help(capsys) -> None:
    main(["--help"])
    output = capsys.readouterr().out
    assert "Usage: deeptrap <command>" in output
    assert "test" in output
    assert "score" in output


def test_cli_version(capsys) -> None:
    main(["--version"])
    assert capsys.readouterr().out.strip() == f"deeptrap {__version__}"

"""Run the hook shell scripts the way Claude Code does: JSON on stdin, exit code as verdict."""

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def run_hook(script: str, payload: dict) -> subprocess.CompletedProcess[str]:  # type: ignore[type-arg]
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(ROOT), "CLAUDE_PLUGIN_ROOT": str(ROOT)}
    return subprocess.run(
        [str(ROOT / script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
        timeout=120,
        check=False,
    )


def test_format_hook_reformats_the_edited_python_file(tmp_path: Path) -> None:
    target = tmp_path / "messy.py"
    target.write_text("import sys,os\nx=[1,2,\n3]\nprint(os.name,sys.argv,x)\n")
    result = run_hook(".claude/hooks/format-python.sh", {"tool_input": {"file_path": str(target)}})
    assert result.returncode == 0, result.stderr
    formatted = target.read_text()
    assert "x = [1, 2, 3]" in formatted
    assert formatted.startswith("import os\nimport sys\n")


def test_format_hook_ignores_non_python_files(tmp_path: Path) -> None:
    target = tmp_path / "notes.md"
    target.write_text("# hi\n")
    result = run_hook(".claude/hooks/format-python.sh", {"tool_input": {"file_path": str(target)}})
    assert result.returncode == 0
    assert target.read_text() == "# hi\n"


def test_format_hook_exits_zero_without_file_path() -> None:
    result = run_hook(".claude/hooks/format-python.sh", {"tool_input": {"notebook_path": "x"}})
    assert result.returncode == 0
    assert result.stdout == ""


@pytest.mark.parametrize(
    "command",
    [
        "git push --force origin main",
        "git push -f origin main",
        "git push origin +main",
        "git commit -m x --no-verify",
        "git reset --hard HEAD~3",
        "git status; git push --force origin main",
        "git -C . push --force origin main",
        "cd repo && git push --force origin main",
    ],
)
def test_guard_blocks_destructive_git(command: str) -> None:
    result = run_hook(
        ".claude/hooks/guard-git.sh", {"tool_name": "Bash", "tool_input": {"command": command}}
    )
    assert result.returncode == 2
    assert result.stderr.strip()


@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "git push -u origin feature/x",
        "git push --force-with-lease origin feature/x",
        "uv run pytest -q",
        "echo 'git push --force' > notes.txt",
        'git commit -m "-n"',
    ],
)
def test_guard_allows_ordinary_commands(command: str) -> None:
    result = run_hook(
        ".claude/hooks/guard-git.sh", {"tool_name": "Bash", "tool_input": {"command": command}}
    )
    assert result.returncode == 0, result.stderr


def test_guard_exits_zero_on_empty_input() -> None:
    assert run_hook(".claude/hooks/guard-git.sh", {}).returncode == 0


def test_session_start_prints_plugin_context() -> None:
    result = run_hook(
        "hooks/scripts/session-start.sh", {"hook_event_name": "SessionStart", "source": "startup"}
    )
    assert result.returncode == 0
    assert "firmvalue" in result.stdout
    assert "estimate_parameters" in result.stdout
    assert "decompose_firm" in result.stdout

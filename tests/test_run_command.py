"""Tests for the `run` command and its supporting functions (resolve_run, discover_scripts)."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner

from reverse_api.session import SessionManager
from reverse_api.utils import discover_scripts, resolve_run


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def session_with_runs(tmp_path):
    """SessionManager with pre-populated runs."""
    history_path = tmp_path / "history.json"
    sm = SessionManager(history_path)
    sm.add_run("abc123def456", "capture the ashby jobs api", mode="manual", paths={"script_path": "/scripts/abc123def456/api_client.py"})
    sm.add_run("def789ghi012", "go to hubspot and create an api", mode="agent", paths={"script_path": "/scripts/def789ghi012/api_client.py"})
    sm.add_run("111222333444", "browserbase mp4 recording api", mode="manual", paths={"script_path": "/scripts/111222333444/api_client.py"})
    return sm


@pytest.fixture
def empty_session(tmp_path):
    """SessionManager with no runs."""
    history_path = tmp_path / "history.json"
    return SessionManager(history_path)


@pytest.fixture
def scripts_dir(tmp_path):
    """Create a fake scripts directory with multiple .py files."""
    run_id = "abc123def456"
    d = tmp_path / "scripts" / run_id
    d.mkdir(parents=True)
    (d / "api_client.py").write_text("print('hello from api_client')")
    (d / "example_usage.py").write_text("print('hello from example')")
    (d / "README.md").write_text("# docs")
    (d / "requirements.txt").write_text("requests>=2.28")
    return d


@pytest.fixture
def scripts_dir_single(tmp_path):
    """Create a scripts directory with a single .py file."""
    run_id = "abc123def456"
    d = tmp_path / "scripts" / run_id
    d.mkdir(parents=True)
    (d / "api_client.py").write_text("print('only script')")
    return d


@pytest.fixture
def scripts_dir_empty(tmp_path):
    """Create a scripts directory with no .py files."""
    run_id = "abc123def456"
    d = tmp_path / "scripts" / run_id
    d.mkdir(parents=True)
    (d / "README.md").write_text("# no scripts here")
    return d


# ---------------------------------------------------------------------------
# resolve_run tests
# ---------------------------------------------------------------------------

class TestResolveRunExactId:
    """Test resolve_run with exact run_id matches."""

    def test_exact_match(self, session_with_runs):
        run = resolve_run("abc123def456", session_with_runs)
        assert run["run_id"] == "abc123def456"

    def test_exact_match_second_run(self, session_with_runs):
        run = resolve_run("def789ghi012", session_with_runs)
        assert run["run_id"] == "def789ghi012"

    def test_exact_match_third_run(self, session_with_runs):
        run = resolve_run("111222333444", session_with_runs)
        assert run["run_id"] == "111222333444"


class TestResolveRunFuzzyMatch:
    """Test resolve_run with fuzzy prompt/name matching."""

    def test_unique_prompt_match(self, session_with_runs):
        run = resolve_run("ashby", session_with_runs)
        assert run["run_id"] == "abc123def456"

    def test_no_match_raises(self, session_with_runs):
        with pytest.raises(click.ClickException, match="No run matching"):
            resolve_run("nonexistent_xyz", session_with_runs)

    def test_no_match_error_message_includes_identifier(self, session_with_runs):
        with pytest.raises(click.ClickException, match="zzzznotfound"):
            resolve_run("zzzznotfound", session_with_runs)

    def test_empty_history_raises(self, empty_session):
        with pytest.raises(click.ClickException, match="No run matching"):
            resolve_run("anything", empty_session)

    def test_case_insensitive_match(self, session_with_runs):
        run = resolve_run("ASHBY", session_with_runs)
        assert run["run_id"] == "abc123def456"

    def test_partial_run_id_match(self, session_with_runs):
        """Partial run_id substring should match via fuzzy search."""
        run = resolve_run("abc123", session_with_runs)
        assert run["run_id"] == "abc123def456"

    def test_multiple_matches_shows_picker(self, session_with_runs):
        """When multiple runs match, questionary picker is shown."""
        # "api" appears in all three prompts
        with patch("questionary.Choice", side_effect=lambda **kw: kw):
            with patch("questionary.select") as mock_select:
                mock_select.return_value.ask.return_value = session_with_runs.history[0]
                run = resolve_run("api", session_with_runs)
                mock_select.assert_called_once()
                assert run is not None

    def test_multiple_matches_user_cancels(self, session_with_runs):
        """When user cancels the picker, click.Abort is raised."""
        with patch("questionary.Choice", side_effect=lambda **kw: kw):
            with patch("questionary.select") as mock_select:
                mock_select.return_value.ask.return_value = None
                with pytest.raises(click.Abort):
                    resolve_run("api", session_with_runs)

    def test_matches_folder_name_from_paths(self, tmp_path):
        """Matches against folder name derived from paths.script_path."""
        history_path = tmp_path / "history.json"
        sm = SessionManager(history_path)
        sm.add_run("aaa111bbb222", "some generic prompt", paths={"script_path": "/scripts/aaa111bbb222/ashby_jobs_api/api_client.py"})
        # "ashby_jobs" should match the folder name in the path
        run = resolve_run("ashby_jobs", sm)
        assert run["run_id"] == "aaa111bbb222"

    def test_match_against_prompt_substring(self, tmp_path):
        """Matches substring within prompt text."""
        history_path = tmp_path / "history.json"
        sm = SessionManager(history_path)
        sm.add_run("xyz123", "go to stripe.com and reverse engineer the billing api")
        run = resolve_run("stripe", sm)
        assert run["run_id"] == "xyz123"

    def test_match_is_case_insensitive_on_prompt(self, tmp_path):
        """Case-insensitive matching on prompt content."""
        history_path = tmp_path / "history.json"
        sm = SessionManager(history_path)
        sm.add_run("xyz123", "Go to GitHub.com and capture API")
        run = resolve_run("github", sm)
        assert run["run_id"] == "xyz123"


# ---------------------------------------------------------------------------
# discover_scripts tests
# ---------------------------------------------------------------------------

class TestDiscoverScripts:
    """Test discover_scripts function."""

    def test_finds_py_files(self, scripts_dir, tmp_path):
        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            scripts = discover_scripts("abc123def456")
        names = [s.name for s in scripts]
        assert "api_client.py" in names
        assert "example_usage.py" in names

    def test_excludes_non_py(self, scripts_dir, tmp_path):
        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            scripts = discover_scripts("abc123def456")
        names = [s.name for s in scripts]
        assert "README.md" not in names
        assert "requirements.txt" not in names

    def test_excludes_init(self, scripts_dir, tmp_path):
        (scripts_dir / "__init__.py").write_text("")
        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            scripts = discover_scripts("abc123def456")
        names = [s.name for s in scripts]
        assert "__init__.py" not in names

    def test_excludes_venv_files(self, scripts_dir, tmp_path):
        venv = scripts_dir / ".venv"
        venv.mkdir()
        (venv / "some_script.py").write_text("")
        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            scripts = discover_scripts("abc123def456")
        for s in scripts:
            assert ".venv" not in str(s)

    def test_empty_dir_returns_empty(self, scripts_dir_empty, tmp_path):
        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            scripts = discover_scripts("abc123def456")
        assert scripts == []

    def test_nonexistent_dir_returns_empty(self, tmp_path):
        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            scripts = discover_scripts("doesnotexist999")
        assert scripts == []

    def test_sorted_by_name(self, scripts_dir, tmp_path):
        (scripts_dir / "zzz_last.py").write_text("")
        (scripts_dir / "aaa_first.py").write_text("")
        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            scripts = discover_scripts("abc123def456")
        names = [s.name for s in scripts]
        assert names == sorted(names)

    def test_custom_output_dir(self, tmp_path):
        custom = tmp_path / "custom_out"
        d = custom / "scripts" / "run1"
        d.mkdir(parents=True)
        (d / "main.py").write_text("print('hi')")
        scripts = discover_scripts("run1", output_dir=str(custom))
        assert len(scripts) == 1
        assert scripts[0].name == "main.py"

    def test_single_script(self, scripts_dir_single, tmp_path):
        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            scripts = discover_scripts("abc123def456")
        assert len(scripts) == 1
        assert scripts[0].name == "api_client.py"

    def test_pycache_dir_contents_excluded(self, scripts_dir, tmp_path):
        cache = scripts_dir / "__pycache__"
        cache.mkdir()
        (cache / "module.cpython-313.pyc").write_text("")
        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            scripts = discover_scripts("abc123def456")
        for s in scripts:
            assert "__pycache__" not in str(s)

    def test_empty_run_id_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            discover_scripts("")

    def test_invalid_run_id_raises(self):
        with pytest.raises(ValueError, match="Invalid run_id"):
            discover_scripts("../../../etc")

    def test_too_long_run_id_raises(self):
        with pytest.raises(ValueError, match="too long"):
            discover_scripts("a" * 65)

    def test_finds_all_language_extensions(self, scripts_dir_empty, tmp_path):
        for name in [
            "api_client.py", "api_client.js", "api_client.ts", "api_client.go",
            "api_client.java", "api_client.cs", "api_client.php",
            "api_client.rb", "api_client.c", "api_client.psm1",
        ]:
            (scripts_dir_empty / name).write_text("")
        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            scripts = discover_scripts("abc123def456")
        assert len(scripts) == 10

    def test_excludes_vendored_cjson(self, scripts_dir_empty, tmp_path):
        (scripts_dir_empty / "api_client.c").write_text("")
        (scripts_dir_empty / "cJSON.c").write_text("")
        (scripts_dir_empty / "cJSON.h").write_text("")
        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            scripts = discover_scripts("abc123def456")
        assert [s.name for s in scripts] == ["api_client.c"]

    def test_excludes_build_dirs(self, scripts_dir_empty, tmp_path):
        (scripts_dir_empty / "api_client.cs").write_text("")
        for d in ["node_modules", "bin", "obj", "target"]:
            sub = scripts_dir_empty / d
            sub.mkdir()
            (sub / "generated.cs").write_text("")
        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            scripts = discover_scripts("abc123def456")
        assert [s.name for s in scripts] == ["api_client.cs"]

    def test_output_dir_under_build_dir_name_still_discovers(self, tmp_path):
        """A custom output_dir whose *parent* path contains a build-dir name
        (e.g. /tmp/target/...) must not exclude the run's scripts."""
        out = tmp_path / "target" / "myout"
        d = out / "scripts" / "run1"
        d.mkdir(parents=True)
        (d / "api_client.go").write_text("")
        scripts = discover_scripts("run1", output_dir=str(out))
        assert [s.name for s in scripts] == ["api_client.go"]

    def test_excludes_non_script_support_files(self, scripts_dir_empty, tmp_path):
        (scripts_dir_empty / "api_client.java").write_text("")
        (scripts_dir_empty / "pom.xml").write_text("")
        (scripts_dir_empty / "go.mod").write_text("")
        (scripts_dir_empty / "ApiClient.csproj").write_text("")
        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            scripts = discover_scripts("abc123def456")
        assert [s.name for s in scripts] == ["api_client.java"]


class TestDiscoverScriptsRunMetadata:
    """Test discover_scripts with run_metadata (stored path) fallback."""

    def test_uses_stored_path_from_metadata(self, tmp_path):
        """Prefers the stored script_path from run metadata over output_dir."""
        stored_dir = tmp_path / "old_output" / "scripts" / "run1"
        stored_dir.mkdir(parents=True)
        (stored_dir / "api_client.py").write_text("print('stored')")

        metadata = {"paths": {"script_path": str(stored_dir / "api_client.py")}}
        # output_dir points somewhere else entirely
        scripts = discover_scripts("run1", output_dir=str(tmp_path / "new_output"), run_metadata=metadata)
        assert len(scripts) == 1
        assert scripts[0].parent == stored_dir

    def test_falls_back_to_output_dir_when_stored_missing(self, tmp_path):
        """Falls back to output_dir when stored path doesn't exist."""
        fallback_dir = tmp_path / "scripts" / "run1"
        fallback_dir.mkdir(parents=True)
        (fallback_dir / "api_client.py").write_text("print('fallback')")

        metadata = {"paths": {"script_path": "/nonexistent/path/api_client.py"}}
        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            scripts = discover_scripts("run1", run_metadata=metadata)
        assert len(scripts) == 1

    def test_falls_back_when_no_metadata(self, scripts_dir, tmp_path):
        """Works without run_metadata (backwards compatible)."""
        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            scripts = discover_scripts("abc123def456", run_metadata=None)
        assert len(scripts) >= 1


# ---------------------------------------------------------------------------
# CLI `run` command integration tests (using Click's CliRunner)
# ---------------------------------------------------------------------------

@pytest.fixture
def cli_runner():
    return CliRunner()


@pytest.fixture
def mock_cli_env(tmp_path, session_with_runs):
    """Patch the module-level globals in cli.py for testing."""
    scripts_dir = tmp_path / "scripts" / "abc123def456"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "api_client.py").write_text("import sys; print('args:', sys.argv[1:])")
    (scripts_dir / "example_usage.py").write_text("print('example')")

    # Single-script run
    scripts_dir2 = tmp_path / "scripts" / "def789ghi012"
    scripts_dir2.mkdir(parents=True)
    (scripts_dir2 / "api_client.py").write_text("print('hubspot client')")

    # Empty run (no .py files)
    scripts_dir3 = tmp_path / "scripts" / "111222333444"
    scripts_dir3.mkdir(parents=True)

    patches = [
        patch("reverse_api.cli.session_manager", session_with_runs),
        patch("reverse_api.cli.config_manager", MagicMock(get=MagicMock(return_value=None))),
        patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path),
    ]
    for p in patches:
        p.start()
    yield tmp_path, session_with_runs
    for p in patches:
        p.stop()


class TestRunCommandHelp:
    """Test --help and basic CLI parsing."""

    def test_help_output(self, cli_runner):
        from reverse_api.cli import main
        result = cli_runner.invoke(main, ["run", "--help"])
        assert result.exit_code == 0
        assert "IDENTIFIER" in result.output
        assert "--ls" in result.output
        assert "--file" in result.output

    def test_help_shows_examples(self, cli_runner):
        from reverse_api.cli import main
        result = cli_runner.invoke(main, ["run", "--help"])
        assert "reverse-api-engineer run" in result.output


class TestRunCommandLs:
    """Test --ls flag."""

    def test_ls_shows_scripts(self, cli_runner, mock_cli_env):
        from reverse_api.cli import main
        result = cli_runner.invoke(main, ["run", "abc123def456", "--ls"])
        assert result.exit_code == 0
        assert "api_client.py" in result.output
        assert "example_usage.py" in result.output

    def test_ls_shows_file_sizes(self, cli_runner, mock_cli_env):
        from reverse_api.cli import main
        result = cli_runner.invoke(main, ["run", "abc123def456", "--ls"])
        assert "Size" in result.output
        assert "Modified" in result.output
        assert "B" in result.output

    def test_ls_no_scripts_error(self, cli_runner, mock_cli_env):
        from reverse_api.cli import main
        result = cli_runner.invoke(main, ["run", "111222333444", "--ls"])
        assert result.exit_code == 1
        assert "No runnable scripts" in result.output

    def test_ls_with_fuzzy_name(self, cli_runner, mock_cli_env):
        from reverse_api.cli import main
        result = cli_runner.invoke(main, ["run", "ashby", "--ls"])
        assert result.exit_code == 0
        assert "api_client.py" in result.output

    def test_ls_does_not_execute(self, cli_runner, mock_cli_env):
        from reverse_api.cli import main
        with patch("subprocess.run") as mock_sub:
            result = cli_runner.invoke(main, ["run", "abc123def456", "--ls"])
        mock_sub.assert_not_called()


class TestRunCommandFileFlag:
    """Test --file flag."""

    def test_file_flag_selects_script(self, cli_runner, mock_cli_env):
        from reverse_api.cli import main
        with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")) as mock_sub:
            result = cli_runner.invoke(main, ["run", "abc123def456", "--file", "example_usage.py"])
        assert mock_sub.called
        call_args = mock_sub.call_args[0][0]
        assert "example_usage.py" in str(call_args[1])

    def test_file_flag_nonexistent_file(self, cli_runner, mock_cli_env):
        from reverse_api.cli import main
        result = cli_runner.invoke(main, ["run", "abc123def456", "--file", "nope.py"])
        assert result.exit_code != 0
        assert "nope.py" in result.output
        assert "Available" in result.output

    def test_file_flag_lists_available_on_error(self, cli_runner, mock_cli_env):
        from reverse_api.cli import main
        result = cli_runner.invoke(main, ["run", "abc123def456", "--file", "missing.py"])
        assert "api_client.py" in result.output
        assert "example_usage.py" in result.output


class TestRunCommandExecution:
    """Test actual script execution."""

    def test_single_script_auto_selected(self, cli_runner, mock_cli_env):
        from reverse_api.cli import main
        with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")) as mock_sub:
            result = cli_runner.invoke(main, ["run", "def789ghi012"])
        assert mock_sub.called
        call_args = mock_sub.call_args[0][0]
        assert "api_client.py" in str(call_args[1])

    def test_args_passthrough(self, cli_runner, mock_cli_env):
        from reverse_api.cli import main
        with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")) as mock_sub:
            result = cli_runner.invoke(main, ["run", "def789ghi012", "--", "--org", "acme", "--limit", "10"])
        call_args = mock_sub.call_args[0][0]
        assert "--org" in call_args
        assert "acme" in call_args
        assert "--limit" in call_args
        assert "10" in call_args

    def test_exit_code_forwarded(self, cli_runner, mock_cli_env):
        from reverse_api.cli import main
        with patch("subprocess.run", return_value=MagicMock(returncode=42, stdout="", stderr="err")):
            result = cli_runner.invoke(main, ["run", "def789ghi012"])
        assert result.exit_code == 42

    def test_exit_code_zero_on_success(self, cli_runner, mock_cli_env):
        from reverse_api.cli import main
        with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="ok", stderr="")):
            result = cli_runner.invoke(main, ["run", "def789ghi012"])
        assert result.exit_code == 0

    def test_multiple_scripts_shows_picker(self, cli_runner, mock_cli_env):
        from reverse_api.cli import main
        tmp_path = mock_cli_env[0]
        script_path = tmp_path / "scripts" / "abc123def456" / "api_client.py"
        with patch("questionary.Choice", side_effect=lambda **kw: kw):
            with patch("questionary.select") as mock_select:
                mock_select.return_value.ask.return_value = script_path
                with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")):
                    result = cli_runner.invoke(main, ["run", "abc123def456"])
                mock_select.assert_called_once()

    def test_multiple_scripts_user_cancels_picker(self, cli_runner, mock_cli_env):
        from reverse_api.cli import main
        with patch("questionary.Choice", side_effect=lambda **kw: kw):
            with patch("questionary.select") as mock_select:
                mock_select.return_value.ask.return_value = None
                result = cli_runner.invoke(main, ["run", "abc123def456"])
        assert result.exit_code != 0


class TestRunCommandNoScripts:
    """Test error handling when no scripts exist."""

    def test_no_scripts_shows_error(self, cli_runner, mock_cli_env):
        from reverse_api.cli import main
        result = cli_runner.invoke(main, ["run", "111222333444"])
        assert result.exit_code == 1
        assert "No runnable scripts" in result.output

    def test_no_scripts_shows_prompt_preview(self, cli_runner, mock_cli_env):
        from reverse_api.cli import main
        result = cli_runner.invoke(main, ["run", "111222333444"])
        assert "browserbase" in result.output

    def test_no_matching_run(self, cli_runner, mock_cli_env):
        from reverse_api.cli import main
        result = cli_runner.invoke(main, ["run", "totallynonexistent"])
        assert result.exit_code != 0
        assert "No run matching" in result.output


class TestRunCommandSharedVenv:
    """Test shared venv and dependency management."""

    def test_creates_shared_venv_on_first_run(self, cli_runner, mock_cli_env):
        from reverse_api.cli import main
        ok = MagicMock(returncode=0, stdout="", stderr="")
        with patch("subprocess.run", return_value=ok) as mock_sub:
            result = cli_runner.invoke(main, ["run", "def789ghi012"])

        # Should have: venv create, pip install requests, script run = 3 calls
        assert mock_sub.call_count == 3
        # First call: create venv
        assert "venv" in mock_sub.call_args_list[0][0][0]
        # Second call: pip install requests
        pip_args = mock_sub.call_args_list[1][0][0]
        assert "requests" in pip_args
        # Third call: script runs with venv python
        assert ".venv" in str(mock_sub.call_args_list[2][0][0][0])

    def test_skips_venv_creation_when_exists(self, cli_runner, mock_cli_env):
        from reverse_api.cli import main
        tmp_path = mock_cli_env[0]
        # Pre-create shared venv
        venv = tmp_path / ".venv"
        venv.mkdir()
        (venv / "bin").mkdir()
        (venv / "bin" / "python").write_text("#!/bin/sh")
        (venv / "bin" / "pip").write_text("#!/bin/sh")

        ok = MagicMock(returncode=0, stdout="", stderr="")
        with patch("subprocess.run", return_value=ok) as mock_sub:
            result = cli_runner.invoke(main, ["run", "def789ghi012"])

        # Only the script execution call — no venv create, no pip install
        assert mock_sub.call_count == 1

    def test_installs_per_run_requirements(self, cli_runner, mock_cli_env):
        from reverse_api.cli import main
        tmp_path = mock_cli_env[0]
        # Pre-create shared venv
        venv = tmp_path / ".venv"
        venv.mkdir()
        (venv / "bin").mkdir()
        (venv / "bin" / "python").write_text("#!/bin/sh")
        (venv / "bin" / "pip").write_text("#!/bin/sh")

        req = tmp_path / "scripts" / "def789ghi012" / "requirements.txt"
        req.write_text("httpx>=0.25")

        ok = MagicMock(returncode=0, stdout="", stderr="")
        with patch("subprocess.run", return_value=ok) as mock_sub:
            result = cli_runner.invoke(main, ["run", "def789ghi012"])

        # pip install -r requirements.txt + script run = 2 calls
        assert mock_sub.call_count == 2
        pip_call = mock_sub.call_args_list[0][0][0]
        assert "-r" in pip_call
        assert str(req) in [str(a) for a in pip_call]

    def test_uses_venv_python_for_execution(self, cli_runner, mock_cli_env):
        from reverse_api.cli import main
        tmp_path = mock_cli_env[0]
        venv = tmp_path / ".venv"
        venv.mkdir()
        (venv / "bin").mkdir()
        (venv / "bin" / "python").write_text("#!/bin/sh")
        (venv / "bin" / "pip").write_text("#!/bin/sh")

        ok = MagicMock(returncode=0, stdout="", stderr="")
        with patch("subprocess.run", return_value=ok) as mock_sub:
            result = cli_runner.invoke(main, ["run", "def789ghi012"])

        script_call = mock_sub.call_args_list[-1][0][0]
        assert ".venv" in str(script_call[0])


class TestRunCommandImportRetry:
    """Test automatic retry on ModuleNotFoundError."""

    def test_offers_install_on_import_error(self, cli_runner, mock_cli_env):
        from reverse_api.cli import main
        tmp_path = mock_cli_env[0]
        venv = tmp_path / ".venv"
        venv.mkdir()
        (venv / "bin").mkdir()
        (venv / "bin" / "python").write_text("#!/bin/sh")
        (venv / "bin" / "pip").write_text("#!/bin/sh")

        # 1st call: run with captured stderr fails, 2nd: pip install, 3rd: retry succeeds
        first_run = MagicMock(returncode=1, stderr="ModuleNotFoundError: No module named 'pandas'")
        pip_ok = MagicMock(returncode=0, stdout="", stderr="")
        retry_ok = MagicMock(returncode=0)
        with patch("subprocess.run", side_effect=[first_run, pip_ok, retry_ok]):
            with patch("questionary.confirm") as mock_confirm:
                mock_confirm.return_value.ask.return_value = True
                result = cli_runner.invoke(main, ["run", "def789ghi012"])
        assert "Missing dependency: pandas" in result.output
        assert "Installed" in result.output

    def test_user_declines_install(self, cli_runner, mock_cli_env):
        from reverse_api.cli import main
        tmp_path = mock_cli_env[0]
        venv = tmp_path / ".venv"
        venv.mkdir()
        (venv / "bin").mkdir()
        (venv / "bin" / "python").write_text("#!/bin/sh")
        (venv / "bin" / "pip").write_text("#!/bin/sh")

        first_run = MagicMock(returncode=1, stderr="ModuleNotFoundError: No module named 'foo'")
        with patch("subprocess.run", side_effect=[first_run]):
            with patch("questionary.confirm") as mock_confirm:
                mock_confirm.return_value.ask.return_value = False
                result = cli_runner.invoke(main, ["run", "def789ghi012"])
        assert result.exit_code == 1

    def test_non_import_error_passes_through(self, cli_runner, mock_cli_env):
        from reverse_api.cli import main
        tmp_path = mock_cli_env[0]
        venv = tmp_path / ".venv"
        venv.mkdir()
        (venv / "bin").mkdir()
        (venv / "bin" / "python").write_text("#!/bin/sh")

        first_run = MagicMock(returncode=1, stderr="TypeError: something else broke")
        with patch("subprocess.run", side_effect=[first_run]):
            result = cli_runner.invoke(main, ["run", "def789ghi012"])
        assert result.exit_code == 1


class TestRunCommandOutputMessages:
    """Test user-facing output messages."""

    def test_shows_running_message(self, cli_runner, mock_cli_env):
        from reverse_api.cli import main
        tmp_path = mock_cli_env[0]
        venv = tmp_path / ".venv"
        venv.mkdir()
        (venv / "bin").mkdir()
        (venv / "bin" / "python").write_text("#!/bin/sh")

        with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")):
            result = cli_runner.invoke(main, ["run", "def789ghi012"])
        assert "scripts/def789ghi012" in result.output

    def test_shows_run_id_in_output(self, cli_runner, mock_cli_env):
        from reverse_api.cli import main
        tmp_path = mock_cli_env[0]
        venv = tmp_path / ".venv"
        venv.mkdir()
        (venv / "bin").mkdir()
        (venv / "bin" / "python").write_text("#!/bin/sh")

        with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")):
            result = cli_runner.invoke(main, ["run", "def789ghi012"])
        assert "def789ghi012" in result.output

    def test_shared_venv_setup_message(self, cli_runner, mock_cli_env):
        from reverse_api.cli import main
        with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")):
            result = cli_runner.invoke(main, ["run", "def789ghi012"])
        assert "Setting up shared venv" in result.output
        assert "Shared venv ready" in result.output


# ---------------------------------------------------------------------------
# _extract_missing_module
# ---------------------------------------------------------------------------

class TestExtractMissingModule:
    """Test _extract_missing_module validation against crafted error messages."""

    def test_plain_module_name(self):
        from reverse_api.cli import _extract_missing_module
        stderr = "ModuleNotFoundError: No module named 'requests'"
        assert _extract_missing_module(stderr) == "requests"

    def test_dotted_module_returns_top_level(self):
        from reverse_api.cli import _extract_missing_module
        stderr = "ModuleNotFoundError: No module named 'bs4.element'"
        assert _extract_missing_module(stderr) == "bs4"

    def test_no_match_returns_none(self):
        from reverse_api.cli import _extract_missing_module
        assert _extract_missing_module("SyntaxError: invalid syntax") is None

    def test_pip_option_injection_rejected(self):
        from reverse_api.cli import _extract_missing_module
        stderr = "ModuleNotFoundError: No module named '--index-url=https://evil.example'"
        assert _extract_missing_module(stderr) is None

    def test_spaces_rejected(self):
        from reverse_api.cli import _extract_missing_module
        stderr = "ModuleNotFoundError: No module named '-q evil-package'"
        assert _extract_missing_module(stderr) is None

    def test_hyphen_rejected(self):
        from reverse_api.cli import _extract_missing_module
        stderr = "ModuleNotFoundError: No module named 'evil-package'"
        assert _extract_missing_module(stderr) is None

    def test_too_long_rejected(self):
        from reverse_api.cli import _extract_missing_module
        stderr = f"ModuleNotFoundError: No module named '{'a' * 65}'"
        assert _extract_missing_module(stderr) is None

    def test_trailing_newline_rejected(self):
        from reverse_api.cli import _extract_missing_module
        stderr = "ModuleNotFoundError: No module named 'requests\n'"
        assert _extract_missing_module(stderr) is None


# ---------------------------------------------------------------------------
# build_script_commands tests
# ---------------------------------------------------------------------------

class TestBuildScriptCommands:
    """Test per-language command dispatch for the run subcommand."""

    def test_javascript(self, tmp_path):
        from reverse_api.utils import build_script_commands
        script = tmp_path / "api_client.js"
        steps, tool = build_script_commands(script)
        assert steps == [["node", str(script)]]
        assert tool == "node"

    def test_typescript(self, tmp_path):
        from reverse_api.utils import build_script_commands
        script = tmp_path / "api_client.ts"
        steps, tool = build_script_commands(script, ("--flag",))
        assert steps == [["npx", "tsx", str(script), "--flag"]]
        assert tool == "npx"

    def test_go(self, tmp_path):
        from reverse_api.utils import build_script_commands
        script = tmp_path / "api_client.go"
        steps, tool = build_script_commands(script)
        assert steps == [["go", "run", str(script)]]
        assert tool == "go"

    def test_java(self, tmp_path):
        from reverse_api.utils import build_script_commands
        script = tmp_path / "api_client.java"
        steps, tool = build_script_commands(script)
        assert steps == [["mvn", "-q", "-f", str(tmp_path / "pom.xml"), "compile", "exec:exec"]]
        assert tool == "mvn"

    def test_java_rejects_script_args(self, tmp_path):
        from reverse_api.utils import build_script_commands
        with pytest.raises(ValueError, match="not supported for Java"):
            build_script_commands(tmp_path / "api_client.java", ("--x",))

    def test_csharp_passes_args_after_separator(self, tmp_path):
        from reverse_api.utils import build_script_commands
        script = tmp_path / "api_client.cs"
        steps, tool = build_script_commands(script, ("--x",))
        assert steps == [["dotnet", "run", "--project", str(tmp_path / "ApiClient.csproj"), "--", "--x"]]
        assert tool == "dotnet"

    def test_php(self, tmp_path):
        from reverse_api.utils import build_script_commands
        script = tmp_path / "api_client.php"
        steps, tool = build_script_commands(script)
        assert steps == [["php", str(script)]]
        assert tool == "php"

    def test_ruby(self, tmp_path):
        from reverse_api.utils import build_script_commands
        script = tmp_path / "api_client.rb"
        steps, tool = build_script_commands(script)
        assert steps == [["ruby", str(script)]]
        assert tool == "ruby"

    def test_c_compiles_then_runs_with_vendored_cjson(self, tmp_path):
        from reverse_api.utils import build_script_commands
        script = tmp_path / "api_client.c"
        (tmp_path / "cJSON.c").write_text("")
        steps, tool = build_script_commands(script, ("--x",))
        binary = str(tmp_path / "api_client")
        assert steps == [
            ["cc", str(script), str(tmp_path / "cJSON.c"), "-lcurl", "-o", binary],
            [binary, "--x"],
        ]
        assert tool == "cc"

    def test_c_without_cjson(self, tmp_path):
        from reverse_api.utils import build_script_commands
        script = tmp_path / "api_client.c"
        steps, _ = build_script_commands(script)
        assert steps[0] == ["cc", str(script), "-lcurl", "-o", str(tmp_path / "api_client")]

    def test_powershell(self, tmp_path):
        from reverse_api.utils import build_script_commands
        script = tmp_path / "api_client.psm1"
        steps, tool = build_script_commands(script, ("--flag",))
        example = str(tmp_path / "Example.ps1")
        assert steps == [["pwsh", "-NoProfile", "-File", example, "--flag"]]
        assert tool == "pwsh"

    def test_unsupported_extension_raises(self, tmp_path):
        from reverse_api.utils import build_script_commands
        with pytest.raises(ValueError, match="unsupported script type"):
            build_script_commands(tmp_path / "api_client.xyz")

    def test_relative_script_path_resolved_to_absolute(self, tmp_path, monkeypatch):
        """Relative script paths (from a relative output_dir) must become
        absolute in the argv: callers run with cwd=script.parent, which would
        otherwise re-anchor the relative path and fail to start."""
        from reverse_api.utils import build_script_commands
        monkeypatch.chdir(tmp_path)
        d = Path("out") / "scripts" / "run1"
        d.mkdir(parents=True)
        script = d / "api_client.js"
        steps, _ = build_script_commands(script)
        assert steps == [["node", str(tmp_path.resolve() / d / "api_client.js")]]

    def test_paths_with_spaces_stay_intact_in_argv(self, tmp_path):
        """argv lists are passed to subprocess without a shell, so spaced
        paths must survive as single arguments — no quoting layer involved."""
        from reverse_api.utils import build_script_commands
        d = tmp_path / "my scripts"
        d.mkdir()
        script = d / "api_client.php"
        steps, _ = build_script_commands(script)
        assert steps == [["php", str(script)]]

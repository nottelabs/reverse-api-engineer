"""Tests for base_engineer.py - BaseEngineer abstract class."""

import shlex
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from reverse_api.base_engineer import REPORT_CLIENT_VERIFIED_INSTRUCTION, BaseEngineer


class ConcreteEngineer(BaseEngineer):
    """Concrete implementation for testing."""

    async def analyze_and_generate(self) -> dict[str, Any] | None:
        return {"test": True}


class TestBaseEngineerInit:
    """Test BaseEngineer initialization."""

    def test_basic_init(self, tmp_path):
        """Basic initialization sets all attributes."""
        har_path = tmp_path / "test.har"
        har_path.touch()

        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
            with patch("reverse_api.base_engineer.MessageStore"):
                engineer = ConcreteEngineer(
                    run_id="test123",
                    har_path=har_path,
                    prompt="test prompt",
                    model="claude-sonnet-4-6",
                    output_dir=str(tmp_path),
                )
                assert engineer.run_id == "test123"
                assert engineer.har_path == har_path
                assert engineer.prompt == "test prompt"
                assert engineer.model == "claude-sonnet-4-6"
                assert engineer.output_mode == "client"
                assert engineer.is_fresh is False
                assert engineer.output_language == "python"

    def test_docs_mode(self, tmp_path):
        """Docs mode uses docs directory."""
        har_path = tmp_path / "test.har"
        har_path.touch()

        with patch("reverse_api.base_engineer.get_docs_dir", return_value=tmp_path / "docs") as mock_docs:
            with patch("reverse_api.base_engineer.MessageStore"):
                engineer = ConcreteEngineer(
                    run_id="test123",
                    har_path=har_path,
                    prompt="test prompt",
                    output_mode="docs",
                    output_dir=str(tmp_path),
                )
                mock_docs.assert_called_once()
                assert engineer.output_mode == "docs"

    def test_existing_client_language_preserved_for_iterative_runs(self, tmp_path):
        """Existing client language overrides the configured output language."""
        har_path = tmp_path / "test.har"
        har_path.touch()
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        client_path = scripts_dir / "api_client.ts"
        client_path.write_text("export {};\n")

        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=scripts_dir):
            with patch("reverse_api.base_engineer.MessageStore"):
                with patch("reverse_api.base_engineer.SessionManager") as mock_session_manager:
                    mock_session_manager.return_value.get_run.return_value = None
                    engineer = ConcreteEngineer(
                        run_id="test123",
                        har_path=har_path,
                        prompt="test prompt",
                        output_language="python",
                        output_dir=str(tmp_path),
                    )

        assert engineer.output_language == "typescript"
        assert engineer.existing_client_path == client_path

    def test_existing_client_language_uses_recorded_script_path(self, tmp_path):
        """Recorded script path takes precedence over config and stale files."""
        har_path = tmp_path / "test.har"
        har_path.touch()
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        python_client = scripts_dir / "api_client.py"
        python_client.write_text("print('python')\n")
        typescript_client = scripts_dir / "api_client.ts"
        typescript_client.write_text("export {};\n")

        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=scripts_dir):
            with patch("reverse_api.base_engineer.MessageStore"):
                with patch("reverse_api.base_engineer.SessionManager") as mock_session_manager:
                    mock_session_manager.return_value.get_run.return_value = {
                        "paths": {"script_path": str(typescript_client)}
                    }
                    engineer = ConcreteEngineer(
                        run_id="test123",
                        har_path=har_path,
                        prompt="test prompt",
                        output_language="python",
                        output_dir=str(tmp_path),
                    )

        assert engineer.output_language == "typescript"
        assert engineer.existing_client_path == typescript_client

    def test_existing_client_language_falls_back_to_newest_file(self, tmp_path):
        """Newest existing client wins when no recorded script path is available."""
        har_path = tmp_path / "test.har"
        har_path.touch()
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        python_client = scripts_dir / "api_client.py"
        python_client.write_text("print('python')\n")
        typescript_client = scripts_dir / "api_client.ts"
        typescript_client.write_text("export {};\n")
        typescript_client.touch()

        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=scripts_dir):
            with patch("reverse_api.base_engineer.MessageStore"):
                with patch("reverse_api.base_engineer.SessionManager") as mock_session_manager:
                    mock_session_manager.return_value.get_run.return_value = None
                    engineer = ConcreteEngineer(
                        run_id="test123",
                        har_path=har_path,
                        prompt="test prompt",
                        output_language="python",
                        output_dir=str(tmp_path),
                    )

        assert engineer.output_language == "typescript"
        assert engineer.existing_client_path == typescript_client

    def test_fresh_runs_can_switch_output_language(self, tmp_path):
        """Fresh runs ignore existing client language and honor the requested one."""
        har_path = tmp_path / "test.har"
        har_path.touch()
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "api_client.ts").write_text("export {};\n")

        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=scripts_dir):
            with patch("reverse_api.base_engineer.MessageStore"):
                engineer = ConcreteEngineer(
                    run_id="test123",
                    har_path=har_path,
                    prompt="test prompt",
                    output_language="python",
                    is_fresh=True,
                    output_dir=str(tmp_path),
                )

        assert engineer.output_language == "python"
        assert engineer.existing_client_path is None


class TestBaseEngineerHelpers:
    """Test helper methods."""

    def _make_engineer(self, tmp_path, **kwargs):
        har_path = tmp_path / "test.har"
        har_path.touch()
        defaults = {
            "run_id": "test123",
            "har_path": har_path,
            "prompt": "test prompt",
            "output_dir": str(tmp_path),
        }
        defaults.update(kwargs)
        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
            with patch("reverse_api.base_engineer.get_docs_dir", return_value=tmp_path / "docs"):
                with patch("reverse_api.base_engineer.MessageStore"):
                    return ConcreteEngineer(**defaults)

    def test_get_output_extension_python(self, tmp_path):
        """Python extension."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert eng._get_output_extension() == ".py"

    def test_get_output_extension_javascript(self, tmp_path):
        """JavaScript extension."""
        eng = self._make_engineer(tmp_path, output_language="javascript")
        assert eng._get_output_extension() == ".js"

    def test_get_output_extension_typescript(self, tmp_path):
        """TypeScript extension."""
        eng = self._make_engineer(tmp_path, output_language="typescript")
        assert eng._get_output_extension() == ".ts"

    def test_get_output_extension_go(self, tmp_path):
        """Go extension."""
        eng = self._make_engineer(tmp_path, output_language="go")
        assert eng._get_output_extension() == ".go"
    def test_get_output_extension_java(self, tmp_path):
        """Java extension."""
        eng = self._make_engineer(tmp_path, output_language="java")
        assert eng._get_output_extension() == ".java"
    def test_get_output_extension_csharp(self, tmp_path):
        """C# extension."""
        eng = self._make_engineer(tmp_path, output_language="csharp")
        assert eng._get_output_extension() == ".cs"
    def test_get_output_extension_php(self, tmp_path):
        """PHP extension."""
        eng = self._make_engineer(tmp_path, output_language="php")
        assert eng._get_output_extension() == ".php"
    def test_get_output_extension_ruby(self, tmp_path):
        """Ruby extension."""
        eng = self._make_engineer(tmp_path, output_language="ruby")
        assert eng._get_output_extension() == ".rb"
    def test_get_output_extension_c(self, tmp_path):
        """C extension."""
        eng = self._make_engineer(tmp_path, output_language="c")
        assert eng._get_output_extension() == ".c"
    def test_get_output_extension_powershell(self, tmp_path):
        """PowerShell extension."""
        eng = self._make_engineer(tmp_path, output_language="powershell")
        assert eng._get_output_extension() == ".psm1"

    def test_get_output_extension_unknown(self, tmp_path):
        """Unknown language defaults to .py."""
        eng = self._make_engineer(tmp_path, output_language="rust")
        assert eng._get_output_extension() == ".py"

    def test_get_client_filename_python(self, tmp_path):
        """Client filename for Python."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert eng._get_client_filename() == "api_client.py"

    def test_get_client_filename_powershell(self, tmp_path):
        """Client filename for PowerShell."""
        eng = self._make_engineer(tmp_path, output_language="powershell")
        assert eng._get_client_filename() == "api_client.psm1"

    def test_get_client_filename_docs(self, tmp_path):
        """Client filename for docs mode."""
        eng = self._make_engineer(tmp_path, output_mode="docs")
        assert eng._get_client_filename() == "openapi.json"

    def test_get_run_command_python(self, tmp_path):
        """Run command for Python."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert eng._get_run_command() == "python api_client.py"

    def test_get_run_command_javascript(self, tmp_path):
        """Run command for JavaScript."""
        eng = self._make_engineer(tmp_path, output_language="javascript")
        assert eng._get_run_command() == "node api_client.js"

    def test_get_run_command_typescript(self, tmp_path):
        """Run command for TypeScript."""
        eng = self._make_engineer(tmp_path, output_language="typescript")
        assert eng._get_run_command() == "npx tsx api_client.ts"

    def test_get_run_command_go(self, tmp_path):
        """Run command for Go."""
        eng = self._make_engineer(tmp_path, output_language="go")
        assert eng._get_run_command() == "go run api_client.go"
    def test_get_run_command_java(self, tmp_path):
        """Run command for Java points -f at this run's own (resolved,
        shell-quoted) pom.xml, not a bare relative path — the agent's cwd is
        scripts_dir.parent.parent (see analyze_and_generate), and unlike
        python/node/npx, Maven hard-fails with no upward search if invoked
        from a directory with no pom.xml."""
        eng = self._make_engineer(tmp_path, output_language="java")
        expected_pom = shlex.quote(str(eng.scripts_dir.resolve() / "pom.xml"))
        assert eng._get_run_command() == f"mvn -q -f {expected_pom} compile exec:exec"

    def test_get_run_command_java_quotes_metacharacters(self, tmp_path):
        """A scripts_dir containing shell metacharacters must round-trip
        back to the literal path, not be left open to $()/backtick
        expansion — what the naive f'"{path}"' approach got wrong."""
        eng = self._make_engineer(tmp_path, output_language="java")
        eng.scripts_dir = Path("/tmp/weird$(rm -rf ~) dir")
        tokens = shlex.split(eng._get_run_command())
        assert tokens[:2] == ["mvn", "-q"]
        assert tokens[3] == str(eng.scripts_dir.resolve() / "pom.xml")

    def test_get_run_command_java_resolves_relative_output_dir(self, tmp_path):
        """A relative scripts_dir must be resolved to an absolute path before
        being embedded in the command — otherwise, once the agent's cwd
        moves to scripts_dir.parent.parent, the same relative string gets
        re-interpreted from there and points at the wrong, doubly-nested
        location."""
        eng = self._make_engineer(tmp_path, output_language="java")
        eng.scripts_dir = Path("relative_output/scripts/run123")
        tokens = shlex.split(eng._get_run_command())
        pom_arg = tokens[3]
        assert Path(pom_arg).is_absolute()
        assert pom_arg == str(eng.scripts_dir.resolve() / "pom.xml")
    def test_get_run_command_csharp(self, tmp_path):
        """Run command for C# points --project at this run's own (resolved,
        shell-quoted) .csproj, not a bare `dotnet run` — the agent's cwd is
        scripts_dir.parent.parent (see analyze_and_generate), and dotnet
        only looks for a project file in the current directory."""
        eng = self._make_engineer(tmp_path, output_language="csharp")
        expected_csproj = shlex.quote(str(eng.scripts_dir.resolve() / "ApiClient.csproj"))
        assert eng._get_run_command() == f"dotnet run --project {expected_csproj}"

    def test_get_run_command_csharp_quotes_metacharacters(self, tmp_path):
        """A scripts_dir containing shell metacharacters must round-trip
        back to the literal path, not be left open to $()/backtick
        expansion — what the naive f'"{path}"' approach got wrong."""
        eng = self._make_engineer(tmp_path, output_language="csharp")
        eng.scripts_dir = Path("/tmp/weird$(rm -rf ~) dir")
        tokens = shlex.split(eng._get_run_command())
        assert tokens[:2] == ["dotnet", "run"]
        assert tokens[3] == str(eng.scripts_dir.resolve() / "ApiClient.csproj")

    def test_get_run_command_csharp_resolves_relative_output_dir(self, tmp_path):
        """A relative scripts_dir must be resolved to an absolute path before
        being embedded in the command — otherwise, once the agent's cwd
        moves to scripts_dir.parent.parent, the same relative string gets
        re-interpreted from there and points at the wrong, doubly-nested
        location."""
        eng = self._make_engineer(tmp_path, output_language="csharp")
        eng.scripts_dir = Path("relative_output/scripts/run123")
        tokens = shlex.split(eng._get_run_command())
        project_arg = tokens[3]
        assert Path(project_arg).is_absolute()
        assert project_arg == str(eng.scripts_dir.resolve() / "ApiClient.csproj")
    def test_get_run_command_php(self, tmp_path):
        """Run command for PHP uses the full, resolved, shell-quoted path,
        not a bare relative filename — the agent's cwd is scripts_dir.
        parent.parent (see analyze_and_generate), not scripts_dir where the
        script lives, and shlex.quote() (not manual double-quoting) is what
        actually neutralizes shell metacharacters in an arbitrary output_dir."""
        eng = self._make_engineer(tmp_path, output_language="php")
        expected_path = shlex.quote(str(eng.scripts_dir.resolve() / "api_client.php"))
        assert eng._get_run_command() == f"php {expected_path}"

    def test_get_run_command_php_quotes_metacharacters(self, tmp_path):
        """A scripts_dir containing shell metacharacters must round-trip
        back to the literal path when the shell tokenizes the command —
        not be left open to $()/backtick expansion, which is exactly what
        the naive f'"{path}"' approach got wrong (double quotes still allow
        command substitution inside them)."""
        eng = self._make_engineer(tmp_path, output_language="php")
        eng.scripts_dir = Path("/tmp/weird$(rm -rf ~) dir")
        command = eng._get_run_command()
        tokens = shlex.split(command)
        assert tokens[0] == "php"
        assert tokens[1] == str(eng.scripts_dir.resolve() / "api_client.php")

    def test_get_run_command_php_resolves_relative_output_dir(self, tmp_path):
        """A relative scripts_dir must be resolved to an absolute path before
        being embedded in the command — otherwise, once the agent's cwd
        moves to scripts_dir.parent.parent, the same relative string gets
        re-interpreted from there and points at the wrong, doubly-nested
        location."""
        eng = self._make_engineer(tmp_path, output_language="php")
        eng.scripts_dir = Path("relative_output/scripts/run123")
        tokens = shlex.split(eng._get_run_command())
        script_arg = tokens[1]
        assert Path(script_arg).is_absolute()
        assert script_arg == str(eng.scripts_dir.resolve() / "api_client.php")
    def test_get_run_command_ruby(self, tmp_path):
        """Run command for Ruby uses the full, resolved, shell-quoted path,
        not a bare relative filename — the agent's cwd is scripts_dir.
        parent.parent (see analyze_and_generate), not scripts_dir where the
        script lives."""
        eng = self._make_engineer(tmp_path, output_language="ruby")
        expected_path = shlex.quote(str(eng.scripts_dir.resolve() / "api_client.rb"))
        assert eng._get_run_command() == f"ruby {expected_path}"

    def test_get_run_command_ruby_quotes_metacharacters(self, tmp_path):
        """A scripts_dir containing shell metacharacters must round-trip
        back to the literal path, not be left open to $()/backtick
        expansion — what the naive f'"{path}"' approach got wrong."""
        eng = self._make_engineer(tmp_path, output_language="ruby")
        eng.scripts_dir = Path("/tmp/weird$(rm -rf ~) dir")
        tokens = shlex.split(eng._get_run_command())
        assert tokens[0] == "ruby"
        assert tokens[1] == str(eng.scripts_dir.resolve() / "api_client.rb")

    def test_get_run_command_ruby_resolves_relative_output_dir(self, tmp_path):
        """A relative scripts_dir must be resolved to an absolute path before
        being embedded in the command — otherwise, once the agent's cwd
        moves to scripts_dir.parent.parent, the same relative string gets
        re-interpreted from there and points at the wrong, doubly-nested
        location."""
        eng = self._make_engineer(tmp_path, output_language="ruby")
        eng.scripts_dir = Path("relative_output/scripts/run123")
        tokens = shlex.split(eng._get_run_command())
        script_arg = tokens[1]
        assert Path(script_arg).is_absolute()
        assert script_arg == str(eng.scripts_dir.resolve() / "api_client.rb")
    def test_get_run_command_c(self, tmp_path):
        """Run command for C compiles and runs as one step, using full,
        resolved, shell-quoted paths throughout — the agent's cwd is
        scripts_dir.parent.parent (see analyze_and_generate), not
        scripts_dir where the source, vendored cJSON, and compiled binary
        all actually live."""
        eng = self._make_engineer(tmp_path, output_language="c")
        resolved = eng.scripts_dir.resolve()
        source = shlex.quote(str(resolved / "api_client.c"))
        cjson = shlex.quote(str(resolved / "cJSON.c"))
        binary = shlex.quote(str(resolved / "api_client"))
        expected = f"cc {source} {cjson} -lcurl -o {binary} && {binary}"
        assert eng._get_run_command() == expected

    def test_get_run_command_c_quotes_metacharacters(self, tmp_path):
        """A scripts_dir containing shell metacharacters must round-trip
        back to the literal path for all three paths (source, cJSON,
        binary), not be left open to $()/backtick expansion — what the
        naive f'"{path}"' approach got wrong."""
        eng = self._make_engineer(tmp_path, output_language="c")
        eng.scripts_dir = Path("/tmp/weird$(rm -rf ~) dir")
        resolved = eng.scripts_dir.resolve()
        tokens = shlex.split(eng._get_run_command())
        assert tokens[:2] == ["cc", str(resolved / "api_client.c")]
        assert tokens[2] == str(resolved / "cJSON.c")
        assert tokens[3:6] == ["-lcurl", "-o", str(resolved / "api_client")]
        assert tokens[6] == "&&"
        assert tokens[7] == str(resolved / "api_client")

    def test_get_run_command_c_resolves_relative_output_dir(self, tmp_path):
        """A relative scripts_dir must be resolved to an absolute path for
        all three paths (source, cJSON, binary) before being embedded in
        the command — otherwise, once the agent's cwd moves to
        scripts_dir.parent.parent, the same relative string gets
        re-interpreted from there and points at the wrong, doubly-nested
        location."""
        eng = self._make_engineer(tmp_path, output_language="c")
        eng.scripts_dir = Path("relative_output/scripts/run123")
        resolved = eng.scripts_dir.resolve()
        tokens = shlex.split(eng._get_run_command())
        assert Path(tokens[1]).is_absolute()
        assert tokens[1] == str(resolved / "api_client.c")
        assert tokens[2] == str(resolved / "cJSON.c")
        assert tokens[5] == str(resolved / "api_client")

    def test_get_run_command_powershell(self, tmp_path):
        """Run command for PowerShell points -File at this run's own
        (resolved, shell-quoted) Example.ps1, not the module itself — the
        agent's cwd is scripts_dir.parent.parent (see analyze_and_generate),
        and api_client.psm1 isn't directly runnable, only importable."""
        eng = self._make_engineer(tmp_path, output_language="powershell")
        expected_example = shlex.quote(str(eng.scripts_dir.resolve() / "Example.ps1"))
        assert eng._get_run_command() == f"pwsh -NoProfile -File {expected_example}"

    def test_get_run_command_powershell_quotes_metacharacters(self, tmp_path):
        """A scripts_dir containing shell metacharacters must round-trip
        back to the literal path, not be left open to $()/backtick
        expansion — what the naive f'"{path}"' approach got wrong."""
        eng = self._make_engineer(tmp_path, output_language="powershell")
        eng.scripts_dir = Path("/tmp/weird$(rm -rf ~) dir")
        tokens = shlex.split(eng._get_run_command())
        assert tokens[:3] == ["pwsh", "-NoProfile", "-File"]
        assert tokens[3] == str(eng.scripts_dir.resolve() / "Example.ps1")

    def test_get_run_command_powershell_resolves_relative_output_dir(self, tmp_path):
        """A relative scripts_dir must be resolved to an absolute path before
        being embedded in the command — otherwise, once the agent's cwd
        moves to scripts_dir.parent.parent, the same relative string gets
        re-interpreted from there and points at the wrong, doubly-nested
        location."""
        eng = self._make_engineer(tmp_path, output_language="powershell")
        eng.scripts_dir = Path("relative_output/scripts/run123")
        tokens = shlex.split(eng._get_run_command())
        example_arg = tokens[3]
        assert Path(example_arg).is_absolute()
        assert example_arg == str(eng.scripts_dir.resolve() / "Example.ps1")

    def test_get_run_command_unknown(self, tmp_path):
        """Unknown language defaults to Python command."""
        eng = self._make_engineer(tmp_path, output_language="rust")
        assert eng._get_run_command() == "python api_client.py"

    def test_get_codegen_instructions_base_version_has_no_verification_instruction(self, tmp_path):
        """BaseEngineer's own version (shared by OpenCode/Copilot/Cursor,
        which don't subclass ClaudeEngineer) must NOT append
        REPORT_CLIENT_VERIFIED_INSTRUCTION — that tool only exists for the
        Claude Agent SDK path (see engineer.py's ClaudeEngineer override,
        the one place this actually gets appended, and its own test
        coverage in test_engineer.py). Regression flagged by automated
        review: an earlier version of this appended it here directly,
        which would have told every other backend's agent to call a tool
        that was never registered in its environment."""
        for language in ("python", "javascript", "typescript", "go", "java", "csharp", "php", "ruby", "c", "powershell"):
            eng = self._make_engineer(tmp_path, output_language=language, output_mode="client")
            assert REPORT_CLIENT_VERIFIED_INSTRUCTION not in eng._get_codegen_instructions(), language

    def test_quote_path_posix(self, monkeypatch):
        """POSIX platforms use shlex.quote (single quotes for spaces)."""
        from reverse_api import base_engineer as be

        monkeypatch.setattr(be.sys, "platform", "linux")
        from reverse_api.base_engineer import BaseEngineer

        assert BaseEngineer._quote_path("/tmp/my dir/pom.xml") == "'/tmp/my dir/pom.xml'"

    def test_quote_path_windows(self, monkeypatch):
        """Windows uses list2cmdline double-quoting that cmd.exe/PowerShell parse."""
        from reverse_api import base_engineer as be

        monkeypatch.setattr(be.sys, "platform", "win32")
        from reverse_api.base_engineer import BaseEngineer

        assert BaseEngineer._quote_path(r"C:\Users\John Smith\pom.xml") == '"C:\\Users\\John Smith\\pom.xml"'


class TestBaseEngineerBuildPrompt:
    """Test _build_analysis_prompt method."""

    def _make_engineer(self, tmp_path, **kwargs):
        har_path = tmp_path / "test.har"
        har_path.touch()
        defaults = {
            "run_id": "test123",
            "har_path": har_path,
            "prompt": "test prompt",
            "output_dir": str(tmp_path),
        }
        defaults.update(kwargs)
        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
            with patch("reverse_api.base_engineer.get_docs_dir", return_value=tmp_path / "docs"):
                with patch("reverse_api.base_engineer.MessageStore") as mock_ms:
                    mock_ms.return_value.messages_path = tmp_path / "messages" / "test.jsonl"
                    return ConcreteEngineer(**defaults)

    def test_python_prompt(self, tmp_path):
        """Python prompt includes Python-specific instructions."""
        eng = self._make_engineer(tmp_path, output_language="python")
        system_prompt, user_message = eng._build_prompts()
        assert "Python script" in system_prompt
        assert "requests" in system_prompt

    def test_javascript_prompt(self, tmp_path):
        """JavaScript prompt includes JS-specific instructions."""
        eng = self._make_engineer(tmp_path, output_language="javascript")
        system_prompt, user_message = eng._build_prompts()
        assert "JavaScript module" in system_prompt
        assert "fetch" in system_prompt

    def test_typescript_prompt(self, tmp_path):
        """TypeScript prompt includes TS-specific instructions."""
        eng = self._make_engineer(tmp_path, output_language="typescript")
        system_prompt, user_message = eng._build_prompts()
        assert "TypeScript module" in system_prompt
        assert "interfaces" in system_prompt

    def test_go_prompt(self, tmp_path):
        """Go prompt includes Go-specific instructions."""
        eng = self._make_engineer(tmp_path, output_language="go")
        system_prompt, user_message = eng._build_prompts()
        assert "Go program" in system_prompt
        assert "net/http" in system_prompt
    def test_java_prompt(self, tmp_path):
        """Java prompt includes Java-specific instructions."""
        eng = self._make_engineer(tmp_path, output_language="java")
        system_prompt, user_message = eng._build_prompts()
        assert "Java program" in system_prompt
    def test_csharp_prompt(self, tmp_path):
        """C# prompt includes C#-specific instructions."""
        eng = self._make_engineer(tmp_path, output_language="csharp")
        system_prompt, user_message = eng._build_prompts()
        assert "C# program" in system_prompt
        assert "HttpClient" in system_prompt
    def test_php_prompt(self, tmp_path):
        """PHP prompt includes PHP-specific instructions."""
        eng = self._make_engineer(tmp_path, output_language="php")
        system_prompt, user_message = eng._build_prompts()
        assert "PHP script" in system_prompt
        assert "curl" in system_prompt
    def test_ruby_prompt(self, tmp_path):
        """Ruby prompt includes Ruby-specific instructions."""
        eng = self._make_engineer(tmp_path, output_language="ruby")
        system_prompt, user_message = eng._build_prompts()
        assert "Ruby script" in system_prompt
        assert "net/http" in system_prompt
    def test_c_prompt(self, tmp_path):
        """C prompt includes C-specific instructions."""
        eng = self._make_engineer(tmp_path, output_language="c")
        system_prompt, user_message = eng._build_prompts()
        assert "C program" in system_prompt
        assert "libcurl" in system_prompt
    def test_powershell_prompt(self, tmp_path):
        """PowerShell prompt includes PowerShell-specific instructions."""
        eng = self._make_engineer(tmp_path, output_language="powershell")
        system_prompt, user_message = eng._build_prompts()
        assert "PowerShell module" in system_prompt
        assert "Invoke-RestMethod" in system_prompt

    def test_docs_prompt(self, tmp_path):
        """Docs mode prompt includes OpenAPI instructions."""
        eng = self._make_engineer(tmp_path, output_mode="docs")
        system_prompt, user_message = eng._build_prompts()
        assert "OpenAPI" in system_prompt

    def test_prompt_includes_har_path(self, tmp_path):
        """User message includes HAR file path."""
        eng = self._make_engineer(tmp_path)
        system_prompt, user_message = eng._build_prompts()
        assert str(eng.har_path) in user_message

    def test_prompt_includes_user_prompt(self, tmp_path):
        """User message includes user's original prompt."""
        eng = self._make_engineer(tmp_path, prompt="capture spotify api")
        system_prompt, user_message = eng._build_prompts()
        assert "capture spotify api" in user_message

    def test_prompt_includes_additional_instructions(self, tmp_path):
        """Additional instructions are in user message."""
        eng = self._make_engineer(tmp_path, additional_instructions="Focus on auth")
        system_prompt, user_message = eng._build_prompts()
        assert "Focus on auth" in user_message

    def test_prompt_includes_run_context(self, tmp_path):
        """User message includes run context (target run id, mode label)."""
        eng = self._make_engineer(tmp_path)
        system_prompt, user_message = eng._build_prompts()
        assert "Run Context" in user_message
        assert eng.run_id in user_message

    def test_prompt_includes_existing_client_guidance(self, tmp_path):
        """User message tells the agent to keep editing the existing client language."""
        har_path = tmp_path / "test.har"
        har_path.touch()
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        client_path = scripts_dir / "api_client.js"
        client_path.write_text("export {};\n")

        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=scripts_dir):
            with patch("reverse_api.base_engineer.get_docs_dir", return_value=tmp_path / "docs"):
                with patch("reverse_api.base_engineer.MessageStore") as mock_ms:
                    with patch("reverse_api.base_engineer.SessionManager") as mock_session_manager:
                        mock_ms.return_value.messages_path = tmp_path / "messages" / "test.jsonl"
                        mock_session_manager.return_value.get_run.return_value = None
                        eng = ConcreteEngineer(
                            run_id="test123",
                            har_path=har_path,
                            prompt="test prompt",
                            output_language="python",
                            output_dir=str(tmp_path),
                        )

        system_prompt, user_message = eng._build_prompts()
        assert str(client_path) in user_message
        assert "iterative edit" in user_message
        assert "JavaScript" in user_message


class TestBaseEngineerSync:
    """Test sync-related methods."""

    def _make_engineer(self, tmp_path, **kwargs):
        har_path = tmp_path / "test.har"
        har_path.touch()
        defaults = {
            "run_id": "test123",
            "har_path": har_path,
            "prompt": "test prompt",
            "output_dir": str(tmp_path),
        }
        defaults.update(kwargs)
        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
            with patch("reverse_api.base_engineer.get_docs_dir", return_value=tmp_path / "docs"):
                with patch("reverse_api.base_engineer.MessageStore"):
                    return ConcreteEngineer(**defaults)

    def test_start_sync_disabled(self, tmp_path):
        """Start sync does nothing when disabled."""
        eng = self._make_engineer(tmp_path, enable_sync=False)
        eng.start_sync()
        assert eng.sync_watcher is None

    def test_stop_sync_no_watcher(self, tmp_path):
        """Stop sync is safe with no watcher."""
        eng = self._make_engineer(tmp_path)
        eng.stop_sync()  # Should not raise

    def test_stop_sync_with_error(self, tmp_path):
        """Stop sync handles errors gracefully."""
        eng = self._make_engineer(tmp_path)
        mock_watcher = MagicMock()
        mock_watcher.stop.side_effect = Exception("stop failed")
        eng.sync_watcher = mock_watcher
        eng.stop_sync()  # Should not raise
        assert eng.sync_watcher is None

    def test_get_sync_status_no_watcher(self, tmp_path):
        """Sync status returns None with no watcher."""
        eng = self._make_engineer(tmp_path)
        assert eng.get_sync_status() is None

    def test_get_sync_status_with_watcher(self, tmp_path):
        """Sync status returns watcher status."""
        eng = self._make_engineer(tmp_path)
        mock_watcher = MagicMock()
        mock_watcher.get_status.return_value = {"active": True}
        eng.sync_watcher = mock_watcher
        status = eng.get_sync_status()
        assert status == {"active": True}

    def test_start_sync_enabled(self, tmp_path):
        """Start sync creates watcher when enabled."""
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir(parents=True)

        eng = self._make_engineer(tmp_path, enable_sync=True)
        eng.scripts_dir = scripts_dir

        with patch("reverse_api.base_engineer.generate_folder_name", return_value="test_project"):
            with patch("reverse_api.base_engineer.get_available_directory", return_value=tmp_path / "local" / "test_project"):
                with patch("reverse_api.base_engineer.FileSyncWatcher") as mock_watcher_cls:
                    mock_watcher = MagicMock()
                    mock_watcher_cls.return_value = mock_watcher

                    eng.start_sync()

                    assert eng.sync_watcher is mock_watcher
                    assert eng.local_scripts_dir == tmp_path / "local" / "test_project"
                    mock_watcher.start.assert_called_once()

    def test_start_sync_docs_mode(self, tmp_path):
        """Start sync uses docs directory in docs mode."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir(parents=True)

        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
            with patch("reverse_api.base_engineer.get_docs_dir", return_value=docs_dir):
                with patch("reverse_api.base_engineer.MessageStore"):
                    har_path = tmp_path / "test.har"
                    har_path.touch()
                    eng = ConcreteEngineer(
                        run_id="test123",
                        har_path=har_path,
                        prompt="test prompt",
                        output_dir=str(tmp_path),
                        enable_sync=True,
                        output_mode="docs",
                    )

        with patch("reverse_api.base_engineer.generate_folder_name", return_value="test_docs"):
            with patch("reverse_api.base_engineer.get_available_directory", return_value=tmp_path / "local" / "test_docs"):
                with patch("reverse_api.base_engineer.FileSyncWatcher") as mock_watcher_cls:
                    mock_watcher = MagicMock()
                    mock_watcher_cls.return_value = mock_watcher
                    eng.start_sync()
                    assert eng.sync_watcher is not None

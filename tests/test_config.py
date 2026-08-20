"""Tests for config.py - ConfigManager."""

import json
from pathlib import Path

import pytest

from reverse_api.config import DEFAULT_CONFIG, ConfigManager


class TestConfigManagerInit:
    """Test ConfigManager initialization."""

    def test_default_config(self, config_path):
        """ConfigManager starts with default config when no file exists."""
        cm = ConfigManager(config_path)
        assert cm.config == DEFAULT_CONFIG

    def test_loads_existing_config(self, config_path):
        """ConfigManager loads config from existing file."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({"sdk": "opencode", "claude_code_model": "claude-opus-4-6"}))
        cm = ConfigManager(config_path)
        assert cm.get("sdk") == "opencode"
        assert cm.get("claude_code_model") == "claude-opus-4-6"

    def test_ignores_invalid_keys(self, config_path):
        """ConfigManager ignores keys not in DEFAULT_CONFIG."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({"sdk": "claude", "unknown_key": "value"}))
        cm = ConfigManager(config_path)
        assert "unknown_key" not in cm.config

    def test_corrupted_json_falls_back_to_defaults(self, config_path):
        """ConfigManager uses defaults when config file has invalid JSON."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("not valid json {{{")
        cm = ConfigManager(config_path)
        assert cm.config == DEFAULT_CONFIG

    def test_empty_file_falls_back_to_defaults(self, config_path):
        """ConfigManager uses defaults for empty file."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("")
        cm = ConfigManager(config_path)
        assert cm.config == DEFAULT_CONFIG


class TestConfigMigration:
    """Test backward compatibility migrations."""

    def test_migrate_model_to_claude_code_model(self, config_path):
        """Old 'model' key migrates to 'claude_code_model'."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({"model": "claude-opus-4-6"}))
        cm = ConfigManager(config_path)
        assert cm.get("claude_code_model") == "claude-opus-4-6"

    def test_no_migrate_if_claude_code_model_exists(self, config_path):
        """Migration skipped if 'claude_code_model' already set."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({"model": "old", "claude_code_model": "new"}))
        cm = ConfigManager(config_path)
        assert cm.get("claude_code_model") == "new"

    def test_removed_browser_use_provider_resets_to_auto(self, config_path):
        """Legacy 'browser-use' agent_provider falls back to 'auto'."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({"agent_provider": "browser-use"}))
        cm = ConfigManager(config_path)
        assert cm.get("agent_provider") == "auto"

    def test_removed_stagehand_provider_resets_to_auto(self, config_path):
        """Legacy 'stagehand' agent_provider falls back to 'auto'."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({"agent_provider": "stagehand"}))
        cm = ConfigManager(config_path)
        assert cm.get("agent_provider") == "auto"


class TestConfigManagerOperations:
    """Test get/set/update/save operations."""

    def test_get_existing_key(self, config_path):
        """Get returns value for existing key."""
        cm = ConfigManager(config_path)
        assert cm.get("sdk") == "claude"

    def test_get_missing_key_returns_default(self, config_path):
        """Get returns default for missing key."""
        cm = ConfigManager(config_path)
        assert cm.get("nonexistent", "fallback") == "fallback"

    def test_get_missing_key_returns_none(self, config_path):
        """Get returns None by default for missing key."""
        cm = ConfigManager(config_path)
        assert cm.get("nonexistent") is None

    def test_set_saves_to_disk(self, config_path):
        """Set persists value to config file."""
        cm = ConfigManager(config_path)
        cm.set("sdk", "opencode")
        assert cm.get("sdk") == "opencode"

        # Verify it was saved to disk
        with open(config_path) as f:
            data = json.load(f)
        assert data["sdk"] == "opencode"

    def test_update_multiple_keys(self, config_path):
        """Update persists multiple values."""
        cm = ConfigManager(config_path)
        cm.update({"sdk": "opencode", "claude_code_model": "claude-haiku-4-5"})
        assert cm.get("sdk") == "opencode"
        assert cm.get("claude_code_model") == "claude-haiku-4-5"

        # Verify on disk
        with open(config_path) as f:
            data = json.load(f)
        assert data["sdk"] == "opencode"

    def test_save_creates_parent_dirs(self, tmp_path):
        """Save creates parent directories if they don't exist."""
        config_path = tmp_path / "nested" / "dir" / "config.json"
        cm = ConfigManager(config_path)
        cm.save()
        assert config_path.exists()

    def test_save_format(self, config_path):
        """Saved config has indented JSON."""
        cm = ConfigManager(config_path)
        cm.save()
        content = config_path.read_text()
        # Check it's indented (not compact)
        assert "\n" in content
        assert "    " in content


class TestDefaultConfig:
    """Test DEFAULT_CONFIG has expected keys."""

    def test_has_required_keys(self):
        """DEFAULT_CONFIG contains all expected keys."""
        expected_keys = {
            "agent_provider",
            "agent_browser_notes",
            "agent_browser_npx_package",
            "claude_code_model",
            "cloud_suggestions",
            "collector_model",
            "copilot_model",
            "cursor_model",
            "cursor_setting_sources",
            "cursor_web_search",
            "opencode_model",
            "opencode_provider",
            "opencode_auto_start",
            "opencode_base_url",
            "opencode_npx_package",
            "ollama_auto_start",
            "ollama_base_url",
            "output_dir",
            "output_language",
            "real_time_sync",
            "sdk",
        }
        assert set(DEFAULT_CONFIG.keys()) == expected_keys

    def test_default_values(self):
        """DEFAULT_CONFIG has expected default values."""
        assert DEFAULT_CONFIG["sdk"] == "claude"
        assert DEFAULT_CONFIG["output_dir"] is None
        assert DEFAULT_CONFIG["output_language"] == "python"
        assert DEFAULT_CONFIG["real_time_sync"] is True
        assert DEFAULT_CONFIG["cursor_model"] == "composer-2.5"
        assert DEFAULT_CONFIG["cursor_web_search"] is True
        assert DEFAULT_CONFIG["cursor_setting_sources"] is None
        assert DEFAULT_CONFIG["opencode_provider"] == "opencode"
        assert DEFAULT_CONFIG["opencode_model"] == "big-pickle"
        assert DEFAULT_CONFIG["opencode_auto_start"] is True
        assert DEFAULT_CONFIG["opencode_npx_package"] == "opencode-ai@latest"
        assert DEFAULT_CONFIG["ollama_auto_start"] is True
        assert DEFAULT_CONFIG["ollama_base_url"] == "http://127.0.0.1:11434"

"""Prompt template loader for reverse-api-engineer.

All LLM prompt text lives in `.md` files alongside this module.
Templates use `{placeholder}` syntax for dynamic values and
`{include:_partial_name}` to inline shared partials (resolved from
the `partials/` subdirectory).

Template names use `/` as a path separator, e.g. `"auto/system"` resolves
to `auto/system.md` relative to this package directory.
"""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent
_PARTIALS_DIR = _PROMPTS_DIR / "partials"

_INCLUDE_PREFIX = "{include:"
_INCLUDE_SUFFIX = "}"


def _resolve_includes(text: str) -> str:
    """Recursively resolve `{include:_partial_name}` directives."""
    while _INCLUDE_PREFIX in text:
        start = text.index(_INCLUDE_PREFIX)
        end = text.index(_INCLUDE_SUFFIX, start + len(_INCLUDE_PREFIX))
        partial_name = text[start + len(_INCLUDE_PREFIX) : end]
        partial_path = _PARTIALS_DIR / f"{partial_name}.md"
        partial_text = partial_path.read_text()
        partial_text = _resolve_includes(partial_text)
        text = text[:start] + partial_text + text[end + 1 :]
    return text


def load(template_name: str, **kwargs: str) -> str:
    """Load a markdown prompt template and fill placeholders.

    Args:
        template_name: Path to the `.md` file (without extension),
            e.g. ``"auto/system"`` or ``"collector/user"``.
        **kwargs: Values to substitute for `{placeholder}` tokens.

    Returns:
        The fully rendered prompt string.
    """
    path = _PROMPTS_DIR / f"{template_name}.md"
    text = path.read_text()
    text = _resolve_includes(text)
    if kwargs:
        text = text.format_map(kwargs)
    return text


def load_language_partial(language: str, **kwargs: str) -> str:
    """Load the language-specific codegen instructions partial.

    Args:
        language: One of "python", "javascript", "typescript", "go", "java", "csharp", "php", "ruby", "c",
            "powershell".
        **kwargs: Placeholder values (scripts_dir, client_filename, run_command).
    """
    return load(f"partials/_language_{language}", **kwargs)


FOLDER_NAME_PROMPT = (
    "Generate a short folder name (1-3 words, lowercase, underscores) "
    "for this task: {prompt}\n\n"
    "Respond with ONLY the folder name, nothing else. Example: apple_jobs_api"
)

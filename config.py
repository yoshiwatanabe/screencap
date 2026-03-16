"""Load and validate configuration from config.json."""
import json
from pathlib import Path

REQUIRED_KEYS = [
    "watch_dir",
    "output_dir",
    "max_age_minutes",
    "image_extensions",
    "copilot_loader",
    "copilot_model",
    "copilot_timeout",
    "metadata_dir",
    "log_file",
    "state_file",
]

ALLOWED_MODELS = {
    "gpt-5.4",
    "gemini-3-pro-preview",
    "claude-haiku-4.5",
    "claude-sonnet-4.5",
    "claude-sonnet-4.6",
    "claude-opus-4.5",
    "claude-opus-4.6",
}

# These keys must resolve to paths inside the repo directory
_REPO_RELATIVE_KEYS = {"metadata_dir", "log_file", "state_file"}


def load_config(config_path: Path | None = None) -> dict:
    """Load config.json, resolve REPO_DIR tokens, validate keys, create dirs.

    Args:
        config_path: explicit path to config.json. When None, looks for
                     config.json in the same directory as this file.

    Returns:
        Validated config dict with all REPO_DIR tokens resolved.

    Raises:
        FileNotFoundError: if config file does not exist.
        ValueError: if any required keys are missing or values are invalid.
    """
    if config_path is None:
        config_path = Path(__file__).parent / "config.json"

    config_path = Path(config_path)
    repo_dir = config_path.parent
    repo_dir_resolved = repo_dir.resolve()

    with config_path.open(encoding="utf-8") as f:
        cfg = json.load(f)

    # Resolve REPO_DIR token in top-level string values only; list/nested values are not substituted.
    for key, value in cfg.items():
        if isinstance(value, str):
            cfg[key] = value.replace("REPO_DIR", str(repo_dir))

    # Validate required keys
    missing = [k for k in REQUIRED_KEYS if k not in cfg]
    if missing:
        raise ValueError(f"Missing required config key(s): {', '.join(missing)}")

    # Validate copilot_loader is an existing .js file
    loader = Path(cfg["copilot_loader"])
    if not loader.exists() or loader.suffix.lower() != ".js":
        raise ValueError(f"copilot_loader must be an existing .js file: {loader}")

    # Validate copilot_model against allowlist
    if cfg["copilot_model"] not in ALLOWED_MODELS:
        raise ValueError(
            f"copilot_model '{cfg['copilot_model']}' not in allowlist: "
            f"{sorted(ALLOWED_MODELS)}"
        )

    # Assert REPO_RELATIVE_KEYS resolve inside repo_dir
    for key in _REPO_RELATIVE_KEYS:
        resolved = Path(cfg[key]).resolve()
        if not str(resolved).startswith(str(repo_dir_resolved)):
            raise ValueError(
                f"Config key '{key}' resolves outside repo directory: {resolved}"
            )

    # Create directories that must exist before any run
    Path(cfg["metadata_dir"]).mkdir(parents=True, exist_ok=True)
    Path(cfg["log_file"]).parent.mkdir(parents=True, exist_ok=True)

    return cfg

"""Reused read-only watchlist and local model discovery. No analysis executor."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

DEFAULT_MODEL = 'gpt-6-astra'
DEFAULT_SYMBOL = 'BYBIT:XAUUSDT.P'

def connector_directory():
    return Path(os.environ.get("SR_TRADINGVIEW_MCP_DIR", Path.home() / "tradingview-mcp")).expanduser().resolve()

def node_executable():
    """Resolve Node even with Explorer's PATH, without changing system settings."""
    override = os.environ.get("SR_NODE_PATH")
    if override:
        path = Path(override).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"SR_NODE_PATH does not exist: {path}")
        return str(path)
    found = shutil.which("node.exe") or shutil.which("node")
    if found:
        return found
    candidates = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "nodejs" / "node.exe",
        Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Programs" / "nodejs" / "node.exe",
    ]
    return next((str(path) for path in candidates if path.is_file()), None)

def sanitize_output(value):
    """Remove terminal escapes and common credential formats from displayed logs."""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    text = str(value or "")
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}", "[REDACTED]", text)
    text = re.sub(r"(?i)(Bearer\s+)\S+", r"\1[REDACTED]", text)
    text = re.sub(
        r'''(?i)(["']?(?:[\w-]*(?:api[_-]?key|token|secret|password))["']?\s*[:=]\s*)["']?[^\s,"'}]+["']?''',
        r"\1[REDACTED]", text,
    )
    return text

def fallback_symbols():
    """User-configured choices, never presented as a retrieved watchlist."""
    configured = os.environ.get("SR_SYMBOLS", "").split(",")
    return list(dict.fromkeys([DEFAULT_SYMBOL] + [s.strip() for s in configured if s.strip()]))

def get_tradingview_watchlist(timeout=25):
    """Reuse the installed connector's CLI and its watchlist_get implementation."""
    try:
        connector = connector_directory()
        node = node_executable()
        launcher = connector / "src" / "cli" / "index.js"
        if not node or not launcher.is_file():
            raise FileNotFoundError("Existing TradingView connector CLI or Node.js was not found.")
        result = subprocess.run(
            [node, str(launcher), "watchlist", "get"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=connector, timeout=timeout, shell=False,
            stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode:
            raise ValueError(result.stderr.strip() or f"Connector exited with code {result.returncode}.")
        data = json.loads(result.stdout)
        if not isinstance(data, dict) or data.get("success") is not True:
            raise ValueError("Connector did not return a successful watchlist response.")
        symbols = list(dict.fromkeys(
            row["symbol"].strip() for row in data.get("symbols", [])
            if isinstance(row, dict) and isinstance(row.get("symbol"), str)
            and re.fullmatch(r"[A-Za-z0-9_]+:[A-Za-z0-9_.!/-]+", row["symbol"].strip())
        ))
        if not symbols:
            raise ValueError("TradingView returned an empty watchlist.")
        return {"symbols": symbols, "source": "live", "name": data.get("list_name") or "current list", "error": ""}
    except subprocess.TimeoutExpired:
        error = f"Watchlist retrieval timed out after {timeout} seconds."
    except (OSError, ValueError, TypeError) as exc:
        error = sanitize_output(exc)
    return {"symbols": fallback_symbols(), "source": "fallback", "name": "", "error": error}

def load_codex_models(catalog_path=None):
    """Read visible CLI model IDs locally; listing is not proof of invocation access."""
    home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    path = Path(catalog_path) if catalog_path is not None else home / "models_cache.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        models = list(dict.fromkeys(
            item["slug"] for item in data.get("models", [])
            if isinstance(item, dict) and item.get("visibility") == "list"
            and item.get("supported_in_api") is not False
            and isinstance(item.get("slug"), str)
            and re.fullmatch(r"[A-Za-z0-9_.-]+", item["slug"])
        ))
        if not models:
            raise ValueError("No visible models were found in the local Codex catalog.")
        return {"models": models, "source": str(path), "fetched_at": data.get("fetched_at", "unknown"), "error": ""}
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        return {"models": [], "source": str(path), "error": sanitize_output(exc)}

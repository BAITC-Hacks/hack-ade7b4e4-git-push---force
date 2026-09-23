import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:  # LLM-шлюз нужен только тестам ассистента. Тесты пайплайна от него не зависят.
    from app import config, llm  # noqa: E402
except Exception:  # noqa: BLE001
    config = llm = None


@pytest.fixture(autouse=True)
def clean_state(monkeypatch, tmp_path):
    """Every test starts in demo mode with empty caches and a private demo cache file."""
    if llm is None or not hasattr(llm, "reset_state"):
        yield
        return
    monkeypatch.setattr(config, "DEMO_MODE", "on")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    monkeypatch.setattr(config, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(llm, "DEMO_CACHE_PATH", tmp_path / "demo_cache.json")
    llm.reset_state()
    llm.set_client(None)
    yield
    llm.set_client(None)

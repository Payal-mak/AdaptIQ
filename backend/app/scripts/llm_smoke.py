"""Smoke test with REAL keys: python -m app.scripts.llm_smoke

Sends one tiny JSON request to EACH configured provider separately (no retries, no fallback,
nothing written to the database) and prints what happened. Never run by pytest.
"""

import json
import sys
import time

from app.core.config import get_settings
from app.llm.base import LLMProvider
from app.llm.client import build_provider
from app.llm.errors import LLMError

SYSTEM = "You are a test endpoint. Reply with a single JSON object and nothing else."
USER = 'Return exactly this JSON, filling in the value: {"ok": true, "capital_of_france": "<the capital>"}'


def check_provider(provider: LLMProvider, timeout: float) -> bool:
    """Call one provider once and print the outcome. Returns True on success."""
    print(f"\n[{provider.name}] model={provider.model}")
    if not provider.is_configured:
        print("  skipped: API key or model name is not set in .env")
        return True  # not configured is not a failure

    started = time.perf_counter()
    try:
        result = provider.generate(SYSTEM, USER, json_mode=True, temperature=0.0, timeout=timeout)
    except LLMError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        print(f"  FAILED after {latency_ms} ms: {type(exc).__name__}: {exc}")
        return False

    latency_ms = int((time.perf_counter() - started) * 1000)
    print(f"  latency: {latency_ms} ms")
    print(f"  tokens: input={result.input_tokens} output={result.output_tokens}")
    try:
        data = json.loads(result.text)
    except json.JSONDecodeError:
        print(f"  FAILED: reply was not valid JSON: {result.text[:200]!r}")
        return False
    print(f"  SUCCESS: {data}")
    return True


def main() -> None:
    settings = get_settings()
    names = ["groq", "gemini"]
    all_ok = True
    for name in names:
        provider = build_provider(name, settings)
        all_ok = check_provider(provider, settings.llm_timeout_seconds) and all_ok
    print()
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()

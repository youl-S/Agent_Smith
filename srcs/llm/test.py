"""Quick manual test for LLMManager key cascade against Groq.

Setup:
    Put your keys in .env as GROQ_API_KEY_1, GROQ_API_KEY_2, ...
    Make the FIRST one (GROQ_API_KEY_1) intentionally invalid.
    The cascade should skip it and succeed on a later key.

Run:
    uv run python test_manager.py
"""

import os
from dotenv import load_dotenv

from client import LLMClient
from manager import LLMManager
from models import ProviderTarget

load_dotenv()

GROQ_URL = "https://api.groq.com/openai/v1"
MODEL = "llama-3.3-70b-versatile"


def discover_key_vars(prefix: str = "GROQ_API_KEY_") -> list[str]:
    """Collect GROQ_API_KEY_1, _2, ... in numeric order from the environment."""
    found = []
    n = 1
    while True:
        var = f"{prefix}{n}"
        if os.environ.get(var) is None:
            break
        found.append(var)
        n += 1
    return found


def main() -> None:
    key_vars = discover_key_vars()
    if not key_vars:
        raise SystemExit("No GROQ_API_KEY_N found in environment / .env")

    print(f"Found {len(key_vars)} key vars: {key_vars}")
    print("(reminder: GROQ_API_KEY_1 should be the invalid one)\n")

    target = ProviderTarget(
        name="groq",
        base_url=GROQ_URL,
        model=MODEL,
        key_env_vars=key_vars,
    )

    manager = LLMManager(targets=[target], client=LLMClient(timeout_s=30.0))

    resp = manager.generate(
        messages=[{"role": "user", "content": "Reply with exactly: pong"}],
        stop_sequences=None,
    )

    print("=== cascade result ===")
    print("success :", resp.success)
    print("text    :", repr(resp.text[:60]))
    print("retries :", resp.retries, "(should be >= 1 if key 1 was invalid)")
    print("model   :", resp.model_name)
    print("url     :", resp.api_url)
    print("error   :", resp.error)

    if resp.success:
        assert resp.text != ""
        assert (
            resp.retries >= 1
        ), "expected at least 1 retry (skipped invalid key 1)"
        print("\n-> OK: cascade skipped the bad key and succeeded")
    else:
        print("\n-> all keys failed:", resp.error)


if __name__ == "__main__":
    main()

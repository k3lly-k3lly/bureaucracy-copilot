"""List the chat models your Groq key can use right now.

    uv run python -m copilot.models

Pick one and set it in .env, e.g.  GROQ_MODEL=openai/gpt-oss-120b
"""

import httpx

from copilot.config import get_settings


def main() -> None:
    settings = get_settings()
    if not settings.groq_api_key:
        raise SystemExit("GROQ_API_KEY is not set in .env")
    response = httpx.get(
        "https://api.groq.com/openai/v1/models",
        headers={"Authorization": f"Bearer {settings.groq_api_key}"},
        timeout=20.0,
    )
    response.raise_for_status()
    ids = sorted(m["id"] for m in response.json()["data"])
    print(f"Currently configured: {settings.groq_model}\n")
    for model_id in ids:
        marker = "  <- configured" if model_id == settings.groq_model else ""
        print(f"  {model_id}{marker}")
    if settings.groq_model not in ids:
        print(f"\nWarning: {settings.groq_model} is not in this list. Set GROQ_MODEL in .env.")


if __name__ == "__main__":
    main()

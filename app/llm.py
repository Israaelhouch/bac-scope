"""Pluggable LLM adapter for text-to-SQL.

Default provider is Groq (free tier). The provider is selected by environment
variables so it can be swapped without code changes:

    GROQ_API_KEY   required to enable /ask
    GROQ_MODEL     default: llama-3.3-70b-versatile

`generate_sql` returns the raw model output (SQL, possibly fenced). Cleaning and
validation happen in nl2sql.py.
"""
from __future__ import annotations

import os
import re


class LLMError(RuntimeError):
    """Raised when the LLM can't be reached or isn't configured."""


def is_configured() -> bool:
    return bool(os.environ.get("GROQ_API_KEY"))


def _extract_sql(text: str) -> str:
    """Pull SQL out of a model reply that may include ``` fences or prose."""
    text = text.strip()
    fence = re.search(r"```(?:sql)?\s*(.+?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    return text


def generate_sql(question: str, system_prompt: str, model: str | None = None) -> str:
    """Ask Groq to translate a question into SQL. Raises LLMError if unavailable."""
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise LLMError(
            "GROQ_API_KEY غير مضبوط. أضف مفتاح Groq المجاني في ملف .env لتفعيل /ask."
        )
    try:
        from groq import Groq
    except ImportError as exc:  # pragma: no cover
        raise LLMError("حزمة groq غير مثبّتة. نفّذ: pip install groq") from exc

    model = model or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    # Construct the client AND make the call inside the guard, so any LLM-side
    # failure (auth, network, proxy, etc.) degrades to a clean 503, never a 500.
    try:
        client = Groq(api_key=key)
        resp = client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
        )
    except Exception as exc:  # noqa: BLE001
        raise LLMError(f"تعذّر الاتصال بـ Groq: {exc}") from exc

    return _extract_sql(resp.choices[0].message.content or "")

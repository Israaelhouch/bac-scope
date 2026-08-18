"""Pluggable LLM adapter for text-to-SQL.

Default provider is Groq (free tier). The provider is selected by environment
variables so it can be swapped without code changes:

    GROQ_API_KEY   required to enable /ask
    GROQ_MODEL     default: openai/gpt-oss-120b

Model IDs are not forever. Groq retires preview-tier models on short notice —
`llama-3.3-70b-versatile`, the original default here, stopped resolving and took
/ask down with it. So a `model_not_found` error is not treated as fatal: the
adapter asks the account which models it can actually see and retries with the
best available one, and any error message names those models instead of echoing
a bare 404.

`generate_sql` returns the raw model output (SQL, possibly fenced). Cleaning and
validation happen in nl2sql.py.
"""
from __future__ import annotations

import os
import re

#: Chosen by measurement, not by size. On the 9-case execution-accuracy suite
#: (scripts/eval.py) the 20B scores the same 9/9 as the 120B and qwen3.6-27b,
#: while being the cheapest and fastest of the three — so it is the default.
DEFAULT_MODEL = "openai/gpt-oss-20b"

#: Preferred chat models, best first. Used to pick a replacement when the
#: configured model is gone. Non-chat models on the account (whisper-*,
#: *prompt-guard*, orpheus-*) are excluded by _is_chat_model below.
MODEL_PREFERENCE = (
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "qwen/qwen3.6-27b",
    "groq/compound",
    "groq/compound-mini",
)

#: Substrings marking models that cannot do chat completions.
_NON_CHAT_HINTS = ("whisper", "prompt-guard", "orpheus", "tts", "safeguard")


class LLMError(RuntimeError):
    """Raised when the LLM can't be reached or isn't configured."""


def is_configured() -> bool:
    return bool(os.environ.get("GROQ_API_KEY"))


def configured_model() -> str:
    return os.environ.get("GROQ_MODEL") or DEFAULT_MODEL


#: Reasoning models (qwen3, deepseek-r1, …) emit a chain-of-thought block before
#: the answer. That text is prose, and prose containing a ';' trips the
#: single-statement validator — so a reasoning model gets disqualified for
#: reasoning unless the block is stripped first.
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_UP_TO_THINK_END = re.compile(r"^.*?</think>", re.DOTALL | re.IGNORECASE)
_SQL_START = re.compile(r"\b(SELECT|WITH)\b", re.IGNORECASE)


def _extract_sql(text: str) -> str:
    """Pull SQL out of a model reply that may include reasoning, fences or prose."""
    text = text.strip()

    # 1. Drop reasoning blocks, closed or left open by a truncated reply.
    text = _THINK_BLOCK.sub("", text)
    if "</think>" in text.lower():
        text = _UP_TO_THINK_END.sub("", text, count=1)
    text = text.strip()

    # 2. A fenced block is the most explicit signal — trust it.
    fence = re.search(r"```(?:sql)?\s*(.+?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        return fence.group(1).strip()

    # 3. Otherwise drop any lead-in prose before the statement itself.
    lowered = text.lstrip().lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        start = _SQL_START.search(text)
        if start:
            text = text[start.start():]

    return text.strip()


def _is_chat_model(model_id: str) -> bool:
    lowered = model_id.lower()
    return not any(hint in lowered for hint in _NON_CHAT_HINTS)


def available_models(client) -> list[str]:
    """Chat-capable model IDs this API key can actually use."""
    try:
        return sorted(m.id for m in client.models.list().data if _is_chat_model(m.id))
    except Exception:  # noqa: BLE001 — listing is best-effort diagnostics
        return []


def _pick_fallback(models: list[str]) -> str | None:
    """Best available chat model: preference order first, else anything."""
    for candidate in MODEL_PREFERENCE:
        if candidate in models:
            return candidate
    return models[0] if models else None


def _is_missing_model(exc: Exception) -> bool:
    text = str(exc).lower()
    return "model_not_found" in text or "does not exist" in text


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

    model = model or configured_model()
    # Construct the client AND make the call inside the guard, so any LLM-side
    # failure (auth, network, proxy, etc.) degrades to a clean 503, never a 500.
    try:
        client = Groq(api_key=key)
    except Exception as exc:  # noqa: BLE001
        raise LLMError(f"تعذّر الاتصال بـ Groq: {exc}") from exc

    def _call(model_id: str):
        return client.chat.completions.create(
            model=model_id,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
        )

    try:
        resp = _call(model)
    except Exception as exc:  # noqa: BLE001
        if not _is_missing_model(exc):
            raise LLMError(f"تعذّر الاتصال بـ Groq: {exc}") from exc

        # The configured model is gone. Find out what this key can actually use.
        models = available_models(client)
        fallback = _pick_fallback([m for m in models if m != model])
        if not fallback:
            listed = "، ".join(models) if models else "لا شيء"
            raise LLMError(
                f"النموذج '{model}' غير متاح لهذا المفتاح، ولا يوجد بديل صالح. "
                f"النماذج المتاحة: {listed}. "
                f"اضبط GROQ_MODEL في ملف .env على أحد هذه النماذج."
            ) from exc
        try:
            resp = _call(fallback)
        except Exception as exc2:  # noqa: BLE001
            raise LLMError(
                f"النموذج '{model}' غير متاح، وفشل البديل '{fallback}' أيضًا: {exc2}. "
                f"النماذج المتاحة: {'، '.join(models)}."
            ) from exc2

    return _extract_sql(resp.choices[0].message.content or "")

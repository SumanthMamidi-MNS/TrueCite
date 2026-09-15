"""On-demand translation of an already-verified answer (PRD §6.3's
multilingual requirement, scoped down deliberately — see docs/decisions.md).

The PRD calls for verifying retrieval quality in English and Hindi
independently, which would mean a Hindi-native corpus, embeddings, and a
whole second set of retrieval-quality gates. Instead: retrieval, generation,
and Layer 2 verification stay English-only (unchanged, zero new risk to
already-tuned retrieval quality), and a user who wants Hindi gets the
already-verified English answer translated on request. Translating settled,
grounded text is a much safer LLM task than open-ended generation — there's
nothing left to hallucinate, only mistranslation risk, which is smaller and
named honestly in the UI rather than hidden. This does not satisfy the PRD's
specific requirement (no independent Hindi retrieval-quality verification
happens, because no Hindi retrieval happens at all) — a real, disclosed
scope narrowing, not a secret one.
"""
import json

import llm_client

TRANSLATE_PROMPT_TEMPLATE = """Translate the following text into {language}. Preserve every citation reference (e.g. "[Source: ...]", section numbers, dates) EXACTLY as written, character-for-character, untranslated — only the surrounding prose should change language. Do not add, remove, or explain anything; translate faithfully, nothing more.

Text:
\"\"\"
{text}
\"\"\"

Respond with ONLY a JSON object in this exact format, no other text:
{{"translated": "the translated text"}}
"""


def translate_answer(text: str, language: str = "Hindi", timeout: int = 60) -> str:
    """Translate an already-composed answer. Raises on a malformed response —
    fail closed, same reasoning as generation/verification: a translation
    that can't be parsed shouldn't be silently swapped for the original or
    for an empty string."""
    prompt = TRANSLATE_PROMPT_TEMPLATE.format(language=language, text=text)
    raw = llm_client.complete(prompt, timeout=timeout)
    result = json.loads(raw)
    translated = result.get("translated")
    if not isinstance(translated, str) or not translated.strip():
        raise ValueError(f"malformed translation response: {result!r}")
    return translated.strip()

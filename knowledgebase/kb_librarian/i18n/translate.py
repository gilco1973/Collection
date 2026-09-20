"""One-shot machine translation of a page's title and body via the Claude Agent SDK.

No tools, no multi-turn loop, no MCP server: a single prompt asking for translated
Markdown back, with the same built-in-tool lockdown ``agent/options.py`` uses for
audits. ``query_fn`` is injected (the SDK's ``query`` by default) so tests run the
whole pipeline against a fake stream — no network call, no API key.
"""

from collections.abc import AsyncIterator, Callable
from typing import Any

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock
from claude_agent_sdk import query as sdk_query

from kb_librarian.agent.options import DISALLOWED_BUILTINS

QueryFn = Callable[..., AsyncIterator[Any]]

LANGUAGE_NAMES: dict[str, str] = {"es": "Spanish", "he": "Hebrew"}
_TITLE_MARK, _BODY_MARK = "---TITLE---", "---BODY---"

_INSTRUCTIONS = """Translate this knowledge-base page into {language}.

Rules:
- Translate only human-readable prose: the title, headings, paragraphs, list items, table cells, link text.
- Never translate: code fences and inline code, URLs, and Markdown syntax itself.
- Preserve the exact structure: the same headings, the same list/table shape, the same link targets.
- Reply with exactly two sections, in this order, and nothing else — no commentary, no extra fences:
{title_mark}
<the translated title, one line>
{body_mark}
<the translated Markdown body>

{title_mark}
{title}

{body_mark}
{body}"""


class TranslationError(Exception):
    """The model's reply did not have both required sections."""


def _parse(text: str) -> tuple[str, str]:
    if _TITLE_MARK not in text or _BODY_MARK not in text:
        raise TranslationError("translation reply is missing the title/body markers")
    _, _, rest = text.partition(_TITLE_MARK)
    title_part, _, body_part = rest.partition(_BODY_MARK)
    title = title_part.strip()
    body = body_part.strip("\n") + "\n"
    if not title:
        raise TranslationError("translated title is empty")
    return title, body


async def translate_markdown(
    title: str, body: str, lang: str, *, model: str | None = None, query_fn: QueryFn = sdk_query
) -> tuple[str, str]:
    """Return ``(translated_title, translated_body)``. Raises ``TranslationError`` on a malformed reply."""
    language = LANGUAGE_NAMES.get(lang, lang)
    prompt = _INSTRUCTIONS.format(
        language=language, title_mark=_TITLE_MARK, body_mark=_BODY_MARK, title=title, body=body
    )
    options = ClaudeAgentOptions(
        tools=[],
        allowed_tools=[],
        disallowed_tools=list(DISALLOWED_BUILTINS),
        permission_mode="default",
        max_turns=1,
        model=model,
        setting_sources=[],
    )
    texts: list[str] = []
    async for message in query_fn(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            texts.extend(b.text for b in message.content if isinstance(b, TextBlock))
    return _parse("".join(texts))

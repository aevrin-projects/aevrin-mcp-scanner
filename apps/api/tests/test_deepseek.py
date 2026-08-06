from __future__ import annotations

import httpx
import pytest
import respx

from aevrin_api.deepseek import (
    BASE_URL,
    DeepSeekError,
    complete_json,
    parse_json_object,
    stream_json,
)

_URL = f"{BASE_URL}/chat/completions"

_ARGS = {
    "api_key": "k",
    "model": "deepseek-v4-pro",
    "system_prompt": "static instructions mentioning json",
    "user_prompt": "the finding",
    "max_tokens": 500,
    "timeout_s": 10.0,
}


def _sse(*frames: str) -> str:
    return "".join(f"data: {f}\n\n" for f in frames) + "data: [DONE]\n\n"


@pytest.mark.asyncio
async def test_complete_json_reports_cache_hits():
    body = {
        "choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 528, "completion_tokens": 100, "prompt_cache_hit_tokens": 512},
    }
    with respx.mock:
        respx.post(_URL).mock(return_value=httpx.Response(200, json=body))
        result = await complete_json(**_ARGS)
    assert result.cache_hit_tokens == 512
    assert round(result.cache_hit_ratio, 3) == 0.970
    assert result.truncated is False


@pytest.mark.asyncio
async def test_complete_json_flags_truncation():
    """`finish_reason: length` is the only way to tell "ran out of budget
    mid-JSON" from "returned something unparseable" — a JSON decoder sees
    both as the same error, but only the first is fixed by raising
    max_tokens."""
    body = {
        "choices": [{"message": {"content": '{"classification": "conf'}, "finish_reason": "length"}],
        "usage": {"prompt_tokens": 528, "completion_tokens": 500},
    }
    with respx.mock:
        respx.post(_URL).mock(return_value=httpx.Response(200, json=body))
        result = await complete_json(**_ARGS)
    assert result.truncated is True


@pytest.mark.asyncio
async def test_error_body_is_surfaced_but_bounded():
    with respx.mock:
        respx.post(_URL).mock(return_value=httpx.Response(402, text="insufficient balance " * 100))
        with pytest.raises(DeepSeekError) as excinfo:
            await complete_json(**_ARGS)
    message = str(excinfo.value)
    assert message.startswith("402:")
    # Echoed into logs, so it must not carry an unbounded response body.
    assert len(message) < 350


@pytest.mark.asyncio
async def test_empty_choices_is_an_error_not_a_crash():
    with respx.mock:
        respx.post(_URL).mock(return_value=httpx.Response(200, json={"choices": []}))
        with pytest.raises(DeepSeekError):
            await complete_json(**_ARGS)


@pytest.mark.asyncio
async def test_stream_reassembles_deltas_and_final_usage():
    stream = _sse(
        '{"choices": [{"delta": {"content": "{\\"patched_content\\": \\"a"}}]}',
        '{"choices": [{"delta": {"content": "bc\\"}"}, "finish_reason": "stop"}]}',
        '{"choices": [], "usage": {"prompt_tokens": 900, "completion_tokens": 40, '
        '"prompt_cache_hit_tokens": 832}}',
    )
    with respx.mock:
        respx.post(_URL).mock(return_value=httpx.Response(200, text=stream))
        result = await stream_json(**_ARGS)
    assert result.content == '{"patched_content": "abc"}'
    assert result.cache_hit_tokens == 832
    assert result.truncated is False


@pytest.mark.asyncio
async def test_stream_flags_truncation():
    stream = _sse('{"choices": [{"delta": {"content": "{\\"a"}, "finish_reason": "length"}]}')
    with respx.mock:
        respx.post(_URL).mock(return_value=httpx.Response(200, text=stream))
        result = await stream_json(**_ARGS)
    assert result.truncated is True


@pytest.mark.asyncio
async def test_stream_tolerates_a_malformed_frame():
    """One unparseable SSE frame must not discard an otherwise complete
    generation."""
    stream = _sse(
        '{"choices": [{"delta": {"content": "hel"}}]}',
        "{not json at all",
        '{"choices": [{"delta": {"content": "lo"}, "finish_reason": "stop"}]}',
    )
    with respx.mock:
        respx.post(_URL).mock(return_value=httpx.Response(200, text=stream))
        result = await stream_json(**_ARGS)
    assert result.content == "hello"


@pytest.mark.asyncio
async def test_stream_surfaces_http_errors():
    with respx.mock:
        respx.post(_URL).mock(return_value=httpx.Response(429, text="rate limited"))
        with pytest.raises(DeepSeekError) as excinfo:
            await stream_json(**_ARGS)
    assert "429" in str(excinfo.value)


@pytest.mark.asyncio
async def test_stream_with_no_content_is_an_error():
    with respx.mock:
        respx.post(_URL).mock(return_value=httpx.Response(200, text="data: [DONE]\n\n"))
        with pytest.raises(DeepSeekError):
            await stream_json(**_ARGS)


def test_parse_json_object_handles_a_fenced_reply():
    raw = 'Here you go:\n```json\n{"classification": "confirmed"}\n```'
    assert parse_json_object(raw) == {"classification": "confirmed"}


def test_parse_json_object_rejects_a_bare_array():
    with pytest.raises(TypeError):
        parse_json_object("[1, 2, 3]")


def test_parse_json_object_propagates_unrecoverable_garbage():
    import json

    with pytest.raises(json.JSONDecodeError):
        parse_json_object("not json, no braces either")

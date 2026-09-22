from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from src.domain.errors import AiError
from src.infrastructure.ai.openai_compat import MAX_REPLY_CHARS, OpenAICompatibleChatCompleter


def reply(content: str, **extra: Any) -> dict[str, Any]:
    return {"choices": [{"message": {"role": "assistant", "content": content}}], **extra}


def completer(
    handler: Any,
    *,
    base_url: str = "https://api.example.com/v1",
    api_key: str | None = "sk-secret",
    model: str = "tiny",
) -> OpenAICompatibleChatCompleter:
    return OpenAICompatibleChatCompleter(
        base_url=base_url,
        model=model,
        api_key=api_key,
        transport=httpx.MockTransport(handler),
    )


def ask(client: OpenAICompatibleChatCompleter) -> str:
    return client.complete(system="be terse", user="hello", timeout=5.0)


def test_posts_to_the_chat_completions_path() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=reply("{}"))

    ask(completer(handler))

    assert str(seen[0].url) == "https://api.example.com/v1/chat/completions"


def test_a_trailing_slash_on_the_base_url_does_not_double_up() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=reply("{}"))

    ask(completer(handler, base_url="https://api.example.com/v1/"))

    assert str(seen[0].url) == "https://api.example.com/v1/chat/completions"


def test_sends_the_model_the_two_messages_and_zero_temperature() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=reply("{}"))

    ask(completer(handler, model="gpt-4o-mini"))

    body = seen[0]
    assert body["model"] == "gpt-4o-mini"
    assert body["temperature"] == 0
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert body["messages"][0]["content"] == "be terse"
    assert body["messages"][1]["content"] == "hello"


def test_sends_a_bearer_token_when_a_key_is_configured() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=reply("{}"))

    ask(completer(handler))

    assert seen[0].headers["Authorization"] == "Bearer sk-secret"


def test_sends_no_authorization_header_for_a_keyless_local_provider() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=reply("{}"))

    ask(completer(handler, api_key=None, base_url="http://127.0.0.1:11434/v1"))

    assert "Authorization" not in seen[0].headers


def test_returns_the_assistant_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=reply('{"tracks": []}'))

    assert ask(completer(handler)) == '{"tracks": []}'


class TestResponseFormat:
    def test_asks_for_a_json_object_on_the_first_attempt(self) -> None:
        seen: list[dict[str, Any]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(json.loads(request.content))
            return httpx.Response(200, json=reply("{}"))

        ask(completer(handler))

        assert seen[0]["response_format"] == {"type": "json_object"}

    def test_retries_once_without_it_when_the_provider_rejects_it(self) -> None:
        seen: list[dict[str, Any]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            seen.append(body)
            if "response_format" in body:
                return httpx.Response(400, json={"error": "unsupported parameter"})
            return httpx.Response(200, json=reply('{"tracks": []}'))

        assert ask(completer(handler)) == '{"tracks": []}'
        assert len(seen) == 2
        assert "response_format" not in seen[1]

    def test_a_second_bad_request_is_not_retried_again(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(400, json={"error": "nope"})

        with pytest.raises(AiError, match="HTTP 400"):
            ask(completer(handler))

        assert calls == 2


class TestFailures:
    def test_a_transport_error_becomes_an_ai_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        with pytest.raises(AiError, match="could not reach"):
            ask(completer(handler))

    def test_a_timeout_becomes_an_ai_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("too slow", request=request)

        with pytest.raises(AiError, match="could not reach"):
            ask(completer(handler))

    def test_a_server_error_becomes_an_ai_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="upstream overloaded")

        with pytest.raises(AiError, match="HTTP 503"):
            ask(completer(handler))

    def test_a_non_json_body_becomes_an_ai_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>proxy error</html>")

        with pytest.raises(AiError, match="did not return JSON"):
            ask(completer(handler))

    def test_a_json_array_body_becomes_an_ai_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[1, 2, 3])

        with pytest.raises(AiError, match="expected an object"):
            ask(completer(handler))

    def test_missing_choices_become_an_ai_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"id": "x"})

        with pytest.raises(AiError, match="no choices"):
            ask(completer(handler))

    @pytest.mark.parametrize("content", ["", "   ", None, 42])
    def test_an_unusable_content_field_becomes_an_ai_error(self, content: Any) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=reply(content))

        with pytest.raises(AiError, match="empty completion"):
            ask(completer(handler))

    def test_an_oversized_reply_is_refused_rather_than_parsed(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=reply("x" * (MAX_REPLY_CHARS + 1)))

        with pytest.raises(AiError, match="over the reply limit"):
            ask(completer(handler))


def test_the_api_key_never_reaches_the_logs(capsys: pytest.CaptureFixture[str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=reply("{}", usage={"prompt_tokens": 11}))

    ask(completer(handler, api_key="sk-do-not-leak"))

    captured = capsys.readouterr()
    assert "sk-do-not-leak" not in captured.out + captured.err


def test_an_error_body_is_truncated_rather_than_echoed_whole() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="e" * 5000)

    with pytest.raises(AiError) as excinfo:
        ask(completer(handler))

    assert len(str(excinfo.value)) < 400

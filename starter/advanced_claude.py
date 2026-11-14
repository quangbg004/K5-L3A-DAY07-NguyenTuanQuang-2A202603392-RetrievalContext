"""Anthropic Messages client for WDR vision answers."""
import json
from time import perf_counter, sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MODEL = "claude-haiku-5-5"
SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"},
                   "citations": {"type": "array", "items": {"type": "string"}}},
    "required": ["answer", "citations"],
    "additionalProperties": False,
}


class Claude:
    def __init__(self, key):
        self.key = key

    def answer(self, system, content, events):
        body = {
            "model": MODEL, "max_tokens": 1200, "system": system,
            "messages": [{"role": "user", "content": content}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        }
        request = Request("https://api.anthropic.com/v1/messages", json.dumps(body).encode(), {
            "x-api-key": self.key, "anthropic-version": "2023-06-01", "content-type": "application/json",
        })
        for attempt in range(3):
            start = perf_counter()
            try:
                with urlopen(request, timeout=55) as response:
                    payload = json.load(response)
                break
            except HTTPError as exc:
                message = f"Anthropic HTTP {exc.code}"
                events.append({"event": "model_error", "error": message,
                               "elapsed_ms": (perf_counter() - start) * 1000})
                if exc.code not in (429, 500, 502, 503, 504, 529) or attempt == 2:
                    raise RuntimeError(message) from None
                retry_after = exc.headers.get("Retry-After", "")
                sleep(min(30, int(retry_after)) if retry_after.isdecimal() else 2 ** attempt)
            except (TimeoutError, URLError) as exc:
                raise RuntimeError(f"Anthropic connection failed: {type(exc).__name__}") from None
        usage = payload["usage"]
        input_tokens = usage["input_tokens"]
        output_tokens = usage["output_tokens"]
        # Standard global price for prompts below 100k, without prompt caching.
        cost = (input_tokens * .10 + output_tokens * .50) / 1_000_000
        events.append({"event": "model", "provider": "Anthropic", "model": payload["model"],
                       "id": payload["id"], "elapsed_ms": (perf_counter() - start) * 1000,
                       "usage": {"prompt_tokens": input_tokens, "completion_tokens": output_tokens,
                                 "cost": cost, "cost_basis": "estimated from Anthropic standard pricing"}})
        if payload["stop_reason"] != "end_turn":
            raise RuntimeError(f"Anthropic stopped: {payload['stop_reason']}")
        return json.loads("".join(block["text"] for block in payload["content"] if block["type"] == "text"))

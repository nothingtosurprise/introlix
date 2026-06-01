from typing import List, Dict, Any, Optional, AsyncGenerator, Union
from introlix.services.LLMState import LLMState
from introlix.config import SUPPORTED_LLMs

llm_state = LLMState()


async def cloud_llm_manager(
    model_name: str,
    provider: str,
    messages: List[Dict[str, Any]],
    stream: bool = False,
    tools: Optional[List[Dict[str, Any]]] = None,
) -> Union[str, AsyncGenerator[str, None]]:
    """
    Make a call to the LLM (AI Studio or OpenRouter) with given messages.

    When stream=True (or tools are provided), returns an async generator yielding
    JSON-encoded event strings:
      - {"type": "thinking",     "content": "..."}   — model reasoning (Gemini)
      - {"type": "tool_call",    "id": "...", "name": "...", "arguments": {...}}
      - {"type": "answer_chunk", "content": "..."}   — streaming text chunk

    When stream=False and no tools, returns a plain string (backward-compatible).

    Args:
        model_name: The name of the model to use.
        provider: The LLM provider (resolved from SUPPORTED_LLMs).
        messages: List of message dicts in OpenAI format.
        stream: Whether to stream the response. Defaults to False.
        tools: Optional list of tool definitions.
               When provided, stream=True is implied.

    Returns:
        str when stream=False and no tools.
        AsyncGenerator[str, None] when stream=True or tools are provided.
    """
    # Resolve provider from supported models list
    for supported in SUPPORTED_LLMs:
        if model_name == supported["value"]:
            provider = supported["provider"]
            break

    # When tools are provided, streaming is always used
    use_stream = stream or (tools is not None)

    if provider == "openrouter":
        if use_stream:
            return await llm_state.get_open_router(
                model_name=model_name,
                messages=messages,
                tools=tools,
            )
        else:
            # Non-streaming fallback (no tools) — uses requests directly
            import requests, json as _json
            from introlix.config import OPEN_ROUTER_KEY
            payload = {"model": model_name, "messages": messages, "stream": False}
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPEN_ROUTER_KEY}",
                    "Content-Type": "application/json",
                },
                data=_json.dumps(payload),
            )
            output = response.json()
            try:
                return output["choices"][0]["message"]["content"]
            except Exception:
                return str(output)

    elif provider == "google_ai_studio":
        if use_stream:
            return await llm_state.get_ai_studio(
                model_name=model_name,
                messages=messages,
                tools=tools,
            )
        else:
            # Non-streaming fallback (no tools) — uses google-genai directly
            from google import genai as _genai
            from google.genai import types as _types
            from introlix.config import GEMINI_API_KEY

            contents = []
            system_instruction = None
            for msg in messages:
                role = msg.get("role")
                content = msg.get("content")
                if role == "system":
                    system_instruction = content
                elif role == "user":
                    contents.append(
                        _types.Content(role="user", parts=[_types.Part.from_text(text=content)])
                    )
                elif role in ["assistant", "model"]:
                    contents.append(
                        _types.Content(role="model", parts=[_types.Part.from_text(text=content)])
                    )

            client = _genai.Client(api_key=GEMINI_API_KEY)
            config = _types.GenerateContentConfig(
                system_instruction=system_instruction,
            )
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            )
            return response.text

    else:
        raise ValueError(f"Unsupported provider: {provider}")

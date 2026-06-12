import asyncio
import json
from typing import List, Dict, Any, Optional, AsyncGenerator, Union
from introlix.services.LLMState import LLMState
from introlix.config import SUPPORTED_LLMs

llm_state = LLMState()


async def cloud_llm_manager(
    model_name: str,
    provider: str,
    messages: List[Dict[str, Any]],
    stream: bool = True,
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

async def local_llm_manager(
    model_name: str,
    messages: List[Dict[str, Any]],
    stream: bool = True,
    tools: Optional[List[Dict[str, Any]]] = None,
) -> AsyncGenerator[str, None]:
    """
    Make a call to a local llama.cpp model and stream the response token-by-token.

    Returns an async generator (matching the cloud_llm_manager contract) yielding
    JSON-encoded event strings:
      - {"type": "thinking",     "content": "..."}   — model reasoning
      - {"type": "tool_call",    "id": "...", "name": "...", "arguments": {...}}
      - {"type": "answer_chunk", "content": "..."}   — streaming text chunk

    llama.cpp is a sync C library. To get true token-by-token streaming inside
    an async FastAPI context without blocking the event loop, we run the sync
    iterator in a background thread and forward each chunk to the async generator
    via an asyncio.Queue + call_soon_threadsafe. This is the minimum necessary
    bridge between a sync producer and an async consumer.

    Args:
        model_name: The name of the local model to use.
        messages: List of message dicts in OpenAI format.
        stream: Whether to stream the response token-by-token. Defaults to True.
        tools: Optional list of tool definitions.
    """
    # load_model uses asyncio.Lock so it must be awaited
    if llm_state.llm is None:
        await llm_state.load_model(model_name)
    model = llm_state.llm

    if model is None:
        raise RuntimeError("Failed to load local llama model")

    _DONE = object()  # sentinel: signals the thread has finished
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def _produce():
        """Runs in a background thread. Pushes each llama.cpp chunk into the queue."""
        try:
            response = model.create_chat_completion(
                messages=messages,
                temperature=0.1,
                max_tokens=0,
                stream=stream,
                tools=tools,
                tool_choice="auto",
            )
            for chunk in response:
                # call_soon_threadsafe is the only safe way to talk to the event
                # loop from a non-async thread
                loop.call_soon_threadsafe(queue.put_nowait, chunk)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _DONE)

    async def _stream_generator():
        # Fire the producer thread — it runs concurrently with this generator
        producer = loop.run_in_executor(None, _produce)
        tool_calls_buffer: Dict[int, Dict] = {}

        while True:
            chunk = await queue.get()  # yields control to event loop between tokens
            if chunk is _DONE:
                break

            delta = chunk["choices"][0]["delta"]

            if delta.get("reasoning_content"):
                yield json.dumps({"type": "thinking", "content": delta["reasoning_content"]})

            elif delta.get("content"):
                yield json.dumps({"type": "answer_chunk", "content": delta["content"]})

            elif "tool_calls" in delta:
                for tool_call in delta["tool_calls"]:
                    index = tool_call["index"]
                    if index not in tool_calls_buffer:
                        tool_calls_buffer[index] = {
                            "id": tool_call.get("id") or f"local_call_{index}",
                            "name": tool_call.get("function", {}).get("name", ""),
                            "arguments": "",
                        }
                    fn = tool_call.get("function", {})
                    if "arguments" in fn:
                        tool_calls_buffer[index]["arguments"] += fn["arguments"]

        await producer  # wait for thread to fully clean up

        # Flush accumulated tool calls after stream ends
        for call in tool_calls_buffer.values():
            try:
                parsed_arguments = json.loads(call["arguments"]) if call["arguments"] else {}
            except json.JSONDecodeError:
                parsed_arguments = {}
            yield json.dumps({
                "type": "tool_call",
                "id": call["id"],
                "name": call["name"],
                "arguments": parsed_arguments,
            })

    return _stream_generator()
import json
import copy
from typing import List, Dict, Any, Optional, AsyncGenerator, Union
from introlix.services.LLMState import LLMState
from introlix.config import SUPPORTED_LLMs
from openai import AsyncOpenAI
from introlix.config import LLAMA_SERVER_PORT

llm_state = LLMState()

def sanitize_messages_for_openai(messages):
    sanitized = []
    for msg in messages:
        # Perform a deep copy so nested lists/dicts aren't mutated in your app state
        new_msg = copy.deepcopy(msg)
        
        if new_msg.get("role") == "assistant" and isinstance(new_msg.get("content"), list):
            text_pieces = []
            for item in new_msg["content"]:
                if item.get("type") in ["thought", "text"]:
                    text_pieces.append(item.get("text", ""))
            
            new_msg["content"] = "\n".join(text_pieces) if text_pieces else ""
            
        sanitized.append(new_msg)
    return sanitized

def messages_preprocess(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Preprocess messages to ensure they are in the correct format and remove any unnecessary fields before sending to the LLM.
    """
    processed_messages = []
    for msg in messages:
        # remove thinking fields
        if msg.get("role") == "assistant" if not isinstance(msg.get("content"), list) else False:
            answer_parts = []
            for item in msg.get("content").strip().split('\n'):
                if not item.strip():
                    continue
                try:
                    obj = json.loads(item)
                    if obj.get("type") == "answer_chunk":
                        answer_parts.append(obj["content"])
                except json.JSONDecodeError:
                    pass

            if answer_parts:
                msg = dict(msg)
                msg["content"] = ''.join(answer_parts)

        processed_messages.append(msg)
    return processed_messages


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

    # proprocess messages before sending to LLM
    messages = messages_preprocess(messages)

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

async def _local_llm_stream(
    client: AsyncOpenAI,
    model_name: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
) -> AsyncGenerator[str, None]:
    """Helper generator to stream local LLM tokens matching the event contract."""
    tool_calls_buffer: Dict[int, Dict] = {}

    try:
        response = await client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0.1,
            stream=True,
            tools=tools if tools else None,
            tool_choice="auto" if tools else None
        )

        async for chunk in response:
            if not chunk.choices:
                continue
                
            delta = chunk.choices[0].delta

            # Extract thinking process
            if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                yield json.dumps({"type": "thinking", "content": delta.reasoning_content})

            # Extract content chunks
            elif delta.content:
                yield json.dumps({"type": "answer_chunk", "content": delta.content})

            # Extract tool calls
            elif delta.tool_calls:
                for tool_call in delta.tool_calls:
                    index = tool_call.index
                    if index not in tool_calls_buffer:
                        tool_calls_buffer[index] = {
                            "id": tool_call.id or f"local_call_{index}",
                            "name": tool_call.function.name if tool_call.function else "",
                            "arguments": "",
                        }
                    if tool_call.function and tool_call.function.arguments:
                        tool_calls_buffer[index]["arguments"] += tool_call.function.arguments

    except Exception as e:
        raise RuntimeError(f"Error communicating with local OpenAI-compatible endpoint: {str(e)}")

    # Flush accumulated tool calls downstream after stream completes
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

async def local_llm_manager(
    model_name: str,
    messages: List[Dict[str, Any]],
    stream: bool = True,
    tools: Optional[List[Dict[str, Any]]] = None,
) -> Union[str, AsyncGenerator[str, None]]:
    """
    Make an HTTP call to the local llama-server instance and stream/return response.

    Args:
        model_name: The name of the local model to use.
        messages: List of message dicts in OpenAI format.
        stream: Whether to stream the response token-by-token. Defaults to True.
        tools: Optional list of tool definitions.
    """
    # load_model uses asyncio.Lock so it must be awaited
    if llm_state.llm is None or llm_state.llm.poll() is not None:
        await llm_state.load_model(model_name)

    # proprocess messages before sending to LLM
    messages = sanitize_messages_for_openai(messages)
    messages = messages_preprocess(messages)

    client = AsyncOpenAI(
        base_url=f"http://localhost:{LLAMA_SERVER_PORT}/v1", 
        api_key="local-llama"
    )

    use_stream = stream or (tools is not None)

    if use_stream:
        return _local_llm_stream(client, model_name, messages, tools)
    else:
        try:
            response = await client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.1,
                stream=False,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            raise RuntimeError(f"Error communicating with local OpenAI-compatible endpoint: {str(e)}")
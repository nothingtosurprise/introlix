"""
LLM State Management Service

This module provides a centralized service for managing Large Language Model (LLM) instances
and API interactions. It supports both local models (via llama.cpp) and cloud-based APIs
(Google AI Studio/Gemini and OpenRouter).

Key Features:
-------------
- Local model loading and management with llama.cpp
- GPU acceleration support with automatic memory management
- Cloud API integration (Google Gemini, OpenRouter)
- Native tool-calling via API (not via system prompt)
- Always-streaming response support
- Thread-safe model loading/unloading with async locks

Supported Providers:
-------------------
- Local: llama.cpp models (GGUF format)
- Google AI Studio: Gemini models
- OpenRouter: Various cloud models
"""

import os
import base64
import asyncio
import gc
import json
import httpx
from fastapi import HTTPException
from typing import Optional, AsyncGenerator, Union, List, Dict, Any, TYPE_CHECKING
from google import genai
from google.genai import types
from introlix.config import MODEL_SAVE_DIR, OPEN_ROUTER_KEY, GEMINI_API_KEY

if TYPE_CHECKING:
    from llama_cpp import Llama


class LLMState:
    """
    Manages LLM instances and API interactions for the application.

    This class provides a singleton-like state manager for LLMs, handling:
    - Loading and unloading of local llama.cpp models
    - API calls to Google Gemini and OpenRouter
    - Streaming responses with native tool-calling support
    - Memory management and GPU cache clearing

    Attributes:
        llm (Optional[Llama]): The currently loaded llama.cpp model instance.
        current_model_name (Optional[str]): Name of the currently loaded model.
        lock (asyncio.Lock): Async lock for thread-safe model operations.
    """

    def __init__(self):
        """
        Initialize the LLM state manager.
        """
        self.llm: Optional["Llama"] = None
        self.current_model_name: Optional[str] = None
        self.lock = asyncio.Lock()

    async def load_model(
        self, model_name: str, n_ctx: int = 2048, n_gpu_layers: int = 0
    ):
        """
        Load a local llama.cpp model from disk.

        Args:
            model_name (str): Name of the model file (must be in MODEL_SAVE_DIR).
            n_ctx (int): Context window size. Defaults to 2048.
            n_gpu_layers (int): Number of layers to offload to GPU. 0 = CPU only. Defaults to 0.

        Returns:
            dict: Status message and model name.

        Raises:
            HTTPException: 400 if model name is invalid.
            HTTPException: 404 if model file not found.
            HTTPException: 500 if model loading fails.
        """
        model_path = os.path.join(MODEL_SAVE_DIR, model_name)

        print(f"\n\n\nModel path is: {model_path}\n\n\n")

        if not os.path.basename(model_name) == model_name:
            print(f"Invalid model name: {model_name} of {os.path.basename(model_name)}")
            raise HTTPException(status_code=400, detail="Invalid model name")
        if not os.path.exists(model_path):
            raise HTTPException(
                status_code=404, detail=f"Model file {model_name} not found"
            )

        if self.current_model_name == model_name:
            return {"status": "Model already loaded", "model_name": model_name}

        async with self.lock:
            if self.llm is not None:
                del self.llm
                self.llm = None
                self.current_model_name = None
                gc.collect()
                if n_gpu_layers > 0:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()

            try:
                from llama_cpp import Llama
            except ImportError:
                raise HTTPException(
                    status_code=500,
                    detail="Local llama.cpp support is unavailable in this deployment."
                )

            try:
                self.llm = Llama(
                    model_path=model_path, n_ctx=n_ctx, n_gpu_layers=n_gpu_layers
                )
                self.current_model_name = model_name
                return {"status": "Model loaded", "model_name": model_name}
            except Exception as e:
                raise HTTPException(
                    status_code=500, detail=f"Error loading model: {str(e)}"
                )

    async def get_ai_studio(
        self,
        model_name: str,
        messages: list,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Get a streaming response from Google AI Studio API using the google-genai library.
        Always streams. Supports native tool-calling via the API.

        Tool calls are yielded as JSON chunks:
          {"type": "tool_call", "id": "...", "name": "...", "arguments": {...}}
        Thinking chunks:
          {"type": "thinking", "content": "..."}
        Answer chunks:
          {"type": "answer_chunk", "content": "..."}

        Args:
            model_name: Gemini model identifier.
            messages: Message list (system/user/assistant roles).
            tools: Optional list of tool definitions.
                   Each item: {"name": str, "description": str, "parameters": {...json schema...}}
        """
        contents = []
        system_instruction = None

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")

            if role == "system":
                system_instruction = content
            elif role == "user":
                if isinstance(content, str):
                    contents.append(
                        types.Content(
                            role="user",
                            parts=[types.Part.from_text(text=content)]
                        )
                    )
                elif isinstance(content, list):
                    # Content may be a list of parts (e.g. tool results)
                    parts = []
                    for part in content:
                        if part.get("type") == "tool_result":
                            parts.append(
                                types.Part.from_function_response(
                                    name=part["tool_use_id"],
                                    response={"result": part["content"]}
                                )
                            )
                        elif part.get("type") == "text":
                            parts.append(types.Part.from_text(text=part["text"]))
                    if parts:
                        contents.append(types.Content(role="user", parts=parts))
            elif role in ["assistant", "model"]:
                if isinstance(content, str) and content:
                    contents.append(
                        types.Content(
                            role="model",
                            parts=[types.Part.from_text(text=content)]
                        )
                    )
                elif isinstance(content, list):
                    # Tool calls from assistant in multi-turn
                    parts = []
                    for part in content:
                        if part.get("type") == "tool_use":
                            ts_b64 = part.get("thought_signature")
                            # Decode from base64 back to raw bytes for AI studio (https://ai.google.dev/gemini-api/docs/thought-signatures)
                            ts_bytes = base64.b64decode(ts_b64) if isinstance(ts_b64, str) else ts_b64
                            parts.append(
                                types.Part(
                                    function_call=types.FunctionCall(
                                        name=part["name"],
                                        args=part.get("input", {})
                                    ),
                                    thought_signature=ts_bytes
                                )
                            )
                        elif part.get("type") == "thought":
                            parts.append(
                                types.Part(
                                    text=part.get("text"),
                                    thought=True
                                )
                            )
                        elif part.get("type") == "text" and part.get("text"):
                            parts.append(types.Part.from_text(text=part["text"]))
                    if parts:
                        contents.append(types.Content(role="model", parts=parts))
            elif role == "tool":
                # Tool result message
                tool_name = msg.get("name", "tool")
                tool_content = msg.get("content", "")
                contents.append(
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_function_response(
                                name=tool_name,
                                response={"result": tool_content}
                            )
                        ]
                    )
                )

        client = genai.Client(api_key=GEMINI_API_KEY)

        # Build Gemini tools from tool definitions
        gemini_tools = None
        if tools:
            function_declarations = []
            for tool_def in tools:
                fn = tool_def.get("function", tool_def)  # handle both wrapped and plain
                # Copy params to avoid mutating the original tool definition dict
                params = dict(fn.get("parameters", {}))
                # Remove $schema and additionalProperties if present (Gemini doesn't accept them)
                params.pop("$schema", None)
                params.pop("additionalProperties", None)

                function_declarations.append(
                    types.FunctionDeclaration(
                        name=fn["name"],
                        description=fn.get("description", ""),
                        parameters=params if params else None,
                    )
                )
            gemini_tools = [types.Tool(function_declarations=function_declarations)]

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            thinking_config=types.ThinkingConfig(
                include_thoughts=True,
            ),
            tools=gemini_tools,
        )

        async def _stream_generator():
            response = await client.aio.models.generate_content_stream(
                model=model_name,
                contents=contents,
                config=config
            )
            async for chunk in response:
                if not chunk.candidates:
                    continue
                candidate = chunk.candidates[0]
                if not candidate.content or not candidate.content.parts:
                    continue
                for part in candidate.content.parts:
                    # Thinking parts
                    if part.thought and part.text:
                        yield json.dumps({"type": "thinking", "content": part.text})
                        continue
                    # Function call parts (native tool call)
                    if part.function_call:
                        fc = part.function_call
                        args = dict(fc.args) if fc.args else {}
                        ts = getattr(part, "thought_signature", None)
                        # thought_signature is raw binary — base64-encode for JSON transport
                        ts_b64 = base64.b64encode(ts).decode("ascii") if isinstance(ts, bytes) else ts
                        yield json.dumps({
                            "type": "tool_call",
                            "id": fc.name,  # Gemini uses name as id
                            "name": fc.name,
                            "arguments": args,
                            "thought_signature": ts_b64,
                        })
                        continue
                    # Text answer parts
                    if part.text:
                        yield json.dumps({"type": "answer_chunk", "content": part.text})

        return _stream_generator()

    async def get_open_router(
        self,
        model_name: str,
        messages: list,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Get a streaming response from OpenRouter API using httpx for async streaming.
        Always streams. Supports native tool-calling.

        Tool calls are yielded as JSON chunks:
          {"type": "tool_call", "id": "...", "name": "...", "arguments": {...}}
        Answer chunks:
          {"type": "answer_chunk", "content": "..."}

        Args:
            model_name: OpenRouter model identifier.
            messages: message list.
            tools: Optional list of tool definitions.
        """
        payload: Dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "stream": True,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        headers = {
            "Authorization": f"Bearer {OPEN_ROUTER_KEY}",
            "Content-Type": "application/json",
        }

        async def _stream_generator():
            # Accumulate tool call deltas per index
            tool_call_accum: Dict[int, Dict] = {}

            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload,
                ) as response:
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        if line.startswith("data: "):
                            data = line[6:]
                            if data == "[DONE]":
                                # Flush any accumulated tool calls
                                for idx in sorted(tool_call_accum.keys()):
                                    tc = tool_call_accum[idx]
                                    try:
                                        args = json.loads(tc.get("arguments", "{}"))
                                    except json.JSONDecodeError:
                                        args = {}
                                    yield json.dumps({
                                        "type": "tool_call",
                                        "id": tc.get("id", ""),
                                        "name": tc.get("name", ""),
                                        "arguments": args,
                                    })
                                break
                            try:
                                chunk = json.loads(data)
                                choices = chunk.get("choices", [])
                                if not choices:
                                    continue
                                delta = choices[0].get("delta", {})
                                finish_reason = choices[0].get("finish_reason")

                                # Accumulate tool call deltas
                                if delta.get("tool_calls"):
                                    for tc_delta in delta["tool_calls"]:
                                        idx = tc_delta.get("index", 0)
                                        if idx not in tool_call_accum:
                                            tool_call_accum[idx] = {
                                                "id": "",
                                                "name": "",
                                                "arguments": "",
                                            }
                                        if tc_delta.get("id"):
                                            tool_call_accum[idx]["id"] += tc_delta["id"]
                                        fn = tc_delta.get("function", {})
                                        if fn.get("name"):
                                            tool_call_accum[idx]["name"] += fn["name"]
                                        if fn.get("arguments"):
                                            tool_call_accum[idx]["arguments"] += fn["arguments"]

                                # Text content
                                content = delta.get("content")
                                if content:
                                    yield json.dumps({"type": "answer_chunk", "content": content})

                                # Flush tool calls when finish_reason is tool_calls
                                if finish_reason == "tool_calls":
                                    for idx in sorted(tool_call_accum.keys()):
                                        tc = tool_call_accum[idx]
                                        try:
                                            args = json.loads(tc.get("arguments", "{}"))
                                        except json.JSONDecodeError:
                                            args = {}
                                        yield json.dumps({
                                            "type": "tool_call",
                                            "id": tc.get("id", ""),
                                            "name": tc.get("name", ""),
                                            "arguments": args,
                                        })
                                    tool_call_accum = {}

                            except json.JSONDecodeError:
                                continue

        return _stream_generator()

    async def unload_model(self):
        """
        Unload the current local model and free memory.

        Returns:
            dict: Status message indicating success or if no model was loaded.
        """
        async with self.lock:
            if self.llm is None:
                return {"status": "No model loaded"}
            del self.llm
            self.llm = None
            self.current_model_name = None
            gc.collect()
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            return {"status": "Model unloaded"}

    def get_llm(self):
        """
        Get the current LLM instance.

        Returns:
            Llama: The currently loaded llama.cpp model instance.

        Raises:
            HTTPException: 500 if no model is currently loaded.
        """
        if self.llm is None:
            raise HTTPException(status_code=500, detail="No model loaded")
        return self.llm

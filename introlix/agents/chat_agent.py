"""
Conversational Chat Agent Module

This module provides the ChatAgent class, an intelligent conversational agent with
internet search capabilities. The agent can:

- Maintain conversation history across multiple turns
- Use search tools via native LLM tool-calling APIs (not via system prompt JSON hacking)
- Always stream responses in real-time
- Iterate through multiple tool-call rounds (up to max_iterations)

The ChatAgent passes tool definitions directly to the LLM API (AI Studio / OpenRouter),
receives native tool-call events from the stream, executes the requested tools, then
feeds results back into the conversation for the next iteration — all while streaming
the final answer to the caller.
"""

import json
from datetime import datetime
from typing import List, Optional, Dict, Any, AsyncGenerator

from introlix.agents.baseclass import AgentInput, BaseAgent, PromptTemplate, Tool
from introlix.agents.explorer_agent import ExplorerAgent
from introlix.llm_config import cloud_llm_manager
from introlix.prompts import chat_agent_prompt
from introlix.tools.tool_def import SEARCH_TOOL_DEF, FAST_SEARCH_TOOL_DEF
from ddgs import DDGS

ALL_TOOL_DEFS = [SEARCH_TOOL_DEF, FAST_SEARCH_TOOL_DEF]


class ChatAgent(BaseAgent):
    """
    An agent designed for conversational interactions with search capabilities.

    Uses native LLM tool-calling (passed via API) rather than embedding tool
    descriptions in the system prompt. Always streams responses. Supports
    multi-turn iteration: tool call → execute → feed result back → repeat.

    Attributes:
        unique_id (str): A unique identifier for the user or session.
        explorer (ExplorerAgent): The deep search agent used by the 'search' tool.
        instruction (str): The system prompt (clean, no tool JSON format).
        conversation_history (List[Dict]): The history of the conversation.
    """

    def __init__(
        self,
        unique_id: str,
        model: str,
        config: Optional[AgentInput] = None,
        max_iterations: int = 5,
        conversation_history: Optional[List[Dict]] = None,
    ):
        """
        Initialize the ChatAgent.

        Args:
            unique_id (str): Unique identifier for the session/user.
            model (str): The name of the LLM model to use.
            config (Optional[AgentInput]): Configuration for the agent.
            max_iterations (int): Maximum tool-call rounds. Defaults to 5.
            conversation_history (Optional[List[Dict]]): Existing conversation history.
        """
        if config is None:
            config = AgentInput(
                name="ChatAgent",
                description="An intelligent agent that can search and reason",
                tools=self._create_tools(),
            )
        super().__init__(model, config, max_iterations, conversation_history)

        self.unique_id = unique_id
        self.explorer = ExplorerAgent()

        self.instruction = chat_agent_prompt.strip().format(
            date=datetime.now().strftime("%Y-%m-%d"),
        )

    def _create_tools(self) -> List[Tool]:
        """
        Creates callable Tool objects for internal execution.

        Returns:
            List[Tool]: A list of Tool objects the agent can execute.
        """

        async def fast_search(queries: List[str] = None, query: str = None) -> str:
            """Fast search using DDGS."""
            if query is not None and queries is None:
                queries = [query]
            elif queries is None:
                return "Error: No search queries provided"

            ddgs_client = DDGS()
            results = []
            for q in queries:
                search_results = ddgs_client.text(q, max_results=5)
                results.append(f"Results for '{q}':\n" + "\n".join(str(search_results)))

            return "\n\n---\n\n".join(results)

        async def search(queries: List[str] = None, query: str = None) -> str:
            """Deep search using ExplorerAgent."""
            if query is not None and queries is None:
                queries = [query]
            elif queries is None:
                return "Error: No search queries provided"

            results = await self.explorer.run(
                queries=queries,
                unique_id=self.unique_id,
                get_answer=True,
                max_results=5,
            )

            print(f"\n\n\n{len(results)}\n\n\n")

            clean_results = [r.chunk_text for r in results if hasattr(r, 'chunk_text')]

            print(f"\n\n\n{len(" ".join(clean_results))}\n\n\n")

            return " ".join(clean_results)

        return [
            Tool(name="search", description="Deep internet search.", function=search),
            Tool(name="fast_search", description="Fast internet search.", function=fast_search),
        ]

    def _build_prompt(self, user_prompt: str, state: Dict[str, Any]) -> PromptTemplate:
        """Legacy method required by BaseAgent — not used by ChatAgent."""
        pass

    async def arun(self, user_prompt: str) -> AsyncGenerator[str, None]:
        """
        Runs the agent asynchronously with native tool-calling and always-on streaming.

        Flow:
        1. Build messages (system + conversation history + current user query).
        2. Call LLM with tools passed via API, stream=True always.
        3. Stream answer chunks directly to caller.
        4. Collect any tool_call events from the stream.
        5. Execute all requested tools.
        6. Append tool results to messages, yield tool status events to caller.
        7. Loop back to step 2 (up to max_iterations).
        8. If no tool calls in an iteration, answer is already streamed — done.

        Args:
            user_prompt (str): The user's input query.

        Yields:
            str: JSON-encoded event strings for the frontend:
                 - {"type": "thinking",     "content": "..."}
                 - {"type": "tool_calls_start", "tools": [...], "count": N}
                 - {"type": "tool_result",  "tool": "...", "content": "completed"|"error..."}
                 - {"type": "answer_chunk", "content": "..."}
        """
        # Build initial messages
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.instruction}
        ]

        # Add conversation history (last 10 messages)
        recent_history = (
            self.conversation_history[-10:]
            if len(self.conversation_history) > 10
            else self.conversation_history
        )
        for msg in recent_history:
            role = msg.get("role")
            content = msg.get("content")
            if role in ["user", "assistant"] and content:
                messages.append({"role": role, "content": content})

        # Add current user message
        messages.append({"role": "user", "content": user_prompt})

        for _ in range(self.max_iterations):
            stream = await self._call_llm_with_messages(
                messages=messages,
                cloud=True if self.CLOUD_PROVIDER else False,
                stream=True,
                tools=ALL_TOOL_DEFS,
            )

            # Consume stream: collect tool calls, stream answer chunks
            pending_tool_calls: List[Dict[str, Any]] = []
            assistant_text_parts: List[str] = []
            thinking_text_parts: List[str] = []

            async for raw_chunk in stream:
                # raw_chunk is a JSON string from LLMState
                try:
                    event = json.loads(raw_chunk)
                except json.JSONDecodeError:
                    # Forward as-is if not JSON
                    yield raw_chunk + "\n"
                    continue

                etype = event.get("type")

                if etype == "thinking":
                    thinking_text_parts.append(event["content"])
                    yield json.dumps({"type": "thinking", "content": event["content"]}) + "\n"

                elif etype == "tool_call":
                    pending_tool_calls.append(event)

                elif etype == "answer_chunk":
                    assistant_text_parts.append(event["content"])
                    yield json.dumps({"type": "answer_chunk", "content": event["content"]}) + "\n"

                else:
                    # Forward unknown event types unchanged
                    yield raw_chunk + "\n"

            # If no tool calls: answer is already streamed, we're done
            if not pending_tool_calls:
                # Append assistant message to messages for history consistency
                if assistant_text_parts:
                    messages.append({"role": "assistant", "content": "".join(assistant_text_parts)})
                break

            # Notify frontend which tools are running
            tool_names = [tc["name"] for tc in pending_tool_calls]
            yield json.dumps({
                "type": "tool_calls_start",
                "tools": tool_names,
                "count": len(tool_names),
            }) + "\n"

            # Add assistant message with tool call intent (for providers that need it)
            assistant_content = []
            if thinking_text_parts:
                assistant_content.append({
                    "type": "thought",
                    "text": "".join(thinking_text_parts)
                })

            for tc in pending_tool_calls:
                assistant_content.append({
                    "type": "tool_use",
                    "name": tc["name"],
                    "input": tc["arguments"],
                    "thought_signature": tc.get("thought_signature")
                })

            messages.append({
                "role": "assistant",
                "content": assistant_content,
                "tool_calls": [
                    {
                        "id": tc.get("id") or tc["name"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"]),
                        },
                    }
                    for tc in pending_tool_calls
                ]
            })

            # Execute each tool
            tool_result_messages: List[Dict[str, Any]] = []
            for tc in pending_tool_calls:
                tool_name = tc.get("name", "")
                tool_args = tc.get("arguments", {})

                tool_obj = next(
                    (t for t in self.config.tools if t.name == tool_name), None
                )

                if not tool_obj:
                    error_msg = f"Tool '{tool_name}' not found"
                    yield json.dumps({
                        "type": "tool_result",
                        "tool": tool_name,
                        "content": f"Error: {error_msg}",
                    }) + "\n"
                    tool_result_messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id") or tc["name"],
                        "name": tool_name,
                        "content": f"Error: {error_msg}",
                    })
                    continue

                try:
                    result = await tool_obj.execute(tool_args)
                    result_str = str(result)
                    stitched = result_str.replace('\n', '')
                    stitched = stitched.replace('\xa0', ' ') # Clean up the weird non-breaking space blocks
                    cleaned_result_str = " ".join(stitched.split())


                    yield json.dumps({
                        "type": "tool_result",
                        "tool": tool_name,
                        "content": "completed",
                    }) + "\n"
                    tool_result_messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id") or tc["name"],
                        "name": tool_name,
                        "content": cleaned_result_str,
                    })
                except Exception as e:
                    error_msg = f"Error: {str(e)}"
                    yield json.dumps({
                        "type": "tool_result",
                        "tool": tool_name,
                        "content": error_msg,
                    }) + "\n"
                    tool_result_messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id") or tc["name"],
                        "name": tool_name,
                        "content": error_msg,
                    })

            # Add tool results to messages for the next iteration
            messages.extend(tool_result_messages)


async def main():
    agent = ChatAgent(unique_id="user2545454", model="gemma-4-E2B-it-Q4_K_M.gguf")
    while True:
        prompt = input("You: ")
        if prompt.lower() in ["exit", "quit"]:
            break

        async for chunk in agent.arun(prompt):
            print(chunk, end="", flush=True)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

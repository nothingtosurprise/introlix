"""
Conversational Chat Agent Module

This module provides the ChatAgent class, an intelligent conversational agent with
internet search capabilities. The agent can:

- Maintain conversation history across multiple turns
- Use search tools to gather current information but for quick search that doesn't require comprehensive results it can use fast_search tool which uses DDGS
- Reason about whether it needs more information
- Stream responses back to users in real-time
- Make decisions about tool usage vs. direct answers

The ChatAgent is designed for interactive chat interfaces where users ask questions
and the agent provides informed, up-to-date answers by searching the web when needed.
"""

import json
from datetime import datetime
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, AsyncGenerator
from introlix.agents.baseclass import (
    AgentInput,
    BaseAgent,
    PromptTemplate,
    Tool,
)
from introlix.agents.explorer_agent import ExplorerAgent
from introlix.llm_config import cloud_llm_manager
from introlix.config import CLOUD_PROVIDER
from introlix.prompts import chat_agent_prompt
from ddgs import DDGS

class ToolCall(BaseModel):
    """Structured tool call from LLM"""

    name: str
    input: Dict[str, Any]


class AgentDecision(BaseModel):
    """LLM decision output"""

    type: str = Field(description="Action type: 'tool', 'final', or 'continue'")
    thought: Optional[str] = Field(default=None, description="Agent's reasoning")
    tool_calls: Optional[List[ToolCall]] = Field(
        default=None, description="Tools to call in parallel"
    )
    answer: Optional[str] = Field(
        default=None, description="Final answer if type is 'final'"
    )
    needs_more_info: Optional[bool] = Field(
        default=False, description="Whether more information is needed"
    )

class ChatAgent(BaseAgent):
    """
    An agent designed for conversational interactions with search capabilities.

    This agent can:
    1. Maintain conversation history.
    2. Use tools (specifically search or fast_search) to gather information.
    3. Reason about whether it needs more information or can answer directly.
    4. Stream its response back to the user.

    Attributes:
        unique_id (str): A unique identifier for the user or session.
        tools (List[Dict]): A list of tool definitions available to the agent.
        sys_prompt (str): The system prompt defining the agent's behavior and persona.
        conversation_history (List[Dict]): The history of the conversation.
    """

    def __init__(
        self,
        unique_id: str,
        model: str,
        config: Optional[AgentInput] = None,
        max_iterations=5,
        conversation_history: Optional[List[Dict]] = None,
    ):
        """
        Initialize the ChatAgent.

        Args:
            unique_id (str): Unique identifier for the session/user.
            model (str): The name of the LLM model to use.
            config (Optional[AgentInput]): Configuration for the agent. If None, a default config
                                           with search tools is created.
            max_iterations (int): Maximum number of reasoning/tool-use steps. Defaults to 5.
            conversation_history (Optional[List[Dict]]): Existing conversation history. Defaults to None.
        """

        if config is None:
            config = AgentInput(
                name="ChatAgent",
                description="An intelligent agent that can search and reason",
                tools=self._create_tools(),
            )
        super().__init__(model, config, max_iterations, conversation_history)

        self.unique_id = unique_id
        self.tools = [{"name": "search", "description": "Search on internet."}, {"name": "fast_search", "description": "A faster search tool using DDGS."}]

        self.explorer = ExplorerAgent()

        self.instruction = chat_agent_prompt.strip().format(
            date=datetime.now().strftime("%Y-%m-%d"), tools=self.tools, tools_info="\n".join([f"- {t['name']}: {t['description']}" for t in self.tools])
        )

    def _create_tools(self):
        """
        Creates the default tools for the agent, specifically the search tool.

        Returns:
            List[Tool]: A list of Tool objects available to the agent.
        """

        async def fast_search(queries: List[str] = None, query: str = None) -> str:
            """Search tool that accepts both 'queries' and 'query' for flexibility - FAST VERSION USING DDGS"""

            # Handle query format
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
            """Search tool that accepts both 'queries' and 'query' for flexibility"""

            # Handle query format
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

            return "\n\n---\n\n".join(str(results))

        return [
            Tool(
                name="search",
                description="Search the internet for information. Use this tool when you need current data or facts you don't know. IMPORTANT: Input must be a dictionary with 'queries' key containing a list of search queries. For single searches, pass one query in the list; for multiple searches, pass multiple queries. Examples: Single search: {'queries': ['weather in Paris']} | Multiple searches: {'queries': ['GPT-5 features', 'Gemini 2.5 features']} | Always use 'queries' (plural) not 'query'.",
                function=search,
            ),
            Tool(
                name="fast_search",
                description="A faster search tool using DDGS. Use this when you need a quick search result and can tolerate less comprehensive results. Input format is the same as 'search' tool.",
                function=fast_search,
            ),
        ]

    def _build_prompt(self, user_prompt: str, state: Dict[str, Any]) -> PromptTemplate:
        """
        Legacy method required by BaseAgent but not used in this implementation.

        The ChatAgent uses `_build_messages_array` instead to support chat history.
        """
        pass

    async def arun(self, user_prompt: str) -> AsyncGenerator[str, None]:
        """
        Runs the agent asynchronously, handling the reasoning loop and streaming the response.

        The process involves:
        1. Iterating up to `max_iterations`.
        2. Building messages and calling the LLM to get a decision (Action/Thought).
        3. Parsing the LLM's JSON output.
        4. Executing tools if requested.
        5. If the agent decides it has enough info (or hits max iterations), it generates a final answer.
        6. The final answer is streamed back to the caller.

        Args:
            user_prompt (str): The user's input query.

        Yields:
            str: Chunks of the response, including thoughts, tool status, and the final answer.
        """
        state = {"history": [], "tool_results": {}}

        for _ in range(self.max_iterations):
            messages = self._build_messages_array(user_prompt, state)

            # Call LLM (non-streaming for decision)
            raw_output = await self._call_llm_with_messages(
                messages=messages, stream=False
            )

            try:
                # Cleaning the raw_output
                raw_output = raw_output.strip()

                if "<｜begin▁of▁sentence｜>" in raw_output:
                    raw_output = raw_output.replace("<｜begin▁of▁sentence｜>", "")

                if "<｜end▁of▁sentence｜>" in raw_output:
                    raw_output = raw_output.replace("<｜end▁of▁sentence｜>", "")

                # Remove any trailing special characters
                raw_output = raw_output.strip().rstrip("<｜").rstrip("▁")

                # Extract JSON from markdown if present
                if "```json" in raw_output:
                    json_start = raw_output.find("```json") + 7
                    json_end = raw_output.find("```", json_start)
                    raw_output = raw_output[json_start:json_end].strip()
                elif "```" in raw_output:
                    json_start = raw_output.find("```") + 3
                    json_end = raw_output.find("```", json_start)
                    raw_output = raw_output[json_start:json_end].strip()
            except:
                pass

            # Parse decision
            try:
                decision = AgentDecision.model_validate_json(raw_output)
            except Exception as e:
                # Fallback parsing
                try:
                    decision_dict = json.loads(raw_output)
                    decision = AgentDecision(**decision_dict)
                except:
                    decision = AgentDecision(
                        type="final",
                        thought="",
                        answer=raw_output,
                    )

            # Show thought process
            if decision.thought:
                yield json.dumps(
                    {"type": "thinking", "content": decision.thought}
                ) + "\n"

            # Handle decision type
            if decision.type == "final":
                yield json.dumps(
                    {
                        "type": "answer",
                        "content": decision.answer,
                    }
                ) + "\n"
                break

            elif decision.type == "tool" and decision.tool_calls:
                yield json.dumps(
                    {
                        "type": "tool_calls_start",
                        "tools": [tc.name for tc in decision.tool_calls],
                        "count": len(decision.tool_calls),
                    }
                ) + "\n"
                for tc in decision.tool_calls:
                    tool = next(
                        (t for t in self.config.tools if t.name == tc.name), None
                    )
                    if not tool:
                        yield json.dumps(
                            {
                                "type": "error",
                                "content": f"Tool {tc.name} not found",
                            }
                        ) + "\n"
                        continue

                    try:
                        result = await tool.execute(tc.input)
                        state["tool_results"][tc.name] = result
                        yield json.dumps(
                            {
                                "type": "tool_result",
                                "tool": tc.name,
                                "content": "completed",
                            }
                        ) + "\n"
                    except Exception as e:
                        error_msg = f"Error: {str(e)}"
                        state["tool_results"][tc.name] = error_msg
                        yield json.dumps(
                            {
                                "type": "tool_result",
                                "tool": tc.name,
                                "content": error_msg,
                            }
                        ) + "\n"

            # If no more information needed
            if not decision.needs_more_info:
                # Phase 3: Generate final answer with streaming

                final_messages = [
                    {
                        "role": "system",
                        "content": "You are a helpful AI assistant. Provide a clear, comprehensive answer based on the search results and conversation context. In the end of answer always include source if the data is from search. If no source is given then don't give source at the end.",
                    }
                ]
                # Add conversation history
                recent_history = (
                    self.conversation_history[-10:]
                    if len(self.conversation_history) > 10
                    else self.conversation_history
                )
                for msg in recent_history:
                    role = msg.get("role")
                    content = msg.get("content")
                    if role in ["user", "assistant"] and content:
                        final_messages.append({"role": role, "content": content})

                # Add current query and tool results
                final_prompt_parts = [f"User asked: {user_prompt}\n"]
                final_prompt_parts.append("\nTool Results:")
                for tool_name, result in state["tool_results"].items():
                    final_prompt_parts.append(
                        f"\nOutput From {tool_name} Tool: {result}"
                    )

                final_prompt_parts.append(
                    "\n\nProvide a comprehensive answer to the user's question based on these search results and conversation history."
                )

                final_messages.append(
                    {"role": "user", "content": "\n".join(final_prompt_parts)}
                )

                # Stream the final response
                response_stream = await self._call_llm_with_messages(
                    final_messages, stream=True
                )

                async for chunk in response_stream:
                    if chunk.strip().startswith('{"type":'):
                        yield chunk + "\n"
                    else:
                        yield json.dumps({"type": "answer_chunk", "content": chunk}) + "\n"

                break


async def main():
    agent = ChatAgent(unique_id="user1", model="gemini-3.1-flash-lite")

    async for chunk in agent.arun("""Alice, Bob, and Carol each live in a different house on the same street: red, green, and blue.
The person who lives in the red house owns a cat.
Bob does not live in the green house.
Carol owns a dog.
The green house is to the left of the red house.
Alice does not own a cat.
Who lives in each house, and what pet do they own?"""):
        print(chunk, end="", flush=True)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())

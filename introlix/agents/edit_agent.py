"""
Document Editing Agent Module

This module provides the EditAgent class, a specialized agent for editing and writing
documents with internet search capabilities. Key features include:

- Document content modification based on user instructions
- Internet search integration for fact verification and new information
- Maintains complete document structure (returns full documents, not diffs)
- Special output format using <<<DOC_CONTENT>>> markers to avoid JSON parsing issues
- Support for various editing operations (rewriting, summarizing, expanding)

The EditAgent uses a unique approach where the JSON decision and document content
are separated, allowing it to handle large text blocks without JSON parsing errors.
"""

import json
from datetime import datetime
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from introlix.agents.baseclass import (
    AgentInput,
    BaseAgent,
    PromptTemplate,
    Tool,
)
from introlix.agents.explorer_agent import ExplorerAgent
from introlix.llm_config import cloud_llm_manager
from introlix.prompts import edit_agent_prompt
from introlix.tools.tool_def import SEARCH_TOOL_DEF, FAST_SEARCH_TOOL_DEF


class ToolCall(BaseModel):
    """
    Represents a structured tool call request from the LLM.

    Attributes:
        name (str): The name of the tool to call.
        input (Dict[str, Any]): The input parameters for the tool.
    """

    name: str
    input: Dict[str, Any]


class AgentDecision(BaseModel):
    """
    Represents the LLM's decision output for document editing.

    This model structures the agent's reasoning and next actions, including
    whether to use tools, continue processing, or finalize the edited document.

    Attributes:
        type (str): Action type - 'tool' (use a tool), 'final' (complete), or 'continue'.
        thought (Optional[str]): The agent's reasoning process.
        tool_calls (Optional[List[ToolCall]]): Tools to call in parallel if type is 'tool'.
        answer (Optional[str]): Final answer or placeholder if type is 'final'.
        needs_more_info (bool): Whether another iteration is needed for more information.
    """

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



class EditAgent(BaseAgent):
    """
    An intelligent agent specialized for editing and writing documents.

    The EditAgent modifies document content based on user instructions, with the ability
    to search the internet for facts or additional information when needed. It maintains
    the complete document structure and returns the full edited content.

    Key Features:
    1. Document editing (rewriting, summarizing, expanding)
    2. Internet search integration for fact verification
    3. Maintains document structure and formatting
    4. Returns complete documents (not diffs or patches)
    5. Uses native API tool-calling for search instead of embedding tool JSON in the prompt

    Attributes:
        unique_id (str): Unique identifier for the session/user.
        current_content (str): The current content of the document being edited.
        sys_prompt (str): The system prompt defining agent behavior.
        conversation_history (List[Dict]): History of the conversation for context.
    """

    def __init__(
        self,
        unique_id: str,
        model: str,
        current_content: str,
        config: Optional[AgentInput] = None,
        max_iterations=5,
        conversation_history: Optional[List[Dict]] = None,
        final_prompt: str = "",
    ):
        """
        Initialize the EditAgent.

        Args:
            unique_id (str): Unique identifier for the session/user.
            model (str): The name of the LLM model to use.
            current_content (str): The current document content to be edited.
            config (Optional[AgentInput]): Configuration for the agent. If None, a default config
                                           with search tools is created.
            max_iterations (int): Maximum number of reasoning/tool-use steps. Defaults to 5.
            conversation_history (Optional[List[Dict]]): Existing conversation history. Defaults to None.
        """

        if config is None:
            config = AgentInput(
                name="EditAgent",
                description="An intelligent agent that can edit documents",
                tools=self._create_tools(),
            )
        super().__init__(model, config, max_iterations, conversation_history)

        self.unique_id = unique_id
        self.current_content = current_content

        self.explorer = ExplorerAgent()

        self.instruction = edit_agent_prompt.strip().format(
            date=datetime.now().strftime("%Y-%m-%d"),
            final_prompt=final_prompt,
        )
        self.conversation_history = conversation_history or []

    EDIT_TOOL_DEFS = [SEARCH_TOOL_DEF, FAST_SEARCH_TOOL_DEF]

    def _create_tools(self):
        """
        Creates the default tools for the agent, specifically the search tool.

        The search tool uses the ExplorerAgent to perform internet searches and
        format results with topics, summaries, sources, and relevance scores.

        Returns:
            List[Tool]: A list of Tool objects available to the agent.
        """
        async def search(queries: List[str] = None, query: str = None) -> str:
            """
            Search tool that accepts both 'queries' (list) and 'query' (single string) for flexibility.

            Args:
                queries (List[str], optional): List of search queries to execute.
                query (str, optional): Single search query (converted to list internally).

            Returns:
                str: Formatted search results with topics, summaries, sources, and relevance scores.
            """

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
                function=search
            )
        ]

    def _build_prompt(self, user_prompt: str, state: Dict[str, Any]) -> PromptTemplate:
        """
        Legacy method required by BaseAgent but not used in this implementation.
        
        The EditAgent uses `_build_messages_array` instead to support conversation history.
        """
        pass

    async def run(self, user_prompt: str) -> str:
        """
        Executes the editing agent and returns the edited document content.

        This method uses native tool-calling through the cloud LLM API rather than
        embedding tool instructions inside the system prompt.

        Args:
            user_prompt (str): The user's editing instruction.

        Returns:
            str: The complete edited document content in markdown format.
        """
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

        # Provide current document content and user instruction to the model.
        messages.append(
            {
                "role": "user",
                "content": (
                    "CURRENT_CONTENT:\n" + self.current_content + "\n\n"
                    "USER_INSTRUCTION:\n" + user_prompt
                ),
            }
        )

        for _ in range(self.max_iterations):
            stream = await self._call_llm_with_messages(
                messages=messages,
                cloud=True if self.CLOUD_PROVIDER else False,
                stream=True,
                tools=self.EDIT_TOOL_DEFS,
            )
            # stream = await cloud_llm_manager(
            #     model_name=self.model,
            #     provider=self.CLOUD_PROVIDER,
            #     messages=messages,
            #     tools=self.EDIT_TOOL_DEFS,
            # )

            pending_tool_calls: List[Dict[str, Any]] = []
            assistant_text_parts: List[str] = []

            async for raw_chunk in stream:
                try:
                    event = json.loads(raw_chunk)
                except json.JSONDecodeError:
                    assistant_text_parts.append(raw_chunk)
                    continue
                
                # TODO: We want to show thinking in fronteend also tool call and document it so we will update it in future but for now we will just ignoring it
                event_type = event.get("type")
                if event_type == "thinking":
                    continue
                elif event_type == "tool_call":
                    pending_tool_calls.append(event)
                elif event_type == "answer_chunk":
                    assistant_text_parts.append(event.get("content", ""))
                else:
                    assistant_text_parts.append(raw_chunk)

            if not pending_tool_calls:
                return "".join(assistant_text_parts).strip()

            # TODO: Needs to show tool calls results in frontend also we will update it in future but for now we will just execute tool calls and add results to messages for next iteration
            for tc in pending_tool_calls:
                tool_name = tc.get("name", "")
                tool_args = tc.get("arguments", {})

                tool_obj = next(
                    (t for t in self.config.tools if t.name == tool_name),
                    None,
                )

                if not tool_obj:
                    error_str = f"Error: Tool '{tool_name}' not found"
                    messages.append(
                        {"role": "user", "content": f"[Tool: {tool_name}] {error_str}"}
                    )
                    continue

                try:
                    result = await tool_obj.execute(tool_args)
                    messages.append(
                        {
                            "role": "user",
                            "content": f"[Tool: {tool_name} result]\n{result}",
                        }
                    )
                except Exception as e:
                    messages.append(
                        {
                            "role": "user",
                            "content": f"[Tool: {tool_name}] Error: {str(e)}",
                        }
                    )

        return self.current_content

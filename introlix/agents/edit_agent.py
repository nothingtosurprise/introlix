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
from typing import List, Optional, Dict, Any, AsyncGenerator
from introlix.agents.baseclass import (
    AgentInput,
    BaseAgent,
    PromptTemplate,
    Tool,
)
from introlix.agents.explorer_agent import ExplorerAgent
from introlix.prompts import edit_agent_prompt


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
    5. Supports iterative refinement with tool usage

    The agent uses a special output format with <<<DOC_CONTENT>>> markers to separate
    the JSON decision from the actual document content, avoiding JSON parsing issues
    with large text blocks.

    Attributes:
        unique_id (str): Unique identifier for the session/user.
        current_content (str): The current content of the document being edited.
        tools (List[Dict]): Available tools (primarily search).
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
        self.tools = [{"name": "search", "description": "Search on internet."}]

        self.explorer = ExplorerAgent()

        self.instruction = edit_agent_prompt.strip().format(
            date=datetime.now().strftime("%Y-%m-%d"),
            tools=self.tools,
            tools_info="\n".join([f"- {t['name']}: {t['description']}" for t in self.tools]),
            final_prompt=final_prompt,
        )
        self.conversation_history = conversation_history or []

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
        

            results = await self.explorer.run(queries=queries, unique_id=self.unique_id, get_answer=True, max_results=5)
            
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

        This method orchestrates the entire editing workflow:
        1. Iterates up to `max_iterations` times
        2. Builds messages and calls the LLM for decisions
        3. Parses the response, extracting both JSON decision and document content
        4. Executes tools (search) if requested
        5. Returns the final edited document when type='final'

        The agent uses a special format where the document content is wrapped in
        <<<DOC_CONTENT>>> markers to avoid JSON parsing issues with large text.

        Args:
            user_prompt (str): The user's editing instruction.

        Returns:
            str: The complete edited document content in markdown format.

        Note:
            This overrides the generator-based arun from ChatAgent/BaseAgent to return
            a single string instead of streaming chunks.
        """
        state = {"history": [], "tool_results": {}}

        for iteration in range(self.max_iterations):
            messages = self._build_messages_array(user_prompt, state)

            # Call LLM (non-streaming for decision)
            raw_output = await self._call_llm_with_messages(messages=messages, stream=False)
            
            # Check for DOC_CONTENT block
            doc_content = None
            raw_output_json = raw_output
            
            if "<<<DOC_CONTENT>>>" in raw_output:
                parts = raw_output.split("<<<DOC_CONTENT>>>")
                if len(parts) >= 2:
                    # parts[0] is the JSON (hopefully)
                    # parts[1] is the content
                    raw_output_json = parts[0]
                    doc_content = parts[1].strip()
                    # If there's a closing tag, ignore what's after
                    if len(parts) > 2:
                         doc_content = parts[1].strip() # Take the middle part
            
            try:
                # Cleaning the raw_output_json
                raw_output_json = raw_output_json.strip()

                if '<｜begin of sentence｜>' in raw_output_json:
                    raw_output_json = raw_output_json.replace('<｜begin of sentence｜>', '')

                if '<｜end of sentence｜>' in raw_output_json:
                    raw_output_json = raw_output_json.replace('<｜end of sentence｜>', '')

                # Remove any trailing special characters
                raw_output_json = raw_output_json.strip().rstrip('<｜').rstrip(' ')

                # Extract JSON from markdown if present
                if "```json" in raw_output_json:
                    json_start = raw_output_json.find("```json") + 7
                    json_end = raw_output_json.find("```", json_start)
                    raw_output_json = raw_output_json[json_start:json_end].strip()
                elif "```" in raw_output_json:
                    json_start = raw_output_json.find("```") + 3
                    json_end = raw_output_json.find("```", json_start)
                    raw_output_json = raw_output_json[json_start:json_end].strip()
            except:
                pass
                
            # Parse decision
            try:
                decision = AgentDecision.model_validate_json(raw_output_json)
            except Exception as e:
                # Fallback parsing
                try:
                    decision_dict = json.loads(raw_output_json)
                    decision = AgentDecision(**decision_dict)
                except:
                    decision = AgentDecision(type="final", answer=raw_output_json)

            # Handle decision type
            if decision.type == "final":
                if doc_content:
                    return doc_content
                elif decision.answer and decision.answer != "See below":
                    return decision.answer
                else:
                    # Fallback if answer is missing or "See below" but no content block found
                    return self.current_content

            elif decision.type == "tool" and decision.tool_calls:
                for tc in decision.tool_calls:
                    tool = next(
                        (t for t in self.config.tools if t.name == tc.name), None
                    )
                    if not tool:
                        state["tool_results"][tc.name] = f"Tool {tc.name} not found"
                        continue

                    try:
                        result = await tool.execute(tc.input)
                        state["tool_results"][tc.name] = result
                    except Exception as e:
                        error_msg = f"Error: {str(e)}"
                        state["tool_results"][tc.name] = error_msg

            # If no more information needed but not final? Should not happen if logic is correct.
            if not decision.needs_more_info and decision.type != "final":
                 # Force final answer generation if it gets stuck?
                 pass
        
        return self.current_content # Fallback to original if failed

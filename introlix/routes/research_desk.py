"""
Research Desk Routes Module

This module provides REST API endpoints for managing research desk workflows within workspaces.
Research desks guide users through a multi-stage research process using AI agents.

Workflow Stages:
----------------
1. **initial** - Desk created, awaiting setup
2. **context_agent** - Gathering context and clarifying research scope
3. **planner_agent** - Creating research plan with topics and keywords
4. **approve_plan** - User review and approval of research plan
5. **explorer_agent** - Searching internet and gathering information
6. **complete** - Research data collected, ready for document creation

Endpoints:
----------
- POST /new - Create a new research desk
- PATCH /{desk_id}/setup - Initialize desk with title generation
- PATCH /{desk_id}/setup/context-agent - Gather context via AI agent
- PATCH /{desk_id}/setup/planner-agent - Generate research plan
- PATCH /{desk_id}/setup/planner-agent/edit - Edit/approve research plan
- PATCH /{desk_id}/setup/explorer-agent - Execute internet search
- PATCH /{desk_id}/docs - Add/update documents
- POST /{desk_id}/edit-doc - Edit document using AI
- POST /{desk_id}/chat - Chat about the research/document
- GET / - List all research desks in workspace
- GET /{desk_id} - Get specific research desk details

Features:
---------
- Multi-stage AI-guided research workflow
- Automatic title generation
- Context gathering with clarifying questions
- Research planning with topics and keywords
- Internet search integration
- Document editing with AI assistance
- Chat interface for Q&A about research
- Conversation history persistence
"""
import json
from datetime import datetime
import logging
from typing import List, Dict, Any
from types import GeneratorType
from fastapi import APIRouter, HTTPException, Query, Body, Depends
from fastapi.responses import StreamingResponse
from httpcore import request
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from introlix.models import (
    ResearchDesk,
    ResearchDeskRequest,
    ResearchDeskContextAgentRequest,
    EditDocRequest,
    Message,
    WorkspaceModel,
    ResearchDeskModel,
    UserModel
)
from introlix.schemas import PaginatedResponse
from introlix.utils.title_gen import generate_title
from introlix.utils.auth import get_current_user
from introlix.database import get_db, async_session_factory
from introlix.agents.context_agent import ContextAgent, ContextOutput, AgentInput
from introlix.agents.planner_agent import PlannerAgent
from introlix.agents.explorer_agent import ExplorerAgent
from introlix.agents.chat_agent import ChatAgent
from introlix.agents.edit_agent import EditAgent
from introlix.config import AUTO_MODEL

logger = logging.getLogger(__name__)

research_desk_router = APIRouter(
    prefix="/workspace/{workspace_id}/research-desk", tags=["research_desk"]
)

explorer_agent = ExplorerAgent()

@research_desk_router.post("/new")
async def create_research_desk(workspace_id: str, request: ResearchDesk, db: AsyncSession = Depends(get_db), current_user: UserModel = Depends(get_current_user)):
    """
    Creating a new research desk.

    Args:
        workspace_id (str): ID of the workspace containing the research desk
        request: (ResearchDesk): Data for new workspace.

    returns:
        message: Success message
        _id: Id for created research desk.

    Raises:
        HTTPException: 404 if Workspace not found
    """
    workspace_result = await db.execute(
        select(WorkspaceModel).where(WorkspaceModel.id == workspace_id)
    )

    workspace = workspace_result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to create research desk in this workspace")

    request.workspace_id = workspace_id
    request.state = "initial"
    item_dict = request.model_dump(exclude={"workspace_id", "created_at", "updated_at"})
    result = ResearchDeskModel(
        workspace_id=workspace_id,
        **item_dict
    )
    
    db.add(result)
    await db.commit()
    await db.refresh(result)
    
    return {"message": "Research Desk created", "_id": str(result.id)}


@research_desk_router.patch("/{desk_id}/setup")
async def setup_research_desk(
    workspace_id: str, desk_id: str, request: ResearchDeskRequest, db: AsyncSession = Depends(get_db), current_user: UserModel = Depends(get_current_user)
):
    """
    Preparing a already existing research desk by adding a new title based on the prompt.

    Args:
        workspace_id (str): ID of the workspace containing the research desk
        desk_id (str): ID of the research desk.
        request: (ResearchDeskRequest): Data for research desk setup.

    Return: 
        message: Success Message
    
    Raises:
        HTTPException: 404 if workspace not found
        HTTPException: 400 if desk is already setup
        HTTPException: 500 if setup fail
    """
    workspace_result = await db.execute(
        select(WorkspaceModel).where(WorkspaceModel.id == workspace_id)
    )
    workspace = workspace_result.scalar_one_or_none()

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    desk_result = await db.execute(
        select(ResearchDeskModel).where(
            ResearchDeskModel.id == desk_id,
            ResearchDeskModel.workspace_id == workspace_id
        ).where(ResearchDeskModel.workspace.has(WorkspaceModel.user_id == current_user.id))
    )
    desk_obj = desk_result.scalar_one_or_none()

    if not desk_obj:
        raise HTTPException(
            status_code=400, detail="Research Desk does not exist for this workspace"
        )

    if desk_obj.state != "initial":
        raise HTTPException(status_code=400, detail="Research Desk is already setup")

    # Create a title for the research desk if not provided
    if not desk_obj.title or desk_obj.title == "":
        try:
            new_title = await generate_title(request.prompt)
            desk_obj.title = new_title

            # Update the parent workspace's updated_at timestamp
            workspace.updated_at = datetime.now()
            
            await db.commit()
        except Exception as e:
            await db.rollback()
            raise HTTPException(status_code=500, detail="Setup failed")

    desk_obj.state = "context_agent"
    await db.commit()

    return {"message": "Research Desk set up"}


@research_desk_router.patch("/{desk_id}/setup/context-agent")
async def setup_research_desk_context_agent(
    workspace_id: str, 
    desk_id: str, 
    request: ResearchDeskContextAgentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    """
    Enhance user prompt using context agent before setting up research desk.
    
    The context agent asks clarifying questions to better understand the research
    scope and builds a more detailed prompt for the research process.
    
    Args:
        workspace_id (str): ID of the workspace containing the research desk
        desk_id (str): ID of the research desk to enhance
        request (ResearchDeskContextAgentRequest): Contains the user prompt, answers to previous questions, and model preference
        
    Returns:
        dict: Contains questions for user, move_next flag, confidence level,
              final prompt if ready, and updated state
              
    Raises:
        HTTPException: 404 if workspace/desk not found
        HTTPException: 400 if desk is not in 'context_agent' state
        HTTPException: 500 if context agent processing fails
    """
    workspace_result = await db.execute(
        select(WorkspaceModel).where(WorkspaceModel.id == workspace_id)
    )
    workspace = workspace_result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    desk_result = await db.execute(
        select(ResearchDeskModel).where(
            ResearchDeskModel.id == desk_id,
            ResearchDeskModel.workspace_id == workspace_id
        ).where(ResearchDeskModel.workspace.has(WorkspaceModel.user_id == current_user.id))
    )
    research_desk = desk_result.scalar_one_or_none()
    if not research_desk:
        raise HTTPException(status_code=404, detail="Research Desk not found")

    if research_desk.state != "context_agent":
        raise HTTPException(
            status_code=400,
            detail=f"Research Desk is in '{research_desk.state}' state, expected 'context_agent'",
        )

    model = AUTO_MODEL if request.model == "auto" else request.model

    # Extract conversation history from JSON/JSONB field safely
    conv_history = []
    if research_desk.context_agent and isinstance(research_desk.context_agent, dict):
        conv_history = research_desk.context_agent.get("conv_history", [])

    try:
        config = AgentInput(
            name="ContextAgent",
            description="Context gathering before research",
            output_type=ContextOutput,
        )

        context_agent = ContextAgent(config=config, conversation_history=conv_history, model=model)

        raw_output = await context_agent.process(
            query=request.prompt,
            answers=request.answers,
            research_scope=request.research_scope,
            user_files=request.user_files,
        )

        if isinstance(raw_output, GeneratorType):
            for update in raw_output:
                output = update
        else:
            output = raw_output

        print(f"/n/n/n{output}/n/n/n")
    except Exception as e:
        logger.error(f"Context agent failed for research desk {desk_id}: {e}")
        raise HTTPException(status_code=500, detail="Context agent processing failed")

    # Determine next state
    next_state = "planner_agent" if output.move_next and output.confidence_level > 0.7 and output.final_prompt else "context_agent"
    # Updating the conv_history list primitives
    conv_history.append({
        "role": "user",
        "content": request.prompt
    })

    if request.answers:
        conv_history.append({
            "role": "user", 
            "content": f"Answers to previous questions: {request.answers}"
        })

    conv_history.append({
        "role": "assistant",
        "content": json.dumps(output.model_dump())
    })

    # Apply updates directly to SQLAlchemy models
    research_desk.context_agent = {
        "conv_history": conv_history,
        "final_prompt": output.final_prompt,
        "research_parameters": output.research_parameters.model_dump(),
        "confidence_level": output.confidence_level,
        "questions": output.questions,
        "move_next": output.move_next,
        "timestamp": datetime.now().isoformat(),  # ISO string serialization representation for JSON fields
    }
    research_desk.state = next_state
    research_desk.updated_at = datetime.now()

    # Explicitly mark mutable JSON field as changed
    flag_modified(research_desk, "context_agent")

    workspace.updated_at = datetime.now()

    await db.commit()

    return {
        "questions": output.questions,
        "move_next": output.move_next,
        "confidence_level": output.confidence_level,
        "final_prompt": output.final_prompt if output.move_next else None,
        "research_parameters": (
            output.research_parameters.model_dump() if output.move_next else None
        ),
        "state": next_state,
    }


@research_desk_router.patch("/{desk_id}/setup/planner-agent")
async def setup_research_desk_planner_agent(
    workspace_id: str, 
    desk_id: str, 
    model: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    """
    Creating a dedicated plan for the research.
    
    The planner agent creates plan with keywords that will be searched on internet to find better articles/paper for the desk.
    
    Args:
        workspace_id (str): ID of the workspace containing the research desk
        desk_id (str): ID of the research desk to enhance
        model (str): Model to be used
        
    Returns:
        dict: Contains topic, priority, estimated_sources_needed and keywords.
              
    Raises:
        HTTPException: 404 if workspace/desk not found
        HTTPException: 400 if desk is not in 'planner_agent' state
        HTTPException: 500 if planner agent processing fails
    """

    workspace_result = await db.execute(
        select(WorkspaceModel).where(WorkspaceModel.id == workspace_id)
    )
    workspace = workspace_result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    desk_result = await db.execute(
        select(ResearchDeskModel).where(
            ResearchDeskModel.id == desk_id,
            ResearchDeskModel.workspace_id == workspace_id
        ).where(ResearchDeskModel.workspace.has(WorkspaceModel.user_id == current_user.id))
    )
    research_desk = desk_result.scalar_one_or_none()
    if not research_desk:
        raise HTTPException(status_code=404, detail="Research Desk not found")
    
    if research_desk.state != "planner_agent":
        raise HTTPException(
            status_code=400,
            detail=f"Research Desk is in '{research_desk.state}' state, expected 'planner_agent'",
        )

    model_to_use = AUTO_MODEL if model == "auto" else model

    # Getting enhanced prompt safely out of context_agent JSON field
    enriched_prompt = None
    if research_desk.context_agent and isinstance(research_desk.context_agent, dict):
        enriched_prompt = research_desk.context_agent.get("final_prompt")

    # Process with planner agent
    try:
        planner_agent = PlannerAgent(model_to_use)
        output = await planner_agent.create_research_plan(enriched_prompt)
    except Exception as e:
        logger.error(f"Planner agent failed for research desk {desk_id}: {e}")
        raise HTTPException(status_code=500, detail="Planner agent processing failed")

    next_state = "approve_plan"

    # Map output fields
    output_data = []
    for topic_item in output.result.topics:
        data = {
            "topic": topic_item.topic,
            "priority": topic_item.priority,
            "estimated_sources_needed": topic_item.estimated_sources_needed,
            "keywords": topic_item.keywords,
        }
        output_data.append(data)

    research_desk.planner_agent = {
        "topics": output_data
    }
    research_desk.state = next_state
    research_desk.updated_at = datetime.now()

    # Track mutated mutable properties
    flag_modified(research_desk, "planner_agent")

    workspace.updated_at = datetime.now()

    await db.commit()

    return {
        "topics": output_data,
        "state": next_state,
    }


@research_desk_router.patch("/{desk_id}/setup/planner-agent/edit")
async def edit_research_desk_planner_agent(
    workspace_id: str, 
    desk_id: str,
    topics: List[Dict[str, Any]] = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    """
    Edits the plan generated by planner agent.

    This is also used for confirming the plan generated by planner agent. When a plan is generated, the state becomes approve_plan rather
    than explorer_agent. So, the user can confirm the plan or edit it, and then confirm to move to explorer_agent.

    Args:
        workspace_id (str): ID of the workspace containing the research desk
        desk_id (str): ID of the research desk to enhance
        topics (List[Dict[str, Any]]): The edited data that will be saved in DB.

    Returns: 
        dict: contains topics, state and message.

    Raises:
        HTTPException: 404 if workspace/desk not found
        HTTPException: 400 if desk is not in 'approve_plan' state
    """

    workspace_result = await db.execute(
        select(WorkspaceModel).where(WorkspaceModel.id == workspace_id)
    )
    workspace = workspace_result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    desk_result = await db.execute(
        select(ResearchDeskModel).where(
            ResearchDeskModel.id == desk_id,
            ResearchDeskModel.workspace_id == workspace_id
        ).where(ResearchDeskModel.workspace.has(WorkspaceModel.user_id == current_user.id))
    )
    research_desk = desk_result.scalar_one_or_none()
    if not research_desk:
        raise HTTPException(status_code=404, detail="Research Desk not found")

    # Validate state - should be in approve_plan state
    if research_desk.state != "approve_plan":
        raise HTTPException(
            status_code=400,
            detail=f"Research Desk is in '{research_desk.state}' state, expected 'approve_plan'",
        )

    # Get existing topics out of JSON dictionary field safely
    planner_field = research_desk.planner_agent or {}
    existing_topics = planner_field.get("topics", [])
    
    data_changed = existing_topics != topics

    next_state = "explorer_agent"

    # Validate topics structure
    for topic in topics:
        if not all(key in topic for key in ["topic", "priority", "estimated_sources_needed", "keywords"]):
            raise HTTPException(
                status_code=400,
                detail="Each topic must have: topic, priority, estimated_sources_needed, and keywords"
            )

    updated_planner_agent = dict(planner_field)
    updated_planner_agent["topics"] = topics
    
    research_desk.planner_agent = updated_planner_agent
    research_desk.state = next_state
    research_desk.updated_at = datetime.now()

    # Track mutating mutable property structural change
    flag_modified(research_desk, "planner_agent")

    workspace.updated_at = datetime.now()

    await db.commit()

    return {
        "topics": topics,
        "state": next_state,
        "message": "Research plan updated successfully" if data_changed else "No changes detected, moving to explorer_agent"
    }

@research_desk_router.patch("/{desk_id}/setup/explorer-agent")
async def setup_research_desk_explorer_agent(
    workspace_id: str, 
    desk_id: str, 
    model: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    """
    Getting data from internet based on the keywords.

    The explorer agent gets data from internet based on the keywords and then stores it in the database.
    
    Args:
        workspace_id (str): ID of the workspace containing the research desk
        desk_id (str): ID of the research desk to enhance
        model (str): Model to be used
        
    Returns:
        dict: Contains status, code and message.
        
    Raises:
        HTTPException: 404 if workspace/desk not found
        HTTPException: 400 if desk is not in 'explorer_agent' state
        HTTPException: 500 if explorer agent processing fails
    """
    workspace_result = await db.execute(
        select(WorkspaceModel).where(WorkspaceModel.id == workspace_id)
    )
    workspace = workspace_result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    desk_result = await db.execute(
        select(ResearchDeskModel).where(
            ResearchDeskModel.id == desk_id,
            ResearchDeskModel.workspace_id == workspace_id
        ).where(ResearchDeskModel.workspace.has(WorkspaceModel.user_id == current_user.id))
    )
    research_desk = desk_result.scalar_one_or_none()
    if not research_desk:
        raise HTTPException(status_code=404, detail="Research Desk not found")
    
    if research_desk.state != "explorer_agent":
        raise HTTPException(
            status_code=400,
            detail=f"Research Desk is in '{research_desk.state}' state, expected 'explorer_agent'",
        )
    
    model_to_use = AUTO_MODEL if model == "auto" else model

    # Extract keywords safely from the JSON field layout
    keywords = []
    if research_desk.planner_agent and isinstance(research_desk.planner_agent, dict):
        topics = [
            x for x in research_desk.planner_agent.get("topics", []) 
            if x.get("priority") == "high"
        ]
        for topic in topics:
            keywords.extend(topic.get("keywords", []))
    
    if len(keywords) == 0:
        raise HTTPException(status_code=400, detail="No keywords found in the plan")

    try:
        await explorer_agent.run(queries=keywords[:20], unique_id=workspace_id, get_answer=False, max_results=5)
    except Exception as e:
        logger.error(f"Explorer agent failed for research desk {desk_id}: {e}")
        raise HTTPException(status_code=500, detail="Explorer agent processing failed")

    # Commit state changes
    research_desk.state = "complete"
    research_desk.updated_at = datetime.now()
    workspace.updated_at = datetime.now()

    await db.commit()
    
    return {"status": "success", "code": 200, "message": "Successfully got data from internet"}


@research_desk_router.patch("/{desk_id}/docs")
async def add_documents(
    workspace_id: str, 
    desk_id: str, 
    documents: dict,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    """
    Adding documents to the research desk.
    
    Args:
        workspace_id (str): ID of the workspace containing the research desk
        desk_id (str): ID of the research desk to enhance
        documents (dict): Contains the documents to be added
    """
    workspace_result = await db.execute(
        select(WorkspaceModel).where(WorkspaceModel.id == workspace_id)
    )
    workspace = workspace_result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    desk_result = await db.execute(
        select(ResearchDeskModel).where(
            ResearchDeskModel.id == desk_id,
            ResearchDeskModel.workspace_id == workspace_id
        ).where(ResearchDeskModel.workspace.has(WorkspaceModel.user_id == current_user.id))
    )
    desk = desk_result.scalar_one_or_none()
    if not desk:
        raise HTTPException(status_code=404, detail="Research Desk not found")

    desk.documents = documents
    desk.updated_at = datetime.now()
    workspace.updated_at = datetime.now()

    flag_modified(desk, "documents")
    await db.commit()

    return {"message": "Documents added to Research Desk"}


@research_desk_router.post("/{desk_id}/edit-doc")
async def edit_document(
    workspace_id: str, 
    desk_id: str, 
    request: EditDocRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    """
    Edit a document using an AI agent.
    
    Args:
        workspace_id (str): ID of the workspace
        desk_id (str): ID of the research desk
        request (EditDocRequest): Contains prompt, model
        
    Returns:
        dict: Status message
    """
    workspace_result = await db.execute(
        select(WorkspaceModel).where(WorkspaceModel.id == workspace_id)
    )
    workspace = workspace_result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    desk_result = await db.execute(
        select(ResearchDeskModel).where(
            ResearchDeskModel.id == desk_id,
            ResearchDeskModel.workspace_id == workspace_id
        ).where(ResearchDeskModel.workspace.has(WorkspaceModel.user_id == current_user.id))
    )
    research_desk = desk_result.scalar_one_or_none()
    if not research_desk:
        raise HTTPException(status_code=404, detail="Research Desk not found")

    model_to_use = AUTO_MODEL if request.model == "auto" else request.model

    # Extract parameters safely out of fields
    messages = list(research_desk.messages) if research_desk.messages else []
    current_docs = dict(research_desk.documents) if research_desk.documents else {}
    
    current_content = ""
    if current_docs and "document" in current_docs and "content" in current_docs["document"]:
        current_content = current_docs["document"]["content"]

    final_prompt = ""
    if research_desk.context_agent and isinstance(research_desk.context_agent, dict):
        final_prompt = research_desk.context_agent.get("final_prompt", "")

    edit_agent = EditAgent(
        unique_id=workspace_id,
        model=model_to_use,
        current_content=current_content,
        conversation_history=messages,
        final_prompt=final_prompt
    )

    try:
        new_content = await edit_agent.run(request.prompt)
        
        if isinstance(current_docs, dict) and "document" in current_docs:
            current_docs["document"]["content"] = new_content

        user_msg = Message(
            role="user",
            content=request.prompt,
            created_at=datetime.now()
        )

        assistant_info = (
            "I have updated the document based on your instructions."
            if new_content else
            "Fail to update the document based on your instructions."
        )

        assistant_msg = Message(
            role="assistant",
            content=assistant_info,
            created_at=datetime.now(),
            model=model_to_use
        )

        messages.append(user_msg.model_dump())
        messages.append(assistant_msg.model_dump())

        # Apply relational mutations
        research_desk.documents = current_docs
        research_desk.messages = messages
        research_desk.updated_at = datetime.now()
        workspace.updated_at = datetime.now()

        flag_modified(research_desk, "documents")
        flag_modified(research_desk, "messages")
        
        await db.commit()

        return {"status": "success", "message": "Document edited successfully"}

    except Exception as e:
        await db.rollback()
        logger.error(f"Edit agent failed for research desk {desk_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Edit agent failed: {str(e)}")

@research_desk_router.post('/{desk_id}/chat')
async def chat(
    workspace_id: str, 
    desk_id: str, 
    request: ResearchDeskRequest,
    current_user: UserModel = Depends(get_current_user)
):
    """
    Chat with AI about the research desk content.
    """
    # Initialize an atomic session scope for the validation phase
    async with async_session_factory() as db:
        workspace_result = await db.execute(
            select(WorkspaceModel).where(WorkspaceModel.id == workspace_id)
        )
        workspace = workspace_result.scalar_one_or_none()
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        desk_result = await db.execute(
            select(ResearchDeskModel).where(
                ResearchDeskModel.id == desk_id,
                ResearchDeskModel.workspace_id == workspace_id
            ).where(ResearchDeskModel.workspace.has(WorkspaceModel.user_id == current_user.id))
        )
        research_desk = desk_result.scalar_one_or_none()
        if not research_desk:
            raise HTTPException(status_code=404, detail="Research Desk not found")
        
        model_to_use = AUTO_MODEL if request.model == "auto" else request.model

        # Safe extraction out of JSON primitives
        messages = list(research_desk.messages) if research_desk.messages else []

        # Intercept and append structural context if it's the first message
        if not messages:
            final_prompt = ""
            if research_desk.context_agent and isinstance(research_desk.context_agent, dict):
                final_prompt = research_desk.context_agent.get("final_prompt", "")
            if final_prompt:
                request.prompt = f"Context: {final_prompt}\n\n{request.prompt}"

        current_docs = research_desk.documents or {}
        if current_docs and "document" in current_docs and "content" in current_docs["document"]:
            doc_content = current_docs["document"]["content"]
            request.prompt = f"Document Content: {doc_content}\n\nUser Question: {request.prompt}"

        user_message = Message(
            role="user",
            content=request.prompt,
            created_at=datetime.now()
        )

        # Mutate list reference locally and synchronize state updates
        messages.append(user_message.model_dump())
        research_desk.messages = messages
        research_desk.updated_at = datetime.now()
        workspace.updated_at = datetime.now()

        flag_modified(research_desk, "messages")
        await db.commit()

        chat_agent = ChatAgent(
            unique_id=workspace_id,
            model=model_to_use,
            conversation_history=messages[:-1] # History prior to this message injection
        )

    # Independent streaming background generator worker process
    async def stream():
        assistant_content = ""
        async for chunk in chat_agent.arun(request.prompt):
            try:
                event = json.loads(chunk)
                if event.get("type") == "answer_chunk":
                    assistant_content += event.get("content", "")
            except json.JSONDecodeError:
                # Treat the chunk as plain text if it's not valid JSON
                assistant_content += chunk
            yield chunk

        # Spawn a localized background connection task loop to write trailing response data
        async with async_session_factory() as background_db:
            # Re-fetch records inside the background thread transaction loop safely
            bg_desk = await background_db.get(ResearchDeskModel, desk_id)
            if bg_desk:
                bg_messages = list(bg_desk.messages) if bg_desk.messages else []
                
                assistant_message = Message(
                    role="assistant",
                    content=assistant_content,
                    created_at=datetime.now(),
                    model=model_to_use
                )
                bg_messages.append(assistant_message.model_dump())
                
                bg_desk.messages = bg_messages
                bg_desk.updated_at = datetime.now()
                
                flag_modified(bg_desk, "messages")
                await background_db.commit()
            
    return StreamingResponse(stream(), media_type="text/plain")


@research_desk_router.get("/", response_model=PaginatedResponse)
async def get_desks(
    workspace_id: str, 
    page: int = Query(1, ge=1), 
    limit: int = Query(10, ge=1),
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    """
    For getting list of research desks that exist in a workspace.
    """
    workspace_result = await db.execute(
        select(WorkspaceModel).where(WorkspaceModel.id == workspace_id)
    )
    workspace = workspace_result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Handle paginated index retrieval (selecting only explicit columns needed)
    desks_query = (
        select(
            ResearchDeskModel.id,
            ResearchDeskModel.workspace_id,
            ResearchDeskModel.created_at,
            ResearchDeskModel.title,
            ResearchDeskModel.updated_at
        )
        .where(ResearchDeskModel.workspace_id == workspace_id)
        .where(ResearchDeskModel.workspace.has(WorkspaceModel.user_id == current_user.id))
        .order_by(desc(ResearchDeskModel.updated_at))
        .offset((page - 1) * limit)
        .limit(limit)
    )
    
    desks_result = await db.execute(desks_query)
    
    # Map raw rows safely into structured dict objects
    desks_list = []
    for row in desks_result.mappings():
        desks_list.append({
            "id": str(row["id"]),
            "workspace_id": str(row["workspace_id"]),
            "created_at": row["created_at"],
            "title": row["title"],
            "updated_at": row["updated_at"]
        })

    return {"items": desks_list, "page": page, "limit": limit, "has_next": len(desks_list) == limit}


@research_desk_router.get("/{desk_id}")
async def get_desk(
    workspace_id: str, 
    desk_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    """
    For getting a specific research desk by its ID.
    """
    workspace_result = await db.execute(
        select(WorkspaceModel).where(WorkspaceModel.id == workspace_id)
    )
    workspace = workspace_result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    desk_result = await db.execute(
        select(ResearchDeskModel).where(
            ResearchDeskModel.id == desk_id,
            ResearchDeskModel.workspace_id == workspace_id
        ).where(ResearchDeskModel.workspace.has(WorkspaceModel.user_id == current_user.id))
    )
    desk = desk_result.scalar_one_or_none()

    if not desk:
        raise HTTPException(status_code=404, detail="Research Desk not found")

    return {
        "id": str(desk.id),
        "workspace_id": str(desk.workspace_id),
        "title": desk.title,
        "state": desk.state,
        "context_agent": desk.context_agent,
        "planner_agent": desk.planner_agent,
        "documents": desk.documents,
        "messages": desk.messages,
        "created_at": desk.created_at,
        "updated_at": desk.updated_at
    }
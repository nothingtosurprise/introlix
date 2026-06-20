"""
Chat Routes Module

This module provides REST API endpoints for managing chat conversations within workspaces.
It handles chat creation, message streaming, chat retrieval, and deletion.

Endpoints:
----------
- POST /workspace/{workspace_id}/chat/new - Create a new chat
- POST /workspace/{workspace_id}/chat/{chat_id}/ - Send a message and get streaming response
- GET /workspace/{workspace_id}/chat/{chat_id}/ - Retrieve chat history
- DELETE /workspace/{workspace_id}/chat/{chat_id}/ - Delete a chat
"""

from datetime import datetime
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from introlix.database import get_db, async_session_factory
from introlix.agents.chat_agent import ChatAgent
from introlix.models import (
    WorkspaceChat,
    Message,
    WorkspaceModel,
    WorkspaceChatModel,
    ChatRequest,
)
from introlix.config import AUTO_MODEL
from introlix.utils.title_gen import generate_title
from introlix.utils.auth import get_current_user
from introlix.models import UserModel

chat_router = APIRouter(prefix="/workspace/{workspace_id}/chat", tags=["chat"])


@chat_router.post("/new")
async def create_chat(
    workspace_id: str, request: WorkspaceChat, db: AsyncSession = Depends(get_db), current_user: UserModel = Depends(get_current_user)
):
    """
    Create a new chat conversation in a workspace.

    This endpoint initializes a new chat session within the specified workspace.
    The chat starts with an empty message history and can be used for subsequent
    message exchanges.
    """
    workspace_result = await db.execute(
        select(WorkspaceModel).where(WorkspaceModel.id == workspace_id)
    )
    workspace = workspace_result.scalar_one_or_none()

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    
    if workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to create chat in this workspace")

    request.workspace_id = workspace_id

    if len(request.messages) > 0:
        raise HTTPException(
            status_code=400, detail="New chat cannot have pre-existing messages"
        )

    item_dict = request.model_dump(exclude={"title", "id", "created_at", "updated_at"})
    result = WorkspaceChatModel(title="New Chat", **item_dict)
    db.add(result)
    await db.commit()
    await db.refresh(result)
    # Update parent workspace updated_at to reflect new chat
    await db.execute(
        update(WorkspaceModel)
        .where(WorkspaceModel.id == workspace_id)
        .values(updated_at=datetime.now())
    )
    await db.commit()
    return {"message": "Chat created", "_id": str(result.id)}


@chat_router.post("/{chat_id}/")
async def chat(
    workspace_id: str,
    chat_id: str,
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """
    Send a message to a chat and receive a streaming response.
    """
    result = await db.execute(
        select(WorkspaceChatModel).where(
            WorkspaceChatModel.id == chat_id,
            WorkspaceChatModel.workspace_id == workspace_id,
            WorkspaceChatModel.workspace.has(WorkspaceModel.user_id == current_user.id)
        )
    )

    chat = result.scalar_one_or_none()

    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    title = chat.title

    if not title or title == "New Chat":
        # Title is missing, set it
        new_title = await generate_title(request.prompt)

        await db.execute(
            update(WorkspaceChatModel)
            .where(
                WorkspaceChatModel.id == chat_id,
                WorkspaceChatModel.workspace_id == workspace_id,
            )
            .values(title=new_title)
        )
        await db.commit()
        await db.refresh(chat)

    if request.model == "auto":
        model = AUTO_MODEL
    else:
        model = request.model

    # Create user message
    user_message = Message(
        role="user", content=request.prompt, created_at=datetime.now()
    )

    # Add user message to database
    updated_messages = (
        chat.messages + [user_message.model_dump(mode="json")]
        if chat.messages
        else [user_message.model_dump(mode="json")]
    )
    chat.messages = updated_messages
    chat.updated_at = datetime.now()
    flag_modified(
        chat, "messages"
    )  # Inform SQLAlchemy that the messages field has been modified

    await db.commit()
    # bump parent workspace updated_at when user message is saved
    await db.execute(
        update(WorkspaceModel)
        .where(WorkspaceModel.id == workspace_id)
        .values(updated_at=datetime.now())
    )
    await db.commit()

    # Initialize chat agent with history
    chat_agent = ChatAgent(
        unique_id=workspace_id,  # This takes workspace_id as data are shared in between workspace
        model=model,
        conversation_history=updated_messages[
            :-1
        ],  # Exclude the current user message from history as it will be passed as prompt
    )

    if request.search:
        user_prompt = f"{request.prompt}\nSearch on the internet. Using fast_search or search tool if necessary. Only use search tool if big search needs to be done, as it is slower than fast_search."
    else:
        user_prompt = request.prompt

    # Collect assistant response
    assistant_content = ""

    async def stream():
        nonlocal assistant_content
        async for chunk in chat_agent.arun(user_prompt):
            assistant_content += chunk
            yield chunk

        # After streaming completes, save assistant message
        async with async_session_factory() as session:
            result = await session.execute(
                select(WorkspaceChatModel).where(
                    WorkspaceChatModel.id == chat_id,
                    WorkspaceChatModel.workspace_id == workspace_id,
                )
            )
            new_chat = result.scalar_one_or_none()

            if new_chat:
                assistant_message = Message(
                    role="assistant",
                    content=assistant_content,
                    created_at=datetime.now(),
                    model=model,
                )

                new_chat.messages = (
                    new_chat.messages + [assistant_message.model_dump(mode="json")]
                    if new_chat.messages
                    else [assistant_message.model_dump(mode="json")]
                )
                new_chat.updated_at = datetime.now()
                flag_modified(new_chat, "messages")
                await session.commit()
                # bump parent workspace updated_at when assistant message saved
                await session.execute(
                    update(WorkspaceModel)
                    .where(WorkspaceModel.id == workspace_id)
                    .values(updated_at=datetime.now())
                )
                await session.commit()

    return StreamingResponse(stream(), media_type="text/plain")


@chat_router.get("/{chat_id}/")
async def get_chat(chat_id: str, db: AsyncSession = Depends(get_db), current_user: UserModel = Depends(get_current_user)):
    """
    Retrieve all messages from a chat conversation.

    This endpoint fetches the complete chat history including all messages,
    metadata, and timestamps.
    """
    query = select(WorkspaceChatModel).where(WorkspaceChatModel.id == chat_id).where(WorkspaceChatModel.workspace.has(WorkspaceModel.user_id == current_user.id))
    result = await db.execute(query)
    chat = result.scalar_one_or_none()

    if not chat:
        return "No Chat Found"
    return WorkspaceChat.model_validate(chat)


@chat_router.delete("/{chat_id}/")
async def delete_chat(chat_id: str, db: AsyncSession = Depends(get_db), current_user: UserModel = Depends(get_current_user)):
    """
    Delete a chat conversation and its entire history.

    This endpoint permanently removes a chat and all its associated messages
    from the database. This action cannot be undone.
    """
    query = select(WorkspaceChatModel).where(WorkspaceChatModel.id == chat_id).where(WorkspaceChatModel.workspace.has(WorkspaceModel.user_id == current_user.id))
    result = await db.execute(query)
    chat = result.scalar_one_or_none()

    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    await db.delete(chat)
    await db.commit()

    return {"message": "Chat deleted successfully"}

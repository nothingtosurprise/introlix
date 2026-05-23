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

Features:
---------
- Automatic title generation for new chats
- Streaming responses for real-time user experience
- Conversation history persistence
- Integration with ChatAgent for intelligent responses
- Optional internet search capability
- Model selection (auto or specific model)
"""

import json
from datetime import datetime
from httpcore import request
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

chat_router = APIRouter(prefix="/workspace/{workspace_id}/chat", tags=["chat"])


@chat_router.post("/new")
async def create_chat(
    workspace_id: str, request: WorkspaceChat, db: AsyncSession = Depends(get_db)
):
    """
    Create a new chat conversation in a workspace.

    This endpoint initializes a new chat session within the specified workspace.
    The chat starts with an empty message history and can be used for subsequent
    message exchanges.

    Args:
        workspace_id (str): The unique identifier of the workspace.
        request (WorkspaceChat): The chat creation request containing initial chat data.

    Returns:
        dict: A dictionary containing:
            - message (str): Success message
            - _id (str): The unique identifier of the created chat

    Raises:
        HTTPException: 404 if the workspace is not found.

    Example:
        POST /workspace/123/chat/new
        Body: {"title": "My Chat"}
        Response: {"message": "Chat created", "_id": "abc123"}
    """
    workspace = await db.execute(
        select(WorkspaceModel).where(WorkspaceModel.id == workspace_id)
    )

    if not workspace.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Workspace not found")

    request.workspace_id = workspace_id

    if len(request.messages) > 0:
        raise HTTPException(
            status_code=400, detail="New chat cannot have pre-existing messages"
        )

    item_dict = request.model_dump(exclude={"title", "id"})
    result = WorkspaceChatModel(title="New Chat", **item_dict)
    db.add(result)
    await db.commit()
    await db.refresh(result)
    return {"message": "Chat created", "_id": str(result.id)}


@chat_router.post("/{chat_id}/")
async def chat(
    workspace_id: str,
    chat_id: str,
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Send a message to a chat and receive a streaming response.

    This endpoint handles the main chat interaction:
    1. Validates the chat exists
    2. Generates a title if this is the first message
    3. Saves the user message to the database
    4. Initializes the ChatAgent with conversation history
    5. Streams the AI response back to the client
    6. Saves the assistant's response to the database

    Args:
        workspace_id (str): The unique identifier of the workspace.
        chat_id (str): The unique identifier of the chat.
        request (ChatRequest): The chat request containing:
            - prompt (str): The user's message
            - model (str): The model to use ("auto" or specific model name)
            - search (bool): Whether to enable internet search

    Returns:
        StreamingResponse: A streaming response containing the AI's reply in real-time.

    Raises:
        HTTPException: 404 if the chat is not found.

    Features:
        - Automatic title generation for new chats
        - Conversation history persistence
        - Real-time streaming responses
        - Optional internet search integration
        - Automatic model selection when "auto" is specified

    Example:
        POST /workspace/123/chat/abc/
        Body: {"prompt": "Hello", "model": "auto", "search": false}
        Response: Streaming text response from the AI
    """
    result = await db.execute(
        select(WorkspaceChatModel).where(
            WorkspaceChatModel.id == chat_id,
            WorkspaceChatModel.workspace_id == workspace_id,
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
    flag_modified(
        chat, "messages"
    )  # Inform SQLAlchemy that the messages field has been modified

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
        user_prompt = f"{request.prompt}\nSearch on the internet."
    else:
        user_prompt = request.prompt

    # Collect assistant response
    assistant_content = ""

    async def stream():
        nonlocal assistant_content
        async for chunk in chat_agent.arun(user_prompt):
            try:
                if json.loads(chunk).get("type") == "answer_chunk":
                    assistant_content += json.loads(chunk).get("content", "")
                else:
                    assistant_content += chunk
            except json.JSONDecodeError:
                # Treat the chunk as plain text if it's not valid JSON
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
                flag_modified(new_chat, "messages")
                await session.commit()

    return StreamingResponse(stream(), media_type="text/plain")


@chat_router.get("/{chat_id}/")
async def get_chat(chat_id: str, db: AsyncSession = Depends(get_db)):
    """
    Retrieve all messages from a chat conversation.

    This endpoint fetches the complete chat history including all messages,
    metadata, and timestamps.

    Args:
        chat_id (str): The unique identifier of the chat.

    Returns:
        dict: The serialized chat document containing:
            - _id (str): Chat identifier
            - workspace_id (str): Associated workspace
            - title (str): Chat title
            - messages (list): Array of message objects
            - created_at (datetime): Chat creation timestamp
            - updated_at (datetime): Last update timestamp
        str: "No Chat Found" if the chat doesn't exist

    Example:
        GET /workspace/123/chat/abc/
        Response: {"_id": "abc", "title": "My Chat", "messages": [...]}
    """
    query = select(WorkspaceChatModel).where(WorkspaceChatModel.id == chat_id)
    result = await db.execute(query)
    chat = result.scalar_one_or_none()

    if not chat:
        return "No Chat Found"
    return WorkspaceChat.model_validate(chat)


@chat_router.delete("/{chat_id}/")
async def delete_chat(chat_id: str, db: AsyncSession = Depends(get_db)):
    """
    Delete a chat conversation and its entire history.

    This endpoint permanently removes a chat and all its associated messages
    from the database. This action cannot be undone.

    Args:
        chat_id (str): The unique identifier of the chat to delete.

    Returns:
        dict: A dictionary containing:
            - message (str): Success confirmation message

    Raises:
        HTTPException: 404 if the chat is not found.

    Example:
        DELETE /workspace/123/chat/abc/
        Response: {"message": "Chat deleted successfully"}
    """
    query = select(WorkspaceChatModel).where(WorkspaceChatModel.id == chat_id)
    result = await db.execute(query)
    chat = result.scalar_one_or_none()

    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    await db.delete(chat)
    await db.commit()

    return {"message": "Chat deleted successfully"}

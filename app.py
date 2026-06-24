import chromadb
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, literal_column, desc, delete
from introlix.database import get_db, init_db
from introlix.utils.auth import get_current_user
from introlix.routes.auth import router as auth_router
from fastapi import FastAPI, HTTPException, Query, Depends
from introlix.models import (
    Workspace,
    WorkspaceModel,
    WorkspaceChatModel,
    ResearchDeskModel,
    UserModel,
)
from introlix.schemas import PaginatedResponse
from introlix.routes.chat import chat_router
from introlix.routes.services import router as services_router
from introlix.tools.web_crawler import get_httpx_client, get_shared_context, shutdown
from introlix.routes.research_desk import research_desk_router
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from introlix.state import app_state
from introlix.config import SUPPORTED_LLMs, CHROMA_DB_DIR
from sentence_transformers import SentenceTransformer


@asynccontextmanager
async def lifespan(app: FastAPI):
    # adding embedding model and pinecone client to app state
    app_state.embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    await init_db()

    # explorer agent setup
    await get_httpx_client()
    await get_shared_context()
    yield
    await shutdown()  # Shutdown the HTTPX client and browser when the app stops


app = FastAPI(title="Introlix", openapi_prefix="/api/v1", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=[
        "Content-Type",
        "X-API-Key",
        "Authorization",
    ],
)


# list of supported LLMs
@app.get("/llms", tags=["llms"])
def get_supported_llms():
    return {"items": SUPPORTED_LLMs}


# workspace endpoints
@app.post("/workspaces", response_model=Workspace, tags=["workspace"])
async def create_workspace(
    workspace: Workspace,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    workspace.user_id = (
        current_user.id
    )  # Ensure the workspace is associated with the current user
    workspace_data = workspace.model_dump(exclude={"id", "created_at", "updated_at"}, exclude_none=True)

    new_workspace = WorkspaceModel(**workspace_data)
    db.add(new_workspace)
    await db.commit()
    await db.refresh(new_workspace)

    return Workspace.model_validate(new_workspace)


@app.get("/workspaces", response_model=PaginatedResponse, tags=["workspace"])
async def get_workspaces(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1),
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    skip = (page - 1) * limit
    query = (
        select(WorkspaceModel)
        .where(WorkspaceModel.user_id == current_user.id)
        .order_by(desc(WorkspaceModel.updated_at))
        .limit(limit + 1)
        .offset(skip)
    )
    total_result = await db.execute(query)
    workspaces = total_result.scalars().all()
    has_next = len(workspaces) > limit
    if has_next:
        workspaces = workspaces[:limit]

    return {
        "items": [Workspace.model_validate(ws).model_dump() for ws in workspaces],
        "page": page,
        "limit": limit,
        "has_next": has_next,
    }


# Get all items in every workspaces (chats, deep research, research desk, etc.)
@app.get("/workspaces/items", response_model=PaginatedResponse, tags=["workspace"])
async def get_all_workspace_items(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1),
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    offset_value = (page - 1) * limit
    user_id = current_user.id

    chat_query = (
        select(
            WorkspaceChatModel.id,
            WorkspaceChatModel.workspace_id,
            WorkspaceChatModel.title,
            WorkspaceChatModel.created_at,
            WorkspaceChatModel.updated_at,
            literal_column("'chat'").label("type"),
        )
        .join(WorkspaceModel, WorkspaceModel.id == WorkspaceChatModel.workspace_id)
        .where(WorkspaceModel.user_id == user_id)
    )
    desk_query = (
        select(
            ResearchDeskModel.id,
            ResearchDeskModel.workspace_id,
            ResearchDeskModel.title,
            ResearchDeskModel.created_at,
            ResearchDeskModel.updated_at,
            literal_column("'desk'").label("type"),
        )
        .join(WorkspaceModel, WorkspaceModel.id == ResearchDeskModel.workspace_id)
        .where(WorkspaceModel.user_id == user_id)
    )

    union_query = chat_query.union_all(desk_query)
    subquery = union_query.subquery()
    combined_query = (
        select(subquery)
        .order_by(
            desc(subquery.c.updated_at)
        )
        .limit(limit + 1)
        .offset(offset_value)
    )

    result = await db.execute(combined_query)

    rows = result.all()
    has_next = len(rows) > limit
    if has_next:
        rows = rows[:limit]

    items = [
        {
            "id": row.id,
            "workspace_id": str(row.workspace_id) if row.workspace_id else None,
            "title": row.title,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "type": row.type,
        }
        for row in rows
    ]

    return {"items": items, "page": page, "limit": limit, "has_next": has_next}


@app.get("/workspaces/{id}", tags=["workspace"])
async def get_workspace(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    query = select(WorkspaceModel).where(WorkspaceModel.id == id)
    result = await db.execute(query)
    workspace = result.scalar_one_or_none()

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    return {
        "id": str(workspace.id),
        "name": workspace.name,
        "user_id": workspace.user_id,
        "created_at": workspace.created_at,
        "updated_at": workspace.updated_at,
    }

# Delete a workspace and all its related items (chats, research desks, etc.)
@app.delete("/workspaces/{id}", tags=["workspace"])
async def delete_workspace(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    query = select(WorkspaceModel).where(WorkspaceModel.id == id)
    result = await db.execute(query)
    workspace = result.scalar_one_or_none()

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    # External Cleanup: Delete Search Vector Data (Chromadb)
    try:
        chroma_client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
        chroma_client.delete_collection(name=f"workspace_{str(workspace.id).replace('-', '_')}")
    except Exception:
        pass  # If vector index cleanup fails or is empty, skip quietly

    await db.delete(workspace)
    await db.commit()

    return {"message": "Workspace and related items deleted"}


# Get all items related to a workspace (chats, deep research, research desk, etc.)
@app.get("/workspaces/{id}/items", tags=["workspace"])
async def get_workspace_items(
    id: str,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1),
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    offset_value = (page - 1) * limit

    chat_query = (
        select(
            WorkspaceChatModel.id,
            WorkspaceChatModel.workspace_id,
            WorkspaceChatModel.title,
            WorkspaceChatModel.created_at,
            WorkspaceChatModel.updated_at,
            literal_column("'chat'").label("type"),
        )
        .join(WorkspaceModel, WorkspaceModel.id == WorkspaceChatModel.workspace_id)
        .where(WorkspaceModel.id == id)
        .where(WorkspaceModel.user_id == current_user.id)
    )
    desk_query = (
        select(
            ResearchDeskModel.id,
            ResearchDeskModel.workspace_id,
            ResearchDeskModel.title,
            ResearchDeskModel.created_at,
            ResearchDeskModel.updated_at,
            literal_column("'desk'").label("type"),
        )
        .join(WorkspaceModel, WorkspaceModel.id == ResearchDeskModel.workspace_id)
        .where(WorkspaceModel.id == id)
        .where(WorkspaceModel.user_id == current_user.id)
    )

    # Merge records using UNION ALL
    union_query = chat_query.union_all(desk_query)
    subquery = union_query.subquery()
    combined_query = (
        select(subquery)
        .order_by(desc(subquery.c.updated_at))
        .limit(limit + 1)
        .offset(offset_value)
    )

    result = await db.execute(combined_query)
    rows = result.all()

    has_next = len(rows) > limit
    if has_next:
        rows = rows[:limit]

    items = [
        {
            "id": row.id,
            "workspace_id": str(row.workspace_id) if row.workspace_id else None,
            "title": row.title,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "type": row.type,
        }
        for row in rows
    ]

    return {"items": items, "page": page, "limit": limit, "has_next": has_next}


# delete any workspace item (chat, deep research, research desk, etc.)
@app.delete("/workspaces/{workspace_id}/items/{item_id}", tags=["workspace"])
async def delete_workspace_item(
    workspace_id: str,
    item_id: str,  # Keeping this as a string since our chat/desk IDs are UUID strings
    type: str = Query(..., description="Type of the item to delete (chat, desk, etc.)"),
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    if type == "chat":
        target_model = WorkspaceChatModel
    elif type == "desk":
        target_model = ResearchDeskModel
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported item type: '{type}'. Must be 'chat' or 'desk'.",
        )

    # Build an atomic delete statement targeting the specific row
    delete_stmt = (
        delete(target_model)
        .where(target_model.id == item_id)
        .where(target_model.workspace_id == workspace_id)
        .where(
            target_model.workspace.has(WorkspaceModel.user_id == current_user.id)
        )
    )

    result = await db.execute(delete_stmt)
    await db.commit()

    # Check rowcount to verify if an actual database row was altered
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Item not found in this workspace")

    return {"message": f"{type.capitalize()} and related data deleted"}


@app.get("/")
def read_root():
    return {"message": "Hello, FastAPI!"}


# basic routes
app.include_router(chat_router)
app.include_router(research_desk_router)
app.include_router(auth_router)
app.include_router(services_router)
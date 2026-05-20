from pinecone import Pinecone
from introlix.config import PINECONE_KEY
from fastapi import FastAPI, HTTPException, Query
from introlix.database import db, serialize_doc, validate_object_id
from introlix.models import Workspace
from introlix.schemas import PaginatedResponse
from introlix.routes.chat import chat_router
from introlix.tools.web_crawler import get_httpx_client, get_browser, shutdown
from introlix.routes.research_desk import research_desk_router
from fastapi.middleware.cors import CORSMiddleware
from pymongo import DESCENDING
from contextlib import asynccontextmanager
from introlix.state import app_state
from introlix.config import PINECONE_KEY, SUPPORTED_LLMs
from sentence_transformers import SentenceTransformer

app = FastAPI(title="Introlix", openapi_prefix="/api/v1")
pc = Pinecone(api_key=PINECONE_KEY)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # adding embedding model and pinecone client to app state
    app_state.embedding_model = SentenceTransformer("all-mpnet-base-v2")
    app_state.pc = Pinecone(api_key=PINECONE_KEY)

    # explorer agent setup
    await get_httpx_client()
    await get_browser()
    yield
    await shutdown() # Shutdown the HTTPX client and browser when the app stops

# list of supported LLMs
@app.get("/llms", tags=["llms"])
def get_supported_llms():
    return {"items": SUPPORTED_LLMs}

# workspace endpoints
@app.post("/workspaces", tags=["workspace"])
async def create_workspace(workspace: Workspace):
    workspace_dict = workspace.model_dump()
    result = await db.workspaces.insert_one(workspace_dict)
    created_workspace = await db.workspaces.find_one({"_id": result.inserted_id})
    return {
        "message": "Workspace created",
        "workspace": serialize_doc(created_workspace),
    }


@app.get("/workspaces", response_model=PaginatedResponse, tags=["workspace"])
async def get_workspaces(page: int = Query(1, ge=1), limit: int = Query(10, ge=1)):
    skip = (page - 1) * limit
    total = await db.workspaces.count_documents({})
    cursor = db.workspaces.find().sort("updated_at", DESCENDING).skip(skip).limit(limit)
    workspaces = [serialize_doc(w) async for w in cursor]
    return {"items": workspaces, "total": total, "page": page, "limit": limit}


# Get all items in every workspaces (chats, deep research, research desk, etc.)
@app.get("/workspaces/items", response_model=PaginatedResponse, tags=["workspace"])
async def get_all_workspace_items(
    page: int = Query(1, ge=1), limit: int = Query(10, ge=1)
):
    # get chats related to the workspace
    chat_total = await db.chats.count_documents({})
    chats = (
        db.chats.find(
            {},
            {"_id": 1, "workspace_id": 1, "created_at": 1, "title": 1, "updated_at": 1},
        )
        .sort("updated_at", DESCENDING)
        .skip((page - 1) * limit)
        .limit(limit)
    )
    chat_list = [serialize_doc(chat) async for chat in chats]

    for chat in chat_list:
        chat["type"] = "chat"

    # get desks related to the workspace
    desk_total = await db.research_desks.count_documents({})
    desks = (
        db.research_desks.find(
            {},
            {"_id": 1, "workspace_id": 1, "created_at": 1, "title": 1, "updated_at": 1},
        )
        .sort("updated_at", DESCENDING)
        .skip((page - 1) * limit)
        .limit(limit)
    )
    desk_list = [serialize_doc(desk) async for desk in desks]

    for desk in desk_list:
        desk["type"] = "desk"

    items = desk_list + chat_list
    items = sorted(items, key=lambda x: x["updated_at"], reverse=True)

    return {"items": items, "total": chat_total + desk_total, "page": page, "limit": limit}


@app.get("/workspaces/{id}", tags=["workspace"])
async def get_workspace(id: str):
    workspace = await db.workspaces.find_one({"_id": validate_object_id(id)})
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return serialize_doc(workspace)


@app.delete("/workspaces/{id}", tags=["workspace"])
async def delete_workspace(id: str):
    object_id = validate_object_id(id)
    result = await db.workspaces.delete_one({"_id": object_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Delete Search Data
    try:
        index = pc.Index("explored-data-index")
        index.delete(namespace="Search", filter={"unique_id": id})
    except:
        pass  # No data to delete

    # Now delete workspace items
    # Delete chats
    await db.chats.delete_many({"workspace_id": str(object_id)})
    # TODO: Delete other related items like deep research, research desk, etc.

    return {"message": "Workspace and related items deleted"}


# Get all items related to a workspace (chats, deep research, research desk, etc.)
@app.get("/workspaces/{id}/items", response_model=PaginatedResponse, tags=["workspace"])
async def get_workspace_items(
    id: str, page: int = Query(1, ge=1), limit: int = Query(10, ge=1)
):
    object_id = validate_object_id(id)
    # get chats related to the workspace
    chat_total = await db.chats.count_documents({"workspace_id": str(object_id)})
    chats = (
        db.chats.find(
            {"workspace_id": str(object_id)},
            {"_id": 1, "workspace_id": 1, "created_at": 1, "title": 1, "updated_at": 1},
        )
        .sort("updated_at", DESCENDING)
        .skip((page - 1) * limit)
        .limit(limit)
    )
    chat_list = [serialize_doc(chat) async for chat in chats]

    for chat in chat_list:
        chat["type"] = "chat"

    # get desks related to the workspace
    desk_total = await db.research_desks.count_documents(
        {"workspace_id": str(object_id)}
    )
    desks = (
        db.research_desks.find(
            {"workspace_id": str(object_id)},
            {"_id": 1, "workspace_id": 1, "created_at": 1, "title": 1, "updated_at": 1},
        )
        .sort("updated_at", DESCENDING)
        .skip((page - 1) * limit)
        .limit(limit)
    )
    desk_list = [serialize_doc(desk) async for desk in desks]

    for desk in desk_list:
        desk["type"] = "desk"

    items = desk_list + chat_list
    items = sorted(items, key=lambda x: x["updated_at"], reverse=True)

    return {"items": items, "total": chat_total + desk_total, "page": page, "limit": limit}

# delete any workspace item (chat, deep research, research desk, etc.)
@app.delete("/workspaces/{workspace_id}/items/{item_id}", tags=["workspace"])
async def delete_workspace_item(workspace_id: str, item_id: str, type: str = Query(..., description="Type of the item to delete (chat, desk, etc.)")):
    object_workspace_id = validate_object_id(workspace_id)
    object_item_id = validate_object_id(item_id)

    if type == "chat":
        # Try deleting from chats
        chat_result = await db.chats.delete_one(
            {"_id": object_item_id, "workspace_id": str(object_workspace_id)}
        )
        if chat_result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Workspace not found")
        
    if type == "desk":
        # Try deleting from research desks
        desk_result = await db.research_desks.delete_one(
            {"_id": object_item_id, "workspace_id": str(object_workspace_id)}
        )
        if desk_result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Workspace not found")

    return {"message": f"{type.capitalize()} and related data deleted"}
        

@app.get("/")
def read_root():
    return {"message": "Hello, FastAPI!"}


# basic routes

app.include_router(chat_router)
app.include_router(research_desk_router)

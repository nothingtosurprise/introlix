from datetime import datetime
from typing import List, Literal, Optional
import uuid
from sqlalchemy import String, DateTime, JSON, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pydantic import BaseModel, Field
from introlix.database import Base

# Workspace Table
class WorkspaceModel(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Workspace Items relationship
    items: Mapped[List["WorkspaceItemModel"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")

# Workspace Item Table
class WorkspaceItemModel(Base):
    __tablename__ = "workspace_items"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)

    item_type: Mapped[str] = mapped_column(String(50), nullable=False)

    workspace: Mapped["WorkspaceModel"] = relationship(back_populates="items")


# Workspace Chat Table
class WorkspaceChatModel(Base):
    __tablename__ = "workspace_chats"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Messages
    messages: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")


# Research Desk Table
class ResearchDeskModel(Base):
    __tablename__ = "research_desks"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    state: Mapped[Optional[str]] = mapped_column(String(50), default="initial", server_default="initial")
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Store documents, agents, and messages as JSON
    documents: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    context_agent: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    planner_agent: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    messages: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


# Chat Agent Response Model
class ChatResponse(BaseModel):
    response: str

# Chat Endpoint Request Model
class ChatRequest(BaseModel):
    prompt: str
    model: str
    search: bool
    agent: str

# Workspace Model
class Workspace(BaseModel):
    id: Optional[str] = None
    name: str
    user_id: str
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Config:
        from_attributes = True

# Workspace Workspace Items
class WorkspaceItem(BaseModel):
    id: Optional[str] = None
    workspace_id: str
    item_type: Literal["research_desk", "chat", "deep_research"]

    class Config:
        from_attributes = True
    
# Chat
class Message(BaseModel):
    """Individual message in a chat"""
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()))
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime = Field(default_factory=datetime.now)
    tokens: Optional[int] = None  # Token count for this message
    model: Optional[str] = None  # Model used (for assistant messages)


    class Config:
        from_attributes = True

class WorkspaceChat(BaseModel):
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()))
    workspace_id: Optional[str] = None
    title: Optional[str] = None
    messages: List[Message] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Config:
        from_attributes = True

# Context Agent
class ContextAgent(BaseModel):
    conv_history: str = None
    questions: List[str] = None
    move_next: bool = None
    confidence_level: float = None
    final_prompt: str = None
    research_parameters: dict = None

    class Config:
        from_attributes = True

# Research Desk
class ResearchDeskRequest(BaseModel):
    prompt: str
    model: str

    class Config:
        from_attributes = True

class ResearchDeskContextAgentRequest(BaseModel):
    prompt: str
    model: str
    answers: Optional[str] = None
    research_scope: str
    user_files: Optional[List] = None

    class Config:
        from_attributes = True

class EditDocRequest(BaseModel):
    prompt: str
    model: str

    class Config:
        from_attributes = True

class ResearchDesk(BaseModel):
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()))
    workspace_id: Optional[str] = None
    state: Optional[Literal["initial", "context_agent", "planner_agnet", "approve_plan", "explorer_agent", "complete"]] = "initial" 
    title: Optional[str] = None
    documents: Optional[dict] = None
    context_agent: Optional[ContextAgent] = None
    planner_agent: Optional[dict] = None
    messages: List[Message] = Field(default_factory=list) # chat messages
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Config:
        from_attributes = True
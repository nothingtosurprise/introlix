from pydantic import BaseModel

class PaginatedResponse(BaseModel):
    items: list
    page: int
    limit: int
    has_next: bool

    class Config:
        from_attributes = True

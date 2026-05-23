from fastapi import HTTPException
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from introlix.config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=True)

async_session_factory = async_sessionmaker(
    bind=engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

class Base(DeclarativeBase):
    pass

# Add an async table initializer function
async def init_db():
    """
    Scans metadata and creates tables if they don't exist.
    """
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

def serialize_model(instance) -> dict | None:
    if instance is None:
        return None
    
    # Converts the SQL row object into a clean Python dictionary
    data = {c.name: getattr(instance, c.name) for c in instance.__table__.columns}
    return data

def validate_int_id(id_str: str) -> int:
    try:
        return int(id_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID format. Must be an integer.")
    

async def get_db():
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()  # Automatically commit changes if no error occurs
        except Exception:
            await session.rollback() # Rollback if something goes wrong
            raise
        finally:
            await session.close()
from introlix.database import get_db
from introlix.models import UserModel
from introlix.utils.auth import create_access_token
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from bcrypt import hashpw, gensalt, checkpw

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup")
async def signup(name: str, email: str, password: str, db: AsyncSession = Depends(get_db)):
    # Check if user already exists
    result = await db.execute(select(UserModel).filter_by(email=email))
    existing_user = result.scalars().first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Hash the password
    password_hash = hashpw(password.encode('utf-8'), gensalt())

    # Create new user
    new_user = UserModel(name=name, email=email, password_hash=password_hash.decode('utf-8'))

    # Add new user to database
    db.add(new_user)
    await db.flush()
    await db.refresh(new_user)

    return {
        "message": "User created successfully",
        "access_token": create_access_token(data={"sub": new_user.id}),
        "token_type": "bearer",
        "name": new_user.name,
        "email": new_user.email
    }


DUMMY_HASHED_PASSWORD = hashpw("password".encode('utf-8'), gensalt()).decode('utf-8')


@router.post("/login")
async def login(email: str, password: str, db: AsyncSession = Depends(get_db)):
    # Check if user exists
    result = await db.execute(select(UserModel).filter_by(email=email))
    user = result.scalars().first()

    db_hashed_password = user.password_hash if user else DUMMY_HASHED_PASSWORD

    # Check if password is correct
    if not checkpw(password.encode('utf-8'), db_hashed_password.encode('utf-8')):
        raise HTTPException(status_code=400, detail="Invalid email or password")

    access_token = create_access_token(data={"sub": user.id})

    return {
        "message": "Login successful",
        "access_token": access_token,
        "token_type": "bearer",
        "name": user.name,
        "email": user.email
    }
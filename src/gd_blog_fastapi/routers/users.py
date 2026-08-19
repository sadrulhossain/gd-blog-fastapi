from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from datetime import timedelta
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .. import models
from ..database import get_db
from ..schemas import PostResponse, UserCreate, UserPublicResponse, UserPrivateResponse, Token, UserUpdate
from ..auth import create_access_token, has_password, oauth2_scheme, verify_access_token, verify_password
from ..config import settings


router = APIRouter()

@router.get("", response_model=list[PostResponse])
async def get_users(db: Annotated[AsyncSession, Depends(get_db)]):
    return (await db.execute(select(models.User))).scalars().all()

@router.post("", response_model=UserPrivateResponse, status_code=status.HTTP_201_CREATED)
async def create_user(user: UserCreate, db: Annotated[AsyncSession, Depends(get_db)]):
    existing_user = ((await db.execute(select(models.User)
                                       .where(func.lower(models.User.username) == user.username.lower())
                                       ))
                     .scalars()
                     .first())

    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")

    existing_email = ((await db.execute(select(models.User)
                                        .where(func.lower(models.User.email) == user.email.lower())
                                        ))
                      .scalars()
                      .first())

    if existing_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists")

    new_user = models.User(
        name=user.name,
        username=user.username,
        email=user.email.lower(),
        password_hash=has_password(user.password),
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user


@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = ((await db.execute(select(models.User)
                              .where(func.lower(models.User.email) == form_data.username.lower())
                              ))
            .scalars()
            .first())

    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create access token with user id as subject
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=access_token_expires,
    )
    return Token(access_token=access_token, token_type="bearer")

@router.get("/me", response_model=UserPrivateResponse)
async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user_id = verify_access_token(token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate user_id is a valid integer (defense against malformed JWT)
    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = ((await db.execute(select(models.User).where(models.User.id == user_id_int)))
            .scalars()
            .first())
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

@router.get("/{user_id}", response_model=UserPublicResponse)
async def get_user(user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    user = ((await db.execute(select(models.User).where(models.User.id == user_id)))
            .scalars()
            .first())

    if user:
        return user
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

@router.patch("/{user_id}", response_model=UserPrivateResponse)
async def update_user(user_id: int, user_data: UserUpdate, db: Annotated[AsyncSession, Depends(get_db)]):
    user = ((await db.execute(select(models.User).where(models.User.id == user_id)))
              .scalars()
              .first())

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user_data.username is not None and user_data.username != user.username:
        existing_user = ((await db.execute(select(models.User)
                                           .where(func.lower(models.User.username) == user.username.lower())
                                           ))
                         .scalars()
                         .first())
        if existing_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Username already exists.")
    if user_data.email is not None and user_data.email != user.email:
        existing_email = ((await db.execute(select(models.User)
                                            .where(func.lower(models.User.email) == user.email.lower())
                                            ))
                         .scalars()
                         .first())
        if existing_email:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email already exists.")

    update_data = user_data.model_dump(exclude_unset=True)
    if "email" in update_data:
        update_data["email"] = update_data["email"].lower()
    for field, value in update_data.items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return user

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    user = ((await db.execute(select(models.User).where(models.User.id == user_id)))
              .scalars()
              .first())
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    await db.delete(user)
    await db.commit()

@router.get("/{user_id}/posts", response_model=list[PostResponse])
async def user_posts(user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    user = ((await db.execute(select(models.User).where(models.User.id == user_id)
                              ))
            .scalars()
            .first())

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    posts = ((await db.execute(select(models.Post)
                               .options(selectinload(models.Post.author))
                               .where(models.Post.user_id == user_id)
                               .order_by(models.Post.date_posted.desc())
                               ))
             .scalars()
             .all())

    return posts

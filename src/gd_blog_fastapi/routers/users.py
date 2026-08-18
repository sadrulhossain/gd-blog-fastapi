from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .. import models
from ..database import get_db
from ..schemas import PostResponse, UserCreate, UserResponse, UserUpdate

router = APIRouter()

@router.get("", response_model=list[PostResponse])
async def get_users(db: Annotated[AsyncSession, Depends(get_db)]):
    return (await db.execute(select(models.User))).scalars().all()

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    user = ((await db.execute(select(models.User).where(models.User.id == user_id)))
            .scalars()
            .first())

    if user:
        return user
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(user: UserCreate, db: Annotated[AsyncSession, Depends(get_db)]):
    existing_user = ((await db.execute(select(models.User).where(models.User.username == user.username)))
                     .scalars()
                     .first())

    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")

    existing_email = ((await db.execute(select(models.User).where(models.User.email == user.email)))
                      .scalars()
                      .first())

    if existing_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists")

    new_user = models.User(
        name=user.name,
        username=user.username,
        email=user.email,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user



@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, user_data: UserUpdate, db: Annotated[AsyncSession, Depends(get_db)]):
    user = ((await db.execute(select(models.User).where(models.User.id == user_id)))
              .scalars()
              .first())

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user_data.username is not None and user_data.username != user.username:
        existing_user = ((await db.execute(select(models.User).where(models.User.username == user.username)))
                         .scalars()
                         .first())
        if existing_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Username already exists.")
    if user_data.email is not None and user_data.email != user.email:
        existing_email = ((await db.execute(select(models.User).where(models.User.email == user.email)))
                         .scalars()
                         .first())
        if existing_email:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email already exists.")

    update_data = user_data.model_dump(exclude_unset=True)
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

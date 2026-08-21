from typing import Annotated
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile
from fastapi.security import OAuth2PasswordRequestForm
from PIL import UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.concurrency import run_in_threadpool

from .. import models
from ..database import get_db
from ..schemas import PostResponse, UserCreate, UserPublicResponse, UserPrivateResponse, Token, UserUpdate
from ..auth import create_access_token, has_password, verify_password, CurrentUser
from ..config import settings
from ..image_utils import delete_profile_image, process_profile_image


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
async def get_current_user(current_user: CurrentUser):
    return current_user

@router.get("/{user_id}", response_model=UserPublicResponse)
async def get_user(user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    user = ((await db.execute(select(models.User).where(models.User.id == user_id)))
            .scalars()
            .first())

    if user:
        return user
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

@router.patch("/{user_id}", response_model=UserPrivateResponse)
async def update_user(user_id: int, user_data: UserUpdate, current_user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]):
    if user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this user")

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

    old_filename = user.image_file

    await db.delete(user)
    await db.commit()

    if old_filename:
        delete_profile_image(old_filename)

@router.get("/{user_id}/posts", response_model=list[PostResponse])
async def user_posts(user_id: int, current_user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]):
    if user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this user")

    user = ((await db.execute(select(models.User).where(models.User.id == user_id)))
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

@router.patch("/{user_id}/picture", response_model=UserPrivateResponse)
async def upload_profile_picture(
    user_id: int,
    file: UploadFile,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this user's picture",
        )

    content = await file.read()

    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size is {settings.max_upload_size_bytes // (1024 * 1024)}MB",
        )

    try:
        new_filename = await run_in_threadpool(process_profile_image, content)
    except UnidentifiedImageError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image file. Please upload a valid image (JPEG, PNG, GIF, WebP).",
        ) from err

    old_filename = current_user.image_file

    current_user.image_file = new_filename
    await db.commit()
    await db.refresh(current_user)

    if old_filename:
        delete_profile_image(old_filename)

    return current_user

@router.delete("/{user_id}/picture", response_model=UserPrivateResponse)
async def delete_user_picture(
    user_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this user's picture",
        )

    old_filename = current_user.image_file

    if old_filename is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No profile picture to delete",
        )

    current_user.image_file = None
    await db.commit()
    await db.refresh(current_user)

    delete_profile_image(old_filename)

    return current_user
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from typing import Annotated
from contextlib import asynccontextmanager
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from . import models
from .database import Base, engine, get_db
from .schemas import UserCreate, UserUpdate, UserResponse, PostCreate, PostUpdate, PostResponse

@asynccontextmanager
async def lifespan(_app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()

BASE_DIR = Path(__file__).parent

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/media", StaticFiles(directory=BASE_DIR / "media"), name="media")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# Frontend page methods
@app.get("/", include_in_schema=False)
async def home(request: Request, db: Annotated[AsyncSession, Depends(get_db)]):
    posts = ((await db.execute(select(models.Post).options(selectinload(models.Post.author))))
             .scalars()
             .all())
    return templates.TemplateResponse(
        request,
        "home.html",
        {"title": 'Home', "posts": posts}
    )

@app.get("/posts/{post_id}", include_in_schema=False)
async def post_page(request: Request, post_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    post = ((await db.execute(select(models.Post)
                              .options(selectinload(models.Post.author))
                              .where(models.Post.id == post_id)
                              ))
            .scalars()
            .first())

    if post:
        title = post.title[:50]
        return templates.TemplateResponse(
            request,
            "post.html",
            {"title": title, "post": post},
        )

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

@app.get("/users/{user_id}/posts", include_in_schema=False)
async def user_posts_page(request: Request, user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    user = ((await db.execute(select(models.User).where(models.User.id == user_id)))
            .scalars()
            .first())

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    posts = ((await db.execute(select(models.Post)
                               .options(selectinload(models.Post.author))
                               .where(models.Post.user_id == user_id)
                               ))
             .scalars()
             .all())

    return templates.TemplateResponse(
        request,
        "user_posts.html",
        {"title": user.name, "user": user, "posts": posts}
    )

# API methods
@app.get("/api/users", response_model=list[PostResponse])
async def get_posts(db: Annotated[AsyncSession, Depends(get_db)]):
    return (await db.execute(select(models.User))).scalars().all()

@app.get("/api/users/{user_id}", response_model=UserResponse)
async def get_post(user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    user = ((await db.execute(select(models.User).where(models.User.id == user_id)))
            .scalars()
            .first())

    if user:
        return user
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

@app.post("/api/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
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



@app.patch("/api/users/{user_id}", response_model=UserResponse)
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

@app.delete("/api/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    user = ((await db.execute(select(models.User).where(models.User.id == user_id)))
              .scalars()
              .first())
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    await db.delete(user)
    await db.commit()

@app.get("/api/users/{user_id}/posts", response_model=list[PostResponse])
async def user_posts(user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    user = ((await db.execute(select(models.User).where(models.User.id == user_id)))
            .scalars()
            .first())

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    posts = ((await db.execute(select(models.Post)
                               .options(selectinload(models.Post.author))
                               .where(models.Post.user_id == user_id)
                               ))
             .scalars()
             .all())

    return posts


@app.get("/api/posts", response_model=list[PostResponse])
async def get_posts(db: Annotated[AsyncSession, Depends(get_db)]):
    return (await db.execute(select(models.Post))).scalars().all()

@app.get("/api/posts/{post_id}", response_model=PostResponse)
async def get_post(post_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    post = ((await db.execute(select(models.Post)
                              .options(selectinload(models.Post.author))
                              .where(models.Post.id == post_id)
                              ))
              .scalars()
              .first())

    if post:
        return post

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

@app.post("/api/posts", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(post: PostCreate, db: Annotated[AsyncSession, Depends(get_db)]):
    user = ((await db.execute(select(models.User).where(models.User.id == post.user_id)))
            .scalars()
            .first())

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    new_post = models.Post(
        title=post.title,
        content=post.content,
        user_id=post.user_id,
    )

    db.add(new_post)
    await db.commit()
    await db.refresh(new_post)

    return new_post

@app.patch("/api/posts/{post_id}", response_model=PostResponse)
async def update_post(post_id: int, post_data: PostUpdate, db: Annotated[AsyncSession, Depends(get_db)]):
    post = ((await db.execute(select(models.Post)
                              .options(selectinload(models.Post.author))
                              .where(models.Post.id == post_id)
                              ))
              .scalars()
              .first())

    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    update_data = post_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(post, field, value)

    await db.commit()
    await db.refresh(post)
    return post

@app.delete("/api/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(post_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    post = ((await db.execute(select(models.Post).where(models.Post.id == post_id)))
              .scalars()
              .first())
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    await db.delete(post)
    await db.commit()


# Helper methods
@app.exception_handler(StarletteHTTPException)
async def general_http_exception_handler(request: Request, exception: StarletteHTTPException):
    if request.url.path.startswith("/api"):
        return await http_exception_handler(request, exception)

    message = (
        exception.detail
        if exception.detail
        else "An error occurred. Please check your request and try again."
    )

    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "status_code": exception.status_code,
            "title": exception.status_code,
            "message": message,
        },
        status_code=exception.status_code,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exception: RequestValidationError):
    if request.url.path.startswith("/api"):
        return await request_validation_exception_handler(request, exception)

    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "status_code": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "title": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "message": "Invalid request. Please check your input and try again.",
        },
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )

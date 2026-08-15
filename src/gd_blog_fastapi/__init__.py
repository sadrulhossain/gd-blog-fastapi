from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from typing import Annotated
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .database import Base, engine, get_db
from .schemas import UserCreate, UserUpdate, UserResponse, PostCreate, PostUpdate, PostResponse

Base.metadata.create_all(bind=engine)


BASE_DIR = Path(__file__).parent

app = FastAPI()
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/media", StaticFiles(directory=BASE_DIR / "media"), name="media")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# Frontend page methods
@app.get("/", include_in_schema=False)
def home(request: Request, db: Annotated[Session, Depends(get_db)]):
    posts = db.execute(select(models.Post)).scalars().all()
    return templates.TemplateResponse(
        request,
        "home.html",
        {"title": 'Home', "posts": posts}
    )

@app.get("/posts/{post_id}", include_in_schema=False)
def post_page(request: Request, post_id: int, db: Annotated[Session, Depends(get_db)]):
    post = (db.execute(select(models.Post).where(models.Post.id == post_id))
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
def user_posts_page(request: Request, user_id: int, db: Annotated[Session, Depends(get_db)]):
    user = (db.execute(select(models.User).where(models.User.id == user_id))
            .scalars()
            .first())

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    posts = (db.execute(select(models.Post).where(models.Post.user_id == user_id))
             .scalars()
             .all())

    return templates.TemplateResponse(
        request,
        "user_posts.html",
        {"title": user.name, "user": user, "posts": posts}
    )

# API methods
@app.get("/api/users", response_model=list[PostResponse])
def get_posts(db: Annotated[Session, Depends(get_db)]):
    return db.execute(select(models.User)).scalars().all()

@app.get("/api/users/{user_id}", response_model=UserResponse)
def get_post(user_id: int, db: Annotated[Session, Depends(get_db)]):
    user = (db.execute(select(models.User).where(models.User.id == user_id))
            .scalars()
            .first())

    if user:
        return user
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

@app.post("/api/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(user: UserCreate, db: Annotated[Session, Depends(get_db)]):
    existing_user = (db.execute(select(models.User).where(models.User.username == user.username))
                     .scalars()
                     .first())

    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")

    existing_email = (db.execute(select(models.User).where(models.User.email == user.email))
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
    db.commit()
    db.refresh(new_user)
    return new_user



@app.patch("/api/users/{user_id}", response_model=UserResponse)
def update_user(user_id: int, user_data: UserUpdate, db: Annotated[Session, Depends(get_db)]):
    user = (db.execute(select(models.User).where(models.User.id == user_id))
              .scalars()
              .first())

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user_data.username is not None and user_data.username != user.username:
        existing_user = (db.execute(select(models.User).where(models.User.username == user.username))
                         .scalars()
                         .first())
        if existing_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Username already exists.")
    if user_data.email is not None and user_data.email != user.email:
        existing_email = (db.execute(select(models.User).where(models.User.email == user.email))
                         .scalars()
                         .first())
        if existing_email:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email already exists.")

    update_data = user_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return user

@app.delete("/api/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, db: Annotated[Session, Depends(get_db)]):
    user = (db.execute(select(models.User).where(models.User.id == user_id))
              .scalars()
              .first())
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    db.delete(user)
    db.commit()

@app.get("/api/users/{user_id}/posts", response_model=list[PostResponse])
def user_posts(user_id: int, db: Annotated[Session, Depends(get_db)]):
    user = (db.execute(select(models.User).where(models.User.id == user_id))
            .scalars()
            .first())

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    posts = (db.execute(select(models.Post).where(models.Post.user_id == user_id))
             .scalars()
             .all())

    return posts


@app.get("/api/posts", response_model=list[PostResponse])
def get_posts(db: Annotated[Session, Depends(get_db)]):
    return db.execute(select(models.Post)).scalars().all()

@app.get("/api/posts/{post_id}", response_model=PostResponse)
def get_post(post_id: int, db: Annotated[Session, Depends(get_db)]):
    post = (db.execute(select(models.Post).where(models.Post.id == post_id))
              .scalars()
              .first())

    if post:
        return post

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

@app.post("/api/posts", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
def create_post(post: PostCreate, db: Annotated[Session, Depends(get_db)]):
    user = (db.execute(select(models.User).where(models.User.id == post.user_id))
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
    db.commit()
    db.refresh(new_post)

    return new_post

@app.patch("/api/posts/{post_id}", response_model=PostResponse)
def update_post(post_id: int, post_data: PostUpdate, db: Annotated[Session, Depends(get_db)]):
    post = (db.execute(select(models.Post).where(models.Post.id == post_id))
              .scalars()
              .first())

    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    update_data = post_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(post, field, value)

    db.commit()
    db.refresh(post)
    return post

@app.delete("/api/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(post_id: int, db: Annotated[Session, Depends(get_db)]):
    post = (db.execute(select(models.Post).where(models.Post.id == post_id))
              .scalars()
              .first())
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    db.delete(post)
    db.commit()


# Helper methods
@app.exception_handler(StarletteHTTPException)
def general_http_exception_handler(request: Request, exception: StarletteHTTPException):
    message = (
        exception.detail
        if exception.detail
        else "An error occurred. Please check your request and try again."
    )

    if request.url.path.startswith("/api"):
        return JSONResponse(
            status_code=exception.status_code,
            content={"detail": message},
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
def validation_exception_handler(request: Request, exception: RequestValidationError):
    if request.url.path.startswith("/api"):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": exception.errors()},
        )

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

# GD Blog FastAPI

A simple blog application built with FastAPI, SQLAlchemy (async), and Jinja2 templates. It serves both server-rendered HTML pages and a JSON REST API for managing users and posts.

## Project Overview

GD Blog FastAPI is a learning-focused blog project that demonstrates:

- An async FastAPI backend backed by SQLite (via `aiosqlite`) and SQLAlchemy's async ORM.
- Server-rendered pages (home page, single post page, and per-user posts page) using Jinja2 templates.
- A REST API for managing users and posts, organized with `APIRouter` modules.
- Centralized error handling that returns JSON for API routes and HTML error pages for frontend routes.

## Installation

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (used for dependency management)

### Setup

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd gd_blog_fastapi
   ```

2. Install dependencies with uv:
   ```bash
   uv sync
   ```

3. Run the development server:
   ```bash
   uv run fastapi dev src/gd_blog_fastapi/__init__.py
   ```

4. Open the app in your browser at [http://127.0.0.1:8000](http://127.0.0.1:8000)

   Interactive API docs are available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

The SQLite database (`blog.db`) and its tables are created automatically on startup.

## Features

- **Home page** — lists all blog posts with their authors.
- **Post page** — view a single post's full content.
- **User posts page** — view all posts written by a specific user.
- **Users API** (`/api/users`)
  - Create, retrieve, update, and delete users.
  - List all posts belonging to a user.
  - Enforces unique username and email.
- **Posts API** (`/api/posts`)
  - Create, retrieve, update, and delete posts.
- **Profile pictures** — users can have a profile image, falling back to a default image.
- **Custom error handling** — JSON error responses for `/api` routes, HTML error page for frontend routes.

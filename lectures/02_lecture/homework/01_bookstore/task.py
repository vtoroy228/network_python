"""
01_bookstore — CRUD API для книжного магазина 📚

Спроектируйте REST API для управления каталогом книг.

Спецификация эндпоинтов (ничего не менять — тесты завязаны на них):

    GET    /books              — список книг (с опциональной фильтрацией)
    GET    /books/{id}         — одна книга по id
    POST   /books              — создать книгу
    PUT    /books/{id}         — полностью обновить книгу
    DELETE /books/{id}         — удалить книгу
    GET    /books/search       — поиск книг по названию или автору

    # Дополнительно — категории
    GET    /categories         — список категорий
    POST   /categories         — создать категорию

Требования к реализации:
    1. Используйте FastAPI + Pydantic
    2. Храните данные в памяти (глобальный список/словарь)
    3. Правильные HTTP-статусы:
        - 200 — успешный GET, PUT
        - 201 — успешный POST
        - 204 — успешный DELETE
        - 404 — ресурс не найден
        - 409 — конфликт (например, дубликат)
        - 422 — невалидные данные (Pydantic сам это делает)
    4. Валидация полей через Pydantic Field:
        - title:  не пустой, до 100 символов
        - author: не пустой, до 100 символов
        - year:   ≥ 0, до 2025
        - isbn:   строка 10 или 13 цифр (978-5-xxx...)
        - price:  > 0
        - category_id: опционально, ссылка на категорию
    5. Кастомная обработка ошибок:
        - BookNotFoundException → 404 c {"detail": "Book not found", "code": "NOT_FOUND"}
        - DuplicateIsbnException → 409 c {"detail": "...", "code": "DUPLICATE_ISBN"}
    6. Поиск /books/search?query=... — ищет по title и author (case-insensitive)
    7. Фильтрация GET /books?category_id=N&year=2024
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from typing import Optional

# ═══════════════════════════════════════════════════════════
# МОДЕЛИ
# ═══════════════════════════════════════════════════════════


class Category(BaseModel):
    """Доменная модель категории. Возвращается в ответах."""

    id: int
    name: str = Field(min_length=1, max_length=50)


class CategoryCreate(BaseModel):
    """Модель для создания категории (без id, лишние поля запрещены)."""

    name: str = Field(min_length=1, max_length=50)

    model_config = {"extra": "forbid"}


class Book(BaseModel):
    """Доменная модель книги. Возвращается в ответах GET/PUT."""

    id: int
    title: str = Field(min_length=1, max_length=100)
    author: str = Field(min_length=1, max_length=100)
    year: int = Field(ge=0, le=2025)
    isbn: str
    price: float = Field(gt=0)
    category_id: Optional[int] = None


class BookCreate(BaseModel):
    """Модель для создания/обновления книги (без id — сервер сгенерирует)."""

    title: str = Field(min_length=1, max_length=100)
    author: str = Field(min_length=1, max_length=100)
    year: int = Field(ge=0, le=2025)
    isbn: str
    price: float = Field(gt=0)
    category_id: Optional[int] = None


# ═══════════════════════════════════════════════════════════
# ИСКЛЮЧЕНИЯ
# ═══════════════════════════════════════════════════════════


class BookNotFoundException(HTTPException):
    """404 — книга не найдена."""

    def __init__(self):
        super().__init__(status_code=404, detail = {"detail": "Book not found", "code": "NOT_FOUND"})


class DuplicateIsbnException(HTTPException):
    """409 — ISBN уже существует."""

    def __init__(self):
        super().__init__(status_code=409, detail = {"detail": "ISBN Already exists", "code": "DUPLICATE_ISBN"})


# ═══════════════════════════════════════════════════════════
# ПРИЛОЖЕНИЕ
# ═══════════════════════════════════════════════════════════

app = FastAPI(title="Bookstore API")

# Хранилище
BOOKS: list[dict] = []
CATEGORIES: list[dict] = []


# ═══════════════════════════════════════════════════════════
# КАТЕГОРИИ
# ═══════════════════════════════════════════════════════════

@app.exception_handler(BookNotFoundException)
def bnf_handler(request, exc):
    return JSONResponse(status_code=404, content={"detail": "Book not found", "code": "NOT_FOUND"})

@app.exception_handler(DuplicateIsbnException)
def dup_handler(request, exc):
    return JSONResponse(status_code=409, content={"detail": "ISBN Already exists", "code": "DUPLICATE_ISBN"})
@app.get("/categories")
def list_categories():
    """GET /categories — список всех категорий."""
    return CATEGORIES


@app.post("/categories", status_code=201)
def create_category(category: CategoryCreate):
    """POST /categories — создать категорию."""
    new_id = len(CATEGORIES) + 1
    new_cat = category.model_dump()
    new_cat["id"] = new_id
    CATEGORIES.append(new_cat)
    return new_cat

# ═══════════════════════════════════════════════════════════
# CRUID КНИГ
# ═══════════════════════════════════════════════════════════


@app.get("/books")
def list_books(category_id: Optional[int] = None, year: Optional[int] = None):
    """GET /books — список книг. Опциональная фильтрация по category_id и year."""
    filtered = BOOKS
    if category_id is not None:
        filtered = [book for book in BOOKS if book.get("category_id") == category_id]
    if year is not None:
        filtered = [book for book in filtered if book.get("year") == year]
    return filtered


@app.get("/books/search")
def search_books(query: str):
    """GET /books/search?query=... — поиск по title и author (case-insensitive)."""
    query = query.lower()
    result = [
        book for book in BOOKS
        if query in book.get("title", "").lower() 
        or query in book.get("author", "").lower()
    ]
    
    return result


@app.get("/books/{book_id}")
def get_book(book_id: int):
    """GET /books/{id} — одна книга."""
    for book in BOOKS:
        if book.get("id") == book_id:
            return book
            
    raise BookNotFoundException()


@app.post("/books", status_code=201)
def create_book(book: BookCreate):
    """POST /books — создать книгу.

    Проверять уникальность ISBN. Если дубликат — DuplicateIsbnException.
    """
    new_book = book.model_dump()
    isbn = new_book["isbn"]
    for exst_book in BOOKS:
        if exst_book.get("isbn") == isbn:
            raise DuplicateIsbnException()
    new_id = len(BOOKS) + 1
    new_book["id"] = new_id
    BOOKS.append(new_book)
    return new_book
    


@app.put("/books/{book_id}")
def update_book(book_id: int, book: BookCreate):
    """PUT /books/{id} — полностью обновить книгу."""
    new_data = book.model_dump()
    
    for i, existing_book in enumerate(BOOKS):
        if existing_book.get("id") == book_id:
            for other_book in BOOKS:
                if other_book.get("id") != book_id and other_book.get("isbn") == new_data["isbn"]:
                    raise DuplicateIsbnException()
            
            new_data["id"] = book_id
            BOOKS[i] = new_data
            return new_data
            
    raise BookNotFoundException()


@app.delete("/books/{book_id}", status_code=204)
def delete_book(book_id: int):
    """DELETE /books/{id} — удалить книгу."""
    for i, existing_book in enumerate(BOOKS):
        if existing_book.get("id") == book_id:
            BOOKS.pop(i)
            return 
            
    raise BookNotFoundException()
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from crud.movies import get_movie_by_id, get_movies, get_or_create
from database import MovieModel, get_db
from database.models import ActorModel, CountryModel, GenreModel, LanguageModel
from schemas.movies import (
    MovieCreateSchema,
    MovieListResponseSchema,
    MovieReadSchema,
    MovieSchema,
    MovieUpdateSchema,
)

router = APIRouter()


@router.get("/movies/", response_model=MovieListResponseSchema)
async def get_all_movies(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    movies = await get_movies(db, per_page, page)
    count_result = await db.execute(select(func.count()).select_from(MovieModel))
    count = count_result.scalar()
    page_count = (count + per_page - 1) // per_page

    prev_page = (
        None if page <= 1 else f"/theater/movies/?page={page - 1}&per_page={per_page}"
    )
    next_page = (
        None
        if page >= page_count
        else f"/theater/movies/?page={page + 1}&per_page={per_page}"
    )

    return MovieListResponseSchema.model_validate(
        {
            "movies": movies,
            "prev_page": prev_page,
            "next_page": next_page,
            "total_pages": page_count,
            "total_items": count,
        }
    )


@router.get("/movies/{movie_id}/", response_model=MovieSchema)
async def get_movie(movie_id: int, db: AsyncSession = Depends(get_db)):
    result = await get_movie_by_id(db, movie_id)
    if not result:
        raise HTTPException(
            status_code=404, detail="Movie with the given ID was not found."
        )
    return result


@router.delete("/movies/{movie_id}/", response_model=MovieSchema)
async def delete_movie(movie_id: int, db: AsyncSession = Depends(get_db)):
    result = await get_movie_by_id(db, movie_id)
    if not result:
        raise HTTPException(
            status_code=404, detail="Movie with the given ID was not found."
        )
    await db.delete(result)
    await db.commit()
    return result


@router.post("/movies/", response_model=MovieReadSchema, status_code=201)
async def create_movie(movie: MovieCreateSchema, db: AsyncSession = Depends(get_db)):
    given = await db.execute(
        select(MovieModel).where(
            MovieModel.name == movie.name, MovieModel.date == movie.date
        )
    )
    if given.scalar():
        raise HTTPException(
            status_code=409,
            detail=f"A movie with the name '{movie.name}' and release date '{movie.date}' already exists.",
        )

    genre_objs = [
        await get_or_create(GenreModel, db, name=name) for name in movie.genres
    ]
    actor_objs = [
        await get_or_create(ActorModel, db, name=name) for name in movie.actors
    ]
    language_objs = [
        await get_or_create(LanguageModel, db, name=name) for name in movie.languages
    ]
    country_obj = await get_or_create(
        CountryModel, db, code=movie.country, name=movie.country
    )

    new_movie = MovieModel(
        name=movie.name,
        date=movie.date,
        score=movie.score,
        overview=movie.overview,
        status=movie.status,
        budget=movie.budget,
        revenue=movie.revenue,
        country_id=country_obj.id,
        genres=genre_objs,
        actors=actor_objs,
        languages=language_objs,
    )
    db.add(new_movie)
    await db.commit()
    await db.refresh(new_movie)

    full_movie = await db.execute(
        select(MovieModel)
        .options(
            joinedload(MovieModel.country),
            joinedload(MovieModel.genres),
            joinedload(MovieModel.actors),
            joinedload(MovieModel.languages),
        )
        .where(MovieModel.id == new_movie.id)
    )
    full_movie_obj = full_movie.unique().scalar_one()
    return MovieReadSchema.model_validate(full_movie_obj)


@router.patch("/movies/{movie_id}/")
async def update_movie(
    movie_id: int = Path(..., ge=1),
    update_data: MovieUpdateSchema = Body(),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(MovieModel).where(MovieModel.id == movie_id))
    db_movie = result.scalar_one_or_none()

    if not db_movie:
        raise HTTPException(
            status_code=404, detail="Movie with the given ID was not found."
        )

    update_dict = update_data.model_dump(exclude_unset=True)

    try:
        for field, value in update_dict.items():
            setattr(db_movie, field, value)
        await db.commit()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid input data.")

    return {"detail": "Movie updated successfully."}

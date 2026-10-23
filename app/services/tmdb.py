"""TMDB integration – thin async client for The Movie Database search API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

import httpx

from app.config import settings

TMDB_API_URL = "https://api.themoviedb.org/3"
TMDB_POSTER_URL = "https://image.tmdb.org/t/p/w342"


@dataclass
class TmdbMovie:
    """One search result from TMDB."""

    id: int
    title: str  # Italian title (language=it-IT)
    original_title: str
    release_date: date | None = None
    popularity: float = 0.0
    poster_path: str | None = None

    @property
    def year(self) -> int | None:
        return self.release_date.year if self.release_date else None

    @property
    def poster_url(self) -> str | None:
        return f"{TMDB_POSTER_URL}{self.poster_path}" if self.poster_path else None

    @classmethod
    def from_api(cls, hit: dict) -> TmdbMovie:
        release = None
        raw_date = hit.get("release_date") or ""
        try:
            release = date.fromisoformat(raw_date) if raw_date else None
        except ValueError:
            release = None
        return cls(
            id=hit["id"],
            title=hit.get("title") or hit.get("original_title") or "",
            original_title=hit.get("original_title") or hit.get("title") or "",
            release_date=release,
            popularity=float(hit.get("popularity") or 0.0),
            poster_path=hit.get("poster_path"),
        )


class MovieSearcher(Protocol):
    """Anything that can search movies by title (the real client or a test fake)."""

    async def search_movies(self, query: str, year: int | None = None) -> list[TmdbMovie]: ...


class TmdbClient:
    """Async TMDB client. Use as ``async with TmdbClient() as tmdb: ...``."""

    def __init__(self, api_key: str | None = None, timeout: float = 10.0) -> None:
        self.api_key = api_key if api_key is not None else settings.TMDB_API_KEY
        if not self.api_key:
            raise ValueError("TMDB_API_KEY non configurata (aggiungila al file .env)")
        self._client = httpx.AsyncClient(base_url=TMDB_API_URL, timeout=timeout)

    async def __aenter__(self) -> TmdbClient:
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def search_movies(self, query: str, year: int | None = None) -> list[TmdbMovie]:
        """Search movies by title in Italian, optionally restricted to a release year."""
        params: dict[str, str | int] = {
            "api_key": self.api_key,
            "query": query,
            "language": "it-IT",
            "region": "IT",
            "include_adult": "false",
        }
        if year:
            params["year"] = year
        resp = await self._client.get("/search/movie", params=params)
        resp.raise_for_status()
        return [TmdbMovie.from_api(hit) for hit in resp.json().get("results", [])]

    async def get_movie(self, tmdb_id: int) -> TmdbMovie | None:
        """Fetch one movie by TMDB id (None if it does not exist)."""
        resp = await self._client.get(f"/movie/{tmdb_id}", params={"api_key": self.api_key, "language": "it-IT"})
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return TmdbMovie.from_api(resp.json())

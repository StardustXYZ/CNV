"""TMDB integration – search for film metadata (poster, year, official title)."""

from __future__ import annotations

import httpx

from app.config import settings


async def search_tmdb(title: str, year: int | None = None) -> dict | None:
    """Query The Movie Database and return the best match.

    Returns ``{"tmdb_id": int, "title": str, "poster_url": str|None, "year": int|None}``
    or ``None`` when no key is configured or no result is found.
    """
    api_key = settings.TMDB_API_KEY
    if not api_key:
        return None

    params: dict[str, str | int] = {
        "api_key": api_key,
        "query": title,
        "language": "it-IT",
    }
    if year:
        params["year"] = year

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://api.themoviedb.org/3/search/movie",
            params=params,
        )
        if resp.status_code != 200:
            return None

        results = resp.json().get("results", [])
        if not results:
            return None

        hit = results[0]
        return {
            "tmdb_id": hit["id"],
            "title": hit["title"],
            "poster_url": (
                f"https://image.tmdb.org/t/p/w300{hit['poster_path']}"
                if hit.get("poster_path")
                else None
            ),
            "year": (
                int(hit["release_date"][:4]) if hit.get("release_date") else None
            ),
        }


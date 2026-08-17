from __future__ import annotations

from secrets import compare_digest
from typing import Any

from .config import Settings
from .db import Database
from .repository import GraphRepository


def create_app():
    try:
        from fastapi import Depends, FastAPI, Header, HTTPException, status
        from fastapi.middleware.cors import CORSMiddleware
        from pydantic import BaseModel, ConfigDict
    except ImportError as exc:  # pragma: no cover - exercised by CLI error path
        raise RuntimeError("Install the API extra: uv sync --extra api") from exc

    settings = Settings.load()
    repo = GraphRepository(Database(settings))
    app = FastAPI(
        title="People Memory API",
        version="0.1.0",
        description="Optional REST API for the private People Memory graph.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    class PersonCreate(BaseModel):
        model_config = ConfigDict(extra="forbid")
        full_name: str
        first_name: str | None = None
        last_name: str | None = None
        birthdate: str | None = None
        birthday_md: str | None = None
        city: str | None = None
        country: str | None = None
        current_org: str | None = None
        current_role: str | None = None
        linkedin_url: str | None = None
        tie_strength: int | None = None
        met_where: str | None = None
        met_when: str | None = None
        summary: str | None = None

    class PersonPatch(BaseModel):
        model_config = ConfigDict(extra="forbid")
        full_name: str | None = None
        first_name: str | None = None
        last_name: str | None = None
        birthdate: str | None = None
        birthday_md: str | None = None
        city: str | None = None
        country: str | None = None
        current_org: str | None = None
        current_role: str | None = None
        linkedin_url: str | None = None
        tie_strength: int | None = None
        met_where: str | None = None
        met_when: str | None = None
        summary: str | None = None

    async def authorize(authorization: str | None = Header(default=None)) -> None:
        if not settings.api_token:
            return
        expected = f"Bearer {settings.api_token}"
        if authorization is None or not compare_digest(authorization, expected):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    @app.get("/health", dependencies=[Depends(authorize)])
    def health() -> dict[str, Any]:
        return repo.status()

    @app.get("/api/graph", dependencies=[Depends(authorize)])
    def graph(limit: int = 5000) -> dict[str, Any]:
        return repo.graph_snapshot(limit)

    @app.get("/api/people", dependencies=[Depends(authorize)])
    def people(q: str = "", limit: int = 50) -> list[dict[str, Any]]:
        return repo.search_people(q, limit)

    @app.get("/api/people/{person_id}", dependencies=[Depends(authorize)])
    def person(person_id: int) -> dict[str, Any]:
        found = repo.get_person(person_id)
        if not found:
            raise HTTPException(status_code=404, detail="Person not found")
        return found

    @app.post("/api/people", dependencies=[Depends(authorize)], status_code=201)
    def create_person(body: PersonCreate) -> dict[str, Any]:
        return repo.create_person(body.model_dump(exclude_none=True))

    @app.patch("/api/people/{person_id}", dependencies=[Depends(authorize)])
    def update_person(person_id: int, body: PersonPatch) -> dict[str, Any]:
        found = repo.update_person(person_id, body.model_dump(exclude_unset=True))
        if not found:
            raise HTTPException(status_code=404, detail="Person not found")
        return found

    @app.delete("/api/people/{person_id}", dependencies=[Depends(authorize)])
    def delete_person(person_id: int) -> dict[str, bool]:
        if not repo.delete_person(person_id):
            raise HTTPException(status_code=404, detail="Person not found")
        return {"deleted": True}

    return app

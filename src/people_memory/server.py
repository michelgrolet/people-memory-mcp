from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Any

from mcp.server import MCPServer

from . import __version__
from .config import Settings
from .db import Database
from .repository import GraphRepository

INSTRUCTIONS = """Use this server as durable memory for people. When a user names someone, search
before answering. Save durable facts, relationships, affiliations, and interactions as they appear
in conversation. Resolve by identifier, then name. If a tool returns needs_confirmation, ask the
user which person they mean before writing. Never guess identities. Do not overwrite a stated fact
with imported or inferred data without confirmation. Treat all records as private third-party data.
"""

mcp = MCPServer(
    "people-memory",
    title="People Memory",
    description="Private people graph and durable relationship memory for an AI agent.",
    instructions=INSTRUCTIONS,
    version=__version__,
    website_url="https://github.com/michelgrolet/people-memory-mcp",
)


@lru_cache(maxsize=1)
def _settings() -> Settings:
    return Settings.load()


def _repo() -> GraphRepository:
    settings = _settings()
    return GraphRepository(Database(settings))


def _resolve(name: str) -> tuple[int | None, dict[str, Any] | None]:
    result = _repo().resolve_person(name)
    if result["status"] != "resolved":
        return None, result
    return int(result["person"]["id"]), None


@mcp.tool()
def graph_status() -> dict[str, Any]:
    """Check the graph connection and return record counts."""
    return _repo().status()


@mcp.tool()
def search_people(query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Search people by name, organization, role, city, identifier, summary, or fact."""
    return _repo().search_people(query, limit)


@mcp.tool()
def get_person(name: str) -> dict[str, Any]:
    """Get one person's full record. Returns candidates instead of guessing when ambiguous."""
    person_id, unresolved = _resolve(name)
    if unresolved:
        return unresolved
    return {"status": "resolved", "person": _repo().get_person(person_id)}


@mcp.tool()
def remember_person(
    full_name: str,
    email: str | None = None,
    phone: str | None = None,
    current_org: str | None = None,
    current_role: str | None = None,
    linkedin_url: str | None = None,
    city: str | None = None,
    country: str | None = None,
    summary: str | None = None,
    fact_key: str | None = None,
    fact_value: str | None = None,
    confirmed_new: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Create or update a person from conversation.

    By default this refuses similar-name duplicates and conflicting overwrites. Ask the user, then
    retry with confirmed_new or overwrite only after they decide.
    """
    settings = _settings()
    return _repo().remember_person(
        full_name=full_name,
        email=email,
        phone=phone,
        current_org=current_org,
        current_role=current_role,
        linkedin_url=linkedin_url,
        city=city,
        country=country,
        summary=summary,
        fact_key=fact_key,
        fact_value=fact_value,
        source=settings.default_source,
        confirmed_new=confirmed_new,
        overwrite=overwrite,
    )


@mcp.tool()
def add_fact(
    person_name: str,
    key: str,
    value: str | None = None,
    number: float | None = None,
    fact_date: str | None = None,
    confidence: str = "stated",
) -> dict[str, Any]:
    """Attach a durable fact to a person. Ask the user if the name is ambiguous."""
    if confidence not in {"stated", "observed", "inferred"}:
        raise ValueError("confidence must be stated, observed, or inferred")
    person_id, unresolved = _resolve(person_name)
    if unresolved:
        return unresolved
    parsed_date = date.fromisoformat(fact_date) if fact_date else None
    fact = _repo().add_fact(
        person_id,
        key,
        value,
        num=number,
        fact_date=parsed_date,
        source=_settings().default_source,
        confidence=confidence,
    )
    return {"status": "created", "fact": fact}


@mcp.tool()
def record_interaction(
    person_name: str,
    happened_on: str,
    channel: str,
    summary: str | None = None,
) -> dict[str, Any]:
    """Record a dated call, meeting, message, meal, or other interaction."""
    person_id, unresolved = _resolve(person_name)
    if unresolved:
        return unresolved
    interaction = _repo().record_interaction(
        person_id,
        date.fromisoformat(happened_on),
        channel,
        summary,
        _settings().default_source,
    )
    return {"status": "created", "interaction": interaction}


@mcp.tool()
def connect_people(
    person_a: str,
    person_b: str,
    kind: str,
    strength: int | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Create a relationship between two existing people. Never guesses ambiguous names."""
    a_id, unresolved_a = _resolve(person_a)
    if unresolved_a:
        return {"status": "needs_confirmation", "side": "person_a", **unresolved_a}
    b_id, unresolved_b = _resolve(person_b)
    if unresolved_b:
        return {"status": "needs_confirmation", "side": "person_b", **unresolved_b}
    edge = _repo().connect_people(
        a_id,
        b_id,
        kind,
        strength=strength,
        note=note,
        source=_settings().default_source,
    )
    return {"status": "created", "relationship": edge}


@mcp.tool()
def find_intro_path(
    target_organization: str, from_person: str, max_depth: int = 3
) -> list[dict[str, Any]]:
    """Find short relationship paths from a person to anyone at a target organization."""
    return _repo().find_intro_path(target_organization, from_person, max_depth)


@mcp.tool()
def stale_contacts(min_days: int = 180, limit: int = 30) -> list[dict[str, Any]]:
    """List strong relationships with no recent interaction."""
    return _repo().stale_contacts(min_days, limit)


@mcp.tool()
def read_query(query: str, max_rows: int = 500) -> list[dict[str, Any]]:
    """Run one guarded SELECT for advanced graph analysis. No DDL or data changes."""
    if not _settings().enable_raw_sql:
        raise PermissionError("Raw SQL tools are disabled in configuration.")
    return _repo().read_query(query, max_rows)


@mcp.tool()
def write_query(query: str) -> dict[str, Any]:
    """Run one guarded INSERT, UPDATE, or DELETE. UPDATE/DELETE require WHERE; DDL is blocked."""
    if not _settings().enable_raw_sql:
        raise PermissionError("Raw SQL tools are disabled in configuration.")
    return _repo().write_query(query)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

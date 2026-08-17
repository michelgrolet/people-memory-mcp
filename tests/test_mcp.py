import asyncio

import pytest

from people_memory import server
from people_memory.server import INSTRUCTIONS, mcp


def test_server_exposes_semantic_tools() -> None:
    tools = asyncio.run(mcp.list_tools())
    names = {tool.name for tool in tools}
    assert {
        "search_people",
        "get_person",
        "remember_person",
        "add_fact",
        "record_interaction",
        "connect_people",
        "find_intro_path",
        "stale_contacts",
        "read_query",
        "write_query",
    } <= names


def test_server_instructions_put_identity_safety_first() -> None:
    normalized = " ".join(INSTRUCTIONS.split())
    assert "search before answering" in normalized
    assert "ask the user" in normalized
    assert "Never guess identities" in normalized


def test_serve_refuses_to_start_without_a_database_url(monkeypatch, tmp_path) -> None:
    # Settings are read on the first tool call, so a missing connection string used to produce a
    # server that started happily and then failed every tool from inside the agent. It has to fail
    # here instead, where the MCP client writes the reason to its own log.
    monkeypatch.delenv("PEOPLE_MEMORY_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("PEOPLE_MEMORY_ENV_FILE", str(tmp_path / "absent.env"))
    server._settings.cache_clear()

    with pytest.raises(SystemExit) as exit_info:
        server.serve()

    assert "PEOPLE_MEMORY_DATABASE_URL is missing" in str(exit_info.value)
    server._settings.cache_clear()

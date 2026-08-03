import asyncio

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

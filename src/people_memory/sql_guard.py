from __future__ import annotations

import re

import sqlparse
from sqlparse.sql import Where
from sqlparse.tokens import DML, Keyword

BLOCKED_KEYWORDS = {
    "ALTER",
    "CALL",
    "COPY",
    "CREATE",
    "DO",
    "DROP",
    "EXECUTE",
    "GRANT",
    "REVOKE",
    "TRUNCATE",
}


def _statement(sql: str):
    statements = [statement for statement in sqlparse.parse(sql) if str(statement).strip()]
    if len(statements) != 1:
        raise ValueError("Exactly one SQL statement is allowed.")
    statement = statements[0]
    keywords = {
        token.normalized.upper()
        for token in statement.flatten()
        if token.ttype in Keyword or token.ttype is Keyword
    }
    blocked = sorted(keywords & BLOCKED_KEYWORDS)
    if blocked:
        raise ValueError(f"Blocked SQL keyword: {blocked[0]}.")
    return statement


def guard_read(sql: str) -> str:
    cleaned = sql.strip().rstrip(";").strip()
    statement = _statement(cleaned)
    if statement.get_type().upper() != "SELECT":
        raise ValueError("read_query accepts a single SELECT statement only.")
    dml = [token.normalized.upper() for token in statement.flatten() if token.ttype is DML]
    if any(keyword != "SELECT" for keyword in dml):
        raise ValueError("Data-changing statements are blocked inside read_query CTEs.")
    if re.search(r"\b(pg_sleep|dblink|lo_import|lo_export)\s*\(", cleaned, re.IGNORECASE):
        raise ValueError("This database function is blocked in raw SQL tools.")
    return cleaned


def guard_write(sql: str) -> str:
    cleaned = sql.strip().rstrip(";").strip()
    statement = _statement(cleaned)
    statement_type = statement.get_type().upper()
    if statement_type not in {"INSERT", "UPDATE", "DELETE"}:
        raise ValueError("write_query accepts one INSERT, UPDATE, or DELETE statement only.")
    dml = [token.normalized.upper() for token in statement.flatten() if token.ttype is DML]
    changing = [keyword for keyword in dml if keyword in {"INSERT", "UPDATE", "DELETE"}]
    if changing != [statement_type]:
        raise ValueError("Only one data-changing operation is allowed per write_query call.")
    if statement_type in {"UPDATE", "DELETE"} and not any(
        isinstance(token, Where) for token in statement.tokens
    ):
        raise ValueError(f"{statement_type} without WHERE is blocked.")
    if re.search(r"\b(pg_sleep|dblink|lo_import|lo_export)\s*\(", cleaned, re.IGNORECASE):
        raise ValueError("This database function is blocked in raw SQL tools.")
    return cleaned

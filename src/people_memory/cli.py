from __future__ import annotations

import argparse
import getpass
import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

from .config import DEFAULT_ENV_PATH, Settings
from .db import Database
from .importers import (
    fetch_linkedin_connections,
    parse_google_csv,
    parse_linkedin_csv,
    parse_whatsapp_export,
)
from .repository import GraphRepository

REPOSITORY_URL = "git+https://github.com/michelgrolet/people-memory-mcp"


def _write_env(values: dict[str, str], path: Path = DEFAULT_ENV_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(f"{key}={value}" for key, value in values.items() if value is not None) + "\n"
    path.write_text(body, encoding="utf-8")
    path.chmod(0o600)
    return path


def _ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    answer = input(f"{prompt}{suffix}: ").strip()
    return answer or (default or "")


def cmd_setup(_: argparse.Namespace) -> None:
    print("People Memory setup\n")
    print("1) Local Supabase (private, offline, Docker required)")
    print("2) Hosted Supabase (recommended free cloud option)")
    print("3) Existing PostgreSQL")
    mode = _ask("Choose where the graph should live", "2")

    if mode == "1":
        if not shutil.which("supabase"):
            raise SystemExit(
                "Supabase CLI is required: https://supabase.com/docs/guides/local-development"
            )
        print("Run `supabase start` from the cloned repository, then copy its DB URL below.")
        database_url = _ask(
            "PostgreSQL URL",
            "postgresql://postgres:postgres@127.0.0.1:54322/postgres",
        )
    else:
        database_url = getpass.getpass("PostgreSQL URL (input hidden): ").strip()
        if not database_url:
            raise SystemExit("A PostgreSQL URL is required.")

    token_choice = _ask("Protect the optional REST API with a generated token? (Y/n)", "Y")
    api_token = secrets.token_urlsafe(32) if token_choice.lower() not in {"n", "no"} else ""
    env_path = _write_env(
        {
            "PEOPLE_MEMORY_DATABASE_URL": database_url,
            "PEOPLE_MEMORY_API_TOKEN": api_token,
            "PEOPLE_MEMORY_ENABLE_RAW_SQL": "false",
            "PEOPLE_MEMORY_DEFAULT_SOURCE": "agent",
        }
    )
    print(f"\nSaved private config to {env_path}")

    agents = _ask("Connect Codex, Claude Code, both, or neither?", "both").lower()
    command = ["uvx", "--from", REPOSITORY_URL, "people-memory-mcp"]
    if agents in {"codex", "both"} and shutil.which("codex"):
        subprocess.run(
            [
                "codex",
                "mcp",
                "add",
                "people-memory",
                "--env",
                f"PEOPLE_MEMORY_ENV_FILE={env_path}",
                "--",
                *command,
            ],
            check=True,
        )
        print("Connected Codex. Start a new task before using the MCP.")
    if agents in {"claude", "claude code", "both"} and shutil.which("claude"):
        subprocess.run(
            [
                "claude",
                "mcp",
                "add",
                "-s",
                "user",
                "people-memory",
                "-e",
                f"PEOPLE_MEMORY_ENV_FILE={env_path}",
                "--",
                *command,
            ],
            check=True,
        )
        print("Connected Claude Code. Start a new session before using the MCP.")

    print(
        "\nPossible imports: LinkedIn Connections.csv, Google Contacts CSV, WhatsApp chat export."
    )
    print("Use `people-memory import --help`, or ask your agent to run the import-contacts skill.")


def _repo() -> GraphRepository:
    return GraphRepository(Database(Settings.load()))


def _import_record(repo: GraphRepository, record, accept_similar_as_new: bool = False) -> dict:
    result = repo.remember_person(
        full_name=record.full_name,
        email=record.emails[0] if record.emails else None,
        phone=record.phones[0] if record.phones else None,
        current_org=record.organization,
        current_role=record.role,
        linkedin_url=record.linkedin_url,
        city=record.city,
        country=record.country,
        birthdate=record.birthdate,
        birthday_md=record.birthday_md,
        source=record.source,
        confirmed_new=accept_similar_as_new,
        overwrite=False,
    )
    person = result.get("person") or {}
    if result.get("status") not in {"created", "updated"} or not person.get("id"):
        return result

    conflicts = []
    for kind, values in (("email", record.emails[1:]), ("phone", record.phones[1:])):
        for value in values:
            added = repo.add_identifier(person["id"], kind, value, record.source)
            if added["status"] == "needs_confirmation":
                conflicts.append(added)
    if conflicts:
        result["identifier_conflicts"] = conflicts
    return result


def _preview(records) -> dict:
    sample = [
        {
            "full_name": record.full_name,
            "has_email": bool(record.emails),
            "has_phone": bool(record.phones),
            "organization": record.organization,
            "source": record.source,
        }
        for record in records[:5]
    ]
    return {"records": len(records), "sample": sample}


def _apply_import(
    repo: GraphRepository, records, interactions: dict, accept_similar_as_new: bool
) -> dict:
    stats = {"created": 0, "updated": 0, "needs_confirmation": 0}
    unresolved = []
    for record in records:
        result = _import_record(repo, record, accept_similar_as_new)
        status = result.get("status", "needs_confirmation")
        stats[status] = stats.get(status, 0) + 1
        if status == "needs_confirmation" and len(unresolved) < 50:
            unresolved.append(
                {
                    "incoming": record.full_name,
                    "reason": result.get("reason"),
                    "candidates": result.get("candidates", []),
                    "conflicts": result.get("conflicts", {}),
                }
            )
        for conflict in result.get("identifier_conflicts", []):
            if len(unresolved) >= 50:
                break
            unresolved.append({"incoming": record.full_name, **conflict})
        person = result.get("person") or {}
        if status in {"created", "updated"} and record.connected_on:
            # `date` as well as `value`: the ISO string is what a person reads on a card, the date
            # column is what SQL can filter and sort on. Writing only the string means every query
            # about when a connection happened has to parse text first.
            repo.add_fact(
                person["id"],
                "linkedin_connected_on",
                record.connected_on.isoformat(),
                fact_date=record.connected_on,
                source="linkedin",
                confidence="observed",
            )
        if status in {"created", "updated"} and record.full_name in interactions:
            latest = max(interactions[record.full_name])
            repo.record_interaction(
                person["id"], latest, "whatsapp", "Latest message in imported chat", "whatsapp"
            )
    return {"counts": stats, "unresolved": unresolved}


def cmd_import(args: argparse.Namespace) -> None:
    path = Path(args.path).expanduser()
    if args.source == "linkedin":
        records = parse_linkedin_csv(path)
        interactions = {}
    elif args.source == "google":
        records = parse_google_csv(path)
        interactions = {}
    else:
        if not args.self_name:
            raise SystemExit("--self-name is required for WhatsApp exports")
        try:
            records, interactions = parse_whatsapp_export(path, args.self_name, args.date_order)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc

    if args.dry_run:
        print(json.dumps(_preview(records), indent=2))
        return

    repo = _repo()
    result = _apply_import(repo, records, interactions, args.accept_similar_as_new)
    print(json.dumps(result, indent=2, default=str))


def cmd_sync_linkedin(args: argparse.Namespace) -> None:
    token = os.environ.get("LINKEDIN_OAUTH_TOKEN")
    if not token:
        raise SystemExit("Set the LINKEDIN_OAUTH_TOKEN environment variable")
    try:
        records = fetch_linkedin_connections(token)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    if args.dry_run:
        print(json.dumps(_preview(records), indent=2))
        return

    repo = _repo()
    result = _apply_import(repo, records, {}, args.accept_similar_as_new)
    print(json.dumps(result, indent=2, default=str))


def cmd_status(_: argparse.Namespace) -> None:
    print(json.dumps(_repo().status(), indent=2, default=str))


def cmd_mcp(_: argparse.Namespace) -> None:
    from .server import main as server_main

    server_main()


def cmd_api(args: argparse.Namespace) -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit("Install the API extra: uv sync --extra api") from exc
    if args.host not in {"127.0.0.1", "localhost", "::1"} and not Settings.load().api_token:
        raise SystemExit(
            "Refusing a network API without PEOPLE_MEMORY_API_TOKEN. "
            "Set a token or bind to 127.0.0.1."
        )
    uvicorn.run("people_memory.api:create_app", factory=True, host=args.host, port=args.port)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="people-memory", description="Private people graph for AI agents"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("setup", help="interactive database and agent setup").set_defaults(
        func=cmd_setup
    )
    sub.add_parser("status", help="check database and counts").set_defaults(func=cmd_status)
    sub.add_parser("mcp", help="run the stdio MCP server").set_defaults(func=cmd_mcp)

    api = sub.add_parser("api", help="run the optional REST API")
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=8765)
    api.set_defaults(func=cmd_api)

    importer = sub.add_parser("import", help="import contacts from an export")
    importer.add_argument("source", choices=["linkedin", "google", "whatsapp"])
    importer.add_argument("path")
    importer.add_argument("--self-name", help="your display name in a WhatsApp export")
    importer.add_argument(
        "--date-order",
        choices=["dmy", "mdy"],
        help="required when WhatsApp dates are ambiguous, for example 03/08/2026",
    )
    importer.add_argument(
        "--dry-run", action="store_true", help="parse and preview without writing"
    )
    importer.add_argument(
        "--accept-similar-as-new",
        action="store_true",
        help="create similar names as new people after manual review",
    )
    importer.set_defaults(func=cmd_import)

    sync = sub.add_parser(
        "sync-linkedin",
        help="fetch 1st-degree connections live via LinkedIn's Member Data Portability API",
    )
    sync.add_argument("--dry-run", action="store_true", help="fetch and preview without writing")
    sync.add_argument(
        "--accept-similar-as-new",
        action="store_true",
        help="create similar names as new people after manual review",
    )
    sync.set_defaults(func=cmd_sync_linkedin)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\nCancelled", file=sys.stderr)
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()

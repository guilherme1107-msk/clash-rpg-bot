"""Configura os identificadores privados da Activity sem exibi-los no terminal."""

from __future__ import annotations

import base64
from getpass import getpass
from pathlib import Path

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
FRONTEND_ENV_PATH = ROOT / "ui" / "discord-activity" / ".env"


def suggested_client_id(token: str) -> str:
    try:
        first = token.split(".", 1)[0]
        padding = "=" * (-len(first) % 4)
        value = base64.urlsafe_b64decode(first + padding).decode("ascii")
        return value if value.isdigit() else ""
    except (ValueError, UnicodeDecodeError):
        return ""


def update_env(path: Path, updates: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(updates)
    result = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else ""
        if key in remaining:
            result.append(f"{key}={remaining.pop(key)}")
        else:
            result.append(line)
    if remaining and result and result[-1]:
        result.append("")
    result.extend(f"{key}={value}" for key, value in remaining.items())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(result) + "\n", encoding="utf-8")


def main() -> None:
    current = dotenv_values(ENV_PATH)
    suggested = str(current.get("DISCORD_CLIENT_ID") or suggested_client_id(str(current.get("DISCORD_TOKEN") or "")))
    label = f" [{suggested}]" if suggested else ""
    client_id = input(f"Application ID do Discord{label}: ").strip() or suggested
    if not client_id.isdigit():
        raise SystemExit("Application ID inválido.")
    existing_secret = str(current.get("DISCORD_CLIENT_SECRET") or "")
    secret = getpass("Client Secret (fica oculto): ").strip() or existing_secret
    if not secret:
        raise SystemExit("Client Secret é obrigatório.")
    update_env(ENV_PATH, {
        "DISCORD_CLIENT_ID": client_id,
        "DISCORD_CLIENT_SECRET": secret,
        "ACTIVITY_PORT": str(current.get("ACTIVITY_PORT") or "8780"),
    })
    update_env(FRONTEND_ENV_PATH, {"VITE_DISCORD_CLIENT_ID": client_id})
    print("Activity configurada. Os segredos permanecem apenas nos arquivos ignorados pelo Git.")


if __name__ == "__main__":
    main()

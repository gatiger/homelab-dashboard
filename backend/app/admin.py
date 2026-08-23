"""Host-side emergency account recovery for Homelab Dashboard.

Run inside the dashboard container, for example:
    python -m app.admin reset-password
    python -m app.admin reset-password alice
    python -m app.admin list-users

This command is intentionally available only to someone who already has shell
access to the dashboard container/host. Passwords are never accepted as
command-line arguments, so credentials are not exposed through process listings.
"""
from __future__ import annotations

import argparse
import getpass
import sys

from .main import audit_account_event, db, hash_password, init_db, iso_now, rotate_recovery_code


def list_users() -> int:
    init_db()
    with db() as connection:
        rows = connection.execute(
            "SELECT id, username, role, enabled FROM dashboard_users ORDER BY id"
        ).fetchall()
    if not rows:
        print("No dashboard users exist yet.")
        return 0
    for row in rows:
        state = "enabled" if bool(row["enabled"]) else "disabled"
        print(f"{row['id']}: {row['username']} ({row['role']}, {state})")
    return 0


def reset_password(username: str | None = None) -> int:
    init_db()
    with db() as connection:
        if username:
            user = connection.execute(
                "SELECT id, username FROM dashboard_users WHERE username = ? COLLATE NOCASE",
                (username.strip(),),
            ).fetchone()
        else:
            user = connection.execute(
                "SELECT id, username FROM dashboard_users WHERE role = 'owner' ORDER BY id LIMIT 1"
            ).fetchone()
        if not user:
            label = f"User {username!r} was not found." if username else "No owner account exists yet."
            print(label, file=sys.stderr)
            return 2

        print(f"Resetting password for dashboard user: {user['username']}")
        first = getpass.getpass("New password (minimum 10 characters): ")
        second = getpass.getpass("Confirm new password: ")
        if len(first) < 10:
            print("Password must be at least 10 characters.", file=sys.stderr)
            return 2
        if first != second:
            print("Passwords do not match.", file=sys.stderr)
            return 2

        now = iso_now()
        connection.execute(
            "UPDATE dashboard_users SET password_hash = ?, password_changed_at = ?, enabled = 1 WHERE id = ?",
            (hash_password(first), now, user["id"]),
        )
        connection.execute("DELETE FROM dashboard_sessions WHERE user_id = ?", (user["id"],))
        recovery = rotate_recovery_code(connection, int(user["id"]))
        audit_account_event(
            connection,
            int(user["id"]),
            user["username"],
            "emergency_password_reset",
            "Password reset from the host-side recovery command; account enabled and all sessions invalidated",
        )
        audit_account_event(
            connection,
            int(user["id"]),
            user["username"],
            "recovery_code_rotated",
            "Recovery code rotated after host-side password reset",
        )

    print("\nPassword reset complete. Existing sessions for this account were signed out.")
    print("The account was enabled and its previous recovery code was invalidated.")
    print("Save this NEW recovery code somewhere safe; it will not be shown again:\n")
    print(recovery.recovery_code)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.admin", description="Homelab Dashboard emergency administration")
    subcommands = parser.add_subparsers(dest="command", required=True)
    reset = subcommands.add_parser("reset-password", help="Reset a local user's password and rotate its recovery code")
    reset.add_argument("username", nargs="?", help="Username to reset; defaults to the first owner account")
    subcommands.add_parser("list-users", help="List local dashboard users and roles")
    args = parser.parse_args()
    if args.command == "reset-password":
        return reset_password(args.username)
    if args.command == "list-users":
        return list_users()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

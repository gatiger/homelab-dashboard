"""Host-side emergency account recovery for Homelab Dashboard.

Run inside the dashboard container, for example:
    python -m app.admin reset-password

This command is intentionally available only to someone who already has shell
access to the dashboard container/host. It never accepts a password as a
command-line argument, so credentials are not exposed through process listings.
"""
from __future__ import annotations

import argparse
import getpass
import sys

from .main import audit_account_event, db, hash_password, init_db, iso_now, rotate_recovery_code


def reset_password() -> int:
    init_db()
    with db() as connection:
        user = connection.execute("SELECT id, username FROM admin_users ORDER BY id LIMIT 1").fetchone()
        if not user:
            print("No administrator account exists yet. Complete first-run setup in the web interface.", file=sys.stderr)
            return 2

        print(f"Resetting password for administrator: {user['username']}")
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
            "UPDATE admin_users SET password_hash = ?, password_changed_at = ? WHERE id = ?",
            (hash_password(first), now, user["id"]),
        )
        connection.execute("DELETE FROM sessions WHERE user_id = ?", (user["id"],))
        recovery = rotate_recovery_code(connection, int(user["id"]))
        audit_account_event(
            connection,
            int(user["id"]),
            user["username"],
            "emergency_password_reset",
            "Password reset from the host-side recovery command; all sessions invalidated",
        )
        audit_account_event(
            connection,
            int(user["id"]),
            user["username"],
            "recovery_code_rotated",
            "Recovery code rotated after host-side password reset",
        )

    print("\nPassword reset complete. All existing dashboard sessions were signed out.")
    print("Your previous recovery code has also been invalidated.")
    print("Save this NEW recovery code somewhere safe; it will not be shown again:\n")
    print(recovery.recovery_code)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.admin", description="Homelab Dashboard emergency administration")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("reset-password", help="Reset the local administrator password and rotate its recovery code")
    args = parser.parse_args()
    if args.command == "reset-password":
        return reset_password()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

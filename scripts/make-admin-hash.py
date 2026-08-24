#!/usr/bin/env python3
"""Generate the admin password hash and session secret for the deployment.

Run locally, paste the OUTPUT into Render's environment variables. The password
itself is never stored anywhere — not in the repo, not in the server's config,
not in this script's output.

    python scripts/make-admin-hash.py
"""
import getpass
import os
import secrets
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from auth import hash_password  # noqa: E402


def main() -> int:
    print("Admin credentials for the EPL Predictor deployment.\n")
    username = input("Admin username: ").strip()
    if not username:
        print("error: username cannot be empty", file=sys.stderr)
        return 1

    password = getpass.getpass("Admin password (not echoed): ")
    if len(password) < 12:
        # Not arbitrary: this is the only account, it is reachable from the public
        # internet, and there is no lockout beyond the rate limit.
        print("error: use at least 12 characters — this is the only admin account", file=sys.stderr)
        return 1
    if password != getpass.getpass("Confirm password: "):
        print("error: passwords do not match", file=sys.stderr)
        return 1

    print("\nSet these in Render -> your service -> Environment:\n")
    print(f"  ADMIN_USERNAME       {username}")
    print(f"  ADMIN_PASSWORD_HASH  {hash_password(password)}")
    print(f"  SESSION_SECRET       {secrets.token_urlsafe(48)}")
    print(f"  ADMIN_API_KEY        {secrets.token_urlsafe(32)}")
    print("\nADMIN_API_KEY also goes in GitHub -> Settings -> Secrets -> Actions,")
    print("so the scheduled data refresh can authenticate.")
    print("\nNothing above contains the password itself. Store it in a password manager;")
    print("there is no reset flow — losing it means editing the env var again.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

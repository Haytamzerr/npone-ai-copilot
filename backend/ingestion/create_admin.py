"""
ingestion/create_admin.py
----------------------------
One-off CLI helper to generate a bcrypt hash for the admin dashboard
password. The plaintext password is never stored -- copy the printed hash
into ADMIN_PASSWORD_HASH in your .env file.

Usage:
    python ingestion/create_admin.py
"""
import getpass
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from utils.security import hash_password


def main():
    password = getpass.getpass("New admin password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords do not match. Aborting.")
        return
    if len(password) < 8:
        print("Password must be at least 8 characters.")
        return

    hashed = hash_password(password)
    print("\nAdd this line to your backend/.env file:\n")
    print(f"ADMIN_PASSWORD_HASH={hashed}\n")


if __name__ == "__main__":
    main()

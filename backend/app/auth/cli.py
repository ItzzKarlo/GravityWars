from __future__ import annotations

import argparse
import getpass
import sys

from argon2 import PasswordHasher


def hash_password() -> int:
    first = getpass.getpass("Admin password: ")
    second = getpass.getpass("Confirm password: ")
    if len(first) < 14:
        print("Password must be at least 14 characters.", file=sys.stderr)
        return 2
    if first != second:
        print("Passwords do not match.", file=sys.stderr)
        return 2
    print(PasswordHasher().hash(first))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Gravity Wars admin tools")
    parser.add_argument("command", choices=["hash-password"])
    args = parser.parse_args()
    if args.command == "hash-password":
        return hash_password()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

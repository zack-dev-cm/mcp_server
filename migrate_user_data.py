"""Explicit, offline migration of the old user-data storage format."""

import argparse
import json
import os
from pathlib import Path
import sqlite3

from secure_store import (
    StorageConfigurationError,
    StorageIntegrityError,
    migrate_legacy_user_data,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-key-env", default="LEGACY_MASTER_KEY")
    parser.add_argument("--apply", action="store_true", help="Apply after validating all rows")
    parser.add_argument("--backup", type=Path, help="New backup file required when applying")
    args = parser.parse_args()
    legacy_key = os.getenv(args.legacy_key_env)
    if legacy_key is None:
        parser.error("The selected legacy-key environment variable must be explicitly set")
    if args.apply and args.backup is None:
        parser.error("--apply requires --backup")
    try:
        result = migrate_legacy_user_data(
            legacy_key, dry_run=not args.apply, backup_path=args.backup
        )
    except (StorageConfigurationError, StorageIntegrityError, ValueError, OSError, sqlite3.Error):
        parser.exit(1, "Migration failed; no row updates were committed. Check key configuration, input data and backup destination.\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

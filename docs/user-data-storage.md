# User-data storage and migration

The user-data store uses Fernet authenticated encryption. Each versioned token
contains both its row identity and its JSON value, so moving a token to another
identity is rejected. The SQLite path, `userdata` table and the public
`store_user_data`, `retrieve_user_data`, `save_user_data`, `load_user_data` and
`delete_user_data` helpers remain available. Missing rows return the helper's
`default`, which is `None` unless supplied. HTTP GET uses a sentinel so stored
`null` is returned as `null`, while a missing row retains the `{}` response.

## Configure a new store

Install `cryptography==50.0.2` and set `MASTER_KEY` in the server's process
environment. A Fernet key is 32 random bytes encoded as URL-safe base64. For
local development, this command generates a key without printing it:

```bash
export MASTER_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
export USERDATA_DB=/path/to/private/userdata.db
```

Keep the key in an appropriate secret store for subsequent starts. Do not
generate a new key on every restart. Never put it in source control, command
arguments, notebooks or application logs. `MASTER_KEY` is read from the process
environment, not automatically from `dev.env`. Without a valid key, storage
operations fail before creating or opening the database.

The default path is `user_store/data.db` beside `secure_store.py`. Explicitly
set `USERDATA_DB` to the existing path when upgrading. The container needs a
persistent volume if data must survive replacement. Fernet tokens reveal their
creation timestamp, and SQLite still contains plaintext row identities. In
this demo those identities are session bearer tokens. New database files use
mode `0600`, and newly created immediate parent directories use `0700`.
Existing files and shared parent permissions are preserved. Check and protect
an existing database, its directory and any journal or WAL files before using
it; encrypted values do not protect a readable session token.

## Migrate an existing store

Legacy rows used base64-encoded XOR with a SHA-256-derived key. That format
cannot authenticate data. A successful decode only shows that the result is
finite JSON; it cannot prove that old contents were intact. Check known values
against a trusted source before accepting the migration.

Stop all application writers and keep the previous code and configuration
available. Work on a protected copy first. Set `USERDATA_DB` to the actual
database, set `MASTER_KEY` to the new Fernet key, and supply the exact previous
key as `LEGACY_MASTER_KEY` through the process environment. Read the old key
from its existing secret configuration. If the old deployment used its
historical default, establish that explicitly; the migration never guesses a
default. Even an empty previous key must be explicitly supplied.

Validate every row without updating it:

```bash
python migrate_user_data.py
```

This dry run opens only an existing database. It rejects malformed legacy
rows, incorrect keys that fail decoding, and current-format rows that fail
authentication or identity verification. Its output contains counts only.

After verifying the decoded values in the protected copy, apply with a new
backup filename in an existing private directory:

```bash
python migrate_user_data.py --apply --backup /private/backups/userdata-before-migration.db
```

The tool first validates all rows, then creates a SQLite backup of the
committed database with mode `0600`, then updates legacy rows in one
transaction. It refuses to overwrite an existing backup or use the database
itself as the backup. Failed updates and interruptions roll back row changes.
A complete backup remains available if applying updates fails. The backup
still contains legacy data and needs the same protection as the source.
Already migrated rows are authenticated with the new key and left unchanged.

Verify representative identities and JSON values using the new code and key
before resuming the application. Keep an independent protected backup and
record the selected code revision, key reference and database path. The CLI
does not print user data or keys. This change has not migrated or verified any
deployed user database.

## Failure and rollback

Normal reads and writes never fall back to legacy decoding. A legacy row
returns HTTP 409 and cannot be silently overwritten. A wrong key, a tampered
token or a token copied between identities returns HTTP 500 and prevents
replacement. A missing or invalid key returns HTTP 503. Deleting a row still
requires configured storage and affects only the selected identity, including
legacy rows.

For rollback, stop writers, preserve the current database, and restore the
backup into a fresh protected path. Run the matching previous code with its
previous key and point `USERDATA_DB` to that restored path. Account for any
writes made after migration before choosing rollback. Do not copy a database
over an active SQLite connection or mix stale WAL files with a restored
database. The old code cannot read the new versioned tokens.

This migration is not a key rotation facility. Replacing `MASTER_KEY` alone
makes current rows unreadable. Durable account identity, provider integrations
and production deployment acceptance remain separate from this storage repair.

## Release qualification

The demo's HTTP identity is a session bearer token held in the server process's
`sessions` dictionary. Keeping the same database and `MASTER_KEY` preserves
encrypted rows, but does not preserve that dictionary. Restarting the process
invalidates its existing bearer tokens; another worker rejects them too. A new
`/v1/initialize` response creates a different identity and cannot retrieve the
old identity's row. Stopping the server for migration therefore also requires
a decision about existing users' access. A successful migration does not
establish end-user recovery.

For a session-local demo, verify the new session's store, retrieve and delete
flow and state its lifetime explicitly. If existing users must regain their
stored data after restart, qualify an identity and session recovery design
before shipping. That design is outside these storage and demo drafts.

Before replacing an existing service, record its exact revision and image,
actual database location and existing rows, previous and new key references,
filesystem permissions, storage durability and SQLite locking support. Confirm
the session lifetime and worker topology against the intended use. Rehearse
the migration on a protected copy, compare known values with a trusted source,
and restore its backup using the previous code and key. Then run the actual
end-user acceptance for that deployment. The container recipe does not
establish these facts. [Cloud Run's container contract](https://docs.cloud.google.com/run/docs/container-contract)
states that its default writable filesystem is in memory and its contents do
not persist when an instance stops.

On October 10, 2026, isolated process checks used the actual previous storage
code from main `13c63d0` to create six synthetic JSON rows in a WAL-backed
database. The migration CLI preserved the dry run, produced a complete `0600`
backup, and made the values readable by the new code in a fresh process. The
restored backup was readable by the previous code. Killing the migration
process after its first uncommitted update recovered every original row and
retained the complete backup. Actual local HTTP server processes confirmed
same-process storage access and 401 responses for an existing token in another
worker or after restart. Direct storage reads confirmed that its encrypted
row remained present.

These results qualify the synthetic migration and rollback procedure and
demonstrate the session limitation. They do not qualify a deployed database,
container, secret configuration or durable HTTP user flow. Those release gates
remain open, so the storage and demo PRs remain drafts.

## Evidence

The repository tests use synthetic values and temporary databases. They cover
the JSON API, identity isolation, wrong keys, tampering, legacy refusal,
deletion, dry runs, backups and rollback after a partial update or interruption.
They block outbound network access and do not establish live deployment or
provider acceptance.

See the [Fernet documentation](https://cryptography.io/en/stable/fernet/) for
the encryption API and its properties.

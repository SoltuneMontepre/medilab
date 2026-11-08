"""The fingerprint of what a module upgrade depends on: Odoo, the MediLab modules, their Python packages and the modules
to install. medilab records the fingerprint of its last upgrade as a system parameter, so a sync of an image the
database was already upgraded with skips the rehearsal and the upgrade.

Usage: fingerprint.py compute <modules> | read <database> | record <database> <fingerprint> | installed <database>
Any database error exits with an error, so a step never takes a failed read for an empty database."""

import hashlib
import os
import sys

import psycopg2

ROOTS = ("/usr/lib/python3/dist-packages/odoo", "/mnt/extra-addons", "/opt/python-packages")
PARAMETER = "medilab.upgrade_fingerprint"
CHUNK = 1024 * 1024


def compute(modules):
    digest = hashlib.sha256(modules.encode())
    for root in ROOTS:
        for directory, folders, files in os.walk(root):
            folders[:] = sorted(folder for folder in folders if folder != "__pycache__")
            for name in sorted(files):
                if name.endswith(".pyc"):
                    continue
                path = os.path.join(directory, name)
                digest.update(path.encode() + b"\0")
                with open(path, "rb") as file:
                    while chunk := file.read(CHUNK):
                        digest.update(chunk)
    return digest.hexdigest()


def connect(database):
    return psycopg2.connect(
        host=os.environ["HOST"], user=os.environ["USER"], password=os.environ["PASSWORD"], dbname=database
    )


def read(database):
    with connect(database) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('ir_config_parameter') IS NOT NULL")
        if not cursor.fetchone()[0]:
            return ""
        cursor.execute("SELECT value FROM ir_config_parameter WHERE key = %s", [PARAMETER])
        row = cursor.fetchone()
    return row[0] if row else ""


def installed(database):
    with connect(database) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('ir_module_module') IS NOT NULL")
        return cursor.fetchone()[0]


def record(database, fingerprint):
    with connect(database) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO ir_config_parameter (key, value, create_date, write_date)
            VALUES (%s, %s, now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC')
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, write_date = EXCLUDED.write_date
            """,
            [PARAMETER, fingerprint],
        )


def main():
    command, *args = sys.argv[1:]
    if command == "compute":
        sys.stdout.write(compute(*args) + "\n")
    elif command == "read":
        sys.stdout.write(read(*args) + "\n")
    elif command == "record":
        record(*args)
    elif command == "installed":
        sys.stdout.write(("yes" if installed(*args) else "no") + "\n")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()

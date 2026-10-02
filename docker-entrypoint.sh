#!/bin/sh
# The database password comes from the compose secret "pgpass" (a libpq password file).
# libpq ignores a password file that others can read, and a secret mounted from a
# Windows disk shows up as 0777: copy it to ~/.pgpass with 0600.
set -e
if [ -f /run/secrets/pgpass ]; then
    install -m 600 /run/secrets/pgpass "$HOME/.pgpass"
fi
exec "$@"

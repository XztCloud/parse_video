#! /usr/bin/env bash

set -e
set -x

# Let the DB start
init-db

# Run migrations
alembic upgrade head

# Create initial data in DB
create-admin

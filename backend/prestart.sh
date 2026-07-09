#! /usr/bin/env bash

set -e
set -x

# Let the DB start
python app/prestart/prestart.py

# Run migrations
alembic upgrade head

# Create initial data in DB
python app/prestart/create_admin.py

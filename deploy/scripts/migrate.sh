#!/bin/sh
set -eu
exec alembic upgrade head

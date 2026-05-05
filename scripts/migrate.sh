#!/bin/bash
# Run database migrations using Alembic

echo "Running database migrations..."
alembic upgrade head
echo "Migrations complete!"

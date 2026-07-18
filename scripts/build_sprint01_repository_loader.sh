#!/bin/bash
set -e

echo "Creating Repository Loader..."

mkdir -p backend/app/repository
mkdir -p backend/tests/repository

touch backend/app/repository/__init__.py
touch backend/app/repository/models.py
touch backend/app/repository/loader.py
touch backend/app/repository/repository.py

touch backend/tests/repository/test_loader.py

echo "Done!"
tree backend/app/repository

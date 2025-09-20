#!/bin/bash

# Exit on error
set -e

echo ">>> Setting up virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo ">>> Upgrading pip..."
pip install --upgrade pip

echo ">>> Installing requirements..."
if [ -f requirements.txt ]; then
    pip install -r requirements.txt
else
    echo "No requirements.txt found. Skipping..."
fi

echo ">>> Setup complete. To activate the environment, run:"
echo "source venv/bin/activate"
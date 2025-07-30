#!/bin/bash
set -e

# Ensure we have the latest pip, setuptools, and wheel
pip install --upgrade pip setuptools wheel

# Install main requirements
pip install -r requirements.txt

# Install surfpy package
cd surfpy
pip install .
cd ..

echo "Build completed successfully!"
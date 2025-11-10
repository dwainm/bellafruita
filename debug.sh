#!/bin/bash
# Debug mode launcher - enables verbose debug logging
cd "$(dirname "$0")"

# Activate virtual environment if it exists
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

# Run with debug mode enabled
DEBUG=1 python main.py "$@"

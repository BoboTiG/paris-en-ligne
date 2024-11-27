#!/bin/bash
set -eu
python -m ruff format get.py
python -m ruff check --fix --unsafe-fixes get.py
python -m mypy get.py

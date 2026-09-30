#!/bin/sh
set -e
python -m src.main T "$(date +%F)"
python -m src.main T1 "$(date -d tomorrow +%F)"

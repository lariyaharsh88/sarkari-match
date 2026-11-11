#!/usr/bin/env bash
# Copies the app into cf/src (Worker code) and cf/public (static assets). Run before dev/deploy.
set -euo pipefail
cd "$(dirname "$0")"
rm -rf src public && mkdir -p src/pipeline public
cp worker.py src/
cp -R ../engine ../web src/
rm -rf src/web/static
cp ../pipeline/__init__.py ../pipeline/store.py src/pipeline/
python3 -c "import json,sys; print('NOTIFICATIONS_JSON = ' + repr(open('../data/notifications.json').read()))" > src/pipeline/_bundled.py
cp -R ../web/static public/static
find src -name __pycache__ -prune -exec rm -rf {} +

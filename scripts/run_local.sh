#!/usr/bin/env bash
# 사용법: ./scripts/run_local.sh --url URL | --text-file FILE | --job-id ID --from-step N
set -euo pipefail
cd "$(dirname "$0")/../pipeline"
uv run python -m pipeline.run "$@"

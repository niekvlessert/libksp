#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
./scripts/bootstrap-macos.sh
printf '\nBuild complete. Press Return to close.\n'
read -r _

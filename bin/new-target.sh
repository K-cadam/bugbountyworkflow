#!/usr/bin/env bash
# usage: bin/new-target.sh <name> <root-domain>
set -euo pipefail
cd "$(dirname "$0")/.."
[ $# -eq 2 ] || { echo "usage: $0 <name> <root-domain>"; exit 1; }
[ -e "$1" ] && { echo "$1 already exists"; exit 1; }
cp -r _template "$1"
sed -i "s/\"TARGET\"/\"$1\"/; s/example.com/$2/" "$1/work/target.json"
sed -i "s/TARGET/$1/" "$1/CLAUDE.md"
chmod 700 "$1/work/sessions"
echo "Created $1/. Next: paste raw policy into $1/policy_raw.md, then have Claude fill $1/CLAUDE.md + scope_hosts.txt."

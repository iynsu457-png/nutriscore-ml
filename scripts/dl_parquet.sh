#!/bin/bash
# Robust, resumable download of the OFF food.parquet from Hugging Face.
# - byte-range resume (curl -C -) survives interruptions
# - re-fetches a fresh signed redirect each attempt (-L)
# - authenticated via stored HF token
# Run under caffeinate to prevent idle sleep:  caffeinate -i bash dl_parquet.sh
set -u
cd "$(dirname "$0")" || exit 1
mkdir -p data
# Pinned to an immutable commit SHA so multi-session resumes never mix daily versions.
REV="1855a5a9e906db6538c24c3b22c6631711430755"
URL="https://huggingface.co/datasets/openfoodfacts/product-database/resolve/$REV/food.parquet"
OUT="data/food.parquet"
TOKEN=$(cat "$HOME/.cache/huggingface/token" 2>/dev/null)
AUTH="Authorization: Bearer $TOKEN"

EXP=$(curl -sIL -H "$AUTH" "$URL" | grep -i '^content-length' | tail -1 | tr -dc '0-9')
[ -z "$EXP" ] && { echo "could not determine size"; exit 1; }
echo "expected size: $EXP bytes ($(echo "scale=1;$EXP/1073741824"|bc) GiB)"

for i in $(seq 1 300); do
  cur=$(stat -f%z "$OUT" 2>/dev/null || echo 0)
  if [ "${cur:-0}" -ge "$EXP" ]; then
    echo "COMPLETE: $cur bytes after $i attempts"
    exit 0
  fi
  echo "[attempt $i] resuming from ${cur:-0} bytes ($(echo "scale=1;${cur:-0}*100/$EXP"|bc)%)"
  curl -L -C - --retry 5 --retry-delay 3 --connect-timeout 30 \
       --no-progress-meter -H "$AUTH" -o "$OUT" "$URL"
  sleep 2
done
echo "gave up after 300 attempts"
exit 1

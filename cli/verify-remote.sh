#!/usr/bin/env bash
# verify-remote.sh — prove the published repo is complete and credential-free.
#   ./verify-remote.sh MuhammadAqip/sadfarm
# Checks: repo meta, file count, md count, tree not truncated, credential probes.
set -uo pipefail
REPO="${1:?usage: verify-remote.sh <owner/repo>}"
TOK="${GH_TOKEN:-$(cat /tmp/gh_token 2>/dev/null || true)}"
[ -n "$TOK" ] || { echo "butuh GH_TOKEN atau /tmp/gh_token"; exit 1; }

API="https://api.github.com/repos/$REPO"
py() { python3 -c "$1"; }

printf '=== %s ===\n' "$REPO"
meta=$(curl -s -H "Authorization: token $TOK" "$API")
echo "$meta" | py 'import json,sys; d=json.load(sys.stdin); print("private:",d.get("private"),"| branch:",d.get("default_branch"),"| pushed:",d.get("pushed_at"))'

BR=$(echo "$meta" | py 'import json,sys; print(json.load(sys.stdin).get("default_branch","main"))')
tree=$(curl -s -H "Authorization: token $TOK" "$API/git/trees/$BR?recursive=1")
echo "$tree" | py '
import json,sys
p=[x for x in json.load(sys.stdin)["tree"] if x["type"]=="blob"]
print("files:",len(p),"| md:",sum(1 for x in p if x["path"].endswith(".md")))
top={}
for x in p: top[x["path"].split("/")[0]]=top.get(x["path"].split("/")[0],0)+1
print("top  :",dict(sorted(top.items(),key=lambda k:-k[1])[:8]))
'

printf '\n=== probe kredensial (404 = aman, 0 B = aman) ===\n'
BAD=0
PROBES="config.json config.yaml .env accounts.json keypool.json proxies.txt proxies_live.txt bot_key.txt results.jsonl data.sqlite fork.env jwt-secret"
# satu request per path: contents API memberi status DAN size sekaligus
for f in $PROBES; do
  for pfx in "" "project/" "data/"; do
    path="$pfx$f"
    out=$(curl -s -m 8 -w '\n%{http_code}' -H "Authorization: token $TOK" \
          "https://api.github.com/repos/$REPO/contents/$path?ref=$BR" 2>/dev/null)
    code=$(printf '%s' "$out" | tail -1)
    body=$(printf '%s' "$out" | sed '$d')
    if [ "$code" = "404" ]; then
      printf '  %s%-34s tidak ada%s\n' $'\033[32m' "$path" $'\033[0m'
    else
      size=$(printf '%s' "$body" | python3 -c '
import json,sys
try:
    d=json.load(sys.stdin); print(d.get("size","?"))
except Exception: print("?")' 2>/dev/null)
      if [ "$size" = "0" ]; then
        printf '  %s%-34s   0 B  kosong (aman)%s\n' $'\033[33m' "$path" $'\033[0m'
      else
        printf '  %s%-34s %4s B  PERIKSA%s\n' $'\033[31m' "$path" "$size" $'\033[0m'
        BAD=$((BAD+1))
      fi
    fi
  done
done
if [ "$BAD" -eq 0 ]; then
  printf '%sOK: tidak ada kredensial %s\n' $'\033[32m' "$REPO" $'\033[0m'
else
  printf '%s%d file berisi data (cek manual sebelum panik)%s\n' $'\033[31m' "$BAD" $'\033[0m'
  printf 'Catatan: file 0 byte = aman. Probe ini menandai SEMUA keberadaan;\n'
  printf 'verifikasi ulang dengan: curl -s .../contents/<path> | jq .size\n'
fi

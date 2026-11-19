#!/usr/bin/env bash
# sanitize.sh — scrub credentials from a package before publishing.
#   ./sanitize.sh /root/SADFARM_PACKAGE
# 1. empties known credential filenames
# 2. rewrites ://REDACTED@host  ->  ://REDACTED@
# 3. rewrites long SPC_*= / bearer tokens / telegram bot tokens
# 4. reports every change; prints residual hits for manual review
set -uo pipefail
PKG="${1:?usage: sanitize.sh <package-dir>}"
[ -d "$PKG" ] || { echo "tidak ada: $PKG"; exit 1; }

G=$'\033[32m'; Y=$'\033[33m'; E=$'\033[31m'; D=$'\033[2m'; R=$'\033[0m'
changed=0

# ---- 1. wipe credential files ---------------------------------------------
WIPE_NAMES=(
  'accounts.json' 'accounts.backup.*.json' 'accounts_for_user.json'
  'accounts_success.txt' 'accounts.csv' 'account_result.json'
  'keypool.json' 'bot_key.txt' 'config.json' 'dryrun_dump.json'
  'proxies.txt' 'proxies_live.txt' 'proxies_live_test.txt'
  '.bot.env' '.env' '_last_email.txt' '_one_proxy.txt'
  'farm_status.json' 'key_store.json' 'phone_reputation.json'
)
for name in "${WIPE_NAMES[@]}"; do
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    case "$f" in
      *.json) printf '[]\n' > "$f" ;;
      *.env)  printf '# redacted\n' > "$f" ;;
      *)      : > "$f" ;;
    esac
    printf '%s  wipe %s%s\n' "$G" "$f" "$R"
    changed=$((changed+1))
  done < <(find "$PKG" -type f -name "$name" -not -path '*/.git/*' 2>/dev/null)
done

# ---- 2-3. redact inside text files ----------------------------------------
mapfile -d '' FILES < <(find "$PKG" -type f \
  \( -name '*.py' -o -name '*.sh' -o -name '*.md' -o -name '*.json' \
     -o -name '*.txt' -o -name '*.html' -o -name '*.yml' -o -name '*.yaml' \) \
  -not -path '*/.git/*' -not -path '*/__pycache__/*' -print0 2>/dev/null)

python3 - "$PKG" "${FILES[@]}" >/tmp/.san_out 2>/tmp/.san_cnt <<'PY'
import re, sys
paths = sys.argv[2:]
patterns = [
    (re.compile(r'(?i)(//)[^:/@\s]+:[^@\s/]+@'), r'\g<1>REDACTED@'),
    (re.compile(r'\bSPC_[A-Z_]+=[A-Za-z0-9%+/_\-]{12,}'), 'SPC_x=[REDACTED]'),
    (re.compile(r'\b\d{9,10}:[A-Za-z0-9_-]{35}\b'), '[TG_TOKEN]'),
    (re.compile(r'(?i)(bearer\s+)[A-Za-z0-9._\-]{25,}'), r'\1[REDACTED]'),
    (re.compile(r'\b(gh[pousr]_|github_pat_)[A-Za-z0-9_]{20,}'), '[GH_TOKEN]'),
    (re.compile(r'\bsk-[A-Za-z0-9._\-]{16,}'), '[API_KEY]'),
]
changed = []
for path in paths:
    try:
        raw = open(path, 'rb').read()
        if b'\x00' in raw[:4096]:       # binary, skip
            continue
        txt = orig = raw.decode('utf-8', 'ignore')
        for pat, rep in patterns:
            txt = pat.sub(rep, txt)
        if txt != orig:
            open(path, 'w', encoding='utf-8').write(txt)
            changed.append(path)
    except Exception:
        pass
for p in changed:
    print(' ', p)
print(len(changed), file=sys.stderr)
PY
cat /tmp/.san_out
count=$(tail -1 /tmp/.san_cnt 2>/dev/null || echo 0)
changed=$(( changed + ${count:-0} ))
echo
printf '%s=== residu (harus kosong) ===%s\n' "$Y" "$R"
resid=$(grep -rIlE 'SPC_[A-Z_]+=[A-Za-z0-9%+/_-]{12,}|[0-9]{9,10}:[A-Za-z0-9_-]{35}|://[^:/@ ]+:[^@ ]+@' \
  "$PKG" --include='*.py' --include='*.sh' --include='*.md' --include='*.json' --include='*.txt' \
  2>/dev/null | grep -v '/.git/' | grep -vF 'sanitize.sh' | grep -vF 'credential-patterns.md' | head -10)
if [ -n "$resid" ]; then
  printf '%s%s%s\n' "$E" "$resid" "$R"
  echo "  ^ periksa manual"
else
  echo "  bersih"
fi

echo
printf '%s%d file di-wipe/redact%s\n' "$G" "$changed" "$R"

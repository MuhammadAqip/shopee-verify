#!/usr/bin/env bash
# shopee-verify.sh — entrypoint interaktif paket ini.
#   ./cli/shopee-verify.sh
# Keys: 1-9 pilih · PgUp/PgDn ganti halaman · h bantuan · q keluar
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
PROJ="$ROOT/project"

# shellcheck disable=SC1091
. "$HERE/menu.sh"

PY=""
for c in "$ROOT/venv/bin/python" "$PROJ/venv/bin/python" python3; do
  if command -v "$c" >/dev/null 2>&1 || [ -x "$c" ]; then PY="$c"; break; fi
done

title() { printf '\n%s%s%s\n' "$C_B" "$*" "$C_R"; }
hr()    { printf '%s' "$C_D"; printf '%.0s─' $(seq 1 58); printf '%s\n' "$C_R"; }
_p()    { printf '\n%s[enter]%s ' "$C_D" "$C_R"; read -r _ || true; }

# ---- SETUP ----------------------------------------------------------------
h_deps() {
  title "Install dependency"
  ( cd "$PROJ" && "$PY" -m pip install -r requirements.txt )
  _p
}

h_env() {
  title ".env"
  hr
  if [ -f "$ROOT/.env" ]; then
    echo "sudah ada: $ROOT/.env"
    echo
    sed -E 's/(TOKEN|KEY|SECRET|PASS)=.*/\1=***/' "$ROOT/.env"
  else
    cp "$PROJ/bot.env.example" "$ROOT/.env"
    echo "dibuat: $ROOT/.env"
    echo "isi SHOPEE_BOT_TOKEN dan ADMIN_ID"
  fi
  _p
}

h_check() {
  title "Kelengkapan"
  hr
  local n=0
  printf '%-10s %s\n' python "${PY:-TIDAK ADA}"; [ -n "$PY" ] && n=$((n+1))
  for f in shopee_bot.py changenumfast.py ivs_engine.py regression.py; do
    if [ -f "$PROJ/$f" ]; then printf '%-10s %s\n' "${f%%.py}" ada; n=$((n+1))
    else printf '%-10s %s\n' "${f%%.py}" "HILANG"; fi
  done
  [ -f "$ROOT/.env" ] && n=$((n+1))
  echo
  echo "$n/6 siap"
  _p
}

# ---- JALANKAN -------------------------------------------------------------
h_regression() {
  title "Regression (59 cek)"
  hr
  ( cd "$PROJ" && "$PY" regression.py )
  _p
}

h_syntax() {
  title "Cek syntax"
  hr
  for f in shopee_bot.py changenumfast.py ivs_engine.py; do
    if ( cd "$PROJ" && "$PY" -c "import ast;ast.parse(open('$f').read())" 2>/dev/null ); then
      printf '  %sOK%s    %s\n' "$C_G" "$C_R" "$f"
    else
      printf '  %sGAGAL%s %s\n' "$C_E" "$C_R" "$f"
    fi
  done
  _p
}

h_engine() {
  title "Tes engine"
  hr
  [ -f "$PROJ/ck_test.txt" ] || { echo "tidak ada project/ck_test.txt"; _p; return; }
  ( cd "$PROJ" && "$PY" - <<'EOF'
import sys, json
sys.path.insert(0, '.')
import changenumfast as c
ck = open('ck_test.txt').read().strip()
print('proxy :', c.proxy_url())
print('akun  :', json.dumps(c.check_account(ck), ensure_ascii=False))
EOF
  )
  _p
}

h_health2() {
  title "Health check (tanpa endpoint OTP)"
  hr
  ( cd "$PROJ" && "$PY" - <<'EOF'
import sys, json
sys.path.insert(0, '.')
import changenumfast as c
try:
    ck = open('ck_test.txt').read().strip()
except FileNotFoundError:
    print('project/ck_test.txt belum ada'); raise SystemExit
a = c.Api(ck)
print('akun :', json.dumps(a.get('/api/v4/account/basic/get_account_info'),
                            ensure_ascii=False)[:220])
print('init :', json.dumps(
    a.post('/api/v4/account/management/change_phone_init_v2',
           {'phone': '628000000000', 'seq_no': None}), ensure_ascii=False)[:220])
EOF
  )
  _p
}

h_bot() {
  title "Jalankan bot (Ctrl-C stop)"
  hr
  ( cd "$PROJ" && "$PY" shopee_bot.py )
  _p
}

h_proxy() {
  title "Cek jalur keluar"
  hr
  ( cd "$PROJ" && "$PY" - <<'EOF'
import sys
sys.path.insert(0, '.')
import changenumfast as c
print('proxy_url :', c.proxy_url())
try:
    print('ip keluar :', c.Api('SPC_U=x').get('https://api.ipify.org'))
except Exception as e:
    print('gagal     :', type(e).__name__, e)
EOF
  )
  _p
}

# ---- DOKUMEN --------------------------------------------------------------
h_readme()   { title "README";   hr; sed -n '1,100p' "$ROOT/README.md" 2>/dev/null; _p; }
h_agents()   { title "AGENTS";   hr; sed -n '1,100p' "$ROOT/AGENTS.md" 2>/dev/null; _p; }
h_index()    { title "INDEX";    hr; sed -n '1,80p'  "$ROOT/INDEX.md"  2>/dev/null; _p; }
h_deepdive() { title "DEEP-DIVE";hr; sed -n '1,100p' "$ROOT/docs/DEEP-DIVE.md" 2>/dev/null; _p; }
h_ref()      { title "REFERENCE";hr; sed -n '1,100p' "$ROOT/docs/REFERENCE.md" 2>/dev/null; _p; }
h_sw()       { title "Kekuatan/Kelemahan"; hr; sed -n '1,100p' "$ROOT/docs/STRENGTHS-WEAKNESSES.md" 2>/dev/null; _p; }
h_roadmap()  { title "Roadmap";  hr; sed -n '1,100p' "$ROOT/docs/ROADMAP.md" 2>/dev/null; _p; }
h_lessons()  { title "Lessons";  hr; sed -n '1,100p' "$ROOT/docs/LESSONS.md" 2>/dev/null; _p; }
h_advice()   { title "ADVICE";   hr; sed -n '1,100p' "$ROOT/docs/ADVICE.md" 2>/dev/null; _p; }

h_tree() {
  title "Struktur"
  hr
  ( cd "$ROOT" && find . -maxdepth 2 \
      -not -path './project/reference/*' -not -path './.git*' \
      -not -path '*/__pycache__*' | sed 's|^\./||' | sort | head -60 )
  echo
  printf '%-8s %s\n' file "$(find "$ROOT" -type f -not -path '*/.git/*' | wc -l)"
  printf '%-8s %s\n' md   "$(find "$ROOT" -name '*.md' -not -path '*/.git/*' | wc -l)"
  printf '%-8s %s\n' size "$(du -sh "$ROOT" | cut -f1)"
  _p
}

h_docslist() {
  title "Checklist dokumen"
  hr
  for f in README.md AGENTS.md INDEX.md docs/DEEP-DIVE.md docs/REFERENCE.md \
           docs/STRENGTHS-WEAKNESSES.md docs/ROADMAP.md docs/LESSONS.md docs/ADVICE.md; do
    if [ -s "$ROOT/$f" ]; then
      printf '  %s[OK]%s %-30s %s B\n' "$C_G" "$C_R" "$f" "$(wc -c < "$ROOT/$f")"
    else
      printf '  %s[--]%s %-30s KURANG\n' "$C_E" "$C_R" "$f"
    fi
  done
  _p
}

# ---- SISTEM ---------------------------------------------------------------
h_sys() {
  title "Environment"
  hr
  printf '%-10s %s\n' python "$($PY --version 2>&1)"
  printf '%-10s %s\n' git "$(git --version 2>&1)"
  printf '%-10s %s\n' terminal "${TERM:-unset}"
  printf '%-10s %s\n' tty "$([ -t 0 ] && echo ya || echo 'pipe')"
  echo
  free -h 2>/dev/null | head -2
  df -h . 2>/dev/null | tail -1
  _p
}

h_zip() {
  title "Buat zip"
  local out="/root/$(basename "$ROOT")_$(date +%Y%m%d).zip"
  rm -f "$out"
  ( cd "$(dirname "$ROOT")" && zip -qr -9 "$out" "$(basename "$ROOT")" \
      -x '*/__pycache__/*' -x '*.pyc' -x '*/.git/*' )
  echo "zip  : $out"
  echo "size : $(du -h "$out" | cut -f1)"
  echo "md5  : $(md5sum "$out" | cut -d' ' -f1)"
  _p
}

# ---- MENU -----------------------------------------------------------------
menu_init "SHOPEE VERIFY" "bot ganti nomor Shopee · python: ${PY:-TIDAK ADA}"

menu_page "Setup"
menu_item 1 "Install dependency"     h_deps
menu_item 2 "Buat / lihat .env"      h_env
menu_item 3 "Cek kelengkapan"        h_check

menu_page "Jalankan"
menu_item 1 "Regression (59 cek)"    h_regression
menu_item 2 "Cek syntax"             h_syntax
menu_item 3 "Tes engine (cookie)"    h_engine
menu_item 4 "Health check"           h_health2
menu_item 5 "Jalankan bot"           h_bot

menu_page "Proxy"
menu_item 1 "Cek jalur keluar"       h_proxy

menu_page "Dokumen"
menu_item 1 "README"                 h_readme
menu_item 2 "AGENTS"                 h_agents
menu_item 3 "INDEX"                  h_index
menu_item 4 "DEEP-DIVE"              h_deepdive
menu_item 5 "REFERENCE"              h_ref

menu_page "Analisis"
menu_item 1 "Kekuatan/Kelemahan"     h_sw
menu_item 2 "Roadmap"                h_roadmap
menu_item 3 "Lessons"                h_lessons
menu_item 4 "ADVICE"                 h_advice
menu_item 5 "Checklist dokumen"      h_docslist

menu_page "Sistem"
menu_item 1 "Struktur folder"        h_tree
menu_item 2 "Environment"            h_sys
menu_item 3 "Buat zip"               h_zip

menu_run

#!/usr/bin/env bash
# menu.sh — interactive numbered-menu library with PgUp/PgDn pagination.
# Source this file, then call menu_init / menu_page / menu_item / menu_run.
#
#   menu_init "TITLE" "subtitle line"
#   menu_page "Page name"
#   menu_item "1" "Label" handler_fn
#   menu_page "Other page"
#   menu_item "1" "Other action" other_fn
#   menu_run
#
# Handlers receive no args and must return; menu_run re-renders afterwards.
# Keys: 1-9 select · PgUp/PgDn page · h help · q quit
#
# Escape sequences (verified against xterm-256color, linux, screen, tmux, putty):
#   PgUp kpp=\E[5~   PgDn knp=\E[6~

_MENU_TITLE=""
_MENU_SUB=""
_MENU_PAGES=()
_MENU_CUR=0
_MENU_KEYS=()
_MENU_LABELS=()
_MENU_HANDLERS=()
_MENU_PAGE_OF=()
_MENU_BUILT=0
_MENU_SAVED_STTY=""
_MENU_IN_RAW=0
_MENU_STATUS=""

# ---------- colour ----------
if [ -t 1 ] && [ "${NO_COLOR:-}" = "" ]; then
  C_B=$'\033[1m'; C_D=$'\033[2m'; C_R=$'\033[0m'
  C_G=$'\033[32m'; C_Y=$'\033[33m'; C_C=$'\033[36m'; C_E=$'\033[31m'
else
  C_B=''; C_D=''; C_R=''; C_G=''; C_Y=''; C_C=''; C_E=''
fi

menu_init() {
  _MENU_TITLE="$1"; _MENU_SUB="${2:-}"
  _MENU_PAGES=(); _MENU_CUR=0
  _MENU_KEYS=(); _MENU_LABELS=(); _MENU_HANDLERS=(); _MENU_PAGE_OF=()
  _MENU_BUILT=0
}

menu_page() {
  _MENU_PAGES+=("$1")
  _MENU_BUILT=$(( ${#_MENU_PAGES[@]} - 1 ))
}

menu_item() {
  local key="$1" label="$2" fn="$3"
  [ "$_MENU_BUILT" -ge 0 ] || { echo "menu_item: call menu_page first" >&2; return 1; }
  _MENU_KEYS+=("$key"); _MENU_LABELS+=("$label"); _MENU_HANDLERS+=("$fn")
  _MENU_PAGE_OF+=("$_MENU_BUILT")
}

menu_clear_status() { _MENU_STATUS=""; }
menu_status() { _MENU_STATUS="$*"; }

# ---------- terminal ----------
_menu_raw_on() {
  [ "$_MENU_IN_RAW" -eq 1 ] && return
  _MENU_SAVED_STTY=$(stty -g 2>/dev/null) || _MENU_SAVED_STTY=""
  [ -n "$_MENU_SAVED_STTY" ] && stty raw -echo 2>/dev/null
  _MENU_IN_RAW=1
}

_menu_raw_off() {
  [ "$_MENU_IN_RAW" -eq 1 ] || return
  [ -n "$_MENU_SAVED_STTY" ] && stty "$_MENU_SAVED_STTY" 2>/dev/null
  _MENU_IN_RAW=0
}

_menu_cleanup() { _menu_raw_off; printf '%s' "$C_R"; }

# read one byte into $_MENU_CH (fd 0). Returns 1 on EOF.
_menu_getbyte() {
  _MENU_CH=$(dd bs=1 count=1 2>/dev/null)
  [ -n "$_MENU_CH" ] || return 1
  # dd gives us raw byte(s); for ESC sequence we need individual chars
  return 0
}

# Read a keypress. Sets _MENU_KEY to: up|down|left|right|pgup|pgdn|home|end|
# quit|help|enter|N|''   Returns 1 on real EOF.
#
# Delegates to scripts/readkey.py — bash cannot read the ESC byte reliably
# (`read -rsn1` yields an empty string for 0x1b, and quoted patterns like
# '\[A' match literally, never the real bytes). Python's os.read gives exact
# bytes, so the CSI parsing lives there and this stays a thin wrapper.
# Locate readkey.py: prefer a copy next to menu.sh (packaged layout), then the
# skill's scripts/ dir (skill layout). Never hardcode one and break the other.
_menu_find_readkey() {
  local here; here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local c
  for c in "$here/readkey.py" "$here/../scripts/readkey.py" "$here/scripts/readkey.py"; do
    [ -f "$c" ] && { printf '%s' "$c"; return 0; }
  done
  printf '%s' "$here/readkey.py"
}
_MENU_READKEY_PY="$(_menu_find_readkey)"

_menu_readkey() {
  _MENU_KEY=""
  local k
  k=$(python3 "$_MENU_READKEY_PY" 2>/dev/null)
  local rc=$?
  [ "$rc" -eq 3 ] && return 1
  case "$k" in
    other|'') _MENU_KEY="" ;;
    esc)      _MENU_KEY="esc" ;;
    *)        _MENU_KEY="$k" ;;
  esac
  return 0
}

# ---------- rendering ----------
_menu_render() {
  local total=${#_MENU_PAGES[@]}
  local page="${_MENU_PAGES[$_MENU_CUR]}"
  printf '\033[H\033[2J'

  printf '%s%s%s\n' "$C_B" "$_MENU_TITLE" "$C_R"
  [ -n "$_MENU_SUB" ] && printf '%s%s%s\n' "$C_D" "$_MENU_SUB" "$C_R"
  printf '%s' "$C_D"
  printf '%.0s─' $(seq 1 58); printf '%s\n' "$C_R"

  # page indicator
  if [ "$total" -gt 1 ]; then
    printf '%s[ %d/%d ] %s%s' "$C_C" $(( _MENU_CUR + 1 )) "$total" "$page" "$C_R"
    printf '\n\n'
  else
    printf '%s%s%s\n\n' "$C_C" "$page" "$C_R"
  fi

  local i n=0
  for i in "${!_MENU_KEYS[@]}"; do
    [ "${_MENU_PAGE_OF[$i]}" -eq "$_MENU_CUR" ] || continue
    printf '  %s%s%s  %s\n' "$C_Y" "${_MENU_KEYS[$i]}" "$C_R" "${_MENU_LABELS[$i]}"
    n=$(( n + 1 ))
  done
  [ "$n" -eq 0 ] && printf '  %s(empty page)%s\n' "$C_D" "$C_R"

  printf '\n%s' "$C_D"
  printf '%.0s─' $(seq 1 58); printf '%s\n' "$C_R"

  if [ -n "$_MENU_STATUS" ]; then
    printf '%s%s%s\n' "$C_G" "$_MENU_STATUS" "$C_R"
    _MENU_STATUS=""
  fi

  local hint="PgUp/PgDn: halaman   h: bantuan   q: keluar"
  printf '%s%s%s\n' "$C_D" "$hint" "$C_R"
  printf '\n%sPilih [%s1-%s9%s]:%s ' "$C_B" "$C_Y" "$C_Y" "$C_B" "$C_R"
}

_menu_help() {
  printf '\033[H\033[2J'
  printf '%sBANTUAN%s\n\n' "$C_B" "$C_R"
  cat <<'HELP'
  Angka 1-9     jalankan item bernomor di halaman ini
  PgUp / PgDn   pindah halaman menu
  h             tampilkan bantuan ini
  q             keluar
  Ctrl-C        keluar dan memulihkan terminal

  Setiap perintah setelah selesai akan kembali ke menu ini.
  Output panjang tetap bisa digulir di scrollback terminal.
HELP
  printf '\n%sTekan tombol apa saja...%s' "$C_D" "$C_R"
  IFS= read -rsn1 _ || true
}

# non-TTY fallback: plain numbered picker, no cursor games
_menu_pick_noninteractive() {
  local i n=0
  echo "$_MENU_TITLE"
  echo
  for i in "${!_MENU_KEYS[@]}"; do
    printf '  %s) %s\n' "${_MENU_KEYS[$i]}" "${_MENU_LABELS[$i]}"
    n=$(( n + 1 ))
  done
  echo
  printf 'Pilih nomor: '
}

menu_run() {
  if [ ! -t 0 ]; then
    # piped/CI: read one selection then run it
    while :; do
      _menu_pick_noninteractive
      local sel; IFS= read -r sel || return 0
      [ -z "$sel" ] && return 0
      local i
      for i in "${!_MENU_KEYS[@]}"; do
        if [ "${_MENU_KEYS[$i]}" = "$sel" ]; then
          "${_MENU_HANDLERS[$i]}"
          return 0
        fi
      done
      echo "Nomor '$sel' tidak ada."
    done
  fi

  trap _menu_cleanup EXIT
  trap '_menu_raw_off; printf "\n"; exit 130' INT TERM

  local total=${#_MENU_PAGES[@]}
  while :; do
    _menu_raw_off
    _menu_render
    _menu_raw_on
    _menu_readkey || break

    case "$_MENU_KEY" in
      quit) _menu_raw_off; printf '\n'; return 0 ;;
      pgdn)
        if [ "$total" -gt 1 ]; then _MENU_CUR=$(( (_MENU_CUR + 1) % total )); fi
        continue ;;
      pgup)
        if [ "$total" -gt 1 ]; then _MENU_CUR=$(( (_MENU_CUR - 1 + total) % total )); fi
        continue ;;
      help) _menu_raw_off; _menu_help; continue ;;
      ''|up|down|home|end) continue ;;
    esac

    # number pressed -> dispatch on current page
    local i found=0
    for i in "${!_MENU_KEYS[@]}"; do
      [ "${_MENU_PAGE_OF[$i]}" -eq "$_MENU_CUR" ] || continue
      [ "${_MENU_KEYS[$i]}" = "$_MENU_KEY" ] || continue
      found=1
      _menu_raw_off
      printf '\n'
      "${_MENU_HANDLERS[$i]}"
      printf '\n%s— tekan tombol apa saja untuk kembali —%s' "$C_D" "$C_R"
      IFS= read -rsn1 _ || true
      break
    done
    [ "$found" -eq 1 ] || _MENU_STATUS="Nomor '$_MENU_KEY' tidak tersedia di halaman ini."
  done
  _menu_raw_off
  printf '\n'
}

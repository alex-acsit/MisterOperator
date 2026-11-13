#!/bin/bash
# Runs the off-hardware tests. Needs only Python 3 (Pillow not required).
# Each test gets a fresh copy of the kiosk and a small set of fake .mra files.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
fail=0

run() {   # run <test file> <fixture sets...>
    local t; t="$(mktemp -d)"
    cp -r "$ROOT/arcade_kiosk" "$t/kiosk"
    mkdir -p "$t/_Arcade"
    for set in "${@:2}"; do cp -r "$HERE/fixtures/$set/." "$t/_Arcade/"; done
    echo "== $1"
    out="$(cd "$t" && python3 "$HERE/$1" "$t/kiosk" "$t" 2>&1)" || true
    echo "$out" | grep -E "^(FAIL|Traceback)|failure" || true
    echo "$out" | grep -qE "^FAIL|Traceback" && fail=1
    case "$1" in test_fb.py) ;; *) echo "$out" | grep -q "^0 failure" || fail=1 ;; esac
    rm -rf "$t"
}

run test_kiosk.py base
run test_fb.py base
run test_orient.py base orient_extra
run test_genre.py base genre_extra
run test_mgl.py base mgl_extra
run test_idle.py base
run test_nvram.py base nvram_extra
run test_screen.py base
run test_layout.py base layout_extra
run test_buttons.py base
run test_coins.py base
run test_operator.py base nvram_extra
run test_fork.py base nvram_extra

[ $fail = 0 ] && echo "ALL TESTS PASSED" || { echo "SOME TESTS FAILED"; exit 1; }

#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
mkdir -p work/input-profile
python3 Vendor/nxnative/dm/games/game.py header 01007EF00011E000 work/input-profile/game_profile.h
xcrun clang -O1 -Wall -Wextra -Werror -fobjc-arc -I work/input-profile -I Vendor/nxnative/dm/games/01007EF00011E000 tests/input_native.m -o work/input_native -framework Cocoa -framework QuartzCore -framework Metal -framework CoreGraphics -framework GameController
work/input_native
xcrun clang -std=c11 -O1 -Wall -Wextra -Werror Vendor/nxnative/dm/host/tests/t_mouse_mac.c -lm -o work/t_mouse_mac
work/t_mouse_mac

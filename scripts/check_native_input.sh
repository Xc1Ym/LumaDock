#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
: "${NXNATIVE_DIR:?Set NXNATIVE_DIR to an external nxnative checkout with DM_INPUT_CONFIG support}"
mkdir -p work/input-profile
python3 "$NXNATIVE_DIR"/dm/games/game.py header 01007EF00011E000 work/input-profile/game_profile.h
xcrun clang -I "$NXNATIVE_DIR/dm/host" -O1 -Wall -Wextra -Werror -fobjc-arc -I work/input-profile -I "$NXNATIVE_DIR"/dm/games/01007EF00011E000 tests/input_native.m -o work/input_native -framework Cocoa -framework QuartzCore -framework Metal -framework CoreGraphics -framework GameController
work/input_native
xcrun clang -std=c11 -O1 -Wall -Wextra -Werror "$NXNATIVE_DIR"/dm/host/tests/t_mouse_mac.c -lm -o work/t_mouse_mac
work/t_mouse_mac

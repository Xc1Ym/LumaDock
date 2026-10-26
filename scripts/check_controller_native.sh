#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
engine="$PWD/Engine/nxnative"
mkdir -p work/controller-profile
python3 -B "$engine/dm/games/game.py" header 010015100B514000 work/controller-profile/game_profile.h
xcrun clang -I "$engine/dm/host" -I work/controller-profile -O1 -Wall -Wextra -Werror -Wno-unused-function -Wno-unused-but-set-variable -fobjc-arc tests/controller_native.m -o work/controller_native -framework Cocoa -framework QuartzCore -framework Metal -framework GameController
work/controller_native

// Registry of touch-only / controller-only behaviors: the mode switch transaction (dm_padmode.c) calls the "leave" of each item on the old side before changing the layout, and the "enter" of each item on the new side after the rebuild completes.
// Leave = the item stands down by itself: void in-flight key-press / message requests made on the player's behalf, write moved original widgets back, clear cached widget addresses (after a rebuild the old addresses are all dangling).
// Side: 0 = acts only in touch mode, 1 = acts only in controller mode, 2 = present on both sides but holding things that become invalid with a rebuild (leaves once and enters once on every switch).
// Register a new mode-specific behavior with one row here; do not check the mode separately elsewhere, and do not have the switch code call some module by name.
//   X(name, side, enter, leave)   enter / leave: void (*)(void); write dm_mode_none (an empty function) when there is none
#define DM_MODE_ITEMS(X) \
    X("runeword list", 2, dm_mode_none, dm_runeword_ui_rebuild) \
    X("front end path straightening and key presses for the player", 0, dm_mode_none, dm_ui_auto_mode_leave) \
    X("UI touch cache and widget move table", 2, dm_mode_none, dm_ui_cache_mode_leave) \
    X("main menu build number and new version notice", 2, dm_update_mode_enter, dm_mode_none) \
    X("death popup reopened for the current mode", 2, dm_dead_modal_mode_enter, dm_mode_none) \
    X("cube side by side", 0, dm_mode_none, dm_cube_side_mode_leave)

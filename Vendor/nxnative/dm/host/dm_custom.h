// "Custom" settings: on/off switches for the features we added ourselves, all read and written here. Each module only calls dm_custom_get and does not read files / environment variables as settings on its own.
#pragma once

// Effective value 0 / 1: changes only after the player taps "Apply" on the options page, unchanged by "Discard", "Default" = each key's default (power-saving mode off, the rest on). Returns 1 for an unrecognized key.
// Callable from any thread: the first call reads the file once, and after that it is just an atomic read + a few string comparisons, lock-free. On iOS it can be read already during startup (before the save is mounted).
// Keys: auto_mana auto-drink potions (both red and blue; the key name is kept) / drop_light light beam on high-value drops / map_mark minimap markers for entrances and exits, waypoints and quest goals / item_notes item notes and old translated names / icloud iCloud save sync (cloud_ios.m, read at startup) / pot_pick potion auto-pickup (dm_potpick.c) / drop_haptic haptics on high-value drops (dm_drophaptic.c) / gem_pick auto-pickup of runes and gems into the advanced stash (pouch) / store_btn the inventory "Deposit" button (dm_pouch.c) / eco_fps power-saving mode 30 fps (nvn_mtl.m, off by default)
int dm_custom_get(const char *key);
int dm_custom_lang_explicit(void);   // Value of the language switch (key lang_en) as written in the settings file: -1 never written (original settings left alone) / 0 Simplified Chinese / 1 English; read by hle_fs.c at save mount
int dm_fps_setting(void);   // Power-saving mode (key eco_fps, off by default): on = 30 fps, off = 60; read by mtl_fps_target in nvn_mtl.m

void dm_custom_init(const char *dir);   // Directory holding the settings file (the iOS shell passes Documents at startup); if not called, the parent of the save commit directory is used (Mac host)

// The following are only for the UI wiring of the custom page
void dm_custom_on_uimsg(const char *cat, const char *act, const char *arg);   // Options page apply / default / discard (forwarded from the UI message callback in dm_cursor.c)
void dm_custom_ui_pump(unsigned long long root);                               // Game main thread, every frame: while the options page is open, read the checkbox of each row (widget name TouchCustom_<key>)

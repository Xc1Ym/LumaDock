#include <stdint.h>
// "Elysium": a per-character switch checked at character creation and unchangeable afterwards. While that character is in a run: unique drop rate ×5, sets ×3 (quality ratio table). For the implementation and its basis see dm_elysium.c
#pragma once
void dm_elysium_arm(int on);     // Called by the checkbox on the character creation page: 1 = the character created this time is an Elysium character, 0 = it is not. Applies only to the immediately following character creation and is cleared once used
int dm_elysium_active(void);     // Whether the current run is the run of an Elysium character (tables changed)
void dm_elysium_pump(void);      // Called every frame on the game main thread (dm_actions_pump)
void dm_elysium_stash_step(uint64_t game, uint64_t player, uint8_t *main_base);   // Called every tick on the game server side (where diag.c reads the player state): tops up the shared stash after a new Elysium character is created

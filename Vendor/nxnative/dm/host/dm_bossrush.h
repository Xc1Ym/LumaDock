#pragma once
// Boss rush: the door in Harrogath → 5 stages at the Arreat Summit → a door into the Worldstone Chamber, 5 stages with the terror zone forced → 2 more stages in Hell. For implementation and rationale see dm_bossrush.c
#include <stdint.h>
void dm_bossrush_tick(uint64_t game, uint64_t player, uint8_t *main_base);   // called every server tick (where diag.c reads the player state)
void dm_bossrush_c2s(uint64_t game, uint64_t player, const uint8_t *pkt, uint32_t len);   // called per packet at the client command packet dispatch entry (observation gate OBS_C2S)
void dm_game_notice(uint8_t *main_base, const char *text);   // original-game system notification (one chat bar line + the system notification box), called from the server thread
int dm_bossrush_owns(uint32_t id);                            // this monster unit was spawned by the current boss rush stage
void dm_kills_tick(uint64_t G, uint64_t player, uint8_t *main_base);   // kill board (dm_kills.c), called in the server tick
void dm_door_label(uint8_t *main_base, uint64_t game, int cls, const char *key, const char *zh, const char *en, int in_town);   // name label of the doors we create: in town the string key of this object class is replaced with key (attached to the original game's string table), and written back on leaving town

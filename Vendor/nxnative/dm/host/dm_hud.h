#pragma once
// HUD numbers for bottom UI v4 (read by the host once per server tick; the front end UIKit draws 'Lv · %', badges and the difficulty number) and difficulty level requests.
// Difficulty goes through the same chain as the original game's /players handler (main+0x415db0): main+0x3102c0 gets the players setting object -> main+0x1199c50(object, N);
// it is applied at the next server tick entry (game thread); the original game's rules apply to monsters spawned from then on (measured: level 8 stat 100 = 8, max life floor(×4.5)).
typedef struct {
    int valid;          // In a run and the controlled player has been read
    int level;          // stat 12
    int exp_permille;   // Experience progress within the current level ‰ (thresholds from the original game's experience.txt)
    int belt[4];        // How many items remain in each of the four belt columns (belt item x % 4 = column)
    int portal;         // Town portal count: quantity in the Tome of Town Portal tbk (stat 70) + number of Scroll of Town Portal tsc
    int players;        // Current players setting (players setting object +0xc); 0 = not read
    int hp, hp_max, mp, mp_max;   // Life / mana (stat 6–9 ÷ 256, rounded to an integer)
    int area, x, y;     // Current area number (levels.txt Id; 0 = not read) and player coordinates (cells)
    int points;         // Unassigned attribute points stat 4 + skill points stat 5 (lit state of the red square cross)
    int holding;        // An item is held on the cursor (a drag-and-drop did not complete and the item is still in hand): the front end uses this to treat 'tap on empty space' as cancel
    int quest_unread;   // A new quest is waiting to be read: the original game's HUD quest hint is lit (client UI state byte main+0x2d5ff58); cleared after the quest panel is opened (the other condition for the red state of the bottom bar cross)
    int dead;           // Player dead (mode 0 / 17): the front end hides the UIKit bottom bar so it does not block the death screen
} dm_hud_info;
// Player 'dead' test = the game's own definition (main+0x6e5c48 / 0x6e5cc8 client command dispatch: a player unit whose [+0xc] mode is 0 or 0x11 is handled as dead;
// D2 player mode 0 = DEATH, in the death animation, 17 = DEAD, already dead; 0 -> 17 when the death animation ends, and it becomes town standing 5 after reviving back in town)
static inline int dm_hud_player_mode_dead(unsigned mode) { return mode == 0 || mode == 17; }
// UIKit bottom bar visibility: shown only in the normal in-run state -- it gets out of the way when the player has not been read, on death, in navigation states (panel / loading screen / cutscene), and when blocked by the panel stack
// Area numbers of the five act towns (levels.txt Id): Rogue Encampment 1, Lut Gholein 40, Kurast Docks 75, Pandemonium Fortress 103, Harrogath 109
static inline int dm_hud_area_is_town(int area) { return area == 1 || area == 40 || area == 75 || area == 103 || area == 109; }
static inline int dm_hud_bar_visible(const dm_hud_info *h, int navigation, int blocked) { return h->valid && !h->dead && !navigation && !blocked; }
void dm_hud_get(dm_hud_info *out);
void dm_hud_request_players(int n);   // 1..8; callable from any thread
// Host internal (diag.c tick entry): take the latest request, publish this tick's readings
int dm_hud_requested_players(void);
void dm_hud_publish(const dm_hud_info *in);

// 'The item the controller cursor / pointer is currently pointing at' in an item panel: taken from the game's own hover object (the function used by the bottom key hints), not back-computed from cell coordinates.
// May only be called from the game main thread (where the controller is read / UI message callbacks): it reads client UI widgets and the client unit table, synchronously, read-only, without locking.
#pragma once
#include <stdint.h>
enum { DM_ITEM_AT_NONE, DM_ITEM_AT_INVENTORY, DM_ITEM_AT_BELT, DM_ITEM_AT_EQUIP, DM_ITEM_AT_STASH, DM_ITEM_AT_CUBE, DM_ITEM_AT_SHOP, DM_ITEM_AT_TRADE };
typedef struct {
    uint32_t id, cls;       // Item unit id, item table row number
    char code[4];           // Item code (trailing spaces removed, e.g. "hp1", "box"), 0-terminated
    int container;          // DM_ITEM_AT_*
    int potion, scroll, book;   // Item type (the game's type membership function): potion / scroll / book
    int beltable;           // Beltable by type (the belt flag in the item type table)
    int belt_room;          // Beltable and the belt has room right now (the same check that precedes the game's "Move to Belt" hint)
    int equippable;         // Can be equipped right now (the same check that precedes the game's "Equip" hint)
    int stack;              // Stack count of this cell in the advanced stash (gem / material / rune pages); not a stacked item = 0 (item data +0x9c, the same byte the original game checks before a long-press takes multiple items)
    int unid;               // Unidentified: bit 0x10 of item data ([item+0x10]) +0x18 is 0 (the original game's 'identified' flag; verified at both ends by flipping it in the test code dm_actions.c)
    int gx, gy, gw, gh;     // Top-left cell and cells occupied of the item in its container (inventory / stash / cube / shop / trade); for the belt gives (cell number, 0, 1, 1), for an equipment slot gives (0, 0, 1, 1)
} dm_cursor_item_info;
int dm_cursor_item(dm_cursor_item_info *out);   // 1 = pointing at an item and out has been filled; 0 = none (panel not open / pointing at an empty cell / focus not on an item cell)
int dm_held_size(int *w, int *h);              // Cells occupied by the item held in hand (width, height); returns 0 if nothing is held. The 'identify scroll used, waiting for a target' case does not count as held
int dm_held_pending(void);                     // Whether the item in hand has an operation pending confirmation right now (the previous command has not been answered yet); returns 0 if nothing is held
int dm_vendor_repair_mode(void);                // Whether the vendor page is in the 'repair' cursor mode right now (repair button tapped, hammer cursor). May only be called from the game main thread
int dm_item_targeting(void);                    // Whether the 'an item was used, waiting to select a target item' state is in effect right now: 0 none; non-zero = the target type of that item in the item table + 1 (identify scroll / identify tome both go through this state)

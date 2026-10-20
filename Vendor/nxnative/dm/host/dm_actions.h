// Host entry points for "select first, then confirm": vendor buying/selling, stat / skill point allocation, setting the quantity box value. For implementation and rationale see dm_actions.c, dm_textinput.c.
// Actions: callable from any thread, executed on the game main thread (where the controller is fetched). Readings: the main thread publishes a snapshot every frame, readable from any thread.
#pragma once
#include <stdint.h>
typedef struct {
    int open;                 // the vendor trade page is open
    int gold, stash_gold;     // gold carried, gold in the stash (purchases can deduct from both, game rule)
    int sel_valid;            // the cursor has selected a piece of goods
    uint32_t sel_id; char sel_code[4]; char sel_name[64]; int buy_price;
    int sel_gx, sel_gy, sel_gw, sel_gh;   // top-left cell and footprint of the selected goods on the shelf (in cells; meaningless when sel_valid is 0). Converted to a screen rectangle for the drag-goods follow image
    int can_buy;              // enough gold (buy price ≤ gold carried + gold in the stash); whether the inventory has room is judged by the game at purchase time
    int held_valid;           // an item is held in hand (being dragged)
    uint32_t held_id; char held_name[64]; int sell_price;   // sell_price = 0: this item cannot be sold
} dm_shop_info;
void dm_shop_get(dm_shop_info *out);
int  dm_shop_open(void);
void dm_shop_buy(void);                   // buy the selected item (the game's own purchase path; not enough gold / no room in the inventory is rejected by the game with the original game's prompt, not blocked here)
void dm_shop_sell_cursor(void);           // sell the item held in hand

typedef struct {
    int stat_points, skill_points;        // remaining stat points / skill points
    int tree_open;                        // the skill tree page is open
    int char_open;                        // the character page is open (and the advanced stats page is not covering it); the phone layer draws the stat "confirm +1 / +5 / all" based on this
    int sel_skill;                        // skill id currently selected on the skill tree page, -1 = none
    int sel_can_add;                      // whether a point can still be added (= sel_block == 0)
    int sel_block;                        // reason a point cannot be added: 0 can add, 1 no skill points, 2 level too low, 3 prerequisite skill not learned, 4 other (already at the cap, etc.)
    char sel_name[64];
} dm_points_info;
void dm_points_get(dm_points_info *out);
void dm_stat_add(int stat, int n);        // stat: 0 strength 1 dexterity 2 vitality 3 energy; n: 1 / 5 / -1 all (valid while the character page is open)
void dm_skill_add_selected(void);         // add 1 point to the skill currently selected on the skill tree page
void dm_belt_put(uint32_t item_id);        // put this inventory item into the belt (the game's own "move to belt" path; does nothing if it is not a potion / the belt is full). item_id uses the id from dm_cursor_item
void dm_item_use(uint32_t item_id);         // use this item immediately (the same function as the original game's "use": the endpoint of controller hold-confirm / keyboard-and-mouse right click; does not wait for the long-press threshold). Drinks potions, reads scrolls, uses tomes, opens the cube. item_id uses the id from dm_cursor_item
int  dm_ui_hover_now(int x, int y);        // put the original game's controller cursor at (x, y) (the same coordinate pair dm_cursor.c writes) and have the game recompute hover / focus / selected cell on the spot; returns 1 = refreshed, 0 = not in controller cursor mode right now. May only be called on the game main thread (where the controller is fetched)
void dm_item_compare(int on);              // equipment comparison on / off: while on, the item worn in the same slot is shown side by side next to the hovered / selected equipment's tooltip (the same state bit as the original game's "hold the compare button", not going through the controller button,
                                           // so it also works on the vendor page and the stash page, where the compare button is taken up by tab switching). Callable from any thread; while on, the host maintains it every frame. The original game does not support comparison on the gambling page, so nothing shows there even when on
void dm_belt_expand(int on);               // expand / collapse the upper rows of the belt (the same panel toggled by the original game's keyboard-and-mouse "show belt" action, panel id 0x1a). Callable from any thread
void dm_belt_use(int col, int row);        // drink the bottle in row `row` (0 = bottom row), column `col` (0–3) of the belt; does nothing if that cell is empty. Goes through the belt branch of dm_item_use. Callable from any thread
void dm_belt_use_merc(int col, int row);   // same as above, but feeds it to the mercenary (belt double-tap); does nothing if the mercenary is absent / dead / this bottle cannot be fed
int  dm_belt_rows(int *expanded);          // belt row count (1–4, depending on the belt worn); when expanded is non-null, writes 1 = currently expanded. Reads the snapshot the main thread publishes every frame
void dm_held_equip(int bodyloc);          // put the held item into this body slot (the same function as the original game's equipment slot "press confirm while holding an item", main+0x3bb24c; empty slot = equip, occupied = swap; nothing happens for what the original game rejects). Callable from any thread
void dm_inv_sort(int page);                // sort (auto-arrange): page 0 inventory, 3 Horadric Cube, 4 current page of the personal stash. The endpoint function of the original game's "hold to sort", without waiting for the long press. Callable from any thread
void dm_name_random(void);                 // character creation naming page: fill the name box with a random name (the same message as the original game's "Random Name" button). Valid while the name panel is open. Callable from any thread
int dm_name_taken(const char *name);       // returns 1 if a character with this name already exists (a same-named directory exists under the save working directory)
int dm_name_gen(char *out, int cap, int (*taken)(const char *));   // random name used when the naming page is left blank (dm_namegen.c): syllable concatenation, draws again if taken is non-zero, at most 64 times; returns 1 on success
void dm_item_equip(uint32_t item_id);       // immediately equip this item from the inventory (or stash / cube) into the corresponding slot (the endpoint of the original game's "hold confirm = equip"; the slot is chosen by the game, and the game swaps by itself when something is already equipped; when the mercenary panel is open and he can wear it, it goes to the mercenary, same as the original game).
                                           // When it cannot be worn (level / stats too low, unidentified, not equipment) only the original game's error sound is played and no packet is sent
void dm_item_unequip(uint32_t item_id);     // immediately unequip this worn item into the inventory (the endpoint of the original game's equipment panel "hold confirm = unequip"; when the inventory cannot hold it the game plays the error sound and does nothing). Not executed while the vendor page is open (in the vendor page that original path would turn into selling it)
void dm_item_identify(uint32_t target_id);   // in the "used an identify scroll / identify tome, waiting to pick a target" state (dm_item_targeting() non-zero), complete the use on this item (the endpoint of the original game's item cell / equipment panel click handling in that state: sends the "use item on item" packet; scroll consumption / tome charge deduction is done by the server as in the original game).
                                             // Not called when not in that state, when the target is not an item on oneself / in the inventory / stash / cube, or when the target has an operation pending confirmation (the log writes the reason)
void dm_item_repair(uint32_t item_id);        // repair this one item in repair mode on the vendor page (the same endpoint as clicking an item in the original game's repair mode); not called when not in repair mode / something is in hand / the original game judges no repair is needed (the log writes the reason)
void dm_belt_fill(uint64_t belt_widget);     // the belt widget in the inventory panel: fill the empty slots in one go with potions from the inventory that can go into the belt (the same code as the original controller "hold R with focus on the belt"); does nothing if the conditions are not met. Callable from any thread
void dm_item_target_cancel(void);            // leave the "waiting to pick a target" state without consuming the scroll (the same code the original game runs when clicking on empty space / an invalid target: clears the pending item, resets the cursor state). Does nothing when not in that state
void dm_stash_take(int count);                   // from the stack the cursor is pointing at right now in the advanced stash (gems / materials / runes pages), take count pieces into the inventory (command 0x63, destination = inventory; 1 piece goes through the grid widget method main+0x39d824, multiple pieces go through main+0x39d9e0 with a piece count).
                                                 // When count exceeds the stack count, takes all that remain. Does nothing when there is no item under the cursor / it is not a stacked item / the stash is not open; the log line "take multiple:" gives the reason. When the inventory cannot hold them, the server decides how many to take (not verified)
void dm_stash_take_id(uint32_t item_id, int count);   // same as above, specified by item id (for testing)
void dm_num_set(int n);                   // set the quantity box value: ≥0 that number, -1 all, -2 half (dm_textinput.c)
void dm_actions_pump(void);               // called every frame where the controller is fetched (main thread)
void dm_held_stow(void);                     // put the item in hand (on the cursor) into the inventory without closing the panel: the step the original game does for "press back while holding an item" (main+0x3cf4d0: finds a place in the inventory for the item and sends 0x18). Callable from any thread, executed on the game main thread next frame
int dm_held_stow_result(void);               // result of the most recent dm_held_stow: -1 no result yet (if it was not stowed it retries every frame for about 1.5 seconds: an item just swapped into the hand has to wait for the server's acknowledgement); 1 put into the inventory (packet sent); 0 not stowed, the held item is untouched
void dm_item_identify_free(uint32_t item_id);   // identify this item for free (double-tap on an unidentified item): calls the original game's identify function main+0x78acf0 in the server tick, without consuming a scroll / tome
// One-press casting of off-hand set skills (that section of dm_actions.c)
uint64_t dm_swapskill_filter(uint64_t buttons);   // where the controller state is fetched (hle_hid.c): hold back / let through the button that needs a weapon swap first
void dm_swapskill_srv_wset(int w);                // the server tick (diag.c hud_tick) publishes the current weapon set 0 / 1
int dm_swapskill_slot(int slot, int *charges);    // skill button display: 1 = the skill is in the other set ("II" badge), 2 = charged skill (*charges = remaining charges)
int dm_swapskill_equipped(int32_t item_id);       // this item is worn on the body (including the weapon-swap set)

#pragma once
// Text box color code mapping table (implementation and notes in dm_textbox_core.c)
#include <stddef.h>
int dm_textbox_load(const char *path);    // Read the table, return the entry count; return -1 if it cannot be opened (table cleared)
void dm_textbox_reset(void);
int dm_textbox_count(void);
// Rewrite by the table: 0 = unchanged (*out is NULL); 1 = whole-string hit; 2 = annotated substrings inside were replaced. *out is freed by the caller
int dm_textbox_rewrite(const char *s, size_t n, char **out, size_t *on);
// Read the mapping table (read only once, does not hook the gate; implemented in dm_textbox.c): returns 1 = table present, 0 = none (item annotations off / no overlay)
int dm_textbox_ensure_loaded(void);

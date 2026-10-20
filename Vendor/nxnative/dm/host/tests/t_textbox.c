// dm_textbox_core unit test: all expectations are hand-written. U+E07E = EE 81 BE.
// Criterion: whole strings / substrings of the annotated version found in the table are replaced by the text box version; strings outside the table (including the original game's own coded strings and strings without codes) are untouched byte for byte; with no table nothing is touched.
#include "../dm_textbox_core.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define C "\xee\x81\xbe"
static int fails, checks;
static void expect(const char *what, const char *in, int want_k, const char *want) {
    char *o; size_t on; int k = dm_textbox_rewrite(in, strlen(in), &o, &on); checks++;
    int ok = k == want_k && (want ? (o && on == strlen(want) && !memcmp(o, want, on)) : !o);
    if (!ok) { fails++; printf("✗ %s: got k=%d '%.*s'\n", what, k, o ? (int)on : 0, o ? o : ""); } else printf("✓ %s\n", what);
    free(o);
}
int main(void) {
    // The table rows and inputs below are game text from the Chinese D2R client (Hongye mod), written as UTF-8 escapes so the bytes stay identical:
    // an "enhanced damage 60-70%" range line, two unique item names, "Found Chronicle item: ...!", "and",
    // the game's whisper line "You whisper to <someone>: hello", and a two-line text "line one" / "line two".
    char path[] = "/tmp/t_textbox_XXXXXX"; int fd = mkstemp(path); FILE *f = fdopen(fd, "w");
    fprintf(f, "# annotated version\ttext box version\n");
    fprintf(f, "%s\t%s\n", C "5[\xe5\xbc\xba\xe4\xbc\xa4" "60-70%]\\n" C "4\xe6\xad\xbb\xe4\xba\xa1\xe4\xb9\x8b\xe9\x93\xb2", "\xe6\xad\xbb\xe4\xba\xa1\xe4\xb9\x8b\xe9\x93\xb2");   // range line + name
    fprintf(f, "%s\t%s\n", C "1\xe6\x80\x80\xe7\x89\xb9\xe4\xb9\x8b\xe8\x84\x9a", "\xe6\x80\x80\xe7\x89\xb9\xe4\xb9\x8b\xe8\x84\x9a");                         // Hongye mod name color
    fclose(f);
    expect("no table: coded string untouched", C "1\xe6\x80\x80\xe7\x89\xb9\xe4\xb9\x8b\xe8\x84\x9a", 0, NULL);
    if (dm_textbox_load(path) != 2) { printf("✗ table entry count is not 2\n"); return 1; }
    expect("whole annotated string in the table → text box version", C "5[\xe5\xbc\xba\xe4\xbc\xa4" "60-70%]\n" C "4\xe6\xad\xbb\xe4\xba\xa1\xe4\xb9\x8b\xe9\x93\xb2", 1, "\xe6\xad\xbb\xe4\xba\xa1\xe4\xb9\x8b\xe9\x93\xb2");
    expect("whole Hongye name-color string → plain name", C "1\xe6\x80\x80\xe7\x89\xb9\xe4\xb9\x8b\xe8\x84\x9a", 1, "\xe6\x80\x80\xe7\x89\xb9\xe4\xb9\x8b\xe8\x84\x9a");
    expect("annotated text inside a longer sentence: only that part is replaced", "\xe5\x8f\x91\xe7\x8e\xb0\xe7\xbc\x96\xe5\xb9\xb4\xe5\x8f\xb2\xe7\x89\xa9\xe5\x93\x81\xef\xbc\x9a" C "1\xe6\x80\x80\xe7\x89\xb9\xe4\xb9\x8b\xe8\x84\x9a" "\xef\xbc\x81", 2, "\xe5\x8f\x91\xe7\x8e\xb0\xe7\xbc\x96\xe5\xb9\xb4\xe5\x8f\xb2\xe7\x89\xa9\xe5\x93\x81\xef\xbc\x9a\xe6\x80\x80\xe7\x89\xb9\xe4\xb9\x8b\xe8\x84\x9a\xef\xbc\x81");
    expect("two occurrences in one sentence: both replaced", C "1\xe6\x80\x80\xe7\x89\xb9\xe4\xb9\x8b\xe8\x84\x9a" "\xe5\x92\x8c" C "1\xe6\x80\x80\xe7\x89\xb9\xe4\xb9\x8b\xe8\x84\x9a", 2, "\xe6\x80\x80\xe7\x89\xb9\xe4\xb9\x8b\xe8\x84\x9a\xe5\x92\x8c\xe6\x80\x80\xe7\x89\xb9\xe4\xb9\x8b\xe8\x84\x9a");
    expect("the original game's own coded string (whisper) is not in the table: untouched", C "0\xe4\xbd\xa0\xe6\x82\x84\xe6\x82\x84\xe5\x9c\xb0\xe5\xaf\xb9" C "1\xe6\x9f\x90\xe4\xba\xba" C "0\xe8\xaf\xb4: \xe4\xbd\xa0\xe5\xa5\xbd", 0, NULL);
    expect("string without codes: untouched", "\xe6\xad\xbb\xe4\xba\xa1\xe4\xb9\x8b\xe9\x93\xb2", 0, NULL);
    expect("multi-line original text (no codes): untouched", "\xe7\xac\xac\xe4\xb8\x80\xe8\xa1\x8c\n\xe7\xac\xac\xe4\xba\x8c\xe8\xa1\x8c", 0, NULL);
    expect("looks annotated but is not in the table: untouched", C "5[\xe5\xbc\xba\xe4\xbc\xa4" "1-2%]\n" C "4\xe6\xad\xbb\xe4\xba\xa1\xe4\xb9\x8b\xe9\x93\xb2", 0, NULL);
    unlink(path); dm_textbox_reset();
    expect("after clearing the table: untouched", C "1\xe6\x80\x80\xe7\x89\xb9\xe4\xb9\x8b\xe8\x84\x9a", 0, NULL);
    printf("TEXTBOX %s checks=%d failures=%d\n", fails ? "FAIL" : "PASS", checks, fails);
    return fails != 0;
}

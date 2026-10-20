// Save write and save transaction unit test (takes seconds): includes hle_fs.c directly and calls its static implementation; pwrite is replaced by a scriptable fake.
// All expected values are hand-written from the semantics, not computed by calling the implementation under test:
//   (1) pwrite returns 0 (can happen when the disk is full) -> WriteFile returns failure after one call (it used to loop forever here);
//   (2) pwrite writes in pieces (3 bytes first, then the rest) -> success and the file content is complete;
//   (3) transaction: the failure in (1) causes this transaction's Commit to be rejected and the working directory to return to the committed version; the next transaction writes in the working directory, the committed directory is still the old version before Commit and the new version after Commit;
//   (4) DM_TEST_FS_FAIL=write:N:errno makes only the Nth save write fail, with writes before and after proceeding normally; that transaction's Commit is rejected, the committed version is unchanged, and the front end receives one notification;
//      the next transaction commits normally, and the final save = the content of the next transaction;
//   (5) remounting discards uncommitted content.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
static ssize_t fake_pwrite(int fd, const void *buf, size_t n, off_t off);
#define pwrite fake_pwrite
#include "../hle_fs.c"
#undef pwrite
ssize_t pwrite(int, const void *, size_t, off_t);

struct dm_flags g_flag; uint64_t g_t0_ns; uint64_t now_ns(void) { return 0; }   // stubs for log timestamps and the read path (not used by the write path)
void dm_prof_add(int id, uint64_t ns, uint64_t b) { (void)id; (void)ns; (void)b; } void dm_guest_write_prepare(void *a, size_t n) { (void)a; (void)n; }
extern int g_nfail, g_lasterr;                                        // front-end notification count (the strong implementation in t_fs_stub.c replaces the weak one in hle_fs.c)
void dm_fs_save_poison(int e);
static int g_mode, g_calls;                   // 0 write normally; 1 always return 0; 2 write only 3 bytes the first time
static ssize_t fake_pwrite(int fd, const void *buf, size_t n, off_t off) {
    g_calls++;
    if (g_mode == 1) { if (g_calls > 1000) { printf("  ✗ pwrite retried over 1000 times after returning 0 (endless loop)\n"); exit(1); } return 0; }
    if (g_mode == 2 && g_calls == 1 && n > 3) n = 3;
    return pwrite(fd, buf, n, off);
}
static int fails, checks;
#define CHECK(c, ...) do { checks++; if (!(c)) { fails++; printf("  ✗ "); } else printf("  ✓ "); printf(__VA_ARGS__); printf("\n"); } while (0)
static void put(const char *p, const char *s) { FILE *f = fopen(p, "w"); fputs(s, f); fclose(f); }
static int same(const char *p, const char *s) {
    char b[64] = {0}; FILE *f = fopen(p, "r"); if (!f) return 0; size_t k = fread(b, 1, sizeof b - 1, f); fclose(f);
    return k == strlen(s) && !memcmp(b, s, k);
}
static Result write_save(const char *path, const char *s) {           // open -> set size -> write -> close
    uint64_t h; Result r = h_fs_OpenFile(&h, path, MODE_WRITE); if (r) return r;
    h_fs_SetFileSize(h, (int64_t)strlen(s));
    r = h_fs_WriteFile(h, 0, s, strlen(s), NULL); h_fs_CloseFile(h); return r;
}
static int read_fs(const char *path, char *out, size_t n) { uint64_t h; size_t got = 0; if (h_fs_OpenFile(&h, path, MODE_READ)) return 0; Result r = h_fs_ReadFile(&got, h, 0, out, n - 1); h_fs_CloseFile(h); out[got] = 0; return !r; }

// Offset translation for zero-stripped archives (dm_data_pread): original content = a fixed byte sequence computed from position, with 0 filled in at zero-run positions; zero-stripped file = zero runs removed.
// Expected values are taken directly from the "original sequence", not through the implementation under test. Covers: crossing kept-run / zero-run boundaries, a whole read falling in a zero run, start and end, reading past end of file.
static int test_holes(void) {
    enum { N = 100000 }; static uint8_t orig[N], got[N]; const long hole[3][2] = {{0, 1000}, {30000, 25000}, {99000, 1000}};   // one zero run each at the start, middle and end
    for (long i = 0; i < N; i++) orig[i] = (uint8_t)(i * 131 + (i >> 8) * 7 + 1);
    for (int h = 0; h < 3; h++) memset(orig + hole[h][0], 0, (size_t)hole[h][1]);
    char path[] = "/tmp/dm-holes.XXXXXX"; int tfd = mkstemp(path); if (tfd < 0) return 1; char hp[64]; snprintf(hp, sizeof hp, "%s.holes", path);
    long pos = 0; for (int h = 0; h <= 3; h++) { long end = h < 3 ? hole[h][0] : N; if (end > pos && write(tfd, orig + pos, (size_t)(end - pos)) != end - pos) return 1; if (h < 3) pos = hole[h][0] + hole[h][1]; }
    close(tfd); FILE *f = fopen(hp, "w"); fprintf(f, "size %d\n", N); for (int h = 0; h < 3; h++) fprintf(f, "%ld %ld\n", hole[h][0], hole[h][1]); fclose(f);
    int fd = open(path, O_RDONLY); dm_data_note_fd(fd, path); int bad = 0;
    const long q[][2] = {{0, 500}, {500, 1000}, {999, 2}, {1000, 29000}, {29990, 20}, {30000, 25000}, {40000, 100}, {54990, 20}, {55000, 44000}, {98990, 1010}, {99500, 500}, {99990, 100}, {0, N}, {100000, 10}, {123456, 10}};
    for (size_t k = 0; k < sizeof q / sizeof *q; k++) {
        long off = q[k][0], n = q[k][1], want = off >= N ? 0 : (off + n > N ? N - off : n);
        memset(got, 0xAA, sizeof got); ssize_t r = dm_data_pread(fd, got, (size_t)n, off);
        if (r != want || (want && memcmp(got, orig + off, (size_t)want))) { fprintf(stderr, "FAIL: zero-stripped read off=%ld n=%ld returned %zd (expected %ld)\n", off, n, r, want); bad++; }
    }
    if (dm_data_logical_size(path, 49000) != N) { fprintf(stderr, "FAIL: original size of the zero-stripped archive\n"); bad++; }
    close(fd); g_hm[fd] = NULL; unlink(path); unlink(hp);
    printf("%s zero-stripped archive offset translation: 15 kinds of read equal the original content byte for byte\n", bad ? "✗" : "✓");
    return bad;
}
int main(void) {
    if (test_holes()) return 1;
    char root[1024], save[1100], work[1200], p[1200];
    const char *sp = getenv("TMPDIR"); snprintf(root, sizeof root, "%s/t_fs.XXXXXX", sp ? sp : "/private/tmp");
    if (!mkdtemp(root)) { perror("mkdtemp"); return 1; }
    char rom[1100], overlay[1100], rdata[1200], odata[1200], fn[1300], got[64];
    snprintf(rom, sizeof rom, "%s/rom", root); snprintf(overlay, sizeof overlay, "%s/overlay", root); snprintf(rdata, sizeof rdata, "%s/data", rom); snprintf(odata, sizeof odata, "%s/data", overlay);
    mkdir(rom, 0755); mkdir(overlay, 0755); mkdir(rdata, 0755); mkdir(odata, 0755);
    snprintf(fn, sizeof fn, "%s/same", rdata); put(fn, "base"); snprintf(fn, sizeof fn, "%s/same", odata); put(fn, "overlay"); snprintf(fn, sizeof fn, "%s/base", rdata); put(fn, "only-base"); snprintf(fn, sizeof fn, "%s/over", odata); put(fn, "only-overlay");
    setenv("DM_ROMFS", rom, 1); setenv("DM_ROMFS_OVERLAY", overlay, 1); CHECK(h_fs_MountRom("rom", NULL, 0) == RES_OK, "mount RomFS with two layers (base + overlay)");
    CHECK(read_fs("rom:/data/same", got, sizeof got) && !strcmp(got, "overlay"), "the overlay file wins"); CHECK(read_fs("rom:/data/base", got, sizeof got) && !strcmp(got, "only-base"), "falls back to the base when the overlay lacks the file");
    uint64_t rh; CHECK(h_fs_OpenFile(&rh, "rom:/data/same", MODE_WRITE) == RES_FAIL, "the two-layer mount refuses writes");
    {   // Find a file in the overlay (dm_overlay_file): two layers joined by a colon (old devices = in-bundle overlay + Legacy Device Pack), searched layer by layer with earlier ones taking priority; treating the whole string as one directory finds nothing
        char l2[1100], two[2300], want[1300]; snprintf(l2, sizeof l2, "%s/pack", root); mkdir(l2, 0755); snprintf(two, sizeof two, "%s:%s", overlay, l2); setenv("DM_ROMFS_OVERLAY", two, 1);
        snprintf(fn, sizeof fn, "%s/mark", overlay); put(fn, "1"); snprintf(fn, sizeof fn, "%s/only2", l2); put(fn, "2"); snprintf(fn, sizeof fn, "%s/mark", l2); put(fn, "2");
        snprintf(want, sizeof want, "%s/mark", overlay); CHECK(dm_overlay_file("mark", p, sizeof p) == 1 && !strcmp(p, want), "in both layers: the first layer's is taken");
        snprintf(want, sizeof want, "%s/only2", l2); CHECK(dm_overlay_file("only2", p, sizeof p) == 1 && !strcmp(p, want), "only in the second layer: the second layer's is taken");
        snprintf(want, sizeof want, "%s/data/over", overlay); CHECK(dm_overlay_file("data/over", p, sizeof p) == 1 && !strcmp(p, want), "relative path with a subdirectory");
        CHECK(dm_overlay_file("none", p, sizeof p) == 0 && !p[0], "in no layer: returns 0, output cleared");
        setenv("DM_ROMFS_OVERLAY", overlay, 1); snprintf(want, sizeof want, "%s/mark", overlay); CHECK(dm_overlay_file("mark", p, sizeof p) == 1 && !strcmp(p, want), "a single layer (newer devices) works as before");
        unsetenv("DM_ROMFS_OVERLAY"); CHECK(dm_overlay_file("mark", p, sizeof p) == 0, "no overlay set: returns 0"); setenv("DM_ROMFS_OVERLAY", overlay, 1); }
    g_nmnt = 0;
    snprintf(save, sizeof save, "%s/save", root); snprintf(work, sizeof work, "%s.work", save);
    mkdir(save, 0755); snprintf(p, sizeof p, "%s/a", save); put(p, "old");
    setenv("DM_SAVE", save, 1); setenv("DM_TEST_FS_FAIL", "write:5:28", 1);   // the 5th save write fails, errno 28 = ENOSPC
    CHECK(h_fs_MountSave("save", NULL) == RES_OK, "mount the save");

    // Save write count: (1)=1st (2)=2nd (3)=3rd (4)=4th/5th/6th/7th (5)=8th
    printf("① pwrite returns 0\n");
    g_mode = 1; g_calls = 0;
    CHECK(write_save("save:/a", "xyz") == RES_FAIL, "WriteFile returns failure 0x2A2");
    CHECK(g_calls == 1, "pwrite called only once (actually %d times; it used to retry forever)", g_calls);

    printf("② pwrite writes in pieces\n");
    g_mode = 2; g_calls = 0;
    CHECK(write_save("save:/a", "abcdefg") == RES_OK, "WriteFile succeeds");
    CHECK(g_calls == 2, "pwrite called twice (3 bytes + 4 bytes; actually %d)", g_calls);
    snprintf(p, sizeof p, "%s/a", work); CHECK(same(p, "abcdefg"), "the work directory holds the complete abcdefg");
    g_mode = 0;

    printf("③ transaction\n");
    CHECK(h_fs_Commit("save") == RES_FAIL && g_nfail == 1 && g_lasterr == ENOSPC, "the Commit of the transaction holding ①② is refused, front end notified once errno=ENOSPC (actually %d times errno=%d)", g_nfail, g_lasterr);
    snprintf(p, sizeof p, "%s/a", work); CHECK(same(p, "old"), "work directory discarded, back to the committed version old");
    CHECK(write_save("save:/a", "new") == RES_OK, "next transaction: write new");
    snprintf(p, sizeof p, "%s/a", save); CHECK(same(p, "old"), "before Commit the committed directory is still old");
    CHECK(h_fs_Commit("save") == RES_OK, "Commit");
    CHECK(same(p, "new"), "after Commit the committed directory is new");
    snprintf(p, sizeof p, "%s.new", save); CHECK(access(p, F_OK) != 0, "the swapped-out old version is deleted (no .new left)");

    printf("④ DM_TEST_FS_FAIL=write:5:28\n");
    CHECK(write_save("save:/b", "4") == RES_PATH_NOT_FOUND, "(b does not exist: open fails, not counted as a write)");
    h_fs_CreateFile("save:/b", 0);
    CHECK(write_save("save:/b", "4") == RES_OK, "4th write succeeds");
    errno = 0; CHECK(write_save("save:/b", "5") == RES_FAIL && errno == 28, "5th write fails errno=28 (actually errno=%d)", errno);
    CHECK(write_save("save:/b", "6") == RES_OK, "6th write succeeds");
    CHECK(h_fs_Commit("save") == RES_FAIL && g_nfail == 2 && g_lasterr == 28, "that transaction's Commit is refused, front end notified errno=28 (%d times in total)", g_nfail);
    snprintf(p, sizeof p, "%s/b", save); CHECK(access(p, F_OK) != 0, "committed directory unchanged (no b)");
    snprintf(p, sizeof p, "%s/b", work); CHECK(access(p, F_OK) != 0, "work directory discarded (no b)");
    snprintf(p, sizeof p, "%s/a", save); CHECK(same(p, "new"), "committed directory a is still new");
    h_fs_CreateFile("save:/b", 0);
    CHECK(write_save("save:/b", "7") == RES_OK && h_fs_Commit("save") == RES_OK, "next transaction: write b=7, Commit succeeds");
    snprintf(p, sizeof p, "%s/b", save); CHECK(same(p, "7"), "final committed b = 7 (the next transaction's content)");
    CHECK(g_nfail == 2, "a successful transaction sends no notification (still %d times in total)", g_nfail);

    printf("⑤ remounting discards uncommitted content\n");
    CHECK(write_save("save:/a", "v9") == RES_OK, "write a=v9 without committing");
    g_nmnt = 0;                                                        // simulate a process restart: clear the mount table
    CHECK(h_fs_MountSave("save", NULL) == RES_OK, "remount");
    snprintf(p, sizeof p, "%s/a", work); CHECK(same(p, "new"), "work directory a is back to the committed version new");
    snprintf(p, sizeof p, "%s/b", work); CHECK(same(p, "7"), "work directory b = the committed 7");

    printf("⑥ failed writes are handled without exiting (DM_TEST_FS_FAILAT)\n");
    unsetenv("DM_TEST_FS_FAIL");
    // 6a Recloning after a refused commit fails: do not exit, the work directory is untouched and the committed version unchanged; the next commit is refused again and the reclone succeeds; the transaction after that commits normally
    setenv("DM_TEST_FS_FAILAT", "reclone:1", 1);
    CHECK(write_save("save:/a", "bad") == RES_OK, "write a=bad");
    dm_fs_save_poison(ENOSPC); int nf0 = g_nfail;
    CHECK(h_fs_Commit("save") == RES_FAIL && g_nfail == nf0 + 1, "this transaction is refused (injected reclone failure), the process is still alive, front end notified once");
    snprintf(p, sizeof p, "%s/a", save); CHECK(same(p, "new"), "committed directory a is still new");
    snprintf(p, sizeof p, "%s/a", work); CHECK(same(p, "bad"), "work directory not deleted (a is still bad)");
    CHECK(h_fs_Commit("save") == RES_FAIL && g_nfail == nf0 + 2, "still tainted: the next commit is refused too");
    snprintf(p, sizeof p, "%s/a", work); CHECK(same(p, "new"), "this time the reclone works: work directory a is back to new");
    snprintf(p, sizeof p, "%s.re", work); CHECK(access(p, F_OK) != 0, "no .re left");
    CHECK(write_save("save:/a", "good") == RES_OK && h_fs_Commit("save") == RES_OK, "next transaction writes a=good, commit succeeds");
    snprintf(p, sizeof p, "%s/a", save); CHECK(same(p, "good"), "committed a = good");
    // 6b Writing the guest name after a rename fails and the rollback fails too: do not exit; the file is in a transactional save, so this transaction's commit is refused and the committed version is unchanged; after recloning everything works
    setenv("DM_TEST_FS_FAILAT", "guestname:1,renameback:1", 1);
    h_fs_CreateFile("save:/c", 0); CHECK(write_save("save:/c", "c") == RES_OK, "write c");
    CHECK(h_fs_RenameFile("save:/c", "save:/d") != RES_OK, "rename c → d returns failure (both steps injected to fail), the process is still alive");
    nf0 = g_nfail; CHECK(h_fs_Commit("save") == RES_FAIL && g_nfail == nf0 + 1, "this transaction's commit is refused");
    snprintf(p, sizeof p, "%s/c", save); CHECK(access(p, F_OK) != 0, "committed directory has no c");
    snprintf(p, sizeof p, "%s/d", save); CHECK(access(p, F_OK) != 0, "committed directory has no d");
    snprintf(p, sizeof p, "%s/a", save); CHECK(same(p, "good"), "committed a is still good");
    CHECK(write_save("save:/a", "ok2") == RES_OK && h_fs_Commit("save") == RES_OK, "the next transaction commits as usual");
    // 6c Cloning the work directory at mount fails: do not exit; mount the committed directory read-only instead. Reads work, writes fail, commits are no-ops, the committed version is unchanged, and the front end is notified once; the next normal mount works as before
    setenv("DM_TEST_FS_FAILAT", "mountclone:1", 1); g_nmnt = 0; nf0 = g_nfail;
    snprintf(p, sizeof p, "rm -rf '%s'", work); system(p);
    CHECK(h_fs_MountSave("save", NULL) == RES_OK && g_nfail == nf0 + 1, "mount returns success, front end notified once (actually %d times)", g_nfail - nf0);
    CHECK(read_fs("save:/a", got, sizeof got) && !strcmp(got, "ok2"), "the read-only mount reads the committed a=ok2 (read %s)", got);
    CHECK(write_save("save:/a", "zzz") != RES_OK, "writes fail");
    CHECK(h_fs_Commit("save") == RES_OK, "commit is a no-op");
    snprintf(p, sizeof p, "%s/a", save); CHECK(same(p, "ok2"), "committed a is still ok2");
    unsetenv("DM_TEST_FS_FAILAT"); g_nmnt = 0;
    CHECK(h_fs_MountSave("save", NULL) == RES_OK && write_save("save:/a", "ok3") == RES_OK && h_fs_Commit("save") == RES_OK, "remount without injection: transactional as usual, writing a=ok3 and committing succeed");
    snprintf(p, sizeof p, "%s/a", save); CHECK(same(p, "ok3"), "committed a = ok3");


    // Language switch rewriting the settings file (settings_lang_apply): expected values computed by hand from the rule -- only when it "does not match the switch" are Language / VoiceLanguage changed to 0 (English) or 8 (Simplified Chinese); other keys and other languages are untouched
    { extern int g_t_lang; char sd[1200], sf[1300], gotj[512]; snprintf(sd, sizeof sd, "%s/langt", root); mkdir(sd, 0755); snprintf(sf, sizeof sf, "%s/Settings", sd); mkdir(sf, 0755); snprintf(sf, sizeof sf, "%s/Settings/Settings.json", sd);
      #define LANGCASE(dm, in, want, what) do { g_t_lang = (dm); put(sf, (in)); settings_lang_apply(sd); FILE *lf = fopen(sf, "rb"); size_t ln_ = lf ? fread(gotj, 1, sizeof gotj - 1, lf) : 0; if (lf) fclose(lf); gotj[ln_] = 0; CHECK(!strcmp(gotj, (want)), "language switch: %s", (what)); } while (0)
      LANGCASE(-1, "{ \"Language\": 8, \"VoiceLanguage\": 8 }", "{ \"Language\": 8, \"VoiceLanguage\": 8 }", "Apply never tapped: not a byte changes");
      LANGCASE(1, "{ \"A\": 1, \"Language\": 8, \"VoiceLanguage\": 8, \"B\": 2 }", "{ \"A\": 1, \"Language\": 0, \"VoiceLanguage\": 0, \"B\": 2 }", "switch = English, file is Simplified Chinese: text and voice both become 0, other keys untouched");
      LANGCASE(0, "{ \"Language\": 0, \"VoiceLanguage\": 0 }", "{ \"Language\": 8, \"VoiceLanguage\": 8 }", "switch = Chinese, file is English: both become 8");
      LANGCASE(0, "{ \"Language\": 9, \"VoiceLanguage\": 9 }", "{ \"Language\": 9, \"VoiceLanguage\": 9 }", "switch = Chinese, the player chose Traditional Chinese in the original game: not changed back to Simplified Chinese");
      LANGCASE(1, "{ \"Language\": 0, \"VoiceLanguage\": 0 }", "{ \"Language\": 0, \"VoiceLanguage\": 0 }", "switch = English, file already English: untouched");
      LANGCASE(1, "{ \"Language\": 0, \"VoiceLanguage\": 8 }", "{ \"Language\": 0, \"VoiceLanguage\": 0 }", "switch = English, text already English but voice still Chinese: the voice follows");
      LANGCASE(1, "{ \"Language\": 12 }", "{\n    \"VoiceLanguage\": 0, \"Language\": 0 }", "switch = English, two-digit language number and no voice key: rewritten and the voice key added");
      g_t_lang = -1; }

    char cmd[1200]; snprintf(cmd, sizeof cmd, "rm -rf '%s'", root); system(cmd);
    printf("== %d checks, %d failed ==\n", checks, fails);
    return fails != 0;
}

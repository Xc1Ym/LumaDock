// iCloud sync core unit test (takes seconds): dm_cloudsync.c. Two local directories act as two devices and one local directory as the cloud; all expectations are derived by hand from "later write overwrites earlier write", not obtained by running the implementation under test.
#include <dirent.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <unistd.h>
int dm_cloud_sync(const char *save, const char *cloud, const char *bak, const char *statef, int allow_down, uint64_t now_ms, int (*ready)(const char *unit));
int dm_cloud_conflict_take(void);
#if __has_include("../stash_seed.h")   // the public repository does not ship this seed (it is the bytes of a save the game generated): when it is absent, the two groups that use it, 18 and 19, are skipped
#include "../stash_seed.h"
#define T_HAVE_STASH_SEED 1
#endif

static int fails, checks;
#define CHECK(c, ...) do { checks++; if (!(c)) { fails++; printf("  ✗ "); printf(__VA_ARGS__); printf("\n"); } } while (0)
static char R[512];
static void path(char *o, const char *a, const char *b) { snprintf(o, 1024, "%s/%s/%s", R, a, b); }
static void put(const char *dev, const char *rel, const char *txt, long sec) {   // write a file and set its modification time to sec seconds
    char p[1024]; path(p, dev, rel); char d[1024]; strcpy(d, p); for (char *s = d + strlen(R) + 1; (s = strchr(s, '/')); s++) { *s = 0; mkdir(d, 0755); *s = '/'; }
    FILE *f = fopen(p, "w"); fputs(txt, f); fclose(f); struct timeval tv[2] = { { sec, 0 }, { sec, 0 } }; utimes(p, tv);
}
static const char *get(const char *dev, const char *rel) { static char b[256]; char p[1024]; path(p, dev, rel); FILE *f = fopen(p, "r"); if (!f) return NULL; size_t n = fread(b, 1, 255, f); b[n] = 0; fclose(f); return b; }
static long mtime(const char *dev, const char *rel) { char p[1024]; struct stat st; path(p, dev, rel); return stat(p, &st) ? -1 : st.st_mtimespec.tv_sec; }
static int dsync(const char *dev, int down, uint64_t now) { char s[1024], c[1024], b[1024], t[1024]; path(s, dev, "save"); snprintf(c, sizeof c, "%s/cloud", R); path(b, dev, "bak"); path(t, dev, "state"); return dm_cloud_sync(s, c, b, t, down, now, NULL); }
static int count_bak(const char *dev, const char *pre) { char d[1024]; path(d, dev, "bak"); DIR *dp = opendir(d); struct dirent *e; int n = 0; while (dp && (e = readdir(dp))) n += !strncmp(e->d_name, pre, strlen(pre)); if (dp) closedir(dp); return n; }
static int no_skip(const char *u) { return strcmp(u, "Alice"); }
// Shared stash file: one page of items (items pieces, only the page header and item count are written) + one chronicle section (chron bytes); side file: n pieces. Only the structure is built, as the sync side only looks at structure (dm_cloudsync.c rich_of)
static void put_bin(const char *dev, const char *rel, const uint8_t *d, size_t n, long sec) {
    char p[1024]; path(p, dev, rel); char dd[1024]; strcpy(dd, p); for (char *x = dd + strlen(R) + 1; (x = strchr(x, '/')); x++) { *x = 0; mkdir(dd, 0755); *x = '/'; }
    FILE *f = fopen(p, "wb"); fwrite(d, 1, n, f); fclose(f); struct timeval tv[2] = { { sec, 0 }, { sec, 0 } }; utimes(p, tv);
}
static void put_d2i(const char *dev, int items, int chron, long sec) {
    static uint8_t b[8192]; memset(b, 0, sizeof b); uint32_t l1 = 68, l2 = (uint32_t)chron;
    memcpy(b, "\x55\xaa\x55\xaa", 4); memcpy(b + 16, &l1, 4); memcpy(b + 64, "JM", 2); b[66] = (uint8_t)items;
    memcpy(b + 68, "\x55\xaa\x55\xaa", 4); memcpy(b + 68 + 16, &l2, 4); b[68 + 64] = 0xc0;
    put_bin(dev, "save/ModernSharedStashSoftCoreV2/ModernSharedStashSoftCoreV2.d2i", b, 68 + l2, sec);
}
static void put_vault(const char *dev, int n, long sec) { uint8_t b[8] = { 'S', 'W', 'V', 'T', 1, 0, (uint8_t)n, 0 }; put_bin(dev, "save/ModernSharedStashSoftCoreV2.swvault", b, 8, sec); }
static int d2i_items(const char *dev, const char *rel) { char p[1024]; path(p, dev, rel); FILE *f = fopen(p, "rb"); if (!f) return -1; uint8_t b[70]; size_t n = fread(b, 1, 70, f); fclose(f); return n >= 67 ? b[66] : -1; }

int main(void) {
    snprintf(R, sizeof R, "%s/t_cloudsync.%d", getenv("TMPDIR") ? getenv("TMPDIR") : "/tmp", getpid()); mkdir(R, 0755);
    char c[1024]; snprintf(c, sizeof c, "%s/cloud", R); mkdir(c, 0755);
    // (1) A has character Alice (timestamp 1000 seconds), the shared stash and Settings; B is empty -> A uploads, B gets Alice and the shared stash at startup, Settings is not synced, and modification times follow A's
    put("A", "save/Alice/Alice.d2s", "a1", 1000); put("A", "save/Alice/Alice.key", "k", 900);
    put("A", "save/SharedStashSoftCoreV2.d2i", "s1", 1100); put("A", "save/ModernSharedStashSoftCoreV2/ModernSharedStashSoftCoreV2.d2i", "m1", 1100); put("A", "save/Settings/Settings.json", "{}", 1100);
    put("B", "save/Settings/Settings.json", "{b}", 1200);
    CHECK(dsync("A", 0, 0) == 2, "① A should upload 2 units (Alice, _stash)");
    CHECK(dsync("B", 1, 0) == 2, "① B should download 2 units");
    CHECK(get("B", "save/Alice/Alice.d2s") && !strcmp(get("B", "save/Alice/Alice.d2s"), "a1"), "① B's Alice should be a1");
    CHECK(mtime("B", "save/Alice/Alice.d2s") == 1000, "① modification time should be restored to 1000, got %ld", mtime("B", "save/Alice/Alice.d2s"));
    CHECK(get("B", "save/ModernSharedStashSoftCoreV2/ModernSharedStashSoftCoreV2.d2i") && !strcmp(get("B", "save/ModernSharedStashSoftCoreV2/ModernSharedStashSoftCoreV2.d2i"), "m1"), "① B's shared stash should be m1");
    CHECK(!strcmp(get("B", "save/Settings/Settings.json"), "{b}"), "① B's Settings should not be touched");
    CHECK(dsync("A", 1, 0) == 0 && dsync("B", 1, 0) == 0, "① syncing once more should do nothing on either side");
    // (2) Only B changed (2000) -> B uploads while running; A gets it at startup, and A's former copy goes to backup
    put("B", "save/Alice/Alice.d2s", "b2", 2000);
    CHECK(dsync("B", 0, 0) == 1, "② B should upload 1");
    CHECK(dsync("A", 0, 0) == 0 && !strcmp(get("A", "save/Alice/Alice.d2s"), "a1"), "② A should not change local files while running");
    CHECK(dsync("A", 1, 0) == 1 && !strcmp(get("A", "save/Alice/Alice.d2s"), "b2"), "② A should have b2 after startup");
    CHECK(get("A", "bak/Alice-1000000/Alice/Alice.d2s") && !strcmp(get("A", "bak/Alice-1000000/Alice/Alice.d2s"), "a1"), "② A's overwritten a1 should be in backup Alice-1000000");
    // (3) Both sides changed, B wrote later (A's 3000 uploaded first, B 3500) -> B still uploads while running (last write wins), the cloud's former a3 goes to B's backup; A gets b3 at startup
    put("A", "save/Alice/Alice.d2s", "a3", 3000); put("B", "save/Alice/Alice.d2s", "b3", 3500);
    CHECK(dsync("A", 0, 0) == 1, "③ A uploads first");
    CHECK(dsync("B", 0, 0) == 1, "③ B wrote later and uploads too");
    CHECK(get("B", "bak/Alice-3000000/Alice/Alice.d2s") && !strcmp(get("B", "bak/Alice-3000000/Alice/Alice.d2s"), "a3"), "③ the overwritten cloud a3 should be in B's backup");
    CHECK(dsync("A", 1, 0) == 1 && !strcmp(get("A", "save/Alice/Alice.d2s"), "b3"), "③ A should have b3 after startup");
    // (4) Both sides changed, A wrote later (A's 5000 uploaded; B's 4000 not uploaded before restarting) -> B gets A's a4 at startup, b4 goes to backup Alice-4000000
    put("A", "save/Alice/Alice.d2s", "a4", 5000); CHECK(dsync("A", 0, 0) == 1, "④ A uploads");
    put("B", "save/Alice/Alice.d2s", "b4", 4000);
    CHECK(dsync("B", 1, 0) == 1 && !strcmp(get("B", "save/Alice/Alice.d2s"), "a4"), "④ B should have a4 after startup (cloud 5000 > local 4000)");
    CHECK(get("B", "bak/Alice-4000000/Alice/Alice.d2s") && !strcmp(get("B", "bak/Alice-4000000/Alice/Alice.d2s"), "b4"), "④ B's overwritten b4 should be in backup");
    // (5) The cloud package has not finished downloading (ready returns 0) -> skip, local files untouched
    put("A", "save/Alice/Alice.d2s", "a5", 6000); CHECK(dsync("A", 0, 0) == 1, "⑤ A uploads");
    { char s[1024], b[1024], t[1024]; path(s, "B", "save"); path(b, "B", "bak"); path(t, "B", "state"); CHECK(dm_cloud_sync(s, c, b, t, 1, 0, no_skip) == 0 && !strcmp(get("B", "save/Alice/Alice.d2s"), "a4"), "⑤ B should stay untouched while the download is unfinished"); }
    CHECK(dsync("B", 1, 0) == 1 && !strcmp(get("B", "save/Alice/Alice.d2s"), "a5"), "⑤ B should have a5 once downloaded");
    // (6) A deletes Alice -> deletion marker in the cloud; B also deletes at startup and B's copy goes to backup; B's backup keeps only 3 copies (before this there were 1000000 not on B, 3000000, 4000000, plus 6000000 = 3 copies)
    { char p[1024]; path(p, "A", "save/Alice/Alice.d2s"); unlink(p); path(p, "A", "save/Alice/Alice.key"); unlink(p); path(p, "A", "save/Alice"); rmdir(p); }
    CHECK(dsync("A", 0, 7000000) == 1, "⑥ A should write a deletion marker");
    CHECK(dsync("B", 1, 0) == 1 && !get("B", "save/Alice/Alice.d2s"), "⑥ B's Alice should be deleted after startup");
    CHECK(get("B", "bak/Alice-6000000/Alice/Alice.d2s") && !strcmp(get("B", "bak/Alice-6000000/Alice/Alice.d2s"), "a5"), "⑥ B's deleted a5 should be in backup");
    CHECK(count_bak("B", "Alice-") == 3, "⑥ B should keep 3 backups of Alice, got %d", count_bak("B", "Alice-"));
    for (long t = 8; t <= 9; t++) { char v[8]; snprintf(v, sizeof v, "x%ld", t); put("B", "save/Bob/Bob.d2s", v, t * 1000); }   // unrelated characters are not affected
    CHECK(dsync("B", 1, 0) == 1, "⑥ B's new character Bob uploads");
    // (7) After the deletion A created a character with the same name again (9500) -> upload (revive); B gets it at startup
    put("A", "save/Alice/Alice.d2s", "a7", 9500);
    CHECK(dsync("A", 1, 0) == 2 && !strcmp(get("A", "save/Bob/Bob.d2s"), "x9"), "⑦ A: Alice uploads + Bob downloads");
    CHECK(dsync("B", 1, 0) == 1 && get("B", "save/Alice/Alice.d2s") && !strcmp(get("B", "save/Alice/Alice.d2s"), "a7"), "⑦ B should have the recreated Alice a7 after startup");
    // (8) Shared stash: B changes it (10000) -> A gets it at startup
    put("B", "save/SharedStashSoftCoreV2.d2i", "s8", 10000);
    CHECK(dsync("B", 0, 0) == 1 && dsync("A", 1, 0) == 1 && !strcmp(get("A", "save/SharedStashSoftCoreV2.d2i"), "s8"), "⑧ A's shared stash should be s8");
    CHECK(!strcmp(get("A", "save/ModernSharedStashSoftCoreV2/ModernSharedStashSoftCoreV2.d2i"), "m1"), "⑧ the shared stash's other file should keep m1");
    // (9) The save directory was emptied by something other than the game (the state file is still there) -> at startup it does not count as a deletion, everything is fetched back from the cloud, and no deletion marker appears in the cloud
    { char p[1024]; path(p, "A", "save"); char cmd[1200]; snprintf(cmd, sizeof cmd, "rm -rf '%s'", p); system(cmd); mkdir(p, 0755); }
    CHECK(dsync("A", 1, 0) == 3, "⑨ A should download 3 at startup (Alice, Bob, _stash)");
    CHECK(get("A", "save/Alice/Alice.d2s") && !strcmp(get("A", "save/Alice/Alice.d2s"), "a7") && get("A", "save/Bob/Bob.d2s") && !strcmp(get("A", "save/SharedStashSoftCoreV2.d2i"), "s8"), "⑨ A should get back Alice a7, Bob, shared stash s8");
    CHECK(dsync("B", 1, 0) == 0 && get("B", "save/Alice/Alice.d2s"), "⑨ B is unaffected (no deletion marker came over)");
    // (10) The backup directory cannot be written (here it is blocked with a regular file of the same name) -> neither overwrite nor delete touches local files; after unblocking it proceeds as usual (previously it still overwrote / deleted when the backup write failed)
    { char s[1024], c2[1024], b[1024], t2[1024], bf[1024]; snprintf(c2, sizeof c2, "%s/cloud2", R); mkdir(c2, 0755);
      #define SY(dev, down, now) (path(s, dev, "save"), path(b, dev, "bak"), path(t2, dev, "state"), dm_cloud_sync(s, c2, b, t2, down, now, NULL))
      put("F", "save/Settings/Settings.json", "{}", 1);   // F is a device that already has a save directory
      put("E", "save/Eve/Eve.d2s", "e1", 1000); CHECK(SY("E", 0, 0) == 1 && SY("F", 1, 0) == 1 && get("F", "save/Eve/Eve.d2s") && !strcmp(get("F", "save/Eve/Eve.d2s"), "e1"), "⑩ setup: F gets Eve e1");
      put("E", "save/Eve/Eve.d2s", "e2", 2000); CHECK(SY("E", 0, 0) == 1, "⑩ E uploads e2");
      path(bf, "F", "bak"); FILE *f = fopen(bf, "w"); fclose(f);          // F's backup directory location is a regular file: the directory cannot be created
      CHECK(SY("F", 1, 0) == 0 && get("F", "save/Eve/Eve.d2s") && !strcmp(get("F", "save/Eve/Eve.d2s"), "e1"), "⑩ F should not overwrite while the backup cannot be written, still e1");
      unlink(bf);
      CHECK(SY("F", 1, 0) == 1 && get("F", "save/Eve/Eve.d2s") && !strcmp(get("F", "save/Eve/Eve.d2s"), "e2") && get("F", "bak/Eve-1000000/Eve/Eve.d2s") && !strcmp(get("F", "bak/Eve-1000000/Eve/Eve.d2s"), "e1"), "⑩ once unblocked F switches to e2, the whole e1 is in the backup");
      { char p2[1024]; path(p2, "E", "save/Eve/Eve.d2s"); unlink(p2); path(p2, "E", "save/Eve"); rmdir(p2); }
      CHECK(SY("E", 0, 3000000) == 1, "⑩ E deleted Eve while running, writes a deletion marker");
      char bk[1100]; snprintf(bk, sizeof bk, "%s.keep", bf); rename(bf, bk); f = fopen(bf, "w"); fclose(f);   // move the existing backup directory aside first, then block it with a regular file
      CHECK(SY("F", 1, 0) == 0 && get("F", "save/Eve/Eve.d2s"), "⑩ F should not delete Eve while the backup cannot be written");
      unlink(bf); rename(bk, bf);
      CHECK(SY("F", 1, 0) == 1 && !get("F", "save/Eve/Eve.d2s") && get("F", "bak/Eve-2000000/Eve/Eve.d2s"), "⑩ once unblocked F deletes Eve, the whole e2 is in the backup");
      #undef SY
    }
    // (11)-(15) Chronicle replaced wholesale by an empty one: a new device's first sync takes the cloud as authoritative; the shared stash must not be overwritten by a copy with "clearly less" (another cloud directory cloud3, devices G / H)
    { char s3[1024], c3[1024], b3[1024], t3[1024]; snprintf(c3, sizeof c3, "%s/cloud3", R); mkdir(c3, 0755);
      #define S3(dev, down) (path(s3, dev, "save"), path(b3, dev, "bak"), path(t3, dev, "state"), dm_cloud_sync(s3, c3, b3, t3, down, 0, NULL))
      #define D2I "save/ModernSharedStashSoftCoreV2/ModernSharedStashSoftCoreV2.d2i"
      put_d2i("G", 5, 300, 1000); put_vault("G", 3, 1000);
      CHECK(S3("G", 0) == 1, "⑫ cloud empty: G's first sync uploads the shared stash");
      dm_cloud_conflict_take();
      put_d2i("H", 0, 148, 5000);   // H freshly installed: the empty shared stash the game just created, with a timestamp newer than the cloud's
      CHECK(S3("H", 0) == 0 && d2i_items("H", D2I) == 0, "⑪ new device's first sync while running: no upload, no change (an empty stash must not overwrite the cloud)");
      CHECK(S3("H", 1) == 1 && d2i_items("H", D2I) == 5 && get("H", "save/ModernSharedStashSoftCoreV2.swvault"), "⑪ new device's first sync at startup: the cloud wins, gets the 5 items and the Chronicle vault");
      CHECK(count_bak("H", "_stash-") == 1, "⑪ the new device's own empty stash goes to backup");
      CHECK(!dm_cloud_conflict_take(), "⑪ a normal first sync is not a conflict");
      put_d2i("G", 6, 400, 6000); CHECK(S3("G", 0) == 1, "⑭ G's Chronicle grew (400), uploads as usual");
      CHECK(S3("H", 1) == 1 && d2i_items("H", D2I) == 6, "⑭ H gets G's new version at startup");
      put_d2i("H", 0, 148, 7000);   // the shared stash on H somehow became empty (chronicle 148, 0 items), with a newer timestamp
      CHECK(S3("H", 0) == 0, "⑬ H wants to upload the emptied copy while running: blocked");
      CHECK(dm_cloud_conflict_take() == 1, "⑬ the block records a conflict (a notice pops up on entering a run)");
      CHECK(S3("G", 1) == 0 && d2i_items("G", D2I) == 6, "⑬ the cloud was not overwritten: G still has 6 items");
      put_d2i("H", 7, 500, 7500); CHECK(S3("H", 0) == 1, "⑮ H plays normally: Chronicle 500 uploads");
      put_d2i("G", 6, 450, 7600);   // G wrote 450 itself without having synced H's 500 (both sides changed, G wrote later)
      CHECK(S3("G", 0) == 0, "⑮ G wants to overwrite the cloud's Chronicle 500 with 450 while running: blocked");
      CHECK(S3("G", 1) == 0 && d2i_items("G", D2I) == 6, "⑮ G at startup: the cloud's 500 is older than the local 450 but its Chronicle is longer -- last write wins would upload, it is blocked; local files untouched");
      CHECK(dm_cloud_conflict_take() == 1, "⑮ conflict recorded");
      { char p3[1024]; path(p3, "H", "save/ModernSharedStashSoftCoreV2.swvault"); unlink(p3); } put_d2i("H", 7, 500, 8000);
      CHECK(S3("H", 0) == 0 && dm_cloud_conflict_take() == 1, "⑬ the Chronicle vault side file is gone (the cloud has 3 items): blocked");
      put_vault("H", 0, 8100); put_d2i("H", 0, 500, 8100);
      CHECK(S3("H", 0) == 1 && !dm_cloud_conflict_take(), "⑯ normal play: shared stash items taken out, Chronicle vault emptied (file still there, 0 items), Chronicle not shorter -- uploads as usual");
      // (17) That rf3 shape: cloud hardcore stash has 2 items and the chronicle is still the freshly created 148; the local copy was replaced by the empty file the game freshly creates (0 items, 148), the state record is still there and the cloud is unchanged = takes the "only local changed" upload
      { char cd[1024]; snprintf(cd, sizeof cd, "%s/cloud4", R); mkdir(cd, 0755);
        #define S4(dev, down) (path(s3, dev, "save"), path(b3, dev, "bak"), path(t3, dev, "state"), dm_cloud_sync(s3, cd, b3, t3, down, 0, NULL))
        put_d2i("J", 2, 148, 1000); CHECK(S4("J", 1) == 1, "⑰ setup: J uploads a stash with 2 items and Chronicle 148");
        put_d2i("J", 0, 148, 2000); dm_cloud_conflict_take();
        CHECK(S4("J", 0) == 0 && dm_cloud_conflict_take() == 1, "⑰ wants to overwrite the 2-item copy with a freshly created empty file (0 items, 148) while running: blocked");
        CHECK(S4("J", 1) == 0, "⑰ blocked at startup too (no upload)");
        put_d2i("J", 0, 300, 3000); CHECK(S4("J", 0) == 1, "⑰ a stash emptied with a Chronicle longer than the fresh size: uploads as usual");
        // (18) The real rf3 shape: the cloud hardcore stash is another device's preset (stash_seed.h), and the local device has no hardcore stash file yet (startup sync runs before the preset is written) -> not blocked, no prompt; uploading after the local device writes the preset is not blocked either
#ifdef T_HAVE_STASH_SEED
        { char cd5[1024]; snprintf(cd5, sizeof cd5, "%s/cloud5", R); mkdir(cd5, 0755);
          #define S5(dev, down) (path(s3, dev, "save"), path(b3, dev, "bak"), path(t3, dev, "state"), dm_cloud_sync(s3, cd5, b3, t3, down, 0, NULL))
          #define HC "save/ModernSharedStashHardCoreV2/ModernSharedStashHardCoreV2.d2i"
          put_bin("K", HC, g_stash_seed, sizeof g_stash_seed, 1000); put_d2i("K", 3, 400, 1000); CHECK(S5("K", 1) == 1, "⑱ setup: K uploads (the hardcore stash is the preset)");
          { char p5[1024]; path(p5, "K", HC); unlink(p5); } put_d2i("K", 3, 400, 2000); dm_cloud_conflict_take();
          S5("K", 0); CHECK(!dm_cloud_conflict_take(), "⑱ no local hardcore stash file yet, the cloud holds only the preset: nothing is lost, no notice");
          put_bin("K", HC, g_stash_seed, sizeof g_stash_seed, 3000); S5("K", 0); CHECK(!dm_cloud_conflict_take(), "⑱ the local device wrote the preset and uploads: not blocked");
          // (19) The reverse: the cloud has real content and the local copy is the preset -> still blocked
          put_d2i("K", 5, 600, 4000); S5("K", 0); dm_cloud_conflict_take();
          { uint8_t big[700]; memset(big, 0, sizeof big); uint32_t l1 = 68, l2 = 300; memcpy(big, "\x55\xaa\x55\xaa", 4); memcpy(big + 16, &l1, 4); memcpy(big + 64, "JM", 2); big[66] = 9; memcpy(big + 68, "\x55\xaa\x55\xaa", 4); memcpy(big + 84, &l2, 4); big[132] = 0xc0;
            put_bin("K", HC, big, 68 + 300, 5000); CHECK(S5("K", 0) == 1, "⑲ setup: hardcore stash with 9 items, Chronicle 300 uploads"); }
          put_bin("K", HC, g_stash_seed, sizeof g_stash_seed, 6000);
          CHECK(S5("K", 0) == 0 && dm_cloud_conflict_take() == 1, "⑲ the local copy reverted to the preset wants to overwrite the 9-item copy: blocked");
          #undef HC
          #undef S5
        }
#else
        printf("skipping ⑱ ⑲: no shared stash seed stash_seed.h (the public repository does not ship it)\n");
#endif
        #undef S4
      }
      #undef D2I
      #undef S3
    }
    printf("t_cloudsync: %d checks, %d failed\n", checks, fails);
    return fails != 0;
}

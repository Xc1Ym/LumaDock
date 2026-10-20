#include "../romfs_validate.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
static int check(int ok, const char *s) { if (!ok) fprintf(stderr, "FAILED: %s\n", s); return ok; }
int main(void) {
    const char *src = getenv("DM_ROMFS"); if (!src) src = getenv("HOME");
    if (!src) return 1;
    char cmd[4096], why[512], rep[2048], sd[4096]; snprintf(sd, sizeof sd, "%s/data", src);
    if (!check(dm_romfs_validate(sd, why, sizeof why), "original RomFS passes")) { fprintf(stderr, "%s\n", why); return 1; }
    if (!check(dm_romfs_report(sd, rep, sizeof rep) == 0, "full list: original RomFS has nothing missing")) return 1;
    {   // Empty directory: none of the 18 archives is present. Expected values come from the need / size tables in romfs_validate.c: 00-00000001.data 1073741824 bytes = 1.00 GB, 17-00000002.data 4496514 bytes = 4 MB
        char r1[] = "/tmp/dm-romfs-test.XXXXXX"; if (!mkdtemp(r1)) return 1;
        if (!check(!dm_romfs_validate(r1, why, sizeof why) && !strcmp(why, "Missing 00-00000001.data"), "empty directory rejected, first archive reported")) { fprintf(stderr, "%s\n", why); return 1; }
        int bad = dm_romfs_report(r1, rep, sizeof rep);
        if (!check(bad == 18 && strstr(rep, "0 / 18 files present") && strstr(rep, "00-00000001.data (1.00 GB)") && strstr(rep, "17-00000002.data (4 MB)") && !strstr(rep, "Incomplete"), "full list: all 18 missing listed one by one")) { fprintf(stderr, "%s\n", rep); return 1; }
        // Small files such as the config, key and manifests are outside the scope of the check: put in a copy with wrong contents, and neither the verdict nor
        // the list shown to the player changes, and their names do not appear in the list
        snprintf(cmd, sizeof cmd, "printf bad > '%s/.build.config' && printf x > '%s/build_key.txt' && printf x > '%s/archive_manifest.psv'", r1, r1, r1); if (system(cmd)) return 1;
        bad = dm_romfs_report(r1, rep, sizeof rep);
        if (!check(bad == 18 && !strstr(rep, "build") && !strstr(rep, "psv"), "full list: small files not mentioned")) { fprintf(stderr, "%s\n", rep); return 1; }
        snprintf(cmd, sizeof cmd, "rm -rf '%s'", r1); system(cmd);
    }
    {   // Archive files alone (no config, key or any manifest) are enough to pass; then check byte counts and zero-stripped archives: build a copy with symlinks, then truncate one small archive / replace it with "zero-stripped + extent table"
        char r2[] = "/tmp/dm-romfs-size.XXXXXX"; if (!mkdtemp(r2)) return 1;
        snprintf(cmd, sizeof cmd, "for f in '%s'/data/*.data; do ln -s \"$f\" '%s/' || exit 1; done", src, r2); if (system(cmd)) return 1;
        if (!check(dm_romfs_validate(r2, why, sizeof why), "directory with only the archive files passes")) { fprintf(stderr, "%s\n", why); return 1; }
        snprintf(cmd, sizeof cmd, "rm '%s/04-00000002.data' && head -c 1000000 '%s/data/04-00000002.data' > '%s/04-00000002.data'", r2, src, r2); if (system(cmd)) return 1;
        if (!check(!dm_romfs_validate(r2, why, sizeof why) && strstr(why, "is incomplete"), "half-copied archive rejected")) { fprintf(stderr, "%s\n", why); return 1; }
        int bad = dm_romfs_report(r2, rep, sizeof rep);
        if (!check(bad == 1 && strstr(rep, "17 / 18 files present") && strstr(rep, "Incomplete: 04-00000002.data (1 MB / 9 MB)"), "full list: incomplete archives listed separately with present / expected size (1000000 bytes = 1 MB, 8915855 bytes = 9 MB, divided by 1048576 and rounded)")) { fprintf(stderr, "%s\n", rep); return 1; }
        snprintf(cmd, sizeof cmd, "printf 'size 8915855\\n1000000 7915855\\n' > '%s/04-00000002.data.holes'", r2); if (system(cmd)) return 1;
        if (!check(dm_romfs_validate(r2, why, sizeof why), "zero-stripped archive (first 1000000 bytes + extent table) passes")) { fprintf(stderr, "%s\n", why); return 1; }
        snprintf(cmd, sizeof cmd, "printf 'size 8915855\\n1000000 100\\n' > '%s/04-00000002.data.holes'", r2); if (system(cmd)) return 1;
        if (!check(!dm_romfs_validate(r2, why, sizeof why) && strstr(why, "is incomplete"), "extent table that does not match the actual length rejected")) { fprintf(stderr, "%s\n", why); return 1; }
        snprintf(cmd, sizeof cmd, "rm -rf '%s'", r2); system(cmd);
    }
    return 0;
}

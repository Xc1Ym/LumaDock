// nn::time: a real device gets the network-calibrated user clock through the time service; the host reads the system clock directly (single machine, offline).
// Layout follows the public Horizon ABI: PosixTime = int64 seconds; CalendarTime = {s16 year, s8 month/day/hour/minute/second};
// CalendarAdditionalInfo = {u32 day of week, u32 day of year, char time zone name[8], u32 DST, s32 UTC offset in seconds}.
#include "hle.h"
#include <stdatomic.h>
#include <time.h>

typedef struct { int16_t year; int8_t month, day, hour, minute, second; int8_t pad; } CalendarTime;
typedef struct { uint32_t wday, yday; char tzname[8]; uint32_t dst; int32_t offset; } CalendarAdditionalInfo;

// DM_FIXED_TIME=seconds (for deterministic comparison; the ground-truth side counterpart is dm/verify/ryu/drive.py --fix-time):
// ① the user clock (source of the save's d2s +0x20 last-played time and .meta last_modified_time) always returns this value;
// ② the one time() at the game-creation random seed (main 0x3509a0 bl time, return point 0x3509a4, same point as drive.py) returns this value.
// This SDK's libc time() is uptime (clock_gettime(0) → __nnmusl_ClockGetTime → GetSystemTick), not wall clock;
// the other 17 time() call sites in main are left alone and forwarded unchanged to the SDK's own time().
static int64_t fixed_time(void) {
    static int64_t v = -2;
    if (v == -2) { const char *e = getenv("DM_FIXED_TIME"); v = e ? strtoll(e, 0, 0) : -1;
                   if (v >= 0) LOG("DM_FIXED_TIME=%lld: user clock and the run-setup time() (main 0x3509a4) return a fixed value", (long long)v); }
    return v;
}
HLE_FORCE("time", "recognizes the run-setup seed call by its return address (DM_FIXED_TIME); everything else passes straight to the SDK's time()", int64_t, h_time_time, int64_t *t) {
    uint64_t lr = (uint64_t)__builtin_return_address(0);
    static int64_t (*sdk_time)(int64_t *); static uint64_t seed_ret;
    if (!sdk_time) {
        module_t *ms = NULL, *mm = NULL;
        for (int i = 0; i < g_nmod; i++) { if (!strcmp(g_mod[i].name, "sdk")) ms = &g_mod[i]; if (!strcmp(g_mod[i].name, "main")) mm = &g_mod[i]; }
        void *f = ms ? module_sym(ms, "time") : NULL; if (!f) die("time not found in the SDK");
        uint32_t w = mm && !strcmp(mm->build_id, DM_D2R_BUILD) ? *(uint32_t *)(mm->base + 0x3509a0) : 0;   // read only on the D2R build (elsewhere this is unrelated code, and a main smaller than 3.3 MB would be read past its end)
        if ((w & 0xfc000000) == 0x94000000) seed_ret = (uint64_t)mm->base + 0x3509a4;               // bl time (build db0507f3…; the rewriter changes the branch target, so only the bl itself is matched)
        else if (fixed_time() >= 0) LOG("[RED] DM_FIXED_TIME: main 0x3509a0 is not the expected bl time (%#x), run-setup time() not fixed", w);
        sdk_time = (int64_t (*)(int64_t *))f;
    }
    int64_t ft = fixed_time();
    if (ft >= 0 && lr == seed_ret) {
        static int once; if (!once++) LOG("DM_FIXED_TIME: run-setup time() returns %lld", (long long)ft);
        if (t) *t = ft; return ft;
    }
    return sdk_time(t);
}

HLE_FORCE("_ZN2nn4time10InitializeEv", "connect to the time service; clocks come from the host system time instead", Result, h_time_Initialize, void) { return RES_OK; }
HLE_FORCE("_ZN2nn4time13IsInitializedEv", "the time service is taken over, always initialized", int, h_time_IsInitialized, void) { return 1; }
// Steady clock (seconds since boot + a clock source ID, a 16-byte UUID): the host's monotonic seconds with a fixed source ID. GetSpanBetween runs as is in sdk: it subtracts only when the source IDs match
HLE_FORCE("_ZN2nn4time19StandardSteadyClock19GetCurrentTimePointEPNS0_20SteadyClockTimePointE", "steady clock → host monotonic clock (seconds), fixed source ID", Result, h_time_SteadyNow, uint8_t *out) {
    int64_t s = (int64_t)(clock_gettime_nsec_np(CLOCK_MONOTONIC) / 1000000000ull);
    memcpy(out, &s, 8); memcpy(out + 8, "dmhost-steady-01", 16); return RES_OK;
}
HLE_FORCE("_ZN2nn4time23StandardUserSystemClock14GetCurrentTimeEPNS0_9PosixTimeE", "user clock → host time()", Result, h_time_GetCurrentTime, int64_t *out) {
    int64_t ft = fixed_time(); *out = ft >= 0 ? ft : time(NULL); return RES_OK;
}
// The C library's real-time clock (SDK 17): clock_gettime(CLOCK_REALTIME) calls the source that nntimeStartup selects once time::Initialize succeeds (sdk+0x8e414: 1 = the standard user clock,
// 2 = the adjustable one; 0, the system tick, before that), and std::chrono::system_clock::now() throws on its failure. The SDK's getters ask the time service: Ace Attorney Investigations
// Collection called std::terminate at its first real-time read, right after the first-boot language dialog (main+0x3f3f68; found by armyja, GitHub issue #18). The host user clock, to the nanosecond
static int h_time_timespec(int64_t *ts) {
    int64_t ft = fixed_time();
    if (ft >= 0) { ts[0] = ft; ts[1] = 0; return 0; }
    struct timespec t; clock_gettime(CLOCK_REALTIME, &t); ts[0] = t.tv_sec; ts[1] = t.tv_nsec; return 0;
}
HLE_FORCE("_ZN2nn4time41GetStandardUserSystemClockCurrentTimespecEP8timespec", "C library real-time clock from the user clock → host real time", int, h_time_StdTimespec, int64_t *ts) { return h_time_timespec(ts); }
HLE_FORCE("_ZN2nn4time43GetAdjustableUserSystemClockCurrentTimespecEP8timespec", "C library real-time clock from the adjustable user clock → host real time", int, h_time_AdjTimespec, int64_t *ts) { return h_time_timespec(ts); }
// User clock context (0x20 bytes: s64 offset + the steady time point it was made at; user time = offset + a steady time point of the same source ID, the snapshot below fills its +0x00 the same way).
// The SDK reads it from the time service's shared memory, which the host never opens: it returns 0x74 and writes nothing. Unity's DateTime.UtcNow (Engage main+0x4ad40c; Ace Attorney Investigations
// 1&2 per PR #14) then never starts its clock and reads 0001-01-01. Unity takes its time from GetCurrentTime plus system ticks and only compares the context to notice the clock being set, so like a
// Switch's it stays the same until the host clock moves against the guest ticks by more than a second (clock set by hand, a sleep mach_absolute_time did not count); with DM_FIXED_TIME it is made once
HLE_FORCE("_ZN2nn4time23StandardUserSystemClock21GetSystemClockContextEPNS0_18SystemClockContextE", "user clock context from the time service; the host's user clock over its steady clock, renewed when the host clock is set",
          Result, h_time_GetContext, uint8_t *out) {
    static pthread_mutex_t mu = PTHREAD_MUTEX_INITIALIZER; static uint8_t ctx[0x20]; static int64_t drift; static int made;
    uint8_t tp[0x18]; int64_t now; h_time_SteadyNow(tp); h_time_GetCurrentTime(&now);
    int64_t d = now - (int64_t)(guest_ns() / 1000000000ull);
    pthread_mutex_lock(&mu);
    if (!made || (fixed_time() < 0 && llabs(d - drift) > 1)) {
        int64_t off = now - *(const int64_t *)tp; memcpy(ctx, &off, 8); memcpy(ctx + 8, tp, 0x18);
        if (made) LOG("time: host clock moved %+lld s against the guest ticks, new user clock context", (long long)(d - drift));
        drift = d; made = 1;
    }
    memcpy(out, ctx, 0x20);
    pthread_mutex_unlock(&mu);
    return RES_OK;
}
// Forced Terror Zone for stages 6–10 of the boss rush (set by dm_bossrush.c): when g_dm_tz_time is non-zero and not expired, only the clock reads at the "Terror Zone" sites get it; save timestamps and all other calls are unchanged.
// Which sites: the return point falls in the cluster starting at the zone function 0x58f1e0 (0x58f1e0–0x591440), or the zone schedule 0x58f310 is called within 8 instructions after the return (server side 0x636b38 applying the zone, 0x694b48 and so on, 9 sites).
// Expiry: dm_bossrush renews it by 1 second every tick; once this run stops ticking (exit / crash) it no longer applies, and the next run gets the real clock when the game is created.
_Atomic int64_t g_dm_tz_time;
_Atomic uint64_t g_dm_tz_live_ns;
static int tz_site(uint64_t lr) {   // Checked only while forcing is active, reading the 8 instructions after the return point each time, no caching (several threads read the clock)
    static _Atomic uint64_t base; uint64_t b = atomic_load(&base);
    if (!b) { for (int i = 0; i < g_nmod; i++) if (!strcmp(g_mod[i].name, "main")) b = (uint64_t)g_mod[i].base; atomic_store(&base, b); }
    if (!b || lr < b) return 0;
    uint64_t off = lr - b; if (off > 0x58f1e0 && off < 0x591440) return 1;
    for (int k = 0; k < 8; k++) { uint32_t w = *(const uint32_t *)(uintptr_t)(lr + 4 * k);
        if ((w & 0xfc000000) == 0x94000000) { int64_t imm = w & 0x3ffffff; if (imm & 0x2000000) imm -= 1 << 26; if (off + 4 * k + imm * 4 == 0x58f310) return 1; } }
    return 0;
}
HLE_FORCE("_ZN2nn4time23StandardUserSystemClock3nowEv", "user clock → host time(); while the boss rush forces a zone, the Terror Zone call sites get a different value", int64_t, h_time_now, void) {
    int64_t tz = atomic_load(&g_dm_tz_time);
    if (tz && (uint64_t)clock_gettime_nsec_np(CLOCK_MONOTONIC) < atomic_load(&g_dm_tz_live_ns) && tz_site((uint64_t)__builtin_return_address(0))) return tz;
    int64_t ft = fixed_time(); return ft >= 0 ? ft : time(NULL); }
HLE_FORCE("_ZN2nn4time23StandardUserSystemClock9to_time_tERKNSt3__16chrono10time_pointINS0_17SystemClockTraitsENS3_8durationIlNS2_5ratioILl1ELl1EEEEEEE",
          "the SDK implementation pairs with now(), taken over with it", int64_t, h_time_to_time_t, const int64_t *tp) { return *tp; }
HLE_FORCE("_ZN2nn4time14ToCalendarTimeEPNS0_12CalendarTimeEPNS0_22CalendarAdditionalInfoERKNS0_9PosixTimeE",
          "time zone rules of the time service; uses the host localtime_r instead", Result, h_time_ToCalendarTime, CalendarTime *ct, CalendarAdditionalInfo *ai, const int64_t *pt) {
    time_t t = *pt; struct tm tm; localtime_r(&t, &tm);
    static int once; if (!once++) LOG("ToCalendarTime: first conversion %lld → %04d-%02d-%02d %02d:%02d (time zone %s, offset %ld s)", (long long)t, tm.tm_year + 1900, tm.tm_mon + 1, tm.tm_mday, tm.tm_hour, tm.tm_min, tm.tm_zone ? tm.tm_zone : "?", (long)tm.tm_gmtoff);
    if (ct) *ct = (CalendarTime){(int16_t)(tm.tm_year + 1900), (int8_t)(tm.tm_mon + 1), (int8_t)tm.tm_mday, (int8_t)tm.tm_hour, (int8_t)tm.tm_min, (int8_t)tm.tm_sec, 0};
    if (ai) { memset(ai, 0, sizeof *ai); ai->wday = tm.tm_wday; ai->yday = tm.tm_yday; strlcpy(ai->tzname, tm.tm_zone ? tm.tm_zone : "UTC", sizeof ai->tzname);
              ai->dst = tm.tm_isdst > 0; ai->offset = (int32_t)tm.tm_gmtoff; }
    return RES_OK;
}
// Explicit time zone rules (Monster Hunter Rise, SDK 11): LoadTimeZoneRule reads the rule from the time service; the host keeps the game's rule buffer untouched and converts with localtime_r as above
HLE_FORCE("_ZN2nn4time16LoadTimeZoneRuleEPNS0_12TimeZoneRuleERKNS0_12LocationNameE", "time zone rule from the time service; the host converts with its own zone, the rule stays unused", Result, h_time_LoadRule,
          void *rule, const char *name) { (void)rule; LOG("time::LoadTimeZoneRule %.36s (host time zone used instead)", name ? name : "?"); return RES_OK; }
HLE_FORCE("_ZN2nn4time14ToCalendarTimeEPNS0_12CalendarTimeEPNS0_22CalendarAdditionalInfoERKNS0_9PosixTimeERKNS0_12TimeZoneRuleE", "conversion with an explicit time zone rule; same as the device zone (host localtime_r)",
          Result, h_time_ToCalendarTimeRule, CalendarTime *ct, CalendarAdditionalInfo *ai, const int64_t *pt, const void *rule) { (void)rule; return h_time_ToCalendarTime(ct, ai, pt); }
HLE_FORCE("_ZN2nn4time26StandardNetworkSystemClock20IsAccuracySufficientEv", "network clock accuracy (time service): offline, never sufficient", unsigned, h_time_NetAccurate, void) { return 0; }
// Clock snapshot (Tears of the Kingdom: CreateWithStandardSystemClock asks the time service, which the host never opens → abort in sm::Initialize). 0xD0 bytes, laid out
// as Ryujinx lays out the service's ClockSnapshot and as this SDK's constructor clears it (its last store is the byte at +0xcd): +0x00 user clock context {offset,
// steady time point}, +0x20 network clock context, +0x40 user time, +0x48 network time, +0x50 / +0x58 user / network calendar, +0x60 / +0x78 their additional info,
// +0x90 steady time point, +0xa8 location name (0x24), +0xcc automatic correction, +0xcd type. Offline, the network fields stay 0, so the SDK's CalculateSpanBetween
// uses the steady time points (same source ID)
HLE_FORCE("_ZN2nn4time13ClockSnapshot29CreateWithStandardSystemClockEPS1_", "snapshot from the time service; the host fills it on the spot (offline: network clock 0)", Result, h_time_Snapshot, uint8_t *s) {
    memset(s, 0, 0xd0);
    uint8_t tp[0x18]; h_time_SteadyNow(tp);
    int64_t now, off; h_time_GetCurrentTime(&now); off = now - *(const int64_t *)tp;
    memcpy(s, &off, 8); memcpy(s + 0x08, tp, 0x18); memcpy(s + 0x40, &now, 8);
    h_time_ToCalendarTime((CalendarTime *)(s + 0x50), (CalendarAdditionalInfo *)(s + 0x60), &now);
    memcpy(s + 0x90, tp, 0x18);
    tzset(); strlcpy((char *)s + 0xa8, tzname[0] && *tzname[0] ? tzname[0] : "UTC", 0x24);
    return RES_OK;
}
// The reverse: local calendar → absolute seconds (13 Sentinels). Around a daylight-saving switch one local time maps to 0 or 2 absolute seconds; the host's mktime gives one
HLE_FORCE("_ZN2nn4time11ToPosixTimeEPiPNS0_9PosixTimeEiRKNS0_12CalendarTimeE",
          "time zone rules of the time service; uses the host mktime instead", Result, h_time_ToPosixTime, int *count, int64_t *out, int n, const CalendarTime *ct) {
    struct tm tm = {.tm_year = ct->year - 1900, .tm_mon = ct->month - 1, .tm_mday = ct->day, .tm_hour = ct->hour, .tm_min = ct->minute, .tm_sec = ct->second, .tm_isdst = -1};
    time_t t = mktime(&tm);
    if (count) *count = n > 0;
    if (n > 0 && out) out[0] = (int64_t)t;
    return RES_OK;
}
// UTC calendar → absolute seconds (Super Mario Odyssey); no time zone involved, the host's timegm
HLE_FORCE("_ZN2nn4time18ToPosixTimeFromUtcERKNS0_12CalendarTimeE", "UTC calendar → absolute seconds; host timegm", int64_t, h_time_ToPosixUtc, const CalendarTime *ct) {
    struct tm tm = {.tm_year = ct->year - 1900, .tm_mon = ct->month - 1, .tm_mday = ct->day, .tm_hour = ct->hour, .tm_min = ct->minute, .tm_sec = ct->second};
    return (int64_t)timegm(&tm);
}
// Local time conversion is forced onto the host libc: the SDK's own localtime / localtime_r / mktime have no time zone data and always use UTC (measured on the host: the chronicle's "First Discovered" is produced by
// main+0xb04d34 calling localtime and then strftime, and was off by 8 hours). The SDK on a real Switch converts by the system time zone, so only following the host system time zone here is consistent;
// the host TZ normally = the system time zone, and is pinned to UTC only for deterministic comparison with DM_FIXED_TIME (main.c). The struct tm layout is the same on both sides (9 ints, long offset, time zone name pointer).
// gmtime / gmtime_r / timegm are UTC anyway and are not taken over. The same-named pass-through entries in hle_table.c only take effect when the symbol has no definition (the SDK defines them), hence HLE_FORCE
HLE_FORCE("localtime", "local time → host localtime (follows the system time zone)", struct tm *, h_localtime, const int64_t *t) { time_t v = (time_t)*t; return localtime(&v); }
HLE_FORCE("localtime_r", "local time → host localtime_r (follows the system time zone)", struct tm *, h_localtime_r, const int64_t *t, struct tm *out) { time_t v = (time_t)*t; return localtime_r(&v, out); }
HLE_FORCE("mktime", "local calendar → absolute seconds, host mktime (follows the system time zone)", int64_t, h_mktime, struct tm *tm) { return (int64_t)mktime(tm); }

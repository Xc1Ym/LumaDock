// Miscellaneous service layer: add-on content / shop / error applet / profanity filter / server name resolution / parental controls / software keyboard.
// On the real device each goes through IPC or a system applet; the host gives results as single-player offline. Pure-computation SDK parts (hash, util, software Opus) are not taken over, the original implementation is used directly.
#include "hle.h"
#include <dirent.h>

// ---------- aoc add-on content (D2R's Reign of the Warlock; other games by the DLC NSPs in the player's folder) / ec shop (excluded) ----------
// Reign of the Warlock is the only add-on content in the Switch package: AOC 0100726014353001 = add-on content index 1 of the base 0100726014352000.
// This DLC is only an unlock ticket of about 100 KB, the content itself is already in the main RomFS; main does not import MountAddOnContent and only judges by "is index 1 present".
// The reimplementation scope requires keeping Reign of the Warlock, so index 1 is reported as owned; what is excluded is the shop (ec), not the DLC itself.
enum { AOC_WARLOCK = 1 };
// Owned add-on content indices (ascending), fixed at the first query:
//   numeric subdirectories of DM_AOC_DIR: each is one DLC's RomFS, which the packing script extracts only from DLC NSPs really in the player's folder (title ID = base + 0x1000 + index).
//     Engage: F001 → 1 (E0), F002 → 2 (H0); the content itself is in the 2.0.0 update's RomFS and each DLC package holds one empty marker file; the game calls MountAddOnContent for each index ListAddOnContent returns (hle_fs.c).
//   No DM_AOC_DIR: D2R (main build db0507f3…) reports {1} (the Warlock expansion, content in the main RomFS, main does not import MountAddOnContent); other builds none --
//     on a Switch 2 Mario 1.2.1 uses it to tell whether the upgrade pack is owned, and the user has no Mario add-on content files.
//   DM_AOC_OWNED=0: always none (test switch, for lockstep comparison against ground truth recorded without the DLC installed); DM_AOC_OWNED=1 without DM_AOC_DIR: reports {1}.
static int g_aoc[64], g_naoc = -1;
static int aoc_int_cmp(const void *a, const void *b) { return *(const int *)a - *(const int *)b; }
static void aoc_load(void) {
    if (g_naoc >= 0) return;
    g_naoc = 0;
    const char *e = getenv("DM_AOC_OWNED"), *dir = getenv("DM_AOC_DIR"); const char *why = "by main build ID";
    if (e && !strcmp(e, "0")) why = "DM_AOC_OWNED=0";
    else if (dir && *dir) {
        why = dir; DIR *d = opendir(dir); struct dirent *ent;
        while (d && (ent = readdir(d)) && g_naoc < (int)(sizeof g_aoc / sizeof *g_aoc)) {
            char *end; long i = strtol(ent->d_name, &end, 10);
            if (ent->d_name[0] >= '1' && ent->d_name[0] <= '9' && !*end && i <= 2000) g_aoc[g_naoc++] = (int)i;
        }
        if (d) closedir(d);
        qsort(g_aoc, g_naoc, sizeof *g_aoc, aoc_int_cmp);
    } else {
        int d2r = 0;
        for (int i = 0; i < g_nmod; i++) if (!strcmp(g_mod[i].name, "main")) d2r = !strcmp(g_mod[i].build_id, "db0507f36b84200ac05f75d76ed5026f");
        if (e) why = "DM_AOC_OWNED";
        if (d2r || e) g_aoc[g_naoc++] = AOC_WARLOCK;
    }
    char list[256] = ""; for (int i = 0; i < g_naoc; i++) snprintf(list + strlen(list), sizeof list - strlen(list), "%s%d", i ? "," : "", g_aoc[i]);
    LOG("aoc: reporting %d add-on contents {%s} (%s)", g_naoc, list, why);
}
HLE_FORCE("_ZN2nn3aoc17CountAddOnContentEv", "add-on content count: length of the owned index list (D2R Reign of the Warlock / DM_AOC_DIR)", int, h_aoc_Count, void) { aoc_load(); return g_naoc; }
// ListAddOnContent(out, start index, max count): writes out from the owned index list starting at the start index, returns the number written
HLE_FORCE("_ZN2nn3aoc16ListAddOnContentEPiii", "add-on content list: the owned index list", int, h_aoc_List, int *out, int off, int n) {
    int w = 0; aoc_load();
    for (int i = off < 0 ? 0 : off; i < g_naoc && w < n; i++) out[w++] = g_aoc[i];
    return w;
}
// The event object is created on demand by the nn::os side table (not signaled), the game waiting on it only times out / gets not-signaled
HLE_FORCE("_ZN2nn3aoc31GetAddOnContentListChangedEventEPNS_2os11SystemEventE", "add-on content change event, out of scope; bound to a kernel event, never signalled (the game polls it with TryWait and aborts if it is uninitialized)", void, h_aoc_GetEv, void *ev) { hle_bind_system_event(ev, 0); }
HLE_FORCE("_ZN2nn2ec24ShowShopAddOnContentListEv", "shop applet, out of scope; cut: no-op", void, h_ec_ShowShop, void) { LOG("ec::ShowShopAddOnContentList (cut)"); }
// The other shop entry points (Engage's title menu item "DLC" calls ShowShopAddOnContentList(ApplicationId, UserHandle)): the original starts the shop applet through applet::CreateLibraryApplet,
// the host has no applet proxy (oe initialization is a no-op), and the SDK reads through the null proxy and crashes (sdk+0x38660). All return void: as if the player closed the shop at once, the game goes back to its menu.
HLE_FORCE("_ZN2nn2ec24ShowShopAddOnContentListENS_13ApplicationIdE", "shop applet, out of scope; cut: no-op", void, h_ec_AocList1, void) { LOG("ec::ShowShopAddOnContentList (cut): the host has no shop"); }
HLE_FORCE("_ZN2nn2ec24ShowShopAddOnContentListENS_13ApplicationIdERKNS_7account10UserHandleE", "shop applet, out of scope; cut: no-op", void, h_ec_AocList2, void) { LOG("ec::ShowShopAddOnContentList (cut): the host has no shop"); }
HLE_FORCE("_ZN2nn2ec30ShowShopApplicationInformationENS_13ApplicationIdE", "shop applet, out of scope; cut: no-op", void, h_ec_AppInfo1, void) { LOG("ec::ShowShopApplicationInformation (cut): the host has no shop"); }
HLE_FORCE("_ZN2nn2ec30ShowShopApplicationInformationENS_13ApplicationIdERKNS_7account10UserHandleE", "shop applet, out of scope; cut: no-op", void, h_ec_AppInfo2, void) { LOG("ec::ShowShopApplicationInformation (cut): the host has no shop"); }
HLE_FORCE("_ZN2nn2ec24ShowShopSubscriptionListENS_13ApplicationIdE", "shop applet, out of scope; cut: no-op", void, h_ec_Sub1, void) { LOG("ec::ShowShopSubscriptionList (cut): the host has no shop"); }
HLE_FORCE("_ZN2nn2ec24ShowShopSubscriptionListENS_13ApplicationIdERKNS_7account10UserHandleE", "shop applet, out of scope; cut: no-op", void, h_ec_Sub2, void) { LOG("ec::ShowShopSubscriptionList (cut): the host has no shop"); }
HLE_FORCE("_ZN2nn2ec24ShowShopSubscriptionListENS_13ApplicationIdERKNS0_8CourseIdE", "shop applet, out of scope; cut: no-op", void, h_ec_Sub3, void) { LOG("ec::ShowShopSubscriptionList (cut): the host has no shop"); }
HLE_FORCE("_ZN2nn2ec24ShowShopSubscriptionListENS_13ApplicationIdERKNS0_8CourseIdERKNS_7account10UserHandleE", "shop applet, out of scope; cut: no-op", void, h_ec_Sub4, void) { LOG("ec::ShowShopSubscriptionList (cut): the host has no shop"); }
HLE_FORCE("_ZN2nn2ec26ShowShopConsumableItemListENS_13ApplicationIdE", "shop applet, out of scope; cut: no-op", void, h_ec_ConsList1, void) { LOG("ec::ShowShopConsumableItemList (cut): the host has no shop"); }
HLE_FORCE("_ZN2nn2ec26ShowShopConsumableItemListENS_13ApplicationIdERKNS_7account10UserHandleE", "shop applet, out of scope; cut: no-op", void, h_ec_ConsList2, void) { LOG("ec::ShowShopConsumableItemList (cut): the host has no shop"); }
HLE_FORCE("_ZN2nn2ec28ShowShopConsumableItemDetailENS_13ApplicationIdERKNS0_12ConsumableIdENS0_5NsUidE", "shop applet, out of scope; cut: no-op", void, h_ec_ConsDet1, void) { LOG("ec::ShowShopConsumableItemDetail (cut): the host has no shop"); }
HLE_FORCE("_ZN2nn2ec28ShowShopConsumableItemDetailENS_13ApplicationIdERKNS0_12ConsumableIdENS0_5NsUidERKNS_7account10UserHandleE", "shop applet, out of scope; cut: no-op", void, h_ec_ConsDet2, void) { LOG("ec::ShowShopConsumableItemDetail (cut): the host has no shop"); }
HLE_FORCE("_ZN2nn2ec22ShowShopEnterCodeSceneEv", "shop applet, out of scope; cut: no-op", void, h_ec_Code1, void) { LOG("ec::ShowShopEnterCodeScene (cut): the host has no shop"); }
HLE_FORCE("_ZN2nn2ec22ShowShopEnterCodeSceneERKNS_7account10UserHandleE", "shop applet, out of scope; cut: no-op", void, h_ec_Code2, void) { LOG("ec::ShowShopEnterCodeScene (cut): the host has no shop"); }
HLE_FORCE("_ZN2nn2ec22ShowShopProductDetailsENS0_5NsUidE", "shop applet, out of scope; cut: no-op", void, h_ec_Prod1, void) { LOG("ec::ShowShopProductDetails (cut): the host has no shop"); }
HLE_FORCE("_ZN2nn2ec22ShowShopProductDetailsENS0_5NsUidERKNS_7account10UserHandleE", "shop applet, out of scope; cut: no-op", void, h_ec_Prod2, void) { LOG("ec::ShowShopProductDetails (cut): the host has no shop"); }
HLE_FORCE("_ZN2nn2ec19ShowShopProductListEPKNS0_5NsUidEiPKc", "shop applet, out of scope; cut: no-op", void, h_ec_ProdList1, void) { LOG("ec::ShowShopProductList (cut): the host has no shop"); }
HLE_FORCE("_ZN2nn2ec19ShowShopProductListEPKNS0_5NsUidEiPKcRKNS_7account10UserHandleE", "shop applet, out of scope; cut: no-op", void, h_ec_ProdList2, void) { LOG("ec::ShowShopProductList (cut): the host has no shop"); }
// The "add-on content lost" error screen is an applet too: logged only
HLE_FORCE("_ZN2nn3aoc25ShowAddOnContentLostErrorEPKii", "add-on content lost error applet; the host only logs it", void, h_aoc_LostErr, const int *idx, int n) { (void)idx; LOG("aoc::ShowAddOnContentLostError (%d entries) (cut)", n); }

// ---------- err error applet: printed by the host ----------
HLE_FORCE("_ZN2nn3err9ShowErrorENS_6ResultE", "error display applet; the host prints the module / description number", void, h_err_ShowError, Result r) {
    LOG("err::ShowError Result=%#x (module %u, description %u)", r, r & 0x1ff, (r >> 9) & 0x1fff);
}

// ---------- ngc profanity filter: the word list is in a system data save (mounted via IPC); single-player has no text visible to others, always judged as no profanity ----------
// The class is polymorphic, and games call it through its vtable too: Monster Hunter Rise checks the hunter's name with slot 8, MaskProfanityWordsInText(int *, char16_t *, uint32_t)
// (main+0x6bca160). The constructor used to do nothing, the object kept what the heap held there, and that call jumped into the heap. It now gets a host vtable: each slot of the SDK's
// (_ZTVN2nn3ngc15ProfanityFilterE) is matched by address with the class's methods and given the host's version (no word list: nothing is profanity, nothing is masked); others return 0
static Result ngc_v_zero(void) { return RES_OK; }
static void ngc_v_none(void *self) { (void)self; }
static Result ngc_v_check(void *self, uint32_t *masks, uint32_t pat, const void **words, uint64_t n) { (void)self; (void)pat; (void)words; for (uint64_t i = 0; masks && i < n; i++) masks[i] = 0; return RES_OK; }
static Result ngc_v_mask(void *self, int *masked, void *text, uint32_t region) { (void)self; (void)text; (void)region; if (masked) *masked = 0; return RES_OK; }
static void *ngc_vtable(void) {
    enum { NV = 40 }; static void *vt[NV + 2]; static int built;
    if (built) return built > 0 ? &vt[2] : NULL;
    void **sdk = guest_sym("_ZTVN2nn3ngc15ProfanityFilterE");
    if (!sdk) { built = -1; LOG("[RED] ProfanityFilter: the SDK has no vtable symbol; objects keep none"); return NULL; }
    static const struct { const char *name; void *fn; } M[] = {
        {"_ZN2nn3ngc15ProfanityFilterD1Ev", (void *)ngc_v_none}, {"_ZN2nn3ngc15ProfanityFilterD0Ev", (void *)ngc_v_none}, {"_ZN2nn3ngc15ProfanityFilter8FinalizeEv", (void *)ngc_v_none},
        {"_ZN2nn3ngc15ProfanityFilter19CheckProfanityWordsEPjjPPKcm", (void *)ngc_v_check}, {"_ZN2nn3ngc15ProfanityFilter19CheckProfanityWordsEPjjPPKDsm", (void *)ngc_v_check},
        {"_ZN2nn3ngc15ProfanityFilter19CheckProfanityWordsEPjjPPKtm", (void *)ngc_v_check},
        {"_ZN2nn3ngc15ProfanityFilter24MaskProfanityWordsInTextEPiPcj", (void *)ngc_v_mask}, {"_ZN2nn3ngc15ProfanityFilter24MaskProfanityWordsInTextEPiPDsj", (void *)ngc_v_mask},
        {"_ZN2nn3ngc15ProfanityFilter24MaskProfanityWordsInTextEPiPtj", (void *)ngc_v_mask},
    };
    void *addr[sizeof M / sizeof *M]; for (unsigned k = 0; k < sizeof M / sizeof *M; k++) addr[k] = guest_sym(M[k].name);
    module_t *mod = module_of(sdk); int n = 0, named = 0;
    vt[0] = sdk[0]; vt[1] = sdk[1];   // offset to top, type info
    // A slot holds SDK code, or the host's version where the loader bound the slot by name to a forced take-over (Initialize, GetContentVersion, CheckProfanityWords): those stay.
    // The table ends at the first value that is neither (Monster Hunter Rise's SDK: 9 slots, then a 1)
    for (; n < NV && (uintptr_t)sdk[2 + n] >= 0x10000; n++) {
        if (module_of(sdk[2 + n]) != mod) { if (module_of(sdk[2 + n])) break; vt[2 + n] = sdk[2 + n]; continue; }   // another guest module: not this class's table
        vt[2 + n] = (void *)ngc_v_zero;
        for (unsigned k = 0; k < sizeof M / sizeof *M; k++) if (addr[k] && sdk[2 + n] == addr[k]) { vt[2 + n] = M[k].fn; named++; break; }
    }
    built = 1; LOG("ngc: ProfanityFilter host vtable of %d slots (%d matched to the class's methods)", n, named);
    return &vt[2];
}
HLE_FORCE("_ZN2nn3ngc15ProfanityFilterC1Ev", "profanity filter, the word list is in a system save; the host builds none and gives the object a host vtable", void, h_ngc_Ctor, void *self) {
    void *vt = ngc_vtable(); if (vt && self) memcpy(self, &vt, sizeof vt);
}
HLE_FORCE("_ZN2nn3ngc15ProfanityFilterD1Ev", "profanity filter", void, h_ngc_Dtor, void *self) { (void)self; }
HLE_FORCE("_ZN2nn3ngc15ProfanityFilter10InitializeEPvm", "profanity filter init; the host has no word list", Result, h_ngc_Init, void *self, void *work, uint64_t sz) { (void)self; (void)work; (void)sz; return RES_OK; }
HLE_FORCE("_ZN2nn3ngc15ProfanityFilter17GetContentVersionEv", "word list version; the host returns 0", uint32_t, h_ngc_Ver, void *self) { (void)self; return 0; }
HLE_FORCE("_ZN2nn3ngc15ProfanityFilter19CheckProfanityWordsEPjjPPKcm", "profanity check; never a hit", Result, h_ngc_Check, void *self, uint32_t *masks, uint32_t pat, const char **words, uint64_t n) {
    (void)self; (void)pat; (void)words;
    for (uint64_t i = 0; i < n; i++) masks[i] = 0;
    return RES_OK;
}

// ---------- nsd server name resolution / pctl free communication: networking, out of scope ----------
HLE_FORCE("_ZN2nn3nsd7ResolveEPNS0_4FqdnERKS1_", "server name resolution, networking out of scope; cut", Result, h_nsd_Resolve, void *out, const void *in) { (void)out; (void)in; return RES_FAIL; }
HLE_FORCE("_ZN2nn3nsd9ResolveExEPNS0_4FqdnERKS1_", "server name resolution, networking out of scope; cut", Result, h_nsd_ResolveEx, void *out, const void *in) { (void)out; (void)in; return RES_FAIL; }
// bool arguments only look at the low 8 bits; returns bool
HLE_FORCE("_ZN2nn4pctl25TryBeginFreeCommunicationEb", "parental controls · communication with others, networking out of scope; never allowed", unsigned, h_pctl_TryBegin, unsigned show_ui) { (void)show_ui; return 0; }
// Parental control of the 3D (VR goggles) mode, Super Mario Odyssey: no restriction, nothing to configure
HLE_FORCE("_ZN2nn4pctl26GetStereoVisionRestrictionEv", "parental controls · 3D view restriction; never restricted", unsigned, h_pctl_GetStereo, void) { return 0; }
HLE_FORCE("_ZN2nn4pctl26SetStereoVisionRestrictionEb", "parental controls · 3D view restriction; the host does not store it", void, h_pctl_SetStereo, unsigned on) { (void)on; }
HLE_FORCE("_ZN2nn4pctl42ConfirmStereoVisionRestrictionConfigurableEv", "parental controls · whether the 3D view restriction can be changed; yes", Result, h_pctl_ConfStereo, void) { return RES_OK; }
HLE_FORCE("_ZN2nn4pctl53RequestStereoVisionRestrictionConfigurationPermissionEv", "parental controls · permission to change the 3D restriction; granted at once", Result, h_pctl_ReqStereo, void) { return RES_OK; }
HLE_FORCE("_ZN2nn4pctl20EndFreeCommunicationEv", "parental controls · communication with others", void, h_pctl_End, void) {}
// Engage asks on entering a battle map (no UI); without this the SDK connects to the pctl service through sm, which the host does not have, and aborts
HLE_FORCE("_ZN2nn4pctl28IsFreeCommunicationAvailableEv", "parental controls · whether communication with others is available, networking out of scope; never", unsigned, h_pctl_IsFree, void) { return 0; }
// The Legend of Zelda: Breath of the Wild: checks the parental-control permission for stereoscopic 3D before VR-related screens (returns bool; the argument = whether to show UI, the game passes 0). The host has no parental controls: permitted
HLE_FORCE("_ZN2nn4pctl27CheckStereoVisionPermissionEb", "parental controls · stereoscopic 3D permission; the host has no parental controls, allowed", unsigned, h_pctl_Stereo, unsigned show_ui) { (void)show_ui; return 1; }

// swkbd software keyboard: see hle_swkbd.c

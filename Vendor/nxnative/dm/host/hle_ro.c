// nn::ro (loading NRO modules at run time): on the real device it connects to the ldr:ro service. The host has no such service; running the SDK's Initialize as is reads a null session in InitializeWithPortName and crashes (Engage).
// Engage (Unity) imports 8 ro interfaces but its RomFS has no .nro / .nrr: at startup it only calls Initialize, and symbol lookups go through LookupSymbol.
// Takeover: Initialize is a no-op; LookupSymbol finds the definition by name in the loaded modules (main / subsdk* / sdk); loading / unloading / registering modules always fails and reports red once (there is nothing to load).
// Only success matters: the game checks IsSuccess only, so the failure code is a non-zero value under the ro module number 22.
#include "hle.h"

#define RO_FAIL ((Result)(22 | (1 << 9)))   // a failure under ro module 22

HLE_FORCE("_ZN2nn2ro10InitializeEv", "connect to the ldr:ro service; the host has none, symbol lookups search the loaded modules directly", Result, h_ro_Initialize, void) { LOG("init takeover: ro::Initialize (no-op)"); return 0; }

HLE_FORCE("_ZN2nn2ro12LookupSymbolEPmPKc", "look up a definition by name in the loaded modules", Result, h_ro_LookupSymbol, uintptr_t *out, const char *name) {
    void *p = name ? guest_sym(name) : NULL;
    static int n; if (n++ < 40) LOG("ro::LookupSymbol %s → %p", name ? name : "(null)", p);
    if (!p) { static int red; if (!red++) LOG("[RED] ro::LookupSymbol cannot find %s (first case)", name ? name : "(null)"); return RO_FAIL; }
    if (out) *out = (uintptr_t)p;
    return 0;
}

HLE_FORCE("_ZN2nn2ro18LookupModuleSymbolEPmPKNS0_6ModuleEPKc", "no NRO loaded: every per-module lookup finds nothing", Result, h_ro_LookupModuleSymbol, uintptr_t *out, const void *m, const char *name) {
    (void)out; (void)m; static int red; if (!red++) LOG("[RED] ro::LookupModuleSymbol %s: no NRO loaded", name ? name : "(null)"); return RO_FAIL;
}

HLE_FORCE("_ZN2nn2ro13GetBufferSizeEPmPKv", "NROs are not loaded", Result, h_ro_GetBufferSize, size_t *out, const void *image) {
    (void)image; if (out) *out = 0; static int red; if (!red++) LOG("[RED] ro::GetBufferSize: the host does not load NROs"); return RO_FAIL;
}

HLE_FORCE("_ZN2nn2ro10LoadModuleEPNS0_6ModuleEPKvPvmi", "NROs are not loaded", Result, h_ro_LoadModule, void *m, const void *image, void *buf, size_t size, int flag) {
    (void)m; (void)image; (void)buf; (void)flag; static int red; if (!red++) LOG("[RED] ro::LoadModule: the host does not load NROs (buffer %#zx)", size); return RO_FAIL;
}

HLE_FORCE("_ZN2nn2ro12UnloadModuleEPNS0_6ModuleE", "NROs are not loaded", void, h_ro_UnloadModule, void *m) { (void)m; }

HLE_FORCE("_ZN2nn2ro18RegisterModuleInfoEPNS0_16RegistrationInfoEPKv", "NRRs are not registered", Result, h_ro_RegisterModuleInfo, void *info, const void *nrr) {
    (void)info; (void)nrr; static int red; if (!red++) LOG("[RED] ro::RegisterModuleInfo: the host does not register NRRs"); return RO_FAIL;
}

HLE_FORCE("_ZN2nn2ro20UnregisterModuleInfoEPNS0_16RegistrationInfoE", "NRRs are not registered", void, h_ro_UnregisterModuleInfo, void *info) { (void)info; }

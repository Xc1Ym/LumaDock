# Getting started with LumaDock

LumaDock runs on Apple Silicon Macs with macOS 26 or later. Preparing games requires the full Xcode app and Apple's Metal compiler component. Other build dependencies are bundled.

See the [complete environment and repair guide](Environment.md) for every dependency, installation method, and live verification. Python is bundled; a separate system Python installation is not required.

1. Open the DMG and drag **LumaDock.app** into **Applications**. The current community build uses ad-hoc signing and is not notarized. Verify the release source and `SHA256SUMS` before opening it through the procedure offered in macOS Privacy & Security.
2. Open LumaDock. The setup assistant checks hardware, macOS, Xcode, Metal, bundled tools, and free space. **Get Xcode on the App Store** opens Apple's listing. Open Xcode once to accept its license and complete initial setup. Return to LumaDock, choose the correct Developer directory if necessary, and check again. Install Metal through the app if it is missing.
3. Choose an empty folder for your managed library. External drives are supported; keep the drive connected during preparation and play. Large games can require tens of gigabytes for source copies and build caches.
4. Import your own **prod.keys**. Keys are stored privately on this Mac and excluded from diagnostics. Format is checked locally; decryption is verified while reading a game.
5. Add authorized **NSP** base, update, and DLC files, or scan their folder. The app matches content metadata rather than filenames and copies files into your library. Missing versions appear in game details.
6. Supported games with all required files are prepared automatically by default. Watch **Tasks** for progress. You can cancel and retry; completed stages are reused only after validation. Preparation and game execution run separately and cannot run simultaneously.
7. Choose **Launch game** after preparation completes. A failed preparation preserves the previous successful runtime. An engine update requires preparing the game again before using the new engine.

In **Settings → Language & appearance**, choose **System default**, **English**, or **简体中文**, and independently select **System default**, **Light**, or **Dark** appearance. Changes apply immediately and are saved. System file-dialog buttons follow the macOS language; raw compiler logs retain their tool language.

Use the toolbar's input mapping button to configure global controls, or game details for a game-specific override. Mapping changes apply on the next launch without rebuilding. Settings also provides diagnostics export and a setup-assistant shortcut.

Removing a game from the library retains files and saves. Managed-copy deletion and cache cleanup are separate actions; neither removes original player files or saves. Back up saves separately before updates or experiments. Uninstalling the Metal compiler removes an Apple-managed shared component and prevents further game preparation until reinstalled.

LumaDock includes no games, updates, DLC, firmware, keys, game artwork, or player caches. Import only content you are authorized to use. Native preparation is not a guarantee of full compatibility. Crashes, graphics problems, stutters, and save loss remain possible.

For tested games, upstream acknowledgements, licenses, limitations, and issue reporting, see the [project README](https://github.com/Xc1Ym/LumaDock#readme) and the included third-party notices. Never upload games, keys, firmware, saves, or private caches with a bug report; review exported diagnostics for private paths before sharing.

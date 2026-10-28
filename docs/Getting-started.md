# Getting started with LumaNX

LumaNX runs on Apple Silicon Macs with macOS 26 or later. Preparing games requires the full Xcode app and Apple's Metal compiler component. nxnative, its reader and translator, and runtime dependencies are bundled.

See the [complete environment and repair guide](Environment.md) for every dependency, installation method, and live verification. Python is bundled; a separate system Python installation is not required.

1. Open the DMG and drag **LumaNX.app** into **Applications**. The current community build uses ad-hoc signing and is not notarized. Verify the release source and `SHA256SUMS` before opening it through the procedure offered in macOS Privacy & Security.
2. Open LumaNX. The setup assistant checks hardware, macOS, Xcode, Metal, bundled tools, and free space. **Get Xcode on the App Store** opens Apple's listing. Open Xcode once to accept its license and complete initial setup. Return to LumaNX, choose the correct Developer directory if necessary, and check again. Install Metal through the app if it is missing.
3. Wait for the included source snapshot and compiled reader to initialize automatically in the private cache. Use **More tools → Repair bundled engine** if initialization fails. Packaged apps need no separate nxnative download, .NET SDK or NuGet restore. Check again after preparation.
4. Choose an empty folder for your managed library. External drives are supported; keep the drive connected during preparation and play. Large games can require tens of gigabytes for source copies and build caches.
5. Import your own **prod.keys**. Keys are stored privately on this Mac and excluded from diagnostics. Format is checked locally; decryption is verified while reading a game.
6. Add authorized **NSP, XCI, NSZ or XCZ** base, update, and DLC files, or scan their folder. NSP and XCI are read directly by nxnative. NSZ/XCZ inputs are automatically decompressed to temporary NSP/XCI files with your library key, then imported without opening File conversion. The app matches content metadata rather than filenames and copies files into your library. Missing versions appear in game details.
7. Supported games with all required files are prepared automatically by default. Watch **Tasks** for progress. You can cancel and retry; completed stages are reused only after validation. Preparation and game execution run separately and cannot run simultaneously.
8. Choose **Launch game** after preparation completes. A failed preparation preserves the previous successful runtime. An engine update requires preparing the game again before using the new engine.

Merged NSP/XCI containers register every base, update and DLC using its own content metadata; one managed copy serves all of them. After upgrading from a reader that registered only one package, use **Settings → More tools → Repair bundled engine**. The library then rescans existing managed containers without another import. With a recent nxnative checkout that provides derived profiles, LumaNX chooses the newest imported version and generates its own profile and shader tables in the private build cache when registered versions or their shader inputs do not match. Game details label this experimental path; successful preparation does not establish gameplay compatibility. Older engines retain their explicit version requirements. Missing profile inputs are independent of DLC or base-game completeness.

You can leave setup at any step, including while checks are running or a component is missing. Choose **Set up later** or press **Esc** to return to the library; choose **Quit LumaNX** or press **⌘Q** to quit normally. Resume from **Continue setup** in the library or reopen the assistant in Settings. Deferring setup does not mark it complete: unfinished setup returns on the next launch, and required checks still gate importing and preparing games.

In **Settings → Language & appearance**, choose **System default**, **English**, or **简体中文**, and independently select **System default**, **Light**, or **Dark** appearance. Changes apply immediately and are saved. System file-dialog buttons follow the macOS language; raw compiler logs retain their tool language.

Use Settings to configure global controls, or game details for a game-specific override. Mapping changes apply on the next launch without rebuilding. Settings also provides diagnostics export and a setup-assistant shortcut.

Game preparation and IPA export show milestone segments, the current step and its purpose, elapsed time, estimated time remaining and estimated finish. Hover over a segment for details. Initial times are reference estimates; successful uncached runs build local history, scoped to the game, target and toolchain. Cache hits and cancelled/failed runs do not train those estimates. Lighter fill is time-based estimation; numeric percentages still require measured counters. Estimates are approximate and are not completion deadlines.

## File conversion

Open **File conversion** in the sidebar. You can convert NSP/XCI (including NSZ/XCZ inputs), compress NSP/XCI, decompress NSZ/XCZ, or merge files for one game into NSP/XCI. Choose files or drop them onto the page, select the operation and output folder, then start. Conversion does not require Xcode, nxnative or a configured game library.

The conversion tools, Python and dependencies are bundled with LumaNX. No separate SAK-Mac installation or first-run download is needed. Conversion commands and progress parsing adapt [SAK-Mac](https://github.com/ggaoph-lab/SAK-Mac) at `c8e0baa59a168d9efaa0b556af70e0a08bda51de`; sources and notices are documented in [third-party licenses](Third-party-licenses.md).

Existing library keys can be reused. **Import conversion keys…** stores a separate private copy of your own `prod.keys`; it does not replace library keys. Status shows which keys are in use.

Tasks support progress, logs, cancellation and retry. Inputs are cloned/copied and verified before processing in a private temporary workspace. A failed or cancelled conversion leaves original files and earlier output intact. Successful outputs pass container-structure and copy-hash checks, then appear in a new folder under your chosen output directory. These checks do not validate game signatures or gameplay. Use **View conversion results** or **Import generated NSP files** from the task. Library import still performs its own metadata and setup checks.

## Export an IPA

Choose **Generate IPA…** in game details and save outside the managed library. This builds an **unsigned iPhone / iPad game package** from the imported NSPs; a Mac runtime is not required first. Install the iOS platform and Metal compiler in your selected Xcode, and install XcodeGen with `brew install xcodegen` before exporting.

Wait for any running game and the preparation queue to finish. The export appears in Tasks with progress, cancellation and retry; completed exports open in Finder. A failed or cancelled export preserves the previous IPA, Mac runtime and saves. Sign the result with your installation tool before installing it. iOS device and game compatibility depend on your selected engine; Mac gameplay results do not validate iOS gameplay.

## Build errors and shader warnings

Long operations share progress bars in Tasks, the global task banner, setup and Settings. Imports, byte/copy/cache verification, engine preparation, game/shader builds, IPA export, environment/component operations, cleanup and diagnostics report real counters where available. Unknown or estimated totals use an indeterminate linear bar with elapsed time; ordinary log/warning messages preserve progress. You can open **View all tasks** while using another page.

An error prompt includes a suggested repair and error code. Choose **View failed task** for the failed stage, redacted compiler output, **Open task log** and **Copy error summary**. The log action selects this task's specific file, including shader logs inside the build cache. Original logs remain local; review them before sharing.

Missing Metal/SDK components, shader conversion/compilation errors, chain mismatches, disk/permission failures and possible memory exhaustion have separate messages. No usable shaders stops the build. A partial shader failure marks the task **Completed with warnings**; cache reuse preserves the warning. Fix the cause and retry instead of assuming every scene will render correctly.

## Game language

Expand **Manage game** in game details and choose **Launch language** on its single row. A brief toast confirms that the choice applies on the next launch. **Use default** follows **Settings → Game language → Default game language**, initially Simplified Chinese. A game-specific choice overrides the default and is remembered after restarting LumaNX. This setting is independent of the launcher interface language.

Quit and relaunch the game to apply a change; no rebuild or firmware import is needed. LumaNX passes the selected Switch language code to nxnative through `DM_LANG`. A language choice does not add translations to a game: the imported version and engine must support it, and some games use their own saved language settings. If a prepared game ignores a supported choice, include the game version, language choice and sanitized runtime log with your report.

Removing a game from the library retains files and saves. Managed-copy deletion and cache cleanup are separate actions; neither removes original player files or saves. Containers shared by multiple games are deleted only after the last game reference is removed, including references held by hidden games. Uninstalling the Metal compiler removes an Apple-managed shared component and prevents further game preparation until reinstalled.

Open **Save backups and version rollback…** in game details to create a manual backup, restore a listed backup, or select a previously prepared runtime version. These actions require gameplay and preparation tasks (including queued tasks) to end first. Backups preserve empty folders and verify file sizes and SHA-256 hashes; symbolic links and special files are rejected. Restoration verifies the backup, backs up current saves, then atomically replaces the save directory. Failures or cancellation before the switch leave current saves intact. A disk that does not support atomic directory exchange refuses the replacement and keeps the current saves and safety backup.

Replacing an existing runtime after preparation, or selecting a historical runtime, automatically backs up existing saves before switching. A backup failure stops the switch. Switching runtime versions does not restore older saves automatically, and an older game version may not understand newer saves. Game details show the version that will actually launch. Backups live in `<library>/backups/<Title ID>` and survive source/cache cleanup. They share the library disk, so copy the complete `backups` folder to another disk for an independent backup. The current restore interface reads managed backups in the selected library only.

LumaNX includes no games, updates, DLC, firmware, keys, game artwork, or player caches. Import only content you are authorized to use. Native preparation is not a guarantee of full compatibility. Crashes, graphics problems, stutters, and save loss remain possible.

For upstream acknowledgements, licenses and issue reporting, see the [project README](https://github.com/Xc1Ym/LumaNX#readme) and the included third-party notices. Historical test scope is recorded in the [validation record](验收记录.md) (Chinese), without guaranteeing compatibility with another engine or device. Never upload games, keys, firmware, saves, or private caches with a bug report; review exported diagnostics for private paths before sharing.

## Game management and shortcuts

Game details keeps the launch action prominent. Expand **Manage game** for language, mapping, save backups, runtime rollback, preparation, IPA export and cleanup. Technical details and imported content are in **Game details**. Use ⌘Q to quit completely, ⌘, for Settings, ⌘O to add games, ⇧⌘K to import keys, ⌘R to refresh, and ⌘1/2/3 to switch pages.

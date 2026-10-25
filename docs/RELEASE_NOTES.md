# LumaDock 0.2.10

## Changes

- **Read every package in merged NSP/XCI files.** Register the base game, embedded updates and DLC from their own content metadata, while keeping one managed copy of the physical container. Reimport repairs older single-package records; after preparing the updated engine reader, existing managed containers are rescanned automatically. Extraction selects the requested title and version instead of choosing an arbitrary NCA of the same type.
- **Prepare the imported version with recent nxnative engines.** When the selected engine provides the derived-profile API, use the newest imported game version and generate a private profile and shader tables when registered builds or their shader inputs do not match. Registered builds retain their applicable fixes. Derived builds use their own shader inputs, C1/CB tables, cache identity and experimental status. Older engines retain explicit version requirements; games with no matching profile remain unsupported.
- **Preserve successful work on failure.** Validate shader input stamps and iOS shader platforms before checkpointing. Cancellation, shader failures and failed installation preserve the previous runtime and saves; retry verifies reusable extraction, rewrite and shader-split stages.
- **Unify the task banner.** Place the global task banner within the content area's background and use the same native Liquid Glass surface as the other controls. Remove its extra button background and the toolbar keyboard button; input mapping remains available in Settings and game details.
- **Protect running applications during packaging.** Refuse to replace an output app while its executable or runtime children are running. Build and validate a complete signed app in a staging directory; restore the previous app if publication or relocated-runtime validation fails. `--output-dir` supports independent local builds. Verify the bundled Python can launch the bundled `spirv-cross` with a GUI-style PATH, both before and after relocation. Missing `spirv-cross` now reports `shader_tool_missing` rather than game shader incompatibility.

## Installation and validation

The release workflow builds **LumaDock-0.2.10-arm64.dmg** and its source archive. Verify `SHA256SUMS`, quit any running LumaDock copy and its tasks, then replace the app in Applications. Requires Apple Silicon and macOS 26+. This release still uses **ad-hoc signing and is not notarized**; a valid local code signature does not guarantee Gatekeeper approval. A Developer ID Application certificate and Apple notarization are required for normal identified-developer distribution.

After upgrading, prepare the engine tools again in Settings to update the container reader. Existing managed game files can then be rescanned without another import. A shader task interrupted by an app replacement can be retried after reopening the complete app; keep the sources, keys and successful caches.

Local verification passed **156 Python tests and 61 Swift Release tests**, plus the later appearance/progress regression subset after the toolbar adjustment. Synthetic pipelines cover derived Mac/iOS preparation, cache reuse, cancellation, failures, wrong shader stamps and wrong iOS shader platforms. The actual nxnative derivation API was checked with synthetic input. Read-only inspection of a player's merged XCI identified both its base and embedded update, and the version planner selected the update without requiring another registered version. The native metadata reader compiled against LibHac 0.19. Signed local apps passed runtime, nested `spirv-cross` execution and distribution-boundary checks; a separate synthetic window was visually checked in light, dark and high-contrast appearances.

**Validation limits:** these checks do not establish successful full compilation or gameplay of the player's 1.0.1 game, iOS device compatibility, or Gatekeeper/notarization acceptance. Tag CI rebuilds and validates public artifacts before publishing them; its completion is not claimed by these local results.

No engine, games, updates, DLC, firmware, player keys, artwork, saves or player caches are included. Third-party notices remain in the bundled documentation.

---

## 中文说明

- **完整识别合并容器。** 按各自内容元数据登记 NSP/XCI 中的本体、内置更新及 DLC，共用一份托管副本。重新导入可修复旧记录；准备新版读取器后，自动重扫已有托管文件。解包器明确选择标题与版本，避免取错同类型 NCA。
- **接入 nxnative 动态派生。** 所选引擎提供相应接口时，选择已导入的最新游戏版本；登记版本或着色器素材不匹配时，在私有缓存生成独立配置和着色器表。登记版本保留对应修复；派生版本使用自己的着色器、C1/CB 表与缓存，并标为实验性。旧引擎继续校验指定版本，没有对应游戏配置时仍不能构建。
- **保留成功阶段。** 着色器输入标记与 iOS 编译平台验证通过后才写检查点。取消、着色器失败和安装失败保留上次成功运行版本与存档；重试会验证并复用解包、代码重写和着色器提取等已完成阶段。
- **统一界面材质。** 底部任务栏移入内容区，共用背景和系统 Liquid Glass 材质；去掉按钮额外底色及右上角键盘按钮。设置和游戏详情保留输入映射入口。
- **避免打包打断任务。** 目标应用或其运行时子进程仍运行时拒绝覆盖。完整包先在暂存目录签名、验证，再发布；发布或搬移后验证失败会恢复旧包。新增 `--output-dir` 独立输出目录；搬移前后验证内置 Python 在 GUI PATH 下能启动内置 `spirv-cross`。缺少工具时报告 `shader_tool_missing`，不再误报游戏着色器不兼容。

工作流生成 **LumaDock-0.2.10-arm64.dmg** 和源码包。核对 `SHA256SUMS`，退出运行中的应用和任务后再替换“应用程序”中的副本。需要 Apple Silicon、macOS 26 及以上。此版仍为 **临时签名、未公证**；本地签名校验通过不代表通过 Gatekeeper。正常的已识别开发者分发仍需 Developer ID Application 证书和 Apple 公证。

升级后在设置中重新准备引擎工具，即可更新读取器并重扫已有托管文件，无需重新导入。若着色器任务曾因应用被替换而中断，重新打开完整应用后重试即可；保留源文件、密钥及成功缓存。

本地通过 **156 项 Python、61 项 Swift Release 测试**，工具栏调整后另通过相关外观与进度回归。合成流程覆盖 Mac/iOS 派生配置、缓存、取消、失败、错误输入标记及 iOS 平台校验；使用合成数据核对真实 nxnative 派生接口。对玩家合并 XCI 的只读检查识别出本体与内置更新，版本规划无需另一登记版本。元数据读取器通过 LibHac 0.19 编译；本地包通过签名、内置 Python/spirv-cross 子进程及分发边界检查；独立合成窗口检查了浅色、深色和高对比外观。

**验证范围：** 未完成玩家 1.0.1 游戏的整套真实编译或游玩验收，未验证 iOS 真机，也未通过 Apple 公证验收。标签 CI 会重建并验证公开附件；本地结果不代表标签 CI 已完成。

不附带引擎、游戏、更新、DLC、固件、玩家密钥、封面、存档或玩家缓存，第三方许可保留在随包文档中。

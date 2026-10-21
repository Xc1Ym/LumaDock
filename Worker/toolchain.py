"""Read-only capability probes and Apple-managed component installation.

Probes use scratch files, never player content, and never install or accept a license.
Bundled tools are addressed by absolute path; a broken bundle cannot borrow Homebrew.
"""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
from core import Failure, read

REPAIR_BUNDLE = '这些组件随完整应用提供，无需另装 Python、Homebrew 或 .NET。请从官方 Release 重新下载 DMG，将完整应用复制到“应用程序”后重新检查；不要只复制可执行文件。'
REPAIR_XCODE = '从 App Store 安装完整 Xcode，打开一次并完成许可及初始组件安装。选择实际 Xcode.app；仅安装 Command Line Tools 不够。'
REPAIR_XCODE_INITIAL = '打开所选 Xcode，完成许可及必需系统组件设置。若已完成，可先退出并重新打开璃游，或点击“重新检查”。仍未通过时查看下方诊断；确需手动初始化时，先阅读并同意 Xcode 许可再执行修复命令，它会安装系统组件并接受许可。'
PROBE_TIMEOUT = '工具检查超时，请重新检查或修复对应组件。'


def probe(c, args, *, timeout=20, cwd=None):
    """Return a bounded diagnostic; kill the whole probe group on timeout."""
    c.check()
    try:
        p = subprocess.Popen([str(a) for a in args], env=c.env(), cwd=cwd,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, errors='replace', start_new_session=True)
    except OSError as error:
        return False, str(error)
    c.children.add(p)
    try:
        try:
            output, _ = p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try: os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            p.communicate()
            return False, PROBE_TIMEOUT
        c.check()
        output = output.strip()[-4000:]
        if p.returncode != 0:
            output = f'Exit status: {p.returncode}\n'+(output or 'No diagnostic output.')
        return p.returncode == 0, output
    finally:
        c.children.discard(p)


def metal_available():
    try:
        metal = ctypes.CDLL('/System/Library/Frameworks/Metal.framework/Metal')
        metal.MTLCreateSystemDefaultDevice.restype = ctypes.c_void_p
        return bool(metal.MTLCreateSystemDefaultDevice())
    except (OSError, AttributeError):
        return False


def inspect_environment(c):
    checks = []
    both = ['prepare', 'launch']

    def add(name, ok, message, help, action, group, scopes=None, detail='', location=None, repairCommand=None):
        item = dict(name=name, ok=bool(ok), message=message, help=help, action=action,
                    group=group, requiredFor=scopes or ['prepare'])
        if detail and not ok:
            item['detail'] = detail
        if location:
            item['location'] = str(location)
        if repairCommand:
            item['repairCommand'] = repairCommand
        checks.append(item)
        c.emit('check', check=item, done=len(checks), total=18)

    add('Apple Silicon', platform.machine() == 'arm64', platform.machine(),
        '需要 Apple Silicon Mac，Intel Mac 或 Rosetta 下运行不受支持。', '', 'system', both)
    version = platform.mac_ver()[0]
    add('macOS 26+', bool(version) and version.split('.')[0].isdigit() and int(version.split('.')[0]) >= 26, version or '缺失',
        '在“系统设置 → 通用 → 软件更新”升级至 macOS 26 或更新版本。', 'systemUpdate', 'system', both)
    add('Metal 图形设备', metal_available(), '检查系统是否能创建 Metal 设备',
        '请在 Apple Silicon Mac 的本机桌面会话中运行；系统图形驱动随 macOS 更新提供。', 'systemUpdate', 'system', both)

    repair = REPAIR_BUNDLE
    runtime = c.runtime
    versions = {}
    try:
        versions = read(runtime/'versions.json')
        manifest_ok = isinstance(versions, dict) and all(isinstance(versions.get(k),str) and versions[k] for k in ('python','capstone','lz4','fonttools','dotnet','spirvCross','zstd'))
    except (OSError, ValueError):
        manifest_ok = False
    add('内置组件清单', manifest_ok, '验证随应用提供的组件版本清单', repair, 'reinstall', 'bundled', location=runtime/'versions.json')
    versions = versions if isinstance(versions, dict) else {}
    py = runtime/'python/bin/python3'
    ok, output = probe(c, [py, '-B', '-I', '-c',
        'import sys,platform,json,ctypes,hashlib,zlib,bz2,lzma; print(json.dumps(dict(version=platform.python_version(),arch=platform.machine(),prefix=sys.base_prefix)))'])
    try:
        data = json.loads(output) if ok else {}
        ok = ok and data['version'] == versions.get('python') and data['arch'] == 'arm64' and Path(data['prefix']).resolve().is_relative_to((runtime/'python').resolve())
    except (ValueError, KeyError, TypeError):
        ok = False
        data = {}
    add('内置 Python', ok, f'Python {data.get("version", "")} · 应用内置' if ok else '内置 Python 无法运行或版本不匹配', repair, 'reinstall', 'bundled', both, output, py)
    python_ok = ok
    ok, output = probe(c, [py, '-B', '-I', '-c',
        'import capstone,lz4.block,fontTools,json,importlib.metadata as m; '
        'from fontTools.ttLib import TTFont; '
        'assert next(capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_ARM).disasm(bytes.fromhex("1f2003d5"),0)).mnemonic=="nop"; '
        'assert lz4.block.decompress(lz4.block.compress(b"LumaDock"))==b"LumaDock"; TTFont(); '
        'print(json.dumps({n:m.version(n) for n in ("capstone","lz4","fonttools")}))']) if python_ok else (False, '')
    try:
        actual = json.loads(output) if ok else {}
        ok = ok and all(actual.get(k) == versions.get(k) for k in ('capstone','lz4','fonttools'))
    except (ValueError, AttributeError, TypeError):
        ok = False
    add('Python 扩展', ok, 'capstone / lz4 / fontTools：加载、版本及基本功能检查', repair, 'reinstall', 'bundled', detail=output, location=runtime/'python')
    dotnet = runtime/'bin/dotnet'
    ok, output = probe(c, [dotnet, '--list-runtimes'])
    ok = ok and isinstance(versions.get('dotnet'),str) and versions['dotnet'].startswith('10.') and any(
        line.startswith('Microsoft.NETCore.App '+versions['dotnet']+' ') and str((runtime/'dotnet/shared/Microsoft.NETCore.App').resolve()) in line for line in output.splitlines())
    add('.NET 10 运行时', ok, f'Microsoft.NETCore.App {versions["dotnet"]} · 应用内置' if ok else '内置 .NET 10 运行时不可用', repair, 'reinstall', 'bundled', detail=output, location=runtime/'dotnet')
    nx = runtime/'nx_extract/nx_extract'
    ok, output = probe(c, [nx])
    # nx_extract intentionally exits 2 for its argument-free usage check.
    nx_ok = 'usage: nx_extract <prod.keys>' in output and (nx.parent/'nx_extract.dll').is_file() and (nx.parent/'LibHac.dll').is_file()
    add('NSP 读取组件', nx_ok, '检查读取程序与 LibHac 能否加载（不读取游戏或密钥）', repair, 'reinstall', 'bundled', detail=output, location=nx)
    xlate = c.engine/'dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate'
    ok, output = probe(c, [xlate, '--source-sha'])
    try:
        expected = hashlib.sha256(b''.join((c.engine/'dm/gfx/tools/dmsh_xlate'/n).read_bytes() for n in ('Program.cs','dmsh_xlate.csproj'))).hexdigest()[:16]
        ok = ok and output == expected and all((xlate.parent/n).is_file() for n in ('dmsh_xlate.dll','Ryujinx.Graphics.Shader.dll','Ryujinx.Common.dll'))
    except OSError:
        ok = False
    add('着色器翻译组件', ok, '检查翻译器能否启动，且与固定引擎源码一致', repair, 'reinstall', 'bundled', detail=output, location=xlate)
    ok, output = probe(c, [runtime/'bin/spirv-cross', '--revision'])
    add('SPIRV-Cross', ok and bool(output), output if ok else '着色器转换组件不可用', repair, 'reinstall', 'bundled', detail=output, location=runtime/'bin/spirv-cross')
    ok, output = probe(c, [runtime/'bin/zstd', '--version'])
    add('Zstandard', ok and 'v1.' in output, output if ok else '压缩组件不可用', repair, 'reinstall', 'bundled', detail=output, location=runtime/'bin/zstd')

    env = c.env()
    developer = Path(env['DEVELOPER_DIR'])
    ok, output = probe(c, ['/usr/bin/xcodebuild','-version'])
    xcode_ok = ok and (developer/'Platforms/MacOSX.platform').is_dir() and 'Xcode ' in output
    add('Xcode', xcode_ok, output if xcode_ok else '需要完整 Xcode，请检查 Developer 目录，不能仅使用 Command Line Tools', REPAIR_XCODE, 'xcodeStore', 'apple', detail=output)
    status_args = ['/usr/bin/env',f'DEVELOPER_DIR={developer}','/usr/bin/xcodebuild','-checkFirstLaunchStatus']
    ok, output = probe(c, ['/usr/bin/xcodebuild','-checkFirstLaunchStatus']) if xcode_ok else (False, '')
    if not xcode_ok:
        initial_message = '请先安装并选择完整 Xcode，再检查初始设置。'
    elif ok:
        initial_message = 'Xcode 首次启动组件已就绪'
    elif output == PROBE_TIMEOUT:
        initial_message = 'Xcode 初始设置检查超时，请稍后重新检查。'
    elif 'license' in output.lower() and any(phrase in output.lower() for phrase in ('not agreed','have not agreed','has not been accepted','must be accepted')):
        initial_message = 'Xcode 许可尚未完成，请打开所选 Xcode 阅读并同意许可。'
    else:
        initial_message = 'Xcode 首次启动任务未完成，或状态检查命令执行失败。'
    initial_detail = shlex.join(status_args)+'\n'+(output or 'No diagnostic output.') if xcode_ok else ''
    manual_command = shlex.join(['sudo','/usr/bin/env',f'DEVELOPER_DIR={developer}','/usr/bin/xcodebuild','-runFirstLaunch']) if xcode_ok and not ok else None
    add('Xcode 初始设置', ok, initial_message, REPAIR_XCODE_INITIAL if xcode_ok and not ok else REPAIR_XCODE,
        'openXcode' if xcode_ok else 'xcodeStore', 'apple', detail=initial_detail, repairCommand=manual_command)
    initialized = ok
    ok, output = probe(c, ['/usr/bin/xcrun','--sdk','macosx','--show-sdk-path']) if initialized else (False, '')
    sdk_ok = ok and Path(output).is_dir() and (Path(output)/'System/Library/Frameworks/Metal.framework').is_dir()
    if sdk_ok:
        version_ok, sdk_version = probe(c, ['/usr/bin/xcrun','--sdk','macosx','--show-sdk-version'])
        sdk_ok = version_ok and sdk_version.split('.')[0].isdigit() and int(sdk_version.split('.')[0]) >= 26
    add('macOS SDK', sdk_ok, output if sdk_ok else 'macOS SDK 不完整', '在 Xcode 中完成初始组件安装，或重新安装完整 Xcode；无需下载其他设备的运行环境。', 'openXcode', 'apple', detail=output)
    compiler_ok = metal_ok = False
    with tempfile.TemporaryDirectory(prefix='environment-', dir=c.private) as directory:
        scratch = Path(directory)
        if sdk_ok:
            (scratch/'probe.m').write_text('#import <Cocoa/Cocoa.h>\n#import <Metal/Metal.h>\n#import <GameController/GameController.h>\nint main(void) { return 0; }\n')
            ok, output = probe(c, ['/usr/bin/xcrun','clang','-arch','arm64','-mmacosx-version-min=26.0','-fobjc-arc',scratch/'probe.m','-o',scratch/'probe',
                *[flag for name in ('Cocoa','QuartzCore','Metal','GameController','AudioToolbox','VideoToolbox','CoreMedia','CoreVideo','ImageIO','UniformTypeIdentifiers') for flag in ('-framework',name)]], timeout=30)
            if ok:
                ok, output = probe(c, ['/usr/bin/codesign','--force','--sign','-',scratch/'probe'])
            if ok:
                ok, output = probe(c, ['/usr/bin/codesign','--verify','--strict',scratch/'probe'])
            if ok:
                ok, output = probe(c, [scratch/'probe'])
            if ok:
                ok, output = probe(c, ['/usr/bin/make','--version'])
            if ok:
                ok, output = probe(c, ['/usr/bin/xcrun','clang','-arch','arm64','-c',scratch/'probe.m','-o',scratch/'probe.o'])
            if ok:
                ok, output = probe(c, ['/usr/bin/xcrun','ar','rcs',scratch/'probe.a',scratch/'probe.o'])
            compiler_ok = ok
        else:
            output = ''
        add('原生编译与本地签名', compiler_ok, '实际编译并链接 arm64 测试程序，验证 make、ar 和 codesign', REPAIR_XCODE, 'openXcode', 'apple', detail=output)
        if sdk_ok:
            (scratch/'probe.metal').write_text('#include <metal_stdlib>\nusing namespace metal;\nkernel void lumadock_probe(device uint *out [[buffer(0)]],uint i [[thread_position_in_grid]]) { out[i]=i; }\n')
            ok, output = probe(c, ['/usr/bin/xcrun','--sdk','macosx','metal','-c',scratch/'probe.metal','-o',scratch/'probe.air'], timeout=30)
            if ok:
                ok, output = probe(c, ['/usr/bin/xcrun','--sdk','macosx','metallib',scratch/'probe.air','-o',scratch/'probe.metallib'], timeout=30)
            metal_ok = ok and (scratch/'probe.metallib').is_file() and (scratch/'probe.metallib').stat().st_size > 0
        else:
            output = ''
        add('Metal 编译组件', metal_ok, '实际编译测试着色器并生成 macOS Metal 库', '先完成 Xcode 初始设置，再点击“安装 Metal 编译组件”。下载由 Apple 管理；完成后重新检查。', 'installMetal', 'apple', detail=output)
    # Validate the actual selected storage, including removable/noexec volumes.
    library_id = c.r.get('storageLibraryId') or c.r.get('libraryId')
    target = c.library if library_id else c.private
    storage_ok = False
    try:
        if library_id and read(target/'.nsmac-library.json',{}).get('id') != library_id:
            raise OSError('游戏库磁盘已断开或位置发生变化，请重新连接后重试。')
        with tempfile.TemporaryDirectory(prefix='.lumadock-check-', dir=target) as directory:
            path = Path(directory)/'execute-check'
            path.write_text('#!/bin/sh\nexit 0\n'); path.chmod(0o700)
            storage_ok, output = probe(c, [path])
        free = shutil.disk_usage(target).free
    except (OSError, ValueError) as error:
        free = 0; output = str(error)
    add('游戏库存储权限', storage_ok, str(target), '选择可读写且允许执行程序的本地或外置磁盘，保持磁盘连接；在设置中重新选择游戏库。', 'library', 'storage', both, output)
    add('可用空间', free >= 5*2**30, f'{free/2**30:.1f} GB（大型游戏通常需要 40–80 GB）', '至少预留 5 GB；实际准备前会按所选游戏文件大小再次检查空间，可选择空间更大的游戏库磁盘。', 'library', 'storage')
    return checks


def require_environment(c, scope='prepare'):
    checks = inspect_environment(c)
    failed = [item['name'] for item in checks if scope in item['requiredFor'] and not item['ok']]
    if failed:
        raise Failure('环境检查未通过，请在设置中修复：'+'\n'+'\n'.join(failed))
    return checks


def require_launch_environment(c):
    c.check()
    version = platform.mac_ver()[0]
    if platform.machine() != 'arm64' or not version or not version.split('.')[0].isdigit() or int(version.split('.')[0]) < 26 or not metal_available():
        raise Failure('启动需要 Apple Silicon、macOS 26+ 和可用的系统 Metal 图形设备，请在设置中重新检查环境。')


def supports_removal(c):
    try:
        result = subprocess.run(['xcodebuild', '-help'], env=c.env(), capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return '-deleteComponent' in result.stdout + result.stderr


def install_metal(c):
    c.begin('安装 Apple Metal 编译组件', 1, 1)
    c.run(['xcodebuild', '-downloadComponent', 'MetalToolchain'])
    return {}


def uninstall_metal(c):
    if c.r.get('confirmed') is not True:
        raise Failure('请先确认卸载共享 Metal 编译组件。')
    if not supports_removal(c):
        raise Failure('当前 Xcode 不支持命令行卸载组件，请在 Xcode 的组件设置中管理。')
    c.begin('卸载 Apple Metal 编译组件', 1, 1)
    c.run(['xcodebuild', '-deleteComponent', 'MetalToolchain'])
    return {}

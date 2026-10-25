"""Unsigned iOS game export through the player's private engine snapshot."""
from __future__ import annotations
import getpass
import os
from pathlib import Path
import plistlib
import re
import shutil
import stat
import sys
import uuid
import zipfile
from core import Failure, chain_of, clone, digest, read
import milestones as ms

IOS_FILES = ('dm/ios/tools/build_ipa.sh', 'dm/ios/tools/pack_ipa.py',
             'dm/ios/tools/ios_metal.py', 'dm/ios/project.yml', 'dm/ios/Sources/main.m')


def destination(c):
    value = c.r.get('outputPath')
    if not isinstance(value, str) or not value or not Path(value).is_absolute():
        raise Failure('请选择 IPA 保存位置。')
    path = Path(value)
    if path.is_symlink() or path.suffix.lower() != '.ipa' or not path.parent.is_dir() or path.is_dir():
        raise Failure('IPA 保存位置无效，请选择以 .ipa 结尾的文件。')
    path = path.resolve()
    if any(path.is_relative_to(root) for root in (c.private, c.library, c.engine) if root):
        raise Failure('请将 IPA 保存到游戏库、引擎及应用私有目录以外的位置。')
    return path


def environment(c, env=None):
    from toolchain import probe
    if c.engine is None or any(not (c.engine/name).is_file() for name in IOS_FILES):
        raise Failure('所选 nxnative 缺少 iOS 打包组件，请选择包含 dm/ios 的完整源码。')
    env = dict(env or c.env())
    env.pop('DM_MAC_ONLY', None)
    # XcodeGen is an optional iOS-only tool, installed by the player with Homebrew.
    env['PATH'] += ':/opt/homebrew/bin:/usr/local/bin'
    env.setdefault('USER', getpass.getuser())
    generator = shutil.which('xcodegen', path=env['PATH'])
    if not generator:
        raise Failure('生成 IPA 需要 XcodeGen，请先运行 brew install xcodegen，再重试。')
    checks = {}
    for name, args in (
        ('sdk', ['xcrun', '--sdk', 'iphoneos', '--show-sdk-version']),
        ('metal', ['xcrun', '--sdk', 'iphoneos', 'metal', '--version']),
        ('xcode', ['xcodebuild', '-version']),
        ('xcodegen', [generator, '--version']),
    ):
        ok, output = probe(c, args, env=env)
        if not ok or not output:
            raise Failure('iOS 构建环境不完整，请在所选 Xcode 中安装 iOS 平台和 Metal 编译组件，再重试。')
        checks[name] = output
    checks['xcodegenHash'] = digest(generator)
    return env, checks


def validate(path, c):
    """Read every ZIP member for CRC validation before replacing the chosen output."""
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            infos = [name for name in names if name.startswith('Payload/') and name.count('/') == 2 and name.endswith('.app/Info.plist')]
            if len(infos) != 1: raise ValueError('app plist')
            info = plistlib.loads(archive.read(infos[0]))
            app = infos[0].rsplit('/', 1)[0]+'/'
            executable = info.get('CFBundleExecutable', '')
            if not executable or '/' in executable or app+executable not in names or info.get('CFBundlePackageType') != 'APPL' or info.get('CFBundleSupportedPlatforms') != ['iPhoneOS']:
                raise ValueError('iOS executable')
            if not any(n.startswith(app+'romfs/') for n in names) or not any(n.startswith(app+'msl/') and n.endswith('.metallib') for n in names):
                raise ValueError('game resources')
            total = sum(i.file_size for i in archive.infolist()); done = 0
            for member in archive.infolist():
                if Path(member.filename).is_absolute() or '..' in Path(member.filename).parts or stat.S_ISLNK(member.external_attr >> 16):
                    raise ValueError('archive path')
                with archive.open(member) as source:
                    while block := source.read(8 << 20):
                        done += len(block); c.progress(done, total)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, RuntimeError, plistlib.InvalidFileException) as error:
        raise Failure('生成的 IPA 结构或完整性检查失败，请查看任务日志后重试。') from error


def validate_shaders(path, gp, repo):
    if gp.get('graphics','nvn') in ('vulkan','gl'):
        api='vk' if gp.get('graphics')=='vulkan' else 'gl'
        if (path/api/(api+'_shaders.metallib')).is_file(): return
    else:
        chain = chain_of(repo,gp)
        directory = path/('b-'+chain)
        reflections = list(directory.glob('*_b.json'))
        if reflections and all(p.with_suffix('.metallib').is_file() and read(p,{}).get('chain') == chain and 'iphoneos' in read(p,{}).get('chain_metal','') for p in reflections): return
    raise Failure('iOS 着色器产物缺失或编译平台不匹配，请重试。')


def package(c, root, repo, env, gp, selected, patched, shaders, aoc, up=None):
    out = destination(c)
    validate_shaders(shaders, gp, repo)
    if shutil.disk_usage(out.parent).free < sum(p.stat().st_size for p in (selected/'RomFS').rglob('*') if p.is_file()) + 2**30:
        raise Failure('IPA 保存磁盘空间不足，请释放空间后重试。')
    built = root/'ipa/game.ipa'; built.parent.mkdir(exist_ok=True)
    font = next((p for p in (Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf'), Path('/System/Library/Fonts/Helvetica.ttc')) if p.is_file()), None)
    if font is None: raise Failure('找不到本机系统字体。')
    own=read(root/'identity.json',{}).get('preparation',{}).get('mode')=='derived'
    if own and gp.get('graphics','nvn')=='nvn':
        from derived import validate_tables
        validate_tables(root/'shader/cache',gp,chain_of(repo,gp))
    elif gp.get('graphics','nvn') not in ('vulkan','gl'):
        chain = chain_of(repo,gp)
        c.run([sys.executable, Path(__file__).parent/'c1_generate.py', repo/'dm/gfx/tools/c1_guard.py',
               root/'shader/cache'/('b-'+chain), gp.table('c1_full.tsv')], root/'logs/c1.log', env)
    packing = dict(env, GAME=gp.id, W=str(root/'ipa/work'), PATCHED=str(patched),
                   ROMFS=str(selected/'RomFS'), MSL_IOS=str(shaders), AOC=str(aoc),
                   GFXAPI=gp.get('graphics','nvn'), FONT_PY=sys.executable, STD_FONT=str(font),
                   DM_DISPLAY_NAME=c.game()['name'], DM_APP_VERSION=gp.builds()[gp.get('package')]['display'],
                   DM_BUNDLE_ID='org.nxnative.'+gp.id.lower())
    icon = selected/'icon.jpg'
    if icon.is_file(): packing['DM_ICON'] = str(icon)
    watch=up.IpaWatch(repo,root/'ipa/work',built) if up is not None and hasattr(up,'IpaWatch') else None
    if watch:up.PROG.stage('app build',poll=watch.poll,step='starting')
    def line(value):
        if re.sub(r'^\[[\d:]+\] ','',value).startswith('pack IPA'): c.begin('打包 IPA')
        if watch:watch.line(value)
    try:c.run(['bash', repo/'dm/ios/tools/build_ipa.sh', built], root/'logs/build_ipa.log', packing,on_line=line)
    finally:
        if watch:up.PROG.watch(None)
    ms.enter(c,'ipa_check','验证 IPA 完整性')
    validate(built, c)
    ms.enter(c,'ipa_export','导出 IPA')
    # Copy to the destination volume before the atomic replace; cancellation keeps
    # any previous export, Mac release and saves intact.
    temporary = out.with_name('.'+out.name+'.'+uuid.uuid4().hex+'.partial')
    try:
        c.check(); clone(built, temporary,c.progress); c.check()
        c.begin('校验导出 IPA')
        checksum = digest(temporary, c.progress)
        c.check(); os.replace(temporary, out)
    finally:
        temporary.unlink(missing_ok=True)
    return dict(outputPath=str(out), size=out.stat().st_size, sha256=checksum, signed=False)


def export(c):
    destination(c)  # Reject invalid output before any expensive build work.
    from build import build
    return build(c, target='ios')

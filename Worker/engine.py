"""Adapter for bundled nxnative, with external-source support in development.

Only private snapshots are modified or compiled. No engine downloads at runtime.
"""
from __future__ import annotations
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid
from core import Failure, atomic, digest, profiles, read

HELP = 'nxnative 随应用内置。组件缺失或校验失败时，请重新安装完整璃游；游戏构建使用私有副本。'
SDK_HELP = '首次准备引擎读取工具需要 Microsoft .NET 10 SDK（macOS Arm64），只有运行时不够。安装官方 SDK 后重新检查；已有完整工具缓存时不再需要 SDK。安装方法见环境安装说明。'
TOOLS_HELP = '点击“准备引擎工具”，将内置引擎与读取器复制到私有缓存。源码开发时首次编译读取器需要 .NET 10 SDK。'
EXCLUDED = {'.git', 'bin', 'obj', 'gen', '__pycache__', 'cache', 'logs'}
ROOTS = {'dm', 'scripts', 'LICENSE'}
PRIVATE_SUFFIXES = {'.nsp', '.xci', '.nsz', '.keys', '.ipa', '.metallib', '.pyc'}
REQUIRED = ('scripts/build_ipa_from_nsp.py', 'dm/games/game.py', 'dm/host/Makefile',
            'dm/host/front_mac.m', 'dm/tools/nx_extract/Program.cs',
            'dm/tools/nx_extract/nx_extract.csproj', 'dm/gfx/tools/dmsh_chain.py',
            'dm/gfx/tools/dmsh_build.py', 'dm/gfx/tools/dmsh_xlate/Program.cs',
            'dm/gfx/tools/dmsh_xlate/dmsh_xlate.csproj',
            'dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate')

def source_files(root):
    root = Path(root).resolve()
    for top in sorted(ROOTS):
        base = root/top
        paths = sorted(base.rglob('*')) if base.is_dir() else [base]
        for path in paths:
            rel = path.relative_to(root)
            if set(rel.parts) & EXCLUDED or path.name in ('dmhost', '.source-ready') or path.suffix.lower() in PRIVATE_SUFFIXES:
                continue
            if path.is_symlink() and not path.resolve().is_relative_to(root):
                raise Failure('引擎目录包含指向外部的符号链接，请选择完整的本地源码副本。')
            if path.is_file():
                yield path

def source_hash(root):
    root = Path(root).resolve()
    h = hashlib.sha256()
    for path in source_files(root):
        h.update(str(path.relative_to(root)).encode()); h.update(b'\0')
        h.update(bytes.fromhex(digest(path)))
    return h.hexdigest()

def inspect_source(c):
    if c.engine is None:
        raise Failure('尚未选择 nxnative 目录，请先在环境设置中指定。')
    if not c.engine.is_dir():
        raise Failure('nxnative 目录不可用，请连接磁盘或重新选择目录。')
    bundled = hasattr(c, 'resource') and c.engine == c.resource/'Engine/nxnative'
    if bundled:
        from bundled_engine import verify_bundle
        try: verify_bundle(c.engine)
        except (OSError, ValueError, KeyError) as error: raise Failure(HELP) from error
    missing = [name for name in REQUIRED if not (c.engine/name).is_file()]
    if missing:
        raise Failure('nxnative 目录不完整，缺少：'+'、'.join(missing))
    try:
        tree = ast.parse((c.engine/REQUIRED[0]).read_text())
        names = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
        if not {'extract', 'extract_aoc', 'rewrite', 'split_shaders', 'build_mac_host', 'Progress'} <= names:
            raise ValueError('unsupported build API')
        ps = profiles(c.engine)
        if not ps or any(not p.get('package') or not p.get('name') or not p['builds'] for p in ps.values()):
            raise ValueError('missing profiles')
        for flag, function in (('shader_glslc_capture','capture_glslc'), ('shader_vk_capture','capture_vk')):
            if any(profile.get(flag)=='on' for profile in ps.values()) and function not in names and not (flag=='shader_vk_capture' and 'capture_shaders' in names):
                raise ValueError('unsupported capture API')
        program = (c.engine/'dm/tools/nx_extract/Program.cs').read_text()
        if '--inspect' not in program and not all(token in program for token in ('static class P', 'OpenNsp(', 'Nacp(', 'TitleName(', 'Icon(')):
            raise ValueError('unsupported metadata API')
        raw = source_hash(c.engine)
    except (OSError, ValueError, KeyError, SyntaxError) as error:
        raise Failure('所选 nxnative 的构建接口或配置不兼容，请查看环境说明并选择完整的兼容源码。') from error
    bridge = hashlib.sha256(Path(__file__).read_bytes()+(Path(__file__).parent/'NspMetadata.cs').read_bytes()+(Path(__file__).parent/'derived.py').read_bytes()).hexdigest()
    fingerprint = ('bundled-' if bundled else 'external-')+hashlib.sha256((raw+bridge).encode()).hexdigest()
    frontend = (c.engine/'dm/host/front_mac.m').read_text()
    header = c.engine/'dm/host/input_config_mac.h'
    inputs = 'DM_INPUT_CONFIG' in frontend or 'input_config_mac.h' in frontend and header.is_file() and 'DM_INPUT_CONFIG' in header.read_text()
    from derived import supported
    return dict(fingerprint=fingerprint, sourceHash=raw, inputConfig=bool(inputs), nativeControllers=(c.engine/'dm/host/controller_native.h').is_file(), derivedProfiles=supported(c.engine))

def sdk_candidates():
    values = [os.environ.get('DOTNET_HOST_PATH'), shutil.which('dotnet')]
    if os.environ.get('DOTNET_ROOT'): values.append(str(Path(os.environ['DOTNET_ROOT'])/'dotnet'))
    values += ['/usr/local/share/dotnet/dotnet', '/opt/homebrew/share/dotnet/dotnet',
               '/opt/homebrew/opt/dotnet/libexec/dotnet']
    return list(dict.fromkeys(Path(value).resolve() for value in values if value))

def sdk_env(c, host):
    env = c.env(); env['DOTNET_ROOT'] = str(Path(host).parent); env['DOTNET_ROOT_ARM64'] = env['DOTNET_ROOT']
    env['DOTNET_HOST_PATH'] = str(host)
    env['DOTNET_CLI_HOME'] = str(c.private/'dotnet-home')
    env['NUGET_PACKAGES'] = str(c.private/'nuget')
    env['DOTNET_SKIP_FIRST_TIME_EXPERIENCE'] = '1'
    env['DOTNET_GENERATE_ASPNET_CERTIFICATE'] = 'false'
    env['DOTNET_NOLOGO'] = '1'
    env['DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE'] = 'true'
    env['DOTNET_CLI_USE_MSBUILD_SERVER'] = '0'
    return env

def find_sdk(c):
    from toolchain import probe
    for host in sdk_candidates():
        if not host.is_file(): continue
        ok, output = probe(c, [host, '--list-sdks'], env=sdk_env(c, host), timeout=5)
        versions = [line.split()[0] for line in output.splitlines() if re.match(r'^10\.\d+\.\d+\s+\[', line)]
        if ok and versions: return host, sorted(versions, key=lambda x:tuple(map(int,x.split('.'))))[-1]
    return None, ''

def prepared_root(c, info):
    return c.private/'engines'/info['fingerprint']

def prepared_tools(c, info=None):
    info = info or inspect_source(c)
    root = prepared_root(c, info)
    try: record = read(root/'ready.json', {})
    except (OSError, ValueError): raise Failure('外部引擎工具缓存不完整，请重新准备引擎工具。')
    if not isinstance(record,dict): raise Failure('外部引擎工具缓存不完整，请重新准备引擎工具。')
    if record.get('fingerprint') != info['fingerprint'] or not record.get('files'):
        raise Failure('外部引擎工具尚未准备或源码已变化，请点击“准备引擎工具”。')
    for name, sha in record['files'].items():
        path = root/name
        if not isinstance(name,str) or not name.startswith('tools/nx_extract/') or '..' in Path(name).parts or not path.resolve().is_relative_to(root.resolve()) or not path.is_file() or digest(path) != sha:
            raise Failure('外部引擎工具缓存不完整，请重新准备引擎工具。')
    reader = root/'tools/nx_extract/nx_extract'
    if not reader.is_file() or not os.access(reader, os.X_OK) or not (root/'source/.source-ready').is_file():
        raise Failure('外部引擎工具缓存不完整，请重新准备引擎工具。')
    if record.get('snapshotHash') != source_hash(root/'source'):
        raise Failure('外部引擎工具缓存不完整，请重新准备引擎工具。')
    return root

def adapt_snapshot(repo):
    program = repo/'dm/tools/nx_extract/Program.cs'
    text = program.read_text()
    if 'LumaNXInspect(a)' not in text:
        text, changed = re.subn(r'\bstatic (?:partial )?class P\b', 'static partial class P', text, count=1)
        entry = re.search(r'static int Main\(string\[\] a\)\s*\{', text)
        if changed != 1 or not entry: raise Failure('所选 nxnative 的 NSP 读取器入口不兼容。')
        start = entry.end()
        text = text[:start]+'\n        a = LumaNXArgs(a);\n        if (a.Length >= 3 && a[1] == "--inspect") return LumaNXInspect(a);\n'+text[start:]
        # The base/update can share one XCI. Select their CNMT content IDs before
        # the upstream extractor picks Program/Control/Data NCAs.
        for index,kind in ((1,'base'),(2,'update')):
            text, count = re.subn(r'OpenNsp\(ks,\s*a\['+str(index)+r'\]\)',
                'LumaNXSelected(ks, a['+str(index)+'], "'+kind+'")',text,count=1)
            if count != 1: raise Failure('所选 nxnative 的 NSP 读取器入口不兼容。')
        text, count = re.subn(r'OpenNsp\(ks,\s*nsp\)', 'LumaNXSelected(ks, nsp, "dlc")',text,count=1)
        if count != 1: raise Failure('所选 nxnative 的 NSP 读取器入口不兼容。')
        program.write_text(text)
    shutil.copy2(Path(__file__).parent/'NspMetadata.cs', program.parent/'LumaNXMetadata.cs')
    chain = repo/'dm/gfx/tools/dmsh_chain.py'
    text = chain.read_text()
    if 'DM_MAC_ONLY' not in text:
        tree = ast.parse(text)
        class MacOnly(ast.NodeTransformer):
            count = 0
            def visit_For(self, node):
                self.generic_visit(node)
                if isinstance(node.iter, ast.Tuple) and [getattr(v, 'value', None) for v in node.iter.elts] == ['macosx', 'iphoneos']:
                    node.iter = ast.parse("('macosx',) if os.environ.get('DM_MAC_ONLY') == '1' else ('macosx', 'iphoneos')", mode='eval').body
                    self.count += 1
                return node
        rewrite = MacOnly(); tree = rewrite.visit(tree)
        if rewrite.count != 1: raise Failure('所选 nxnative 的 Metal 工具链接口不兼容。')
        tree.body.insert(0, ast.Import(names=[ast.alias(name='os')]))
        chain.write_text(ast.unparse(ast.fix_missing_locations(tree))+'\n')

def prepare(c):
    with c.toolchain_lock(exclusive=True):
        c.begin('验证 nxnative', 1, 3)
        info = inspect_source(c)
        try:
            root = prepared_tools(c, info)
            return dict(info, path=str(root), reused=True)
        except Failure: pass
        shipped = c.resource/'Engine/reader'
        shipped_record = read(shipped/'manifest.json', {})
        use_shipped = info['fingerprint'].startswith('bundled-') and shipped_record.get('fingerprint') == info['fingerprint']
        if shipped.exists() and not use_shipped: raise Failure('内置读取器与引擎版本不匹配，请重新安装完整璃游。')
        sdk, version = (None, shipped_record.get('sdk', '')) if use_shipped else find_sdk(c)
        if not use_shipped and sdk is None: raise Failure(SDK_HELP)
        engines = c.private/'engines'; engines.mkdir(exist_ok=True)
        stage = engines/('.partial-'+uuid.uuid4().hex)
        stage.mkdir()
        try:
            c.begin('复制引擎到私有工作目录', 2, 3)
            repo = stage/'source'; repo.mkdir()
            files=list(source_files(c.engine));total=sum(path.stat().st_size for path in files);done=0
            for path in files:
                c.check(); dest=repo/path.relative_to(c.engine); dest.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(path,dest)
                dest.chmod(dest.stat().st_mode | 0o600)
                done+=path.stat().st_size;c.progress(done,total)
            if source_hash(repo) != info['sourceHash']: raise Failure('复制期间引擎源码发生变化，请重新准备。')
            adapt_snapshot(repo)
            atomic(repo/'global.json', {'sdk':{'version':version,'rollForward':'latestPatch','allowPrerelease':False}})
            c.begin('准备引擎读取工具', 3, 3)
            # An ASCII output path avoids an MSBuild apostrophe-path bug.
            with tempfile.TemporaryDirectory(prefix='lumanx-reader-') as directory:
                output=Path(directory)/'publish'
                config=Path(directory)/'NuGet.Config'
                config.write_text('<configuration><packageSources><clear/><add key="nuget.org" value="https://api.nuget.org/v3/index.json"/></packageSources></configuration>')
                if use_shipped:
                    files = shipped_record.get('files', {})
                    actual = {p.name:digest(p) for p in shipped.iterdir() if p.is_file() and p.name != 'manifest.json'}
                    if not files or files != actual or any(p.is_symlink() or p.is_dir() for p in shipped.iterdir()): raise Failure('内置读取器校验失败，请重新安装完整璃游。')
                    output.mkdir()
                    for name in files: shutil.copy2(shipped/name, output/name)
                else:
                    c.run([sdk, 'publish', repo/'dm/tools/nx_extract/nx_extract.csproj', '-c', 'Release', '-r', 'osx-arm64', '--self-contained', 'false', '--disable-build-servers', '-p:UseSharedCompilation=false', '--configfile', config, '-o', output, '-v', 'quiet'], env=sdk_env(c,sdk), cwd=repo)
                for name in ('nx_extract','nx_extract.dll','LibHac.dll','nx_extract.runtimeconfig.json'):
                    if not (output/name).is_file(): raise Failure('引擎读取工具编译后缺少必需产物。')
                shutil.copytree(output, stage/'tools/nx_extract')
            from toolchain import probe
            _, usage = probe(c, [stage/'tools/nx_extract/nx_extract'])
            if 'usage: nx_extract <prod.keys>' not in usage: raise Failure('引擎读取工具编译后无法启动，请查看日志。')
            if inspect_source(c)['fingerprint'] != info['fingerprint']: raise Failure('复制期间引擎源码发生变化，请重新准备。')
            (repo/'.source-ready').write_text(info['fingerprint'])
            files={str(p.relative_to(stage)):digest(p) for p in (stage/'tools').rglob('*') if p.is_file()}
            atomic(stage/'ready.json', dict(info, files=files, sdk=version, snapshotHash=source_hash(repo)))
            target=prepared_root(c,info); backup=engines/('.previous-'+uuid.uuid4().hex)
            if target.exists(): target.rename(backup)
            try: stage.rename(target)
            except Exception:
                if backup.exists(): backup.rename(target)
                raise
            shutil.rmtree(backup,ignore_errors=True)
            return dict(info, path=str(target), reused=False)
        finally:
            shutil.rmtree(stage,ignore_errors=True)

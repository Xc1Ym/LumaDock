"""Environment fault injection uses original scratch files, never player data."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Worker'))
from core import Context, atomic
import toolchain, engine
from engine_fixture import make_engine, mark_prepared


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='lumadock-env-')
        self.root=Path(self.temp.name)
        self.c=Context(dict(schema=1,operation='preflight',privateRoot=str(self.root/'private'),resources=str(self.root/'resources'),engineDir=str(make_engine(self.root/'External 引擎')),developerDir=str(self.root/'Xcode.app/Contents/Developer')))
        self.versions=dict(python='3.14.8',capstone='5.0.9',lz4='4.4.5',fonttools='4.67.0',dotnet='10.0.13',spirvCross='fixture',zstd='fixture')
        atomic(self.c.runtime/'versions.json',self.versions)
        self.developer=Path(self.c.env()['DEVELOPER_DIR'])
        (self.developer/'Platforms/MacOSX.platform').mkdir(parents=True)
        self.sdk=self.root/'MacOSX.sdk';(self.sdk/'System/Library/Frameworks/Metal.framework').mkdir(parents=True)
        shader=self.c.engine/'dm/gfx/tools'
        for name in ('Program.cs','dmsh_xlate.csproj'):
            path=shader/'dmsh_xlate'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(name)
        self.sha=hashlib.sha256(b'Program.csdmsh_xlate.csproj').hexdigest()[:16]
        for name in ('dmsh_xlate.dll','Ryujinx.Graphics.Shader.dll','Ryujinx.Common.dll'):
            path=shader/'dmsh_xlate_bin'/name;path.parent.mkdir(exist_ok=True);path.write_text('fixture')
        mark_prepared(self.c)
        self.sdk_host=self.root/'dotnet';self.sdk_host.write_text('fixture')
        self.calls=[];self.fail=set()
    def tearDown(self):self.temp.cleanup()
    def fake_probe(self,c,args,**kw):
        args=list(map(str,args));self.calls.append(args)
        executable=Path(args[0]).name
        key=executable
        if executable=='python3':key='modules' if 'capstone' in args[-1] else 'python'
        if executable=='xcodebuild':key='initial' if '-checkFirstLaunchStatus' in args else 'xcode'
        if executable=='xcrun':key=args[1] if args[1]!='--sdk' else args[3]
        if key in self.fail:return False,'broken '+key
        if key=='python':return True,json.dumps(dict(version=self.versions['python'],arch='arm64',prefix=str(c.runtime/'python')))
        if key=='modules':return True,json.dumps({k:self.versions[k] for k in ('capstone','lz4','fonttools')})
        if key=='dotnet' and '--list-sdks' in args:return True,'10.0.101 [fixture]'
        if key=='dotnet':return True,'Microsoft.NETCore.App 10.0.13 ['+str(c.runtime/'dotnet/shared/Microsoft.NETCore.App')+']'
        if key=='nx_extract':return False,'usage: nx_extract <prod.keys> <base.nsp>'
        if key=='dmsh_xlate':return True,self.sha
        if key=='spirv-cross':return True,'revision fixture'
        if key=='zstd':return True,'Zstandard v1.5.7'
        if key=='xcode':return True,'Xcode 27.1'
        if key=='--show-sdk-path':return True,str(self.sdk)
        if key=='--show-sdk-version':return True,'27.0'
        if '-o' in args:Path(args[args.index('-o')+1]).write_bytes(b'original compiler fixture')
        return True,''
    def inspect(self):
        with patch('engine.sdk_candidates',return_value=[self.sdk_host]),patch('toolchain.probe',side_effect=self.fake_probe),patch('toolchain.metal_available',return_value=True),patch('toolchain.platform.machine',return_value='arm64'),patch('toolchain.platform.mac_ver',return_value=('27.0.1',(),'')),patch('toolchain.shutil.disk_usage',return_value=type('Disk',(),{'free':100*2**30})()),contextlib.redirect_stdout(io.StringIO()):
            return {x['name']:x for x in toolchain.inspect_environment(self.c)}
    def test_complete_checklist_and_no_implicit_global_dependencies(self):
        checks=self.inspect();self.assertEqual(len(checks),20)
        self.assertTrue(all(x['ok'] for x in checks.values()))
        self.assertTrue(all(x['help'] for x in checks.values()))
        self.assertTrue(all(x[0].startswith(str(self.c.runtime)) for x in self.calls if Path(x[0]).name in ('python3','spirv-cross','zstd')))
        self.assertTrue(any('metallib' in call for call in self.calls))
        self.assertTrue(any('rcs' in call for call in self.calls))
        self.assertFalse(any('downloadComponent' in call or '-runFirstLaunch' in call for call in self.calls))
        self.assertFalse(list(self.c.private.glob('environment-*')))
        for name in ('内置 Python','.NET 10 运行时'):
            self.assertNotIn(str(self.root),checks[name]['message'])
            self.assertTrue(checks[name]['location'].startswith(str(self.c.runtime)))
    def test_broken_python_and_extensions_are_reported_individually(self):
        self.fail={'python'};checks=self.inspect()
        self.assertFalse(checks['内置 Python']['ok']);self.assertFalse(checks['Python 扩展']['ok'])
        self.assertEqual(checks['内置 Python']['action'],'reinstall')
        self.assertFalse(any('capstone' in call[-1] for call in self.calls))
        self.fail={'modules'};checks=self.inspect()
        self.assertTrue(checks['内置 Python']['ok']);self.assertFalse(checks['Python 扩展']['ok'])
    def test_python_outside_bundle_and_mismatched_translator_are_rejected(self):
        original=self.fake_probe
        def outside(c,args,**kw):
            if Path(args[0]).name=='python3' and 'capstone' not in str(args[-1]):return True,json.dumps(dict(version='3.14.8',arch='arm64',prefix='/opt/homebrew'))
            return original(c,args,**kw)
        with patch.object(self,'fake_probe',side_effect=outside):self.assertFalse(self.inspect()['内置 Python']['ok'])
        self.sha='wrong source';self.assertFalse(self.inspect()['着色器翻译组件']['ok'])
    def test_missing_manifest_and_dotnet_failure_do_not_abort_other_checks(self):
        (self.c.runtime/'versions.json').write_text('malformed')
        self.fail={'dotnet','nx_extract','spirv-cross','zstd'}
        checks=self.inspect()
        for name in ('内置组件清单','内置 Python','.NET 10 运行时','NSP 读取组件','SPIRV-Cross','Zstandard'):self.assertFalse(checks[name]['ok'],name)
        self.assertTrue(checks['Xcode']['ok'])
    def test_full_xcode_initialization_and_real_metal_compilation_are_required(self):
        (self.developer/'Platforms/MacOSX.platform').rmdir()
        checks=self.inspect();self.assertFalse(checks['Xcode']['ok']);self.assertFalse(checks['macOS SDK']['ok'])
        (self.developer/'Platforms/MacOSX.platform').mkdir()
        self.fail={'initial'};checks=self.inspect();self.assertFalse(checks['Xcode 初始设置']['ok']);self.assertFalse(checks['Metal 编译组件']['ok'])
        self.fail={'metallib'};checks=self.inspect();self.assertFalse(checks['Metal 编译组件']['ok'])
        self.assertTrue(checks['原生编译与本地签名']['ok'])
        self.assertNotIn('launch',checks['Metal 编译组件']['requiredFor'])
    def test_silent_initial_setup_failure_has_diagnostics_and_selected_xcode_repair(self):
        developer=self.root/"Xcode 中文's Beta.app/Contents/Developer"
        (developer/'Platforms/MacOSX.platform').mkdir(parents=True)
        self.c.r['developerDir']=str(developer)
        original=self.fake_probe
        def silent(c,args,**kw):
            if '-checkFirstLaunchStatus' in args:
                self.calls.append(list(map(str,args)));return False,''
            return original(c,args,**kw)
        with patch.object(self,'fake_probe',side_effect=silent):
            item=self.inspect()['Xcode 初始设置']
        self.assertFalse(item['ok'])
        self.assertIn('状态检查命令执行失败',item['message'])
        self.assertIn('No diagnostic output.',item['detail'])
        self.assertIn(shlex.quote('DEVELOPER_DIR='+str(developer)),item['detail'])
        self.assertEqual(shlex.split(item['repairCommand']),['sudo','/usr/bin/env','DEVELOPER_DIR='+str(developer),'/usr/bin/xcodebuild','-runFirstLaunch'])
        self.assertIn('接受许可',item['help'])
        self.assertFalse(any('-runFirstLaunch' in args or 'sudo' in args for args in self.calls))
        self.assertEqual(item['requiredFor'],['prepare'])
    def test_initial_setup_distinguishes_missing_xcode_license_and_timeout(self):
        (self.developer/'Platforms/MacOSX.platform').rmdir()
        item=self.inspect()['Xcode 初始设置']
        self.assertEqual(item['action'],'xcodeStore');self.assertNotIn('repairCommand',item)
        (self.developer/'Platforms/MacOSX.platform').mkdir()
        original=self.fake_probe
        for output,expected in [('You have not agreed to the Xcode license agreements.','许可尚未完成'),('工具检查超时，请重新检查或修复对应组件。','检查超时')]:
            def status(c,args,**kw):
                if '-checkFirstLaunchStatus' in args:return False,output
                return original(c,args,**kw)
            with patch.object(self,'fake_probe',side_effect=status):
                item=self.inspect()['Xcode 初始设置']
            self.assertFalse(item['ok']);self.assertIn(expected,item['message'])
            self.assertIn(output,item['detail'])
        item=self.inspect()['Xcode 初始设置']
        self.assertTrue(item['ok']);self.assertIn('已就绪',item['message'])
        self.assertNotIn('repairCommand',item)
    def test_silent_failed_probe_reports_exit_status(self):
        ok,diagnostic=toolchain.probe(self.c,[sys.executable,'-c','raise SystemExit(17)'])
        self.assertFalse(ok);self.assertIn('Exit status: 17',diagnostic)
        self.assertIn('No diagnostic output.',diagnostic)
    def test_disconnected_library_is_reported_without_creating_a_replacement(self):
        self.c.r['storageLibraryId']='external-drive'
        self.c.library=self.root/'offline'
        checks=self.inspect();self.assertFalse(checks['游戏库存储权限']['ok'])
        self.assertFalse(self.c.library.exists());self.assertFalse(checks['可用空间']['ok'])
    def test_low_space_is_prepare_only_and_noexec_is_a_launch_failure(self):
        self.fail={'execute-check'};checks=self.inspect()
        self.assertFalse(checks['游戏库存储权限']['ok']);self.assertIn('launch',checks['游戏库存储权限']['requiredFor'])
        self.fail=set()
        with patch('toolchain.shutil.disk_usage',return_value=type('Disk',(),{'free':1*2**30})()):
            # inspect's disk fixture is overridden directly for this call below.
            with patch('engine.sdk_candidates',return_value=[self.sdk_host]),patch('toolchain.probe',side_effect=self.fake_probe),patch('toolchain.metal_available',return_value=True),contextlib.redirect_stdout(io.StringIO()):
                checks={x['name']:x for x in toolchain.inspect_environment(self.c)}
        self.assertFalse(checks['可用空间']['ok']);self.assertNotIn('launch',checks['可用空间']['requiredFor'])
    def test_probe_timeout_kills_descendants_and_missing_binary_is_a_check_failure(self):
        ok,_=toolchain.probe(self.c,[self.root/'absent']);self.assertFalse(ok)
        pidfile=self.root/'pid';script=self.root/'probe.py'
        script.write_text('import subprocess,sys,time\np=subprocess.Popen([sys.executable,"-c","import time;time.sleep(300)"])\nopen(sys.argv[1],"w").write(str(p.pid))\ntime.sleep(300)\n')
        ok,_=toolchain.probe(self.c,[sys.executable,script,pidfile],timeout=1)
        self.assertFalse(ok);self.assertFalse(self.c.children)
        pid=int(pidfile.read_text());time.sleep(.1)
        with self.assertRaises(ProcessLookupError):os.kill(pid,0)


if __name__=='__main__':unittest.main()

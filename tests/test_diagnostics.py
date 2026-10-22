"""Real child-process error transport, shader warnings and private-data redaction."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'Worker'))
from core import Context, Failure, atomic, read
import build
import diagnostics


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="lumadock-diagnostics-中文's-")
        self.root=Path(self.temp.name).resolve()
        self.request=dict(schema=1,operation='build',privateRoot=str(self.root/'private'),
            library=str(self.root/'library'),resources=str(self.root/'resources'),engineDir=str(self.root/'engine'))
        self.c=Context(self.request);self.log=self.c.private/'logs/compiler.log'
    def tearDown(self):self.temp.cleanup()
    def quiet(self,fn,*args,**kwargs):
        with contextlib.redirect_stdout(io.StringIO()):return fn(*args,**kwargs)
    def script(self,text,name='dmsh_build.py'):
        path=self.root/name;path.write_text(text);return [sys.executable,path]

    def test_specific_error_classification_and_suggestions(self):
        samples=[
            ('No space left on device',None,'disk_full'),
            ('Operation not permitted',None,'permission_denied'),
            ("cannot execute tool 'metal' due to missing Metal Toolchain",1,'metal_toolchain_missing'),
            ('SDK "iphoneos" cannot be located',1,'sdk_missing'),
            ('translation chain tools do not match the lock file',1,'shader_chain_mismatch'),
            ('killed',-9,'memory_exhausted'),
            ('SPIRV-Cross: unsupported instruction',1,'shader_translation_failed'),
            ('file.metal:7: error: unknown type',1,'shader_compile_failed'),
            ('command not found',127,'component_missing'),
        ]
        for text,status,expected in samples:
            with self.subTest(expected=expected):
                result=diagnostics.failure(self.c,text,tool='fixture',status=status,log=self.log)
                self.assertEqual(result['code'],expected);self.assertTrue(result['suggestion'])
                self.assertEqual(result['logPath'],str(self.log))

    def test_nonzero_process_preserves_specific_log_stage_and_early_compiler_error(self):
        self.quiet(self.c.begin,'转换并编译 Metal 着色器')
        command=self.script("print('first.metal:9: error: unknown type')\nfor i in range(1000):print('build output',i,'x'*2000)\nraise SystemExit(2)\n")
        with self.assertRaises(Failure) as raised:self.quiet(self.c.run,command,self.log)
        diagnostic=raised.exception.diagnostic
        self.assertEqual(diagnostic['component'],'dmsh_build.py');self.assertEqual(diagnostic['exitCode'],2)
        self.assertIn('first.metal:9',diagnostic['detail']);self.assertLessEqual(len(diagnostic['detail']),3000)
        self.assertEqual(diagnostic['stage'],'转换并编译 Metal 着色器')
        self.assertEqual(read(self.c.jobpath)['diagnostics'],[diagnostic])
        self.quiet(self.c.report,diagnostic|{'detail':'updated compiler output'})
        self.assertEqual(len(self.c.job['diagnostics']),1)
        self.assertEqual(self.c.job['diagnostics'][0]['detail'],'updated compiler output')

    def test_partial_shader_success_is_warning_and_survives_checkpoint_reuse(self):
        root=self.root/'cache';root.mkdir();artifact=root/'shader.metallib'
        command=self.script("print('shaders 100: ok 97, translation failed 3')\n")
        def compile():self.c.run(command,self.log);artifact.write_text('synthetic')
        self.quiet(build.Stages(self.c,root).run,'编译着色器',[artifact],compile)
        warning=self.c.job['diagnostics'][0]
        self.assertEqual(warning['code'],'shader_partial');self.assertEqual(warning['severity'],'warning')
        recovered=Context(self.request)
        def must_not_run():self.fail('a valid checkpoint should be reused')
        self.quiet(build.Stages(recovered,root).run,'编译着色器',[artifact],must_not_run)
        self.assertEqual(recovered.job['diagnostics'],[warning])
        self.quiet(recovered.finish,'completed','操作完成')
        self.assertIn('警告',read(recovered.jobpath)['message'])

    def test_zero_success_is_failure_even_when_shader_tool_exits_zero(self):
        root=self.root/'cache';root.mkdir();artifact=root/'empty'
        command=self.script("print('shaders 10: ok 0, metal failed 10')\n")
        def compile():artifact.write_text('partial');self.c.run(command,self.log)
        stages=build.Stages(self.c,root)
        with self.assertRaises(Failure) as raised:self.quiet(stages.run,'编译着色器',[artifact],compile)
        self.assertEqual(raised.exception.diagnostic['code'],'shader_empty');self.assertEqual(stages.saved,{})

    def test_success_does_not_replay_old_appended_log_errors(self):
        self.log.parent.mkdir(parents=True);self.log.write_text('old.metal:1: error: obsolete\n')
        self.quiet(self.c.run,self.script("print('shaders 10: ok 10, ')\n"),self.log)
        self.assertFalse(self.c.job.get('diagnostics'))

    def test_missing_executable_is_actionable_and_not_an_unhandled_traceback(self):
        with self.assertRaises(Failure) as raised:self.quiet(self.c.run,[self.root/'missing-tool'],self.log)
        self.assertEqual(raised.exception.diagnostic['code'],'component_missing')

    def test_redaction_removes_credentials_and_private_paths(self):
        secret='a'*64
        raw=f'header_key = {secret}\nAuthorization: token=abc123\nAuthorization: Bearer bearer-secret\nhttps://user:linkpass@example.invalid\npassword="privatepass"\n{self.c.library}/游戏.nsp {self.c.engine}/tool {self.c.private}/keys/prod.keys'
        result=diagnostics.redact(raw,self.c)
        for value in (secret,'abc123','privatepass','bearer-secret','linkpass',str(self.c.library),str(self.c.engine),str(self.c.private)):self.assertNotIn(value,result)
        self.assertIn('[LIBRARY]',result);self.assertIn('[REDACTED]',result)

    def test_worker_result_contains_persistent_structured_failure(self):
        request=self.root/'request.json';atomic(request,self.request)
        result=subprocess.run([sys.executable,'-B','-I',str(ROOT/'Worker/main.py'),'--request',str(request)],capture_output=True,text=True)
        self.assertEqual(result.returncode,1)
        events=[json.loads(line) for line in result.stdout.splitlines()]
        final=events[-1];self.assertEqual(final['state'],'failed')
        self.assertEqual(final['diagnostics'][0]['code'],'task_failed')
        record=read(self.c.private/'jobs'/f"{final['taskId']}.json")
        self.assertEqual(record['diagnostics'],final['diagnostics'])


if __name__=='__main__':unittest.main()

#!/usr/bin/env python3
import argparse, json, os, signal, sys, traceback, subprocess, threading, time
from pathlib import Path
from core import Context, Failure, Cancelled
import library, build, input_config, toolchain

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--request',required=True); args=parser.parse_args()
    path=Path(args.request)
    if path.stat().st_mode & 0o077: raise SystemExit('request file must be private (0600)')
    request=json.loads(path.read_text())
    if request.get('schema')!=1: raise SystemExit('unsupported request schema')
    c=Context(request)
    def stop(sig,frame): c.stop(); raise Cancelled()
    signal.signal(signal.SIGTERM,stop); signal.signal(signal.SIGINT,stop)
    # Register every subprocess, including upstream runtime capture and shader grandchildren.
    real_popen = subprocess.Popen
    def spawn(*a, **kw):
        kw['start_new_session'] = True
        p = real_popen(*a, **kw); c.children.add(p); return p
    subprocess.Popen = spawn
    parent = request.get('parentPid')
    def supervise():
        while parent and not c.cancelled:
            time.sleep(1)
            try: os.kill(parent, 0)
            except ProcessLookupError:
                os.kill(os.getpid(), signal.SIGTERM); return
    threading.Thread(target=supervise, daemon=True).start()
    ops={'installMetal':toolchain.install_metal,'uninstallMetal':toolchain.uninstall_metal,'setup':library.setup,'preflight':library.preflight,'keys':library.keys,'import':library.import_games,'catalog':library.catalog,'remove':library.remove,'clean':library.clean,'diagnostics':library.diagnostics,'build':build.build,'migrate':build.migrate,'launch':build.launch,'saveInput':input_config.save,'defaultInput':lambda c:input_config.defaults()}
    try:
        if request['operation'] not in ops: raise Failure('不支持的任务类型。')
        operation=request['operation']
        if operation in ('installMetal','uninstallMetal','build','migrate','launch'):
            with c.toolchain_lock(exclusive=operation in ('installMetal','uninstallMetal')):
                result=ops[operation](c)
        else:
            result=ops[operation](c)
        c.finish('completed','操作完成',result)
        return 0
    except (Cancelled,KeyboardInterrupt):
        c.stop(); c.finish('cancelled','任务已取消；上次成功的运行版本和存档已保留。'); return 130
    except Exception as e:
        # Exceptions never include file contents; full tool output remains in local allowlisted logs.
        message=str(e) if isinstance(e,Failure) else '操作失败，请检查磁盘连接、权限和任务日志后重试。'
        if not isinstance(e,Failure):
            p=c.private/'logs'/f'{c.task}-worker.log'; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(traceback.format_exc())
        c.finish('failed',message); return 1
if __name__=='__main__': sys.exit(main())

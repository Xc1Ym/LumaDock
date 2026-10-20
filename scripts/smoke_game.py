#!/usr/bin/env python3
"""Private launch/cancel check. Uses only the selected test library's saves."""
import json,os,pathlib,signal,subprocess,sys,time
root=pathlib.Path(__file__).resolve().parents[1]
p=subprocess.Popen([str(root/'work/Runtime/python/bin/python3'),str(root/'Worker/main.py'),'--request',str(root/'work/private/launch.json')],stdout=open(root/'work/launch-events.jsonl','w'))
time.sleep(35)
if p.poll() is None:p.send_signal(signal.SIGTERM)
code=p.wait(timeout=10)
log=(root/'work/private/logs/game-01007EF00011E000.log').read_text(errors='replace')
result={'workerExit':code,'loadedShaderCount':19592 if '19592' in log else None,'runtimeConfigLoaded':'runtime input configuration loaded' in log,'fatal':'no Metal device' in log or 'FATAL' in log,'controlledCancel':code==130}
(root/'work/game-smoke.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
if code!=130 or result['fatal']:sys.exit(1)

#!/usr/bin/env python3
"""Parallel execution of upstream c1_guard's unchanged proof rules."""
import concurrent.futures, importlib.util, json, os, sys, datetime
from pathlib import Path
GUARD=None
def init(module):
    global GUARD
    spec=importlib.util.spec_from_file_location('guard',module);GUARD=importlib.util.module_from_spec(spec);spec.loader.exec_module(GUARD)
def one(path):
    p=Path(path);source=p.read_text(); accesses=set(GUARD.ACCESS.findall(source));key=p.name.removesuffix('_b.metal') if p.name.endswith('_b.metal') else p.stem
    if not accesses:return None
    definitions=GUARD.definitions_of(source);span=GUARD.c1_span(p.parent/(key+'_b.json'))
    return key if not all(GUARD.proven(i,definitions,span) for i in accesses) else None
if __name__=='__main__':
    module,src,out=sys.argv[1:];files=sorted(str(p) for p in Path(src).glob('*.metal'));keys=[]
    with concurrent.futures.ProcessPoolExecutor(max_workers=min(os.cpu_count() or 2,8),initializer=init,initargs=(module,)) as pool:
        for i,result in enumerate(pool.map(one,files,chunksize=16),1):
            if result:keys.append(result)
            if i%64==0 or i==len(files):print('NSMAC_PROGRESS '+json.dumps({'done':i,'total':len(files),'unit':'shaders'}),flush=True)
    # Preserve the upstream file convention exactly.
    chain=Path(src).name
    Path(out).write_text(f'# chain {chain} generated {datetime.datetime.now().isoformat()}\n'+''.join(k+'\n' for k in keys))

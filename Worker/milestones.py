"""Game milestone plans/history adapted from S2Arm pack/jobs/milestones.py.

Source: jhaizhou-ops/S2Arm at 601b5454 (2026-10-24). LumaDock's nxnative
stages differ; only stages it actually executes are planned. Shader counters
continue to count nxnative's completed reflection/Metal-library pairs.
"""
from __future__ import annotations
import hashlib
import json
import math
import statistics
import time
from core import atomic, read

# Initial weights are reference estimates adapted from S2Arm, not LumaDock
# benchmarks. Successful uncached runs replace them with local medians.
REFERENCE_GB = 5.4
STEPS = {
    'verify': ('校验游戏文件', '确认源文件与已登记的内容一致。', 20, True),
    'unpack': ('解包与合并', '解出程序与资源，并合并所需更新。', 15, True),
    'dlc': ('处理 DLC', '准备该游戏已导入的附加内容。', 5, True),
    'rewrite': ('重写原生代码', '将游戏程序转换为引擎所需的原生代码。', 60, False),
    'capture_gl': ('采集运行时 GLSLC 着色器', '采集当前配置所需的运行时着色器。', 300, False),
    'capture_vk': ('采集运行时 Vulkan 着色器', '采集当前配置所需的运行时着色器。', 300, False),
    'extract': ('提取并核对着色器', '从游戏资源中提取并核对着色器。', 60, True),
    'shaders': ('转换并编译着色器', '转换着色器并校验已完成的 Metal 产物。', 820, True),
    'host': ('编译 Mac 主程序', '编译并检查 Mac 游戏主程序。', 30, False),
    'install': ('检查并安装运行版本', '校验资源并安装到新的运行版本。', 60, True),
    'ipa': ('编译 iOS 应用并生成 IPA', '编译 iPhone 与 iPad 应用并生成安装包。', 150, False),
    'ipa_check': ('验证 IPA 完整性', '检查安装包结构与所有成员的完整性。', 20, True),
    'ipa_export': ('导出 IPA', '验证复制结果后导出安装包。', 10, True),
}


def positive(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 < value < 315360000


def history_path(c):
    return c.private/'stats'/('prepare-'+c.milestone_history+'.json')


def history(c):
    try:
        rows=read(history_path(c),[])
        return rows if isinstance(rows,list) else []
    except (OSError,ValueError):return []


def plan(c, game, target, versions, profile, identity):
    size = max(.1, sum(p.get('size', 0) for p in game['packages']) / 1e9)
    history_id = hashlib.sha256(json.dumps(dict(game=game['id'], target=target,
        tools=identity.get('tools', {})), sort_keys=True).encode()).hexdigest()[:24]
    c.milestone_history=history_id;c.milestone_size=size
    rows=history(c)
    ids=['verify']+[f'unpack-{i}' for i in range(len(versions))]+['dlc','rewrite']
    for key in ('capture_gl','capture_vk'):
        if profile.get('shader_glslc_capture' if key=='capture_gl' else 'shader_vk_capture','off')=='on':ids.append(key)
    if profile.get('graphics','nvn')!='vulkan':ids.append('extract')
    ids+=['shaders']+(['ipa','ipa_check','ipa_export'] if target=='ios' else ['host','install'])
    result=[]
    for mid in ids:
        kind='unpack' if mid.startswith('unpack-') else mid
        label,purpose,default,scaled=STEPS[kind];samples=[]
        for row in rows[-50:]:
            if not isinstance(row,dict):continue
            sec=row.get('seconds',{});gb=row.get('size_gb')
            if not isinstance(sec,dict) or not positive(gb) or not positive(sec.get(mid)):continue
            samples.append(sec[mid]/gb*size if scaled else sec[mid])
        expected=statistics.median(samples) if samples else default*(size/REFERENCE_GB if scaled else 1)
        result.append(dict(id=mid,label=label,purpose=purpose,expected=round(min(315359999,max(.1,expected)),1),
            source='history' if samples else 'default',samples=len(samples)))
    c.milestones=result;c.milestone=None;c.milestone_started={};c.milestone_times={};c.milestone_cached=set()
    for field in ('milestone','milestoneStarted'):c.job.pop(field,None)
    c.job.update(milestones=result,milestoneCached=[]);atomic(c.jobpath,c.job)
    c.emit('plan','准备计划',milestones=result)


def enter(c, mid, stage=None):
    rows=getattr(c,'milestones',[])
    item=next((row for row in rows if row['id']==mid),None)
    if item is None:
        if stage:c.begin(stage)
        return
    with c.guard:
        c.check()
        if c.milestone!=mid:
            now=time.monotonic()
            if c.milestone in c.milestone_times:
                start,_=c.milestone_times[c.milestone];c.milestone_times[c.milestone]=(start,now)
            c.milestone_times[mid]=(now,None)
            c.milestone_started[mid]=time.time();c.milestone=mid
        c.job.update(milestone=mid,milestoneStarted=dict(c.milestone_started))
        c.begin(stage or item['label'])


def cached(c):
    if getattr(c,'milestone',None):
        c.milestone_cached.add(c.milestone)
        c.job['milestoneCached']=sorted(c.milestone_cached);atomic(c.jobpath,c.job)


def record(c):
    """Only successful, uncached stage durations may train later estimates."""
    if c.cancelled or not getattr(c,'milestone_times',None):return
    now=time.monotonic()
    seconds={mid:round((end or now)-start,3) for mid,(start,end) in c.milestone_times.items()
        if mid not in c.milestone_cached and positive((end or now)-start)}
    if not seconds:return
    try:atomic(history_path(c),(history(c)+[dict(size_gb=c.milestone_size,seconds=seconds)])[-50:])
    except OSError:pass

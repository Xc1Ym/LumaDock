import math
from core import Failure, atomic
TARGETS=['A','B','X','Y','LS','RS','L','R','ZL','ZR','PLUS','MINUS','LEFT','UP','RIGHT','DOWN','LS_UP','LS_DOWN','LS_LEFT','LS_RIGHT','RS_UP','RS_DOWN','RS_LEFT','RS_RIGHT']
PAD=['east','south','north','west','leftStick','rightStick','leftShoulder','rightShoulder','leftTrigger','rightTrigger','menu','options','dpadLeft','dpadUp','dpadRight','dpadDown']
def defaults():
    keys={'A':14,'B':56,'X':49,'L':12,'R':5,'ZR':15,'LS':59,'RS':8,'PLUS':48,'MINUS':46,'LEFT':123,'UP':126,'RIGHT':124,'DOWN':125,'LS_UP':13,'LS_DOWN':1,'LS_LEFT':0,'LS_RIGHT':2}
    return {'schema':1,'keyboard':{k:{'code':v,'modifiers':0} for k,v in keys.items()},'mouse':{'Y':0,'ZL':1},'gamepad':dict(zip(TARGETS[:16],PAD)),'axes':{k:{'source':v,'invert':False} for k,v in zip(['LX','LY','RX','RY'],['leftX','leftY','rightX','rightY'])},'mouseOptions':{'mode':'camera','sensitivityX':1.0,'sensitivityY':1.0,'invertX':False,'invertY':False,'recenter':True},'deadzone':0.15}
def validate(v):
    if v.get('schema')!=1: raise Failure('不支持的输入配置版本。')
    for device in ['keyboard','mouse','gamepad']:
        seen=set()
        for target,b in v.get(device,{}).items():
            if target not in TARGETS: raise Failure('输入配置包含未知目标。')
            if device=='keyboard':
                code=b.get('code'); mods=b.get('modifiers',0)
                if not isinstance(code,int) or not 0<=code<=127 or code==53 or not isinstance(mods,int) or mods<0 or mods>7: raise Failure('无效的键盘绑定（Esc 保留给鼠标捕获）。')
                code={60:56,62:59,61:58}.get(code,code)
                if code in (54,55): raise Failure('Command 保留给系统快捷键。')
                physical=(code,mods)
            elif device=='mouse':
                if b not in range(5): raise Failure('不支持的鼠标按钮。')
                physical=b
            else:
                if b not in PAD: raise Failure('不支持的手柄按钮。')
                physical=b
            if physical in seen: raise Failure(f'{device} 存在重复绑定，请先解除冲突。')
            seen.add(physical)
    seen=set()
    for target,b in v.get('axes',{}).items():
        if target not in ('LX','LY','RX','RY') or b.get('source') not in ('leftX','leftY','rightX','rightY'): raise Failure('手柄摇杆配置无效。')
        if b['source'] in seen: raise Failure('手柄轴存在重复绑定。')
        seen.add(b['source'])
    m=v.get('mouseOptions',{})
    for key in ('sensitivityX','sensitivityY'):
        x=m.get(key,1)
        if not isinstance(x,(int,float)) or not math.isfinite(x) or not .1<=x<=10: raise Failure('鼠标灵敏度应在 0.1–10 之间。')
    if m.get('mode') not in ('camera','touch'): raise Failure('鼠标模式无效。')
    if not 0<=v.get('deadzone',.15)<.9: raise Failure('手柄死区无效。')

def save(c):
    v=c.r['config']; validate(v)
    if c.r.get('gameId'): c.check()
    target=c.library/'mappings'/f"{c.r['gameId']}.json" if c.r.get('gameId') else c.private/'default-input.json'
    atomic(target,v); return {'path':str(target)}

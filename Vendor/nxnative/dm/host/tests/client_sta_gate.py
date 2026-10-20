# Executes only the client STA gate/rule trampoline after the original GetStat; the end uses an explicit STOP stand-in, and neither the original getter nor the real Move speed is verified.
import sys,struct
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm64_const import *
b=Path(sys.argv[1]).read_bytes();u=Uc(UC_ARCH_ARM64,UC_MODE_ARM);u.mem_map(0,0x4000000);u.mem_write(0,b);u.mem_map(0x7000000,0x10000)
UNIT=0x7001000;ctx={}
def hook(u,a,n,d):
 if a in [0x4ac36c,0x4ac3f4]:ctx['target']=a;u.emu_stop()
u.hook_add(UC_HOOK_CODE,hook);bad=0;n=0
for kind in [0,1,2,3,4,5,6,99]:
 for sta in [0,1,22016,0xffffffff]:
  ctx.clear();u.mem_write(UNIT,struct.pack('<I',kind));u.reg_write(UC_ARM64_REG_X19,UNIT);u.reg_write(UC_ARM64_REG_W0,sta);u.reg_write(UC_ARM64_REG_SP,0x700f000);u.reg_write(UC_ARM64_REG_NZCV,0xa0000000)
  u.emu_start(0x4ac368,0x4000000,count=100)
  target=0x4ac3f4 if kind==0 or sta else 0x4ac36c
  ok=ctx.get('target')==target and u.reg_read(UC_ARM64_REG_W0)==sta and u.reg_read(UC_ARM64_REG_X19)==UNIT and u.reg_read(UC_ARM64_REG_SP)==0x700f000 and u.reg_read(UC_ARM64_REG_NZCV)==0xa0000000
  n+=1
  if not ok:bad+=1;print('FAIL type',kind,'STA',sta,'expected',hex(target),'→ got',ctx)
print(f'CLIENT_STA_GATE {n} cases, {bad} failed; only type0 skips the STA auto Stop, non-player keeps the original zero / non-zero branch, original W0/X19/SP/NZCV unchanged; the end is a stand-in')
sys.exit(bool(bad))

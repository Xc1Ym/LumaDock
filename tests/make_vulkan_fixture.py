"""Original minimal SPIR-V fixtures; contains no game or proprietary shader data."""
import pathlib,struct,sys
out=pathlib.Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
def instruction(op,*args):return [((len(args)+1)<<16)|op,*args]
def string(s):
 b=s.encode()+b'\0';b+=b'\0'*((-len(b))%4);return list(struct.unpack('<'+'I'*(len(b)//4),b))
for stage,model in [('vert',0),('frag',4)]:
 w=[0x07230203,0x00010000,0,12,0]
 def op(code,*args):w.extend(instruction(code,*args))
 op(17,1);op(14,0,1);op(15,model,10,*string('main'),6)
 if model==4:op(16,10,7)
 op(71,6,11 if model==0 else 30,0)
 op(19,1);op(33,2,1);op(22,3,32);op(23,4,3,4);op(32,5,3,4);op(59,5,6,3)
 op(43,3,7,0);op(43,3,8,0x3f800000);op(44,4,9,7,7,7,8)
 op(54,1,10,0,2);op(248,11);op(62,6,9);op(253);op(56)
 (out/(stage+'.spv')).write_bytes(struct.pack('<'+'I'*len(w),*w))

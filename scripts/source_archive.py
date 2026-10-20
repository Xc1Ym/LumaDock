#!/usr/bin/env python3
"""Export rebuildable sources using the same explicit private-data boundary as releases."""
import pathlib,zipfile,os
from product import ROOT,RELEASE,PRODUCT,checksums
EXCLUDED={'work','release','.build','.git','Runtime','__pycache__','bin','obj','gen','.agents','.codex'}
SOURCE_DIRS={'Sources','Worker','Vendor','Assets','scripts','tests','docs','.github'}
SOURCE_ARTWORK={f'Assets/LumaDock{x}' for x in ('.png','.svg','.icns','.ico')} | {f'docs/screenshots/{screen}-{language}.jpg' for screen in ('library','setup','settings') for language in ('en','zh')}
SOURCE_FILES={'Package.swift','product.json','requirements-runtime.txt','README.md','README.zh-CN.md','LICENSE','.gitignore'}
def main():
 out=RELEASE/f"{PRODUCT['name']}-{PRODUCT['version']}-source.zip";out.parent.mkdir(exist_ok=True)
 count=0
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for directory,dirs,names in os.walk(ROOT):
   dirs[:]=sorted(d for d in dirs if d not in EXCLUDED and (pathlib.Path(directory)!=ROOT or d in SOURCE_DIRS))
   for name in sorted(names):
    p=pathlib.Path(directory)/name;rel=p.relative_to(ROOT)
    if pathlib.Path(directory)==ROOT and name not in SOURCE_FILES:continue
    if p.is_symlink() or not p.is_file() or any(part in EXCLUDED for part in rel.parts) or p.name=='.DS_Store':continue
    if p.suffix in ('.keys','.nsp','.xci','.nsz','.ipa','.metallib','.pyc') or p.name=='dmhost':raise RuntimeError('Unexpected generated/private asset: '+str(rel))
    if p.suffix.lower() in ('.png','.jpg','.jpeg','.webp','.ico','.icns','.svg') and str(rel) not in SOURCE_ARTWORK:raise RuntimeError('Unexpected source artwork: '+str(rel))
    z.write(p,PRODUCT['name']+'/'+str(rel));count+=1
 checksums()
 print('Source archive:',out,'files:',count)
if __name__=='__main__':main()

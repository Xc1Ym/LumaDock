#!/usr/bin/env python3
"""Collect pinned SAK-Mac conversion backends on the release builder, never at runtime."""
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from product import ROOT

UPSTREAM = {
    'SAK-Mac': ('ggaoph-lab/SAK-Mac', 'c8e0baa59a168d9efaa0b556af70e0a08bda51de'),
    'NSC_BUILDER': ('julesontheroad/NSC_BUILDER', 'e9083e83383281bdd9e167d3141163dcc56b6710'),
    'nsz': ('nicoboss/nsz', '4aea60e8ea7cb1099f286fc57cc7aade6338f32c'),
}
# Provide corresponding source for redistributed GPL/MPL dependencies as well as
# each wheel's original license/notice files. All other package sources are linked
# with their exact versions and published hashes in the manifest.
SOURCE_PACKAGES = {'unidecode','pykakasi','enlighten','jinxed','prefixed','certifi','tqdm'}


def fetch(url, destination, sha256=None):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.is_file():
        temporary=destination.with_suffix(destination.suffix+'.partial')
        try:
            with urllib.request.urlopen(url, timeout=90) as source, temporary.open('wb') as target:
                shutil.copyfileobj(source,target)
            temporary.replace(destination)
        finally: temporary.unlink(missing_ok=True)
    digest=hashlib.sha256(destination.read_bytes()).hexdigest()
    if sha256 and digest!=sha256: raise RuntimeError('Source archive hash mismatch: '+str(destination))
    return digest


def unpack(archive, destination):
    with tarfile.open(archive) as tar:
        tar.extractall(destination,filter='data')
    children=list(destination.iterdir())
    if len(children)!=1 or not children[0].is_dir(): raise RuntimeError('Unexpected source archive layout')
    return children[0]


def copy_code(source, destination):
    """Do not redistribute databases, player content, keys, artwork or Windows tools."""
    for path in source.rglob('*'):
        rel=path.relative_to(source)
        if path.is_symlink(): raise RuntimeError('Unexpected converter source link: '+str(rel))
        if not path.is_file() or any(p in {'DB','web','bin','__pycache__','.git'} for p in rel.parts): continue
        if path.suffix.lower() not in {'.py','.json','.txt','.md'} and 'LICENSE' not in path.name.upper(): continue
        if 'key' in path.name.lower() and path.suffix!='.py': continue
        target=destination/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)


def build(destination):
    cache=ROOT/'work/converter-downloads';cache.mkdir(parents=True,exist_ok=True)
    destination.mkdir(parents=True)
    manifest={'upstream':{},'packages':[]}
    with tempfile.TemporaryDirectory(prefix='converter-build-',dir=ROOT/'work') as directory:
        folder=pathlib.Path(directory);sources={}
        for name,(repo,commit) in UPSTREAM.items():
            url=f'https://api.github.com/repos/{repo}/tarball/{commit}'
            archive=cache/(name+'-'+commit+'.tar.gz')
            digest=fetch(url,archive)
            manifest['upstream'][name]={'repository':'https://github.com/'+repo,'commit':commit,'sha256':digest}
            sources[name]=unpack(archive,folder/name)
        patch=sources['SAK-Mac']/'patches/nscb-macos.patch'
        subprocess.run(['git','apply','--no-index',str(patch)],cwd=sources['NSC_BUILDER'],check=True)
        copy_code(sources['NSC_BUILDER']/'py/ztools',destination/'NSC_BUILDER/ztools')
        copy_code(sources['NSC_BUILDER']/'py/zconfig',destination/'NSC_BUILDER/zconfig')
        packages=destination/'python'
        subprocess.run([sys.executable,'-m','pip','install','--disable-pip-version-check','--no-compile',
                        '--target',str(packages),'-r',str(ROOT/'requirements-conversion.txt')],check=True)
        copy_code(sources['nsz']/'nsz',packages/'nsz')
        shutil.copy2(sources['nsz']/'nsz.py',destination/'nsz.py')
        shutil.rmtree(packages/'bin',ignore_errors=True)
        for path in packages.rglob('__pycache__'): shutil.rmtree(path)
        for path in packages.glob('*.dist-info/direct_url.json'):path.unlink()
        licenses=destination/'licenses';licenses.mkdir()
        for name,filename in [('SAK-Mac','LICENSE'),('NSC_BUILDER','LICENSE'),('nsz','LICENSE.md')]:
            shutil.copy2(sources[name]/filename,licenses/(name+'-LICENSE.txt'))
        shutil.copy2(patch,licenses/'nscb-macos.patch')
        shutil.copy2(ROOT/'requirements-conversion.txt',destination/'requirements.txt')
        # Retain package metadata (including nested licenses), and exact source
        # distributions for components whose source-distribution terms require it.
        for info in sorted(packages.glob('*.dist-info/METADATA')):
            from email.parser import BytesParser
            meta=BytesParser().parsebytes(info.read_bytes());name=meta['Name'];version=meta['Version']
            with urllib.request.urlopen(f'https://pypi.org/pypi/{name}/{version}/json',timeout=60) as response:
                release=json.load(response)
            sdists=[file for file in release['urls'] if file['packagetype']=='sdist']
            if not sdists: raise RuntimeError('Missing corresponding source: '+name)
            source=sdists[0]
            record={'name':name,'version':version,'source':source['url'],'sha256':source['digests']['sha256']}
            if name.lower() in SOURCE_PACKAGES:
                archive=cache/source['filename'];fetch(source['url'],archive,record['sha256'])
                target=destination/'sources'/source['filename'];target.parent.mkdir(exist_ok=True);shutil.copy2(archive,target)
                record['bundledSource']='sources/'+source['filename']
            manifest['packages'].append(record)
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')


def main():
    output=ROOT/'work/Converter'
    with tempfile.TemporaryDirectory(prefix='converter-stage-',dir=ROOT/'work') as directory:
        stage=pathlib.Path(directory)/'converter';build(stage)
        previous=output.with_suffix('.previous');shutil.rmtree(previous,ignore_errors=True)
        if output.exists(): output.rename(previous)
        stage.rename(output);shutil.rmtree(previous,ignore_errors=True)
    print('Pinned converter ready:',output)


if __name__=='__main__': main()

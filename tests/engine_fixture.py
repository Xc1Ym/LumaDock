"""Original protocol fixtures, not nxnative sources or executable engine code."""
from pathlib import Path
import hashlib
from core import atomic, digest
import engine

def make_engine(root):
    root=Path(root)
    for name in engine.REQUIRED:
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('# protocol fixture\n')
    (root/'scripts/build_ipa_from_nsp.py').write_text('\n'.join('def '+name+'(*args): pass' for name in ('extract','extract_aoc','rewrite','split_shaders','build_mac_host'))+'\nclass Progress: pass\n')
    (root/'dm/tools/nx_extract/Program.cs').write_text('static class P { static int Main(string[] a) { return 0; } void OpenNsp() {} void Nacp() {} void TitleName() {} void Icon() {} }')
    (root/'dm/gfx/tools/dmsh_chain.py').write_text("def tools_now():\n    for sdk in ('macosx', 'iphoneos'):\n        pass\n")
    for tid in ('01007EF00011E000','0100000000010000'):
        path=root/'dm/games'/tid/'game.tsv';path.parent.mkdir()
        path.write_text('name\tProtocol fixture\npackage\tv1114112\nmodules\tmain\nbuild\tv1114112\t1.0\tmain=fixture-build\n')
    return root

def mark_prepared(c):
    info=engine.inspect_source(c);root=engine.prepared_root(c,info)
    source=root/'source';source.mkdir(parents=True,exist_ok=True);(source/'.source-ready').write_text(info['fingerprint'])
    tools=root/'tools/nx_extract';tools.mkdir(parents=True,exist_ok=True)
    for name in ('nx_extract','nx_extract.dll','LibHac.dll','nx_extract.runtimeconfig.json'):
        path=tools/name;path.write_text('original protocol fixture');path.chmod(0o700)
    atomic(root/'ready.json',dict(info,snapshotHash=engine.source_hash(source),files={str(p.relative_to(root)):digest(p) for p in tools.iterdir()}))
    return root

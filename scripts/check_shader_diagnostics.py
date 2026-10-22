#!/usr/bin/env python3
"""Compile original Metal samples and an unsigned iOS fixture, without player data."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Worker'))
from core import Context, Failure
import ipa


def main():
    root=ROOT/'work/shader-diagnostics-smoke';root.mkdir(parents=True,exist_ok=True)
    report={}
    for sdk in ('macosx','iphoneos'):
        c=Context(dict(operation='build',privateRoot=str(root/sdk),resources=str(ROOT),
                       developerDir=os.environ.get('DEVELOPER_DIR','/Applications/Xcode.app/Contents/Developer')))
        env=c.env();env['PATH']+=':/opt/homebrew/bin:/usr/local/bin'
        source=c.private/'sample.metal'
        source.write_text('#include <metal_stdlib>\nusing namespace metal;\nkernel void probe(device uint *values [[buffer(0)]], uint i [[thread_position_in_grid]]) { values[i] = i; }\n')
        air=c.private/'sample.air';library=c.private/'sample.metallib';log=c.private/'logs/metal.log'
        with contextlib.redirect_stdout(io.StringIO()):
            c.begin('转换并编译 Metal 着色器')
            c.run(['xcrun','--sdk',sdk,'metal','-c',source,'-o',air],log,env)
            c.run(['xcrun','--sdk',sdk,'metallib',air,'-o',library],log,env)
            source.write_text('#include <metal_stdlib>\nkernel void invalid( {\n')
            try:c.run(['xcrun','--sdk',sdk,'metal','-c',source,'-o',air],log,env)
            except Failure as error:
                assert error.diagnostic['code']=='shader_compile_failed',error.diagnostic
                assert '[PRIVATE]' in error.diagnostic['detail']
                assert str(c.private) not in error.diagnostic['detail']
                report[sdk]=dict(compiled=True,errorCode=error.diagnostic['code'],redacted=True)
            else:raise AssertionError('Invalid shader unexpectedly compiled')
        assert library.stat().st_size>0
    # Build a small original UIKit app with real Xcode, then validate its IPA
    # structure and CRCs with the production exporter. This is not a game test.
    fixture=root/'ios-app';fixture.mkdir(exist_ok=True)
    (fixture/'main.m').write_text('''#import <UIKit/UIKit.h>
@interface FixtureDelegate : UIResponder <UIApplicationDelegate>
@property(strong,nonatomic) UIWindow *window;
@end
@implementation FixtureDelegate
- (BOOL)application:(UIApplication *)app didFinishLaunchingWithOptions:(NSDictionary *)options {
    self.window=[[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
    self.window.rootViewController=[UIViewController new];[self.window makeKeyAndVisible];return YES;
}
@end
int main(int argc,char **argv) { @autoreleasepool { return UIApplicationMain(argc,argv,nil,NSStringFromClass(FixtureDelegate.class)); } }
''')
    (fixture/'project.yml').write_text('''name: LumaShaderFixture
targets:
  LumaShaderFixture:
    type: application
    platform: iOS
    deploymentTarget: "26.0"
    sources: [main.m]
    settings:
      PRODUCT_BUNDLE_IDENTIFIER: org.lumadock.shaderfixture
      GENERATE_INFOPLIST_FILE: YES
      CODE_SIGNING_ALLOWED: NO
schemes:
  LumaShaderFixture:
    build:
      targets:
        LumaShaderFixture: all
''')
    generator=shutil.which('xcodegen',path=env['PATH'])
    assert generator,'Install XcodeGen before running the iOS packaging smoke test'
    with contextlib.redirect_stdout(io.StringIO()):
        c.run([generator,'generate'],fixture/'xcode.log',env,cwd=fixture)
        c.run(['xcodebuild','-project','LumaShaderFixture.xcodeproj','-scheme','LumaShaderFixture','-configuration','Release','-destination','generic/platform=iOS','-derivedDataPath',fixture/'derived','CODE_SIGNING_ALLOWED=NO','CODE_SIGNING_REQUIRED=NO','CODE_SIGN_IDENTITY=','build'],fixture/'xcode.log',env,cwd=fixture)
        app=fixture/'derived/Build/Products/Release-iphoneos/LumaShaderFixture.app'
        output=fixture/'synthetic.ipa'
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(app.rglob('*')):
                if path.is_file():archive.write(path,'Payload/LumaShaderFixture.app/'+str(path.relative_to(app)))
            archive.writestr('Payload/LumaShaderFixture.app/romfs/fixture.txt','Original synthetic resources')
            archive.write(library,'Payload/LumaShaderFixture.app/msl/vk/fixture.metallib')
        ipa.validate(output,c)
    report['iosApp']=dict(built=True,unsigned=True,ipaValidated=True,commercialGame=False)
    (ROOT/'work/shader-diagnostics-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':main()

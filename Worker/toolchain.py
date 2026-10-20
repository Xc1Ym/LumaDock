"""Manage Apple's shared Metal component through xcodebuild only."""
import subprocess
from core import Failure


def supports_removal(c):
    try:
        result = subprocess.run(['xcodebuild', '-help'], env=c.env(), capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return '-deleteComponent' in result.stdout + result.stderr


def install_metal(c):
    c.begin('安装 Apple Metal 编译组件', 1, 1)
    c.run(['xcodebuild', '-downloadComponent', 'MetalToolchain'])
    return {}


def uninstall_metal(c):
    if c.r.get('confirmed') is not True:
        raise Failure('请先确认卸载共享 Metal 编译组件。')
    if not supports_removal(c):
        raise Failure('当前 Xcode 不支持命令行卸载组件，请在 Xcode 的组件设置中管理。')
    c.begin('卸载 Apple Metal 编译组件', 1, 1)
    c.run(['xcodebuild', '-deleteComponent', 'MetalToolchain'])
    return {}

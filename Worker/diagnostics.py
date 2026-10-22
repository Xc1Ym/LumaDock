"""Bounded, redacted task diagnostics shared by subprocesses and worker failures."""
from collections import deque
from pathlib import Path
import re


def redact(text, c, limit=3000):
    text = re.sub(r'\x1b\[[0-9;]*m', '', str(text))
    text = re.sub(r'(?i)(authorization\s*:\s*(?:bearer|basic|token)\s+)\S+',r'\1[REDACTED]',text)
    text = re.sub(r'(?i)(https?://)[^/\s:@]+:[^/\s@]+@',r'\1[REDACTED]@',text)
    text = re.sub(r'(?i)([\w-]*(?:key|secret|token|password)[\w-]*\s*[=:]\s*)[\"\']?[^\s,;\"\']+', r'\1[REDACTED]', text)
    text = re.sub(r'\b[0-9a-fA-F]{64,}\b', '[REDACTED]', text)
    for path, label in ((c.library,'[LIBRARY]'),(c.private,'[PRIVATE]'),(c.engine,'[ENGINE]'),(Path.home(),'~')):
        if path: text = text.replace(str(path), label)
    if limit and len(text)>limit:
        split=limit//2
        return text[:split]+'\n...\n'+text[-(limit-split-5):]
    return text


def component(args):
    return next((Path(str(a)).name for a in args[:3] if str(a).endswith(('.py','.sh'))), Path(str(args[0])).name)


class Output:
    def __init__(self):
        self.tail=deque(maxlen=20);self.important=deque(maxlen=10);self.shaders=None
    def feed(self, line):
        line=line.strip()[:2000]
        if not line: return
        self.tail.append(line)
        if re.search(r'(?i)(error:|\[RED\]|failed|exception|no space left|permission denied|missing Metal Toolchain)',line) and line not in self.important:
            self.important.append(line)
        match=re.search(r'\bshaders\s+(\d+):\s*ok\s+(\d+)',line)
        if match: self.shaders=tuple(map(int,match.groups()))
    @property
    def text(self): return '\n'.join(dict.fromkeys([*self.important,*self.tail]))


def make(c, code, summary, suggestion, *, detail='', log=None, tool=None, status=None, severity='error'):
    result=dict(code=code,severity=severity,summary=summary,suggestion=suggestion,detail=redact(detail,c),stage=c.stage)
    if log: result['logPath']=str(Path(log).resolve())
    if tool: result['component']=tool
    if status is not None: result['exitCode']=status
    return result


def failure(c, output, *, log=None, tool=None, status=None):
    text=str(output).lower()
    if 'no space left' in text or 'disk full' in text:
        code='disk_full';summary='磁盘空间不足，任务已停止。';suggestion='释放游戏库和导出磁盘的空间后重试；已完成阶段会重新校验。'
    elif 'permission denied' in text or 'operation not permitted' in text:
        code='permission_denied';summary='文件或构建工具访问被拒绝。';suggestion='检查游戏库磁盘的读写权限、所选 Xcode 和系统隐私设置，再重试。'
    elif 'metal toolchain' in text or 'cannot execute tool' in text and 'metal' in text:
        code='metal_toolchain_missing';summary='Metal 编译组件不可用。';suggestion='在设置中安装 Metal 编译组件，完成后重新检查环境并重试。'
    elif ('sdk' in text and any(s in text for s in ('cannot be located','unable to find','not found','not installed'))) or 'ios platform' in text:
        code='sdk_missing';summary='所需的 Apple 平台 SDK 不可用。';suggestion='检查所选 Xcode；生成 IPA 还需在 Xcode 中安装 iOS 平台，然后重新检查环境。'
    elif 'chain' in text and any(s in text for s in ('mismatch','do not match','stale','expected')):
        code='shader_chain_mismatch';summary='着色器缓存与当前工具链不一致。';suggestion='重新准备引擎工具，再重新准备游戏；不要混用 Mac 与 iOS 的着色器产物。'
    elif status in (-9,137) or 'out of memory' in text or 'cannot allocate memory' in text:
        code='memory_exhausted';summary='构建进程被终止，可能内存不足。';suggestion='关闭占用大量内存的应用后重试；若仍失败，请保留日志检查系统终止原因。'
    elif any(s in text for s in ('translation failed','msl failed','spirv-cross','unsupported instruction','no spv')):
        code='shader_translation_failed';summary='着色器转换失败。';suggestion='核对游戏版本与引擎配置，并确认使用完整的兼容引擎源码；保留日志中的失败着色器信息反馈上游。'
    elif tool in ('dmsh_build.py','vk_shaders.py') or 'metal failed' in text or '.metal:' in text:
        code='shader_compile_failed';summary='Metal 着色器编译失败。';suggestion='先重新检查 Xcode 和 Metal 组件；若环境通过仍失败，请核对引擎与游戏版本，并查看失败着色器的编译信息。'
    elif isinstance(output, FileNotFoundError) or 'command not found' in text or 'no such file or directory' in text:
        code='component_missing';summary='构建组件或输入文件缺失。';suggestion='检查磁盘连接、游戏源文件和外部引擎完整性，再重新检查环境；应用内置组件缺失时重新安装完整应用。'
    else:
        code='component_failed';summary='本地组件运行失败。';suggestion='查看本任务的具体日志，修复提示的问题后重试；反馈时复制已脱敏的错误摘要。'
    return make(c,code,summary,suggestion,detail=output,log=log,tool=tool,status=status)


def shader_result(c, output, log, tool):
    if tool != 'dmsh_build.py' or output.shaders is None: return None
    total, ready=output.shaders
    if ready >= total and total > 0: return None
    empty=ready == 0
    return make(c,'shader_empty' if empty else 'shader_partial',
        '没有生成可用的着色器，构建已停止。' if empty else f'部分着色器构建失败：成功 {ready}/{total}。',
        '查看失败着色器日志，核对游戏和引擎版本后重试；构建完成不代表所有场景的图形效果正常。',
        detail=output.text,log=log,tool=tool,severity='error' if empty else 'warning')


def exception(c, error, log=None):
    if isinstance(error,OSError): return failure(c,error,log=log)
    from core import Failure
    summary=str(error) if isinstance(error,Failure) else '操作失败，请检查磁盘连接、权限和任务日志后重试。'
    return make(c,'task_failed',summary,'查看本任务日志和失败阶段，按提示修复后重试；反馈时复制错误摘要。',
                log=log,detail='' if isinstance(error,Failure) else type(error).__name__)

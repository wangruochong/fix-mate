"""限制 Claude Code 能做什么。

缺陷的标题和描述**任何人都能写**,里面可能夹带指令,诱导 AI 读取本机的密钥、改动无关的文件、把敏感内容写进提交。
所以不能只靠提示词劝它守规矩,要在工具调用的层面硬性拦住。这里是最后一道关,分两层:

1. 可用的工具只有读文件和改文件(没有命令行、没有网络),在启动时就限定了(见 claude.py)。
2. 每一次工具调用执行前,都用 `check_tool_call` 检查它碰的路径。这个检查对所有调用生效,
   包括已经被自动批准的,而且检查本身出错时也会拦下调用(on_failure="block")。

判断逻辑是纯函数,没有任何 IO,所以不需要真的调用 AI 就能测试。
"""

import fnmatch
from pathlib import Path

#: 只读的工具
READ_TOOLS = ("Read", "Grep", "Glob")
#: 能修改文件的工具
EDIT_TOOLS = ("Edit", "Write")
#: SDK 内部用来交回「结构化结果」的工具。它不碰文件,只是把结果交给我们,必须放行,否则拿不到结构化输出
INTERNAL_TOOLS = ("StructuredOutput",)
ALLOWED_TOOLS = (*READ_TOOLS, *EDIT_TOOLS, *INTERNAL_TOOLS)

#: 工具参数里可能是路径的字段
_PATH_KEYS = ("file_path", "path", "notebook_path")

#: 敏感文件:密钥、证书、签名配置、环境变量。AI 既不该读,也不该写
_SENSITIVE_NAMES = (
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.keystore",
    "id_rsa*", "id_ed25519*", "id_ecdsa*", "key.properties", "*.mobileprovision", "*.p8",
)  # fmt: skip

#: 这些目录整个不让碰:git 内部数据;以及 Claude 自己的配置(防止 AI 给自己放权)
_FORBIDDEN_DIRS = (".git", ".claude")


def check_tool_call(tool_name: str, tool_input: dict, workdir: Path) -> str | None:
    """检查一次工具调用。允许返回 None,否则返回拒绝的原因(会告诉 AI)。"""
    if tool_name not in ALLOWED_TOOLS:
        return f"不允许使用工具 {tool_name}。你只能读取和修改当前工作目录里的文件。"

    root = workdir.resolve()
    for value in _paths_in(tool_name, tool_input):
        reason = _check_path(value, root, writing=tool_name in EDIT_TOOLS)
        if reason:
            return reason
    return None


def _paths_in(tool_name: str, tool_input: dict) -> list[str]:
    values = [str(tool_input[k]) for k in _PATH_KEYS if tool_input.get(k)]
    if tool_name == "Glob" and tool_input.get("pattern"):
        values.append(str(tool_input["pattern"]))  # Glob 的匹配模式本身也可能指向目录外
    if tool_name == "Grep" and tool_input.get("glob"):
        values.append(str(tool_input["glob"]))
    return values


def _check_path(value: str, root: Path, *, writing: bool) -> str | None:
    if ".." in Path(value).parts:
        return f"路径 {value} 含有「..」,不允许跳出工作目录。"
    path = Path(value)
    target = (path if path.is_absolute() else root / path).resolve()  # resolve 会展开符号链接,防止借链接绕出去
    if not target.is_relative_to(root):
        return f"路径 {value} 在工作目录之外,不允许访问。"

    parts = target.relative_to(root).parts
    for forbidden in _FORBIDDEN_DIRS:
        if forbidden in parts:
            return f"不允许{'修改' if writing else '读取'}「{forbidden}」目录里的文件。"
    name = target.name
    if any(fnmatch.fnmatch(name.lower(), pattern) for pattern in _SENSITIVE_NAMES):
        return f"{name} 是敏感文件(密钥、证书或环境变量),不允许{'修改' if writing else '读取'}。"
    return None


def make_guard_hook(workdir: Path):
    """生成 PreToolUse 钩子:每次工具调用前检查,不通过就拒绝。"""

    async def guard(input_data, tool_use_id, context):
        reason = check_tool_call(input_data["tool_name"], input_data.get("tool_input") or {}, workdir)
        if reason is None:
            return {}
        return {
            "hookSpecificOutput": {
                "hookEventName": input_data["hook_event_name"],
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }

    return guard

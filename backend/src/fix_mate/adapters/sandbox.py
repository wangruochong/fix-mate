"""开发用的沙盒仓库:一个临时的裸 origin 和一个 FixMate 专用克隆,里面是几个演示文件。

让开发模式下的「假改代码」也能在真实的 git 里建分支、提交、接受,而不碰任何真实项目。
"""

import subprocess
from pathlib import Path

_FILES = {
    "README.md": "# FixMate 沙盒仓库\n\n开发模式下 AI 的修改都发生在这里。\n",
    "src/app.py": "def main():\n    print('hello')\n",
}


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def ensure_sandbox(base: Path) -> Path:
    """返回沙盒里的专用克隆目录。已经存在就直接用,不会重复创建。"""
    origin, clone = base / "origin.git", base / "repo"
    if clone.exists():
        return clone
    base.mkdir(parents=True, exist_ok=True)
    _git(base, "init", "--bare", "-b", "main", str(origin))

    seed = base / "seed"
    _git(base, "clone", str(origin), str(seed))
    _configure(seed)
    for name, content in _FILES.items():
        (seed / name).parent.mkdir(parents=True, exist_ok=True)
        (seed / name).write_text(content)
    _git(seed, "add", "-A")
    _git(seed, "commit", "-m", "init")
    _git(seed, "push", "origin", "main")

    _git(base, "clone", str(origin), str(clone))
    _configure(clone)  # 提交身份写在仓库里,不依赖本机的全局 git 配置
    return clone


def _configure(repo: Path) -> None:
    _git(repo, "config", "user.name", "FixMate")
    _git(repo, "config", "user.email", "fixmate@localhost")
    _git(repo, "config", "commit.gpgsign", "false")

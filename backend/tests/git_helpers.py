"""git 测试的公共夹具:一个裸 origin、一个 FixMate 专用克隆、一个模拟同事的克隆。"""

import os
import subprocess
from pathlib import Path

from fix_mate.adapters.git import GitWorkspace

IDENTITY = {
    "GIT_AUTHOR_NAME": "FixMate", "GIT_AUTHOR_EMAIL": "fixmate@local",
    "GIT_COMMITTER_NAME": "FixMate", "GIT_COMMITTER_EMAIL": "fixmate@local",
}  # fmt: skip


def run(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env={**os.environ, **IDENTITY})
    assert r.returncode == 0, f"git {' '.join(args)}: {r.stderr}"
    return r.stdout.strip()


class Repos:
    """origin(远端)、clone(FixMate 专用克隆)、colleague(别人的克隆,用来模拟 main 被别人推进)。"""

    def __init__(self, root: Path):
        self.origin, self.clone, self.colleague = root / "origin.git", root / "clone", root / "colleague"
        run(root, "init", "--bare", "-b", "main", str(self.origin))
        run(root, "clone", str(self.origin), str(self.colleague))
        self.colleague_commit("a.txt", "line1\nline2\nline3\n", "init", pull=False)
        run(root, "clone", str(self.origin), str(self.clone))
        self.workspace = GitWorkspace(self.clone, root / "worktrees", env=IDENTITY)

    def colleague_commit(self, name: str, content: str, message: str, *, pull: bool = True) -> None:
        if pull:  # 第一次提交时远端还是空的,没东西可拉
            run(self.colleague, "pull", "--rebase", "origin", "main")
        (self.colleague / name).parent.mkdir(parents=True, exist_ok=True)
        (self.colleague / name).write_text(content)
        run(self.colleague, "add", "-A")
        run(self.colleague, "commit", "-m", message)
        run(self.colleague, "push", "origin", "main")

    def origin_main(self) -> str:
        return run(self.origin, "rev-parse", "main")

    def origin_file(self, name: str) -> str:
        return run(self.origin, "show", f"main:{name}")

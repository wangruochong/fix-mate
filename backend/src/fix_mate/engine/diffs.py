"""把 `git diff` 的输出解析成界面要显示的改动内容。纯函数,没有 IO。"""

from fix_mate.domain.models import DiffLine, FixFile


def parse_diff(text: str) -> list[FixFile]:
    """解析统一格式的 diff(git diff 的默认输出)。每个文件一项,行保留原来的 +/-/空格前缀。

    注意区分「文件头」和「代码行」:`--- a/x`、`+++ b/x` 只出现在第一个 `@@` 之前;
    进入 `@@` 之后,以 `-`/`+` 开头的一律是代码行(比如被删掉的 SQL 注释 `-- foo` 在 diff 里是 `--- foo`)。
    """
    files: list[FixFile] = []
    current: FixFile | None = None
    in_hunk = False
    for raw in text.splitlines():
        if raw.startswith("diff --git "):
            current = FixFile(name=_file_name(raw), additions=0, deletions=0, lines=[])
            files.append(current)
            in_hunk = False
        elif current is None:
            continue
        elif raw.startswith("@@"):
            in_hunk = True
            current.lines.append(DiffLine(kind="hunk", text=raw))
        elif not in_hunk or raw.startswith("\\ No newline"):
            continue  # 文件头(index、---、+++ 等),或「文件末尾没有换行」的提示
        elif raw.startswith("+"):
            current.additions += 1
            current.lines.append(DiffLine(kind="add", text=raw))
        elif raw.startswith("-"):
            current.deletions += 1
            current.lines.append(DiffLine(kind="del", text=raw))
        else:
            current.lines.append(DiffLine(kind="ctx", text=raw))
    return files


def _file_name(header: str) -> str:
    """`diff --git a/x/y.ts b/x/y.ts` → `x/y.ts`(取 b 侧,重命名时是新名字)。"""
    return header.rsplit(" b/", 1)[-1]

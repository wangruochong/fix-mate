"""契约测试:Python 模型的字段必须和前端 `web/src/types/` 里的 TypeScript 类型一致。

前后端各写一份类型,最容易悄悄跑偏。这里直接读 TypeScript 源文件比对,任何一边改了字段,这个测试就会失败。
"""

import re
import typing
from pathlib import Path

import pytest

from fix_mate.domain import models as m

TYPES_DIR = Path(__file__).parents[2] / "web" / "src" / "types"


def _ts(file: str) -> str:
    return (TYPES_DIR / file).read_text()


def ts_interface(file: str, name: str) -> dict[str, bool]:
    """TypeScript 接口的字段:{字段名: 是否可选}。只看顶层字段(缩进 2 格)。"""
    body = re.search(rf"export interface {name}\s*\{{(.*?)^\}}", _ts(file), re.S | re.M)
    assert body, f"在 {file} 里没找到接口 {name}"
    text = re.sub(r"/\*\*.*?\*/", "", body.group(1), flags=re.S)
    text = re.sub(r"//.*", "", text)
    return {f.group(1): bool(f.group(2)) for f in re.finditer(r"^ {2}(\w+)(\?)?:", text, re.M)}


def py_model(model: type[m.BaseModel]) -> dict[str, bool]:
    return {(f.alias or n): not f.is_required() for n, f in model.model_fields.items()}


def ts_union(file: str, name: str) -> set[str]:
    """TypeScript 字面量联合类型的取值。"""
    body = re.search(rf"export type {name} =(.*?)(?=\n\n|\nexport|\n/\*\*|\Z)", _ts(file), re.S)
    assert body, f"在 {file} 里没找到类型 {name}"
    return set(re.findall(r"'([^']+)'", re.sub(r"//.*", "", body.group(1))))


INTERFACES = [
    ("defect.ts", "Defect", m.Defect),
    ("defect.ts", "Fix", m.Fix),
    ("defect.ts", "FixFile", m.FixFile),
    ("defect.ts", "DiffLine", m.DiffLine),
    ("defect.ts", "FixConflict", m.FixConflict),
    ("defect.ts", "CachedConclusion", m.CachedConclusion),
    ("defect.ts", "PauseInfo", m.PauseInfo),
    ("defect.ts", "AcceptError", m.AcceptError),
    ("list.ts", "DefectList", m.DefectList),
    ("events.ts", "AppNotification", m.AppNotification),
]


@pytest.mark.parametrize(("file", "name", "model"), INTERFACES, ids=[i[1] for i in INTERFACES])
def test_interface_fields_match(file, name, model):
    assert py_model(model) == ts_interface(file, name)


UNIONS = [
    ("defect.ts", "DefectState", m.DefectState),
    ("defect.ts", "DefectType", m.DefectType),
    ("defect.ts", "Priority", m.Priority),
    ("defect.ts", "PauseCause", m.PauseCause),
    ("defect.ts", "DiffLineKind", typing.get_type_hints(m.DiffLine)["kind"]),
    ("list.ts", "ListState", m.ListState),
    ("events.ts", "NotificationKind", m.NotificationKind),
]


@pytest.mark.parametrize(("file", "name", "literal"), UNIONS, ids=[u[1] for u in UNIONS])
def test_literal_values_match(file, name, literal):
    assert set(typing.get_args(literal)) == ts_union(file, name)


def test_defect_json_omits_missing_fields_instead_of_null():
    from tests.conftest import make_defect

    assert "pause" not in make_defect("a").to_json()
    assert "createdAt" in make_defect("a").to_json()

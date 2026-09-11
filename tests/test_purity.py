"""Luật code số 1: lõi thuần không chạm I/O.

``model``, ``tables`` và ``epg.transform`` chỉ nhận dữ liệu vào và trả dữ liệu
ra. Không đọc đĩa, không gọi tiến trình, không ra mạng, và **không gọi đồng
hồ** — thời điểm hiện tại phải là tham số truyền vào.

Đây không phải sạch sẽ cho vui. Tính tất định là cơ chế đồng bộ giữa hai nguồn
ngang hàng: cùng commit phải cho cùng byte. Mất nó là mất mô hình dự phòng, và
mất theo kiểu im lặng cho tới lúc mux chuyển input. Rẻ hơn nhiều nếu chặn ở đây.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "vtcsi"

PURE_PACKAGES = ("model", "tables", "epg/transform")

FORBIDDEN_MODULES = {
    "os", "sys", "pathlib", "shutil", "tempfile", "glob",
    "subprocess", "socket", "asyncio", "threading", "multiprocessing",
    "urllib", "http", "requests", "httpx",
    "sqlite3", "pickle", "logging", "random", "secrets",
    "yaml", "tsduck",
}

# Gọi đồng hồ bị cấm trong lõi thuần: thời gian là tham số, không phải hiệu ứng phụ.
FORBIDDEN_CALLS = {
    ("datetime", "now"), ("datetime", "today"), ("datetime", "utcnow"),
    ("date", "today"),
    ("time", "time"), ("time", "monotonic"),
}


def _pure_files() -> list[Path]:
    files: list[Path] = []
    for pkg in PURE_PACKAGES:
        root = SRC.joinpath(*pkg.split("/"))
        if root.is_dir():
            files.extend(sorted(root.rglob("*.py")))
    return files


class TestPureCore(unittest.TestCase):
    def test_at_least_one_pure_module_exists(self) -> None:
        """Nếu bài test này rỗng thì nó không canh gì cả — bắt nó tự chứng minh."""
        self.assertTrue(_pure_files(), "khong tim thay module thuan nao trong " + str(SRC))

    def test_no_io_imports(self) -> None:
        for path in _pure_files():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    names = [node.module]
                for name in names:
                    top = name.split(".")[0]
                    with self.subTest(file=path.name, imported=name):
                        self.assertNotIn(
                            top, FORBIDDEN_MODULES,
                            f"{path.relative_to(SRC)} import '{name}' — lõi thuần không được chạm I/O",
                        )

    def test_no_clock_calls(self) -> None:
        for path in _pure_files():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = node.func
                if not isinstance(fn, ast.Attribute) or not isinstance(fn.value, ast.Name):
                    continue
                pair = (fn.value.id, fn.attr)
                with self.subTest(file=path.name, call=".".join(pair)):
                    self.assertNotIn(
                        pair, FORBIDDEN_CALLS,
                        f"{path.relative_to(SRC)} gọi {pair[0]}.{pair[1]}() — "
                        "thời gian phải truyền vào như tham số",
                    )


if __name__ == "__main__":
    unittest.main()

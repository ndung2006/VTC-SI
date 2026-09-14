"""Kho git có mang đủ mã nguồn không.

Một file nguồn không nằm trong git là một file **không tồn tại** với bất kỳ ai
khác: máy thứ hai, máy dự phòng, ảnh container. Trên máy lập trình mọi thứ vẫn
chạy hoàn hảo, vì ở đó file có trên đĩa. Chênh lệch chỉ lộ ra ở lần clone đầu
tiên, và lộ dưới dạng khó đọc nhất — một ``ModuleNotFoundError`` giữa lúc
triển khai, trông như hỏng môi trường chứ không như thiếu code.

Bài học phải trả giá mới có. ``.gitignore`` có dòng ``epg/`` để loại hộp thư
lịch ở gốc dự án. Nhưng mẫu không mở đầu bằng ``/`` thì git khớp ở **mọi cấp**,
nên nó nuốt luôn ``src/vtcsi/epg/`` — cả gói xử lý lịch EPG, bảy file, chưa bao
giờ vào git. Suốt nhiều phiên không ai thấy. Nó chỉ lộ ra khi container trên
máy Ubuntu chết với ``No module named 'vtcsi.epg'``.

Cùng một cái bẫy đã có sẵn trong ``.dockerignore`` với đúng dòng đó.
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(ROOT),
                          capture_output=True, text=True, timeout=60,
                          encoding="utf-8", errors="replace")


def _la_kho_git() -> bool:
    return _git("rev-parse", "--git-dir").returncode == 0


class TestEverySourceFileIsInGit(unittest.TestCase):
    def setUp(self) -> None:
        if not _la_kho_git():
            self.skipTest("chua phai kho git")

    def _bi_bo_qua(self) -> list[str]:
        r = _git("ls-files", "--others", "--ignored", "--exclude-standard",
                 "--", "src", "tests")
        return [d for d in r.stdout.splitlines()
                if d.endswith(".py") and "__pycache__" not in d]

    def test_no_source_file_is_ignored(self) -> None:
        """Mã nguồn bị .gitignore nuốt là mã nguồn không tới được máy khác."""
        thieu = self._bi_bo_qua()
        self.assertEqual(thieu, [], "nhung file nay khong vao git duoc: "
                                    + ", ".join(thieu))

    def test_every_package_dir_has_files_in_git(self) -> None:
        """Từng gói con một, để thông điệp chỉ thẳng gói nào hụt."""
        src = ROOT / "src" / "vtcsi"
        for d in sorted(p for p in src.rglob("*")
                        if p.is_dir() and p.name != "__pycache__"):
            if not any(p.suffix == ".py" for p in d.iterdir() if p.is_file()):
                continue
            ten = d.relative_to(ROOT).as_posix()
            with self.subTest(package=ten):
                r = _git("ls-files", "--", ten)
                self.assertTrue(r.stdout.strip(),
                                f"git khong theo doi file nao trong {ten}")

    def test_the_counts_match(self) -> None:
        tren_dia = {p.relative_to(ROOT).as_posix()
                    for p in (ROOT / "src").rglob("*.py")
                    if "__pycache__" not in p.parts}
        trong_git = {d for d in _git("ls-files", "--", "src").stdout.splitlines()
                     if d.endswith(".py")}
        self.assertEqual(tren_dia - trong_git, set(),
                         "co tren dia nhung khong trong git")


class TestTheIgnorePatternsAreAnchored(unittest.TestCase):
    """Mẫu loại trừ trỏ vào thư mục ở **gốc** phải mở đầu bằng ``/``.

    Không neo thì nó khớp ở mọi cấp, và một cái tên phổ thông như ``build`` hay
    ``epg`` sẽ nuốt mất một gói mã nguồn trùng tên ở đâu đó bên dưới.
    """

    #: Tên thư mục ở gốc dự án, đủ phổ thông để trùng với một gói con.
    O_GOC = ("build", "epg", "config", "refs")

    def _kiem(self, ten_file: str) -> None:
        f = ROOT / ten_file
        if not f.exists():
            self.skipTest(f"khong co {ten_file}")
        for dong in f.read_text(encoding="utf-8").splitlines():
            d = dong.strip()
            if not d or d.startswith("#"):
                continue
            goc = d.rstrip("/").lstrip("/")
            if goc in self.O_GOC:
                with self.subTest(file=ten_file, pattern=d):
                    self.assertTrue(
                        d.startswith("/"),
                        f"{d!r} trong {ten_file} chua neo vao goc — no se khop "
                        f"ca 'src/vtcsi/{goc}/'")

    def test_gitignore_is_anchored(self) -> None:
        self._kiem(".gitignore")

    def test_dockerignore_is_anchored(self) -> None:
        self._kiem(".dockerignore")


class TestTheMailboxIsStillIgnored(unittest.TestCase):
    """Neo lại rồi thì hộp thư lịch ở gốc vẫn phải nằm ngoài git.

    Sửa quá tay theo chiều ngược lại cũng là hỏng: file lịch là dữ liệu vận
    hành hằng ngày, hàng trăm KB mỗi ngày, không phải cấu hình.
    """

    def setUp(self) -> None:
        if not _la_kho_git():
            self.skipTest("chua phai kho git")

    def test_the_inbox_at_the_root_is_ignored(self) -> None:
        r = _git("check-ignore", "-q", "epg/inbox/2026-01-01.xml")
        self.assertEqual(r.returncode, 0, "hop thu lich o goc phai bi bo qua")

    def test_the_build_dir_at_the_root_is_ignored(self) -> None:
        r = _git("check-ignore", "-q", "build/nit.xml")
        self.assertEqual(r.returncode, 0, "thu muc build o goc phai bi bo qua")

    def test_but_the_epg_package_is_not(self) -> None:
        r = _git("check-ignore", "-q", "src/vtcsi/epg/store.py")
        self.assertNotEqual(r.returncode, 0,
                            "goi vtcsi.epg dang bi bo qua — dung cai bay cu")


if __name__ == "__main__":
    unittest.main()

"""Bộ triển khai container — ``Dockerfile`` và ``docker-compose.yml``.

Đây là loại file không ai chạy test bao giờ, và cũng là loại hỏng lặng nhất:
sai một đường dẫn thì không có ngoại lệ nào được ném, không có dòng log nào
được ghi, chỉ có một hệ trông như đang chạy mà thật ra hai nửa của nó đang nói
chuyện với hai thư mục khác nhau.

Bài quan trọng nhất là ``TestBothHalvesShareTheSameDirectories``. Nó canh đúng
cái bẫy đã có thật trong file này: ``vtcsi web`` nhận ``--build`` và ``--inbox``
mặc định **tương đối**, giải theo ``WORKDIR /app``. Bỏ trống chúng thì giao
diện ghi file lịch vào ``/app/epg/inbox`` trong khi ``vtcsi run`` đọc
``/repo/epg/inbox``. Trình duyệt báo "đã nhận", màn giám sát trống trơn, và
EPG không bao giờ lên sóng.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "docker-compose.yml"
DOCKERFILE = ROOT / "Dockerfile"

#: Những tuỳ chọn trỏ tới thư mục dùng chung giữa hai dịch vụ.
DUNG_CHUNG = ("--build", "--eit-dir", "--inbox")


def _compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def _opts(command: list[str]) -> dict[str, str]:
    """``['--build=/build', ...]`` thành ``{'--build': '/build'}``."""
    ra: dict[str, str] = {}
    for item in command:
        if isinstance(item, str) and item.startswith("--") and "=" in item:
            ten, _, gia = item.partition("=")
            ra[ten] = gia
    return ra


class ComposeCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not COMPOSE.exists():
            raise unittest.SkipTest("khong co docker-compose.yml")
        cls.d = _compose()
        cls.sv = cls.d["services"]


class TestBothHalvesShareTheSameDirectories(ComposeCase):
    """`si` và `web` phải nhìn vào **cùng** thư mục. Lệch là hỏng im lặng."""

    def test_every_shared_path_matches(self) -> None:
        si = _opts(self.sv["si"]["command"])
        web = _opts(self.sv["web"]["command"])
        for ten in DUNG_CHUNG:
            with self.subTest(option=ten):
                self.assertIn(ten, si, f"si thieu {ten}")
                self.assertIn(ten, web,
                              f"web thieu {ten} — mac dinh la duong dan TUONG DOI "
                              f"theo /app, khong phai {si.get(ten)}")
                self.assertEqual(si[ten], web[ten])

    def test_the_shared_paths_are_absolute(self) -> None:
        """Tương đối nghĩa là phụ thuộc `WORKDIR` — thứ không ai nhìn thấy."""
        for ten_dv in ("si", "web"):
            for ten, gia in _opts(self.sv[ten_dv]["command"]).items():
                if ten in DUNG_CHUNG:
                    with self.subTest(service=ten_dv, option=ten):
                        self.assertTrue(gia.startswith("/"), f"{ten}={gia}")

    def test_the_inbox_lives_in_the_mounted_repo(self) -> None:
        """Hộp thư phải nằm trong ổ gắn từ ngoài, không thì dựng lại là mất."""
        self.assertTrue(_opts(self.sv["si"]["command"])["--inbox"]
                        .startswith("/repo/"))


class TestTheBroadcasterCanActuallyReachTheNetwork(ComposeCase):
    def test_the_si_service_uses_host_networking(self) -> None:
        """Multicast KHÔNG đi ra đúng cách qua mạng bridge của Docker.

        Đây không phải chuyện tinh chỉnh: đổi sang bridge thì luồng biến mất
        khỏi mạng, mà container vẫn xanh và log vẫn sạch.
        """
        self.assertEqual(self.sv["si"].get("network_mode"), "host")

    def test_the_si_service_has_no_cpu_quota(self) -> None:
        """Bóp CPU chèn khựng vào đúng chỗ cần đều nhịp — mux đọc thành mất nguồn."""
        for khoa in ("cpus", "cpu_quota", "cpu_shares"):
            self.assertNotIn(khoa, self.sv["si"], khoa)


class TestNoAddressIsFrozenIntoTheImage(ComposeCase):
    """Địa chỉ đầu ra đọc từ `config/dau-ra.yaml`, không ghim vào compose."""

    def test_the_command_does_not_pass_to(self) -> None:
        """`--to` còn **tắt luôn đường sao chép** — xem FR-86 và `cmd_run`."""
        for item in self.sv["si"]["command"]:
            self.assertFalse(str(item).startswith("--to="), item)

    def test_the_command_does_not_pass_a_local_address(self) -> None:
        for item in self.sv["si"]["command"]:
            self.assertFalse(str(item).startswith("--local-address"), item)


class TestTheRepoMountCanPointOutside(ComposeCase):
    """Dưới Coolify, kho phải nằm NGOÀI thư mục Coolify tự quản.

    Coolify clone kho vào thư mục của nó và `reset --hard` mỗi lần triển khai
    lại, trong khi giao diện thì commit vào chính kho ấy. Trỏ vào đó nghĩa là
    mỗi lần bấm Redeploy là xoá việc người trực vừa làm.
    """

    def test_the_mount_is_configurable(self) -> None:
        raw = COMPOSE.read_text(encoding="utf-8")
        self.assertIn("${VTCSI_REPO", raw)

    def test_it_still_works_with_nothing_set(self) -> None:
        """Chạy tay thì không phải đặt biến nào — mặc định là thư mục hiện tại."""
        self.assertIn("${VTCSI_REPO:-.}", COMPOSE.read_text(encoding="utf-8"))


class TestEveryCommandTheImageRunsExists(unittest.TestCase):
    """Lệnh mà Dockerfile và compose gọi phải là console script có thật.

    Bài học phải trả giá mới có. ``pyproject.toml`` thiếu ``[project.scripts]``
    suốt từ đầu, nên ``pip install`` không tạo ra file thực thi nào. Trên máy
    lập trình không ai thấy, vì ở đó luôn chạy ``python -m vtcsi.cli``. Nó chỉ
    lộ ra ở lần triển khai container **đầu tiên**, và lộ dưới dạng khó đọc
    nhất: container restart liên tục với ``exec vtcsi failed: No such file or
    directory`` — trông như hỏng Docker chứ không như thiếu một khai báo gói.
    """

    @classmethod
    def setUpClass(cls) -> None:
        import tomllib
        pp = ROOT / "pyproject.toml"
        if not pp.exists():
            raise unittest.SkipTest("khong co pyproject.toml")
        cls.scripts = tomllib.loads(
            pp.read_text(encoding="utf-8")).get("project", {}).get("scripts", {})

    def _lenh_duoc_goi(self) -> set[str]:
        """Tên chương trình mà ảnh thực sự chạy, lấy từ Dockerfile và compose."""
        ra: set[str] = set()
        if DOCKERFILE.exists():
            for dong in DOCKERFILE.read_text(encoding="utf-8").splitlines():
                d = dong.strip()
                if d.startswith("CMD ["):
                    ra.add(d.split('"')[1])
                elif d.startswith("CMD ") and "||" in d:      # HEALTHCHECK CMD
                    ra.add(d.split()[1])
        if COMPOSE.exists():
            for sv in _compose()["services"].values():
                lenh = sv.get("command")
                if isinstance(lenh, list) and lenh:
                    ra.add(str(lenh[0]))
                elif isinstance(lenh, str) and lenh:
                    ra.add(lenh.split()[0])
        return ra

    def test_the_package_declares_a_console_script(self) -> None:
        self.assertTrue(self.scripts,
                        "pyproject.toml thieu [project.scripts] — pip install "
                        "se khong tao ra file thuc thi nao")

    def test_every_invoked_command_is_declared(self) -> None:
        goi = self._lenh_duoc_goi()
        self.assertTrue(goi, "khong tim thay lenh nao duoc goi")
        for ten in sorted(goi):
            with self.subTest(command=ten):
                self.assertIn(ten, self.scripts,
                              f"anh goi {ten!r} nhung pyproject khong khai no")

    def test_the_entry_point_actually_resolves(self) -> None:
        """Khai đúng tên chưa đủ — đích của nó phải import và gọi được."""
        import importlib
        for ten, dich in self.scripts.items():
            with self.subTest(command=ten):
                mod, _, ham = dich.partition(":")
                self.assertTrue(ham, f"{dich!r} thieu phan ':ham'")
                doi_tuong = getattr(importlib.import_module(mod), ham, None)
                self.assertIsNotNone(doi_tuong, f"{dich!r} khong ton tai")
                self.assertTrue(callable(doi_tuong), f"{dich!r} khong goi duoc")


class TestTheImageDoesNotBroadcastByAccident(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not DOCKERFILE.exists():
            raise unittest.SkipTest("khong co Dockerfile")
        cls.raw = DOCKERFILE.read_text(encoding="utf-8")

    def test_the_default_command_only_validates(self) -> None:
        """Chạy một ảnh mới mà nó lập tức bơm multicast vào mạng nhà đài là
        cách hỏng tệ nhất có thể. Phát sóng phải là việc nói ra."""
        dong = [d for d in self.raw.splitlines() if d.startswith("CMD ")]
        self.assertTrue(dong)
        self.assertIn("validate", dong[-1])
        self.assertNotIn('"run"', dong[-1])

    def test_tsduck_version_is_pinned(self) -> None:
        """Tự nâng TSDuck là tự đổi byte trên sóng mà không ai duyệt — và chỉ
        cần một trong hai máy nâng là phép so byte giữa hai bên hết đúng."""
        self.assertIn("ARG TSDUCK_VERSION=", self.raw)
        dong = next(d for d in self.raw.splitlines()
                    if d.startswith("ARG TSDUCK_VERSION="))
        self.assertNotIn("latest", dong)
        self.assertRegex(dong, r"=\d+\.\d+")

    def test_git_is_installed(self) -> None:
        """git là phụ thuộc thật: giao diện commit, và git là cơ chế đồng bộ."""
        self.assertIn(" git ", self.raw)

    def test_the_timezone_is_set_for_both_services(self) -> None:
        """Ngày của file lịch suy từ giờ ĐỊA PHƯƠNG. Container mặc định UTC thì
        một file bàn giao lúc 0h30 sẽ bị đặt tên lùi một ngày."""
        d = _compose()
        raw = COMPOSE.read_text(encoding="utf-8")
        self.assertIn("Asia/Ho_Chi_Minh", raw)


if __name__ == "__main__":
    unittest.main()

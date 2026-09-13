"""Tăng version SDT và BAT tự động — ``model.version.auto_next`` và
``version.autobump``.

Bài quan trọng nhất là ``TestTwoMachinesAgree``. Cả kiến trúc này dựa trên việc
hai máy ngang hàng sinh ra **cùng byte** từ cùng một commit; một cơ chế tăng
version đếm theo thao tác sẽ phá đúng điều đó, và phá theo kiểu tệ nhất — cùng
một version mang hai nội dung khác nhau, nên đầu thu không đọc lại và giữ
nguyên dữ liệu sai. Nếu ai đó "cải tiến" ``auto_next`` thành một bộ đếm, bài
đó phải đỏ.

Bài quan trọng thứ hai là ``TestItAgreesWithPreflight``. Hai bộ máy cùng phán
về một việc mà dùng hai phép so khác nhau thì sẽ có lúc bên này tăng còn bên
kia vẫn kêu, và người trực không biết tin bên nào.
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

import seed
from vtcsi.config import loader
from vtcsi.model import version as V
from vtcsi.model.entities import Config, epg_on
from vtcsi.version import autobump, preflight


def _cfg() -> Config:
    """Cấu hình đã commit — mốc ổn định, không phải thư mục đang sửa."""
    td = seed.committed_config()
    cfg = loader.load(Path(td.name) / "config")
    td.cleanup()
    return cfg


def _doi_ten_kenh(cfg: Config, moi: str) -> Config:
    """Đổi tên dịch vụ đầu tiên của SDT actual — một sửa đổi nội dung thật."""
    sdt = next(s for s in cfg.sdts if s.actual)
    dv = sdt.services[0]
    return replace(cfg, sdts=tuple(
        replace(s, services=(replace(dv, name=moi),) + tuple(s.services[1:]))
        if s.ts_id == sdt.ts_id else s
        for s in cfg.sdts))


def _ten_sdt(cfg: Config) -> str:
    return f"SDT ts{next(s for s in cfg.sdts if s.actual).ts_id}"


class TestTheRuleItself(unittest.TestCase):
    """``auto_next`` — chỉ động vào đúng một ô của bảng phán quyết."""

    def test_content_changed_and_version_untouched_bumps(self) -> None:
        self.assertEqual(V.auto_next(on_disk=26, committed=26,
                                     content_same=False), 27)

    def test_same_content_never_bumps(self) -> None:
        self.assertIsNone(V.auto_next(on_disk=26, committed=26,
                                      content_same=True))

    def test_a_hand_set_version_is_respected(self) -> None:
        """Người ta đã quyết rồi. Tôn trọng con số họ đặt."""
        self.assertIsNone(V.auto_next(on_disk=30, committed=26,
                                      content_same=False))

    def test_reverting_to_an_old_number_is_left_alone(self) -> None:
        """Đặt lại số cũ là đường sửa một lần bấm nhầm — không được xoá nó."""
        self.assertIsNone(V.auto_next(on_disk=25, committed=26,
                                      content_same=True))

    def test_it_wraps_at_thirty_one(self) -> None:
        self.assertEqual(V.auto_next(on_disk=31, committed=31,
                                     content_same=False), 0)

    def test_the_result_is_always_a_valid_version(self) -> None:
        for n in range(V.MODULUS):
            with self.subTest(version=n):
                ra = V.auto_next(on_disk=n, committed=n, content_same=False)
                self.assertIsNotNone(ra)
                V.validate(ra)


class TestTwoMachinesAgree(unittest.TestCase):
    """Cùng commit gốc + cùng nội dung cuối = cùng version, bất kể thao tác.

    Đây là ràng buộc dễ vỡ nhất của cả tính năng. Một bộ đếm theo thao tác sẽ
    làm bài này đỏ.
    """

    def setUp(self) -> None:
        self.goc = _cfg()

    def test_one_save_and_ten_saves_land_on_the_same_number(self) -> None:
        may_a = self.goc
        for i in range(10):                       # máy A: sửa mười lần
            may_a = _doi_ten_kenh(may_a, f"Lan sua thu {i}")
            may_a = autobump.apply(may_a, autobump.plan(may_a, self.goc))

        may_b = _doi_ten_kenh(self.goc, "Lan sua thu 9")   # máy B: một lần
        may_b = autobump.apply(may_b, autobump.plan(may_b, self.goc))

        ten = _ten_sdt(self.goc)
        a = {f"SDT ts{s.ts_id}": s.version for s in may_a.sdts}[ten]
        b = {f"SDT ts{s.ts_id}": s.version for s in may_b.sdts}[ten]
        self.assertEqual(a, b, "hai may ra hai version khac nhau")

    def test_ten_saves_bump_exactly_once(self) -> None:
        """Một lần tăng cho mỗi chu kỳ commit, không phải mỗi lần bấm Lưu."""
        ten = _ten_sdt(self.goc)
        truoc = {f"SDT ts{s.ts_id}": s.version for s in self.goc.sdts}[ten]

        nay = self.goc
        for i in range(10):
            nay = _doi_ten_kenh(nay, f"Ten {i}")
            nay = autobump.apply(nay, autobump.plan(nay, self.goc))

        sau = {f"SDT ts{s.ts_id}": s.version for s in nay.sdts}[ten]
        self.assertEqual(sau, V.next_version(truoc))

    def test_the_plan_is_empty_the_second_time(self) -> None:
        nay = _doi_ten_kenh(self.goc, "Ten moi")
        nay = autobump.apply(nay, autobump.plan(nay, self.goc))
        self.assertEqual(autobump.plan(nay, self.goc), {})


class TestWhatItTouches(unittest.TestCase):
    def setUp(self) -> None:
        self.goc = _cfg()

    def test_nothing_changed_means_nothing_to_do(self) -> None:
        self.assertEqual(autobump.plan(self.goc, self.goc), {})

    def test_an_sdt_edit_bumps_that_sdt(self) -> None:
        nay = _doi_ten_kenh(self.goc, "Ten khac han")
        self.assertEqual(set(autobump.plan(nay, self.goc)), {_ten_sdt(self.goc)})

    def test_it_never_touches_the_nit(self) -> None:
        """Đổi NIT là cả mạng dò lại kênh — phải có người quyết định."""
        nay = replace(self.goc,
                      network=replace(self.goc.network, name="Ten mang khac"))
        self.assertNotIn("NIT", autobump.plan(nay, self.goc))

    def test_the_nit_version_is_left_alone_even_when_sdt_bumps(self) -> None:
        nay = _doi_ten_kenh(self.goc, "Ten khac")
        sau = autobump.apply(nay, autobump.plan(nay, self.goc))
        self.assertEqual(sau.network.version, self.goc.network.version)

    def test_a_bouquet_edit_bumps_that_bat(self) -> None:
        q = self.goc.bouquets[0]
        nay = replace(self.goc, bouquets=tuple(
            replace(b, name=b.name + " sua") if b.bouquet_id == q.bouquet_id else b
            for b in self.goc.bouquets))
        self.assertIn(f"BAT {q.bouquet_id:04x}", autobump.plan(nay, self.goc))

    def test_only_the_edited_table_moves(self) -> None:
        nay = _doi_ten_kenh(self.goc, "Chi doi mot cho")
        ke = autobump.plan(nay, self.goc)
        sau = autobump.apply(nay, ke)
        for b, cu in zip(sau.bouquets, self.goc.bouquets):
            self.assertEqual(b.version, cu.version, f"BAT {b.bouquet_id:04x}")

    def test_a_table_missing_from_the_baseline_is_skipped(self) -> None:
        """Bảng mới chưa từng commit thì không có mốc nào để so."""
        thieu = replace(self.goc, bouquets=self.goc.bouquets[1:])
        self.assertNotIn(f"BAT {self.goc.bouquets[0].bouquet_id:04x}",
                         autobump.plan(self.goc, thieu))

    def test_apply_does_not_mutate_its_input(self) -> None:
        nay = _doi_ten_kenh(self.goc, "Ten khac")
        truoc = [s.version for s in nay.sdts]
        autobump.apply(nay, autobump.plan(nay, self.goc))
        self.assertEqual([s.version for s in nay.sdts], truoc)

    def test_an_empty_plan_returns_the_very_same_object(self) -> None:
        self.assertIs(autobump.apply(self.goc, {}), self.goc)


class TestItAgreesWithPreflight(unittest.TestCase):
    """Hai bộ máy cùng phán về một việc phải dùng chung một phép so."""

    def setUp(self) -> None:
        self.goc = _cfg()

    def test_what_preflight_calls_a_silent_change_is_what_gets_bumped(self) -> None:
        nay = _doi_ten_kenh(self.goc, "Ten khac han")
        ngam = {r.name for r in preflight.check(nay, self.goc).rows
                if r.verdict is V.Verdict.SILENT_CHANGE}
        self.assertEqual(set(autobump.plan(nay, self.goc)), ngam - {"NIT"})

    def test_after_bumping_preflight_is_happy(self) -> None:
        """Tăng xong thì không còn bảng nào bị chặn — đó là cả mục đích."""
        nay = _doi_ten_kenh(self.goc, "Ten khac han")
        sau = autobump.apply(nay, autobump.plan(nay, self.goc))
        bao = preflight.check(sau, self.goc)
        self.assertEqual([r.name for r in bao.blocking], [])


class TestReadingTheBaselineFromGit(unittest.TestCase):
    def test_it_reads_config_at_head(self) -> None:
        from vtcsi.config import git
        td = git.config_at_head(Path(__file__).resolve().parent.parent)
        if td is None:
            self.skipTest("chua phai kho git hoac chua co commit nao")
        try:
            cfg = loader.load(Path(td.name) / "config")
            self.assertTrue(cfg.sdts)
            self.assertTrue(cfg.bouquets)
        finally:
            td.cleanup()

    def test_a_directory_that_is_not_a_repo_gives_none(self) -> None:
        """Không có mốc thì trả ``None`` — nơi gọi phải không làm gì, không đoán."""
        from tempfile import TemporaryDirectory

        from vtcsi.config import git
        with TemporaryDirectory() as d:
            self.assertIsNone(git.config_at_head(Path(d)))


class TestThroughTheRealSavePath(unittest.TestCase):
    """Qua đúng đường mà người trực đi: một lượt POST của giao diện.

    Các bài trên gọi thẳng ``plan``/``apply``. Bài này kiểm cả chỗ nối — đọc
    HEAD, tăng, ghi YAML, rồi **nói ra cho người dùng biết**. Version tự đổi
    mà im lặng thì đúng là thứ hệ này sinh ra để chống.
    """

    def setUp(self) -> None:
        import shutil
        import subprocess
        from tempfile import TemporaryDirectory

        from fastapi.testclient import TestClient
        from vtcsi.web.app import create_app

        td = seed.committed_config()
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        shutil.copytree(Path(td.name) / "config", self.root / "config")
        td.cleanup()

        def git(*a):
            return subprocess.run(["git", *a], cwd=self.root,
                                  capture_output=True, text=True)

        git("init", "-q")
        git("add", "-A")
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "goc")

        cfg = loader.load(self.root / "config")
        self.sdt = next(s for s in cfg.sdts if s.actual)
        self.dv = self.sdt.services[0]
        self.c = TestClient(create_app(self.root / "config", self.root,
                                       require_login=False))

    def _luu(self, ten: str):
        """Gửi đúng trạng thái hiện có, chỉ đổi tên.

        Tên trường phải khớp **đúng** chữ ký của tuyến: một cờ ``epg``, không
        phải ``eit_pf``/``eit_schedule``. Gửi tên lạ thì FastAPI lấy giá trị
        mặc định ``False``, tức là lặng lẽ TẮT EPG của kênh — và bài "lưu y
        nguyên thì không tăng" sẽ đỏ vì lỗi của bài test chứ không phải của
        code. Đó chính là cái bẫy bài này đã sập hai lần.
        """
        return self.c.post(
            f"/ts/{self.sdt.ts_id}/service/save",
            data={"service_id": self.dv.service_id, "name": ten,
                  "provider": self.dv.provider,
                  "service_type": int(self.dv.service_type),
                  "free_ca_mode": "on" if self.dv.free_ca_mode else "",
                  "epg": "on" if epg_on(self.dv) else ""},
            follow_redirects=False)

    def _version(self) -> int:
        return next(x for x in loader.load(self.root / "config").sdts
                    if x.ts_id == self.sdt.ts_id).version

    def test_the_first_save_bumps(self) -> None:
        self._luu("Ten hoan toan khac")
        self.assertEqual(self._version(), V.next_version(self.sdt.version))

    def test_it_tells_the_operator(self) -> None:
        from urllib.parse import unquote_plus
        r = self._luu("Ten hoan toan khac")
        self.assertIn("tự tăng version",
                      unquote_plus(r.headers.get("location", "")))

    def test_saving_again_does_not_bump_again(self) -> None:
        self._luu("Lan mot")
        sau_lan_dau = self._version()
        self._luu("Lan hai")
        self._luu("Lan ba")
        self.assertEqual(self._version(), sau_lan_dau)

    def test_saving_the_same_content_never_bumps(self) -> None:
        """Lưu mà không đổi gì thì không được làm cả mạng đọc lại bảng."""
        self._luu(self.dv.name)
        self.assertEqual(self._version(), self.sdt.version)


if __name__ == "__main__":
    unittest.main()

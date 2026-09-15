"""Dòng lệnh ``tsp`` — khoá lại những chỗ trí nhớ dễ sai.

Ba bài quan trọng nhất không kiểm "có chạy không" mà kiểm **đúng ba cái bẫy**
đã tra ra từ tài liệu TSDuck: ``--interval`` không tồn tại, ``--ts-id`` và
``--time`` là bắt buộc vì luồng không có PAT lẫn TDT, và định dạng thời gian
không phải ISO.

``TestAgainstInstalledTsduck`` bỏ qua khi máy chưa cài TSDuck, và tự chạy khi
có — nên phần "chờ cài" thu về đúng một bài test, thay vì chặn cả module.
"""

from __future__ import annotations

import subprocess
import unittest
from datetime import datetime, timezone
from pathlib import Path

import tsduck_path
from vtcsi.pipeline import tspbuild as B

T0 = datetime(2026, 9, 11, 10, 0, tzinfo=timezone.utc)


def _plan(**kw) -> B.Plan:
    args = dict(build_dir="build", eit_dir="build/eit", ts_id=8,
                other_ts_ids=(3, 1000),
                bouquet_ids=(0x0044, 0x3622, 0x6510, 0x6520, 0x6550, 0x6604),
                destination="236.30.232.1:6000",
                local_address="10.10.30.240")
    args.update(kw)
    return B.plan_from_config(**args)


class TestTheThreeTraps(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cmd = B.build(_plan(), start_time=T0)

    def test_no_interval_option_anywhere(self) -> None:
        """``inject`` không có ``--interval``; chu kỳ đi trong tham số file."""
        self.assertNotIn("--interval", self.cmd)
        self.assertIn("build/nit.xml=2000", self.cmd)

    def test_eitinject_gets_ts_id_and_time(self) -> None:
        """Luồng không có PAT để đọc ts-id, không có TDT để lấy giờ."""
        i = self.cmd.index("eitinject")
        tail = self.cmd[i:]
        self.assertIn("--ts-id", tail)
        self.assertIn("--time", tail)
        self.assertEqual(tail[tail.index("--ts-id") + 1], "8")

    def test_time_format_is_not_iso(self) -> None:
        value = self.cmd[self.cmd.index("--time") + 1]
        self.assertEqual(value, "2026/09/11:10:00:00")
        self.assertNotIn("T", value)


class TestStructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cmd = B.build(_plan(), start_time=T0)

    def test_starts_from_null_input(self) -> None:
        self.assertEqual(self.cmd[:6],
                         ["tsp", "--bitrate", "2000000", "-I", "null", "-P"])

    def test_the_bitrate_is_declared_before_every_plugin(self) -> None:
        """`-I null` khong khai bitrate, va `inject` can biet de tinh nhip goi.

        Dua bitrate cho rieng `regulate` — nam CUOI chuoi — thi khong du:
        ``tsp`` chet ngay khi khoi dong voi *input bitrate unknown or too low*.
        Lan chay toan trinh dau tien bat duoc; truoc do dong lenh nay chi duoc
        so chuoi trong cac bai kiem chu chua bao gio duoc chay that.
        """
        self.assertLess(self.cmd.index("--bitrate"), self.cmd.index("-P"))
        i = self.cmd.index("--bitrate")
        j = len(self.cmd) - 1 - self.cmd[::-1].index("--bitrate")
        self.assertEqual(self.cmd[i + 1], self.cmd[j + 1],
                         "bitrate khai o dau phai bang bitrate cua regulate")

    def test_three_pids_only(self) -> None:
        pids = [self.cmd[i + 1] for i, a in enumerate(self.cmd) if a == "--pid"]
        self.assertEqual(pids, ["16", "17", "18"])

    def test_exactly_one_rate_option_per_inject(self) -> None:
        """TSDuck đòi đúng một trong --replace / --bitrate / --inter-packet."""
        for i, a in enumerate(self.cmd):
            if a == "inject":
                seg = self.cmd[i:i + 8]
                picked = [o for o in ("--replace", "--bitrate", "--inter-packet")
                          if o in seg]
                self.assertEqual(len(picked), 1, seg)

    def test_regulate_before_output(self) -> None:
        self.assertLess(self.cmd.index("regulate"), self.cmd.index("-O"))

    def test_destination_is_last_positional(self) -> None:
        self.assertEqual(self.cmd[-1], "236.30.232.1:6000")

    def test_ttl_is_not_left_at_one(self) -> None:
        """Mặc định hệ điều hành là 1 — chết ngay tại switch đầu tiên."""
        self.assertGreater(int(self.cmd[self.cmd.index("--ttl") + 1]), 1)

    def test_build_is_deterministic(self) -> None:
        self.assertEqual(B.build(_plan(), start_time=T0), self.cmd)


class TestWildcardTrap(unittest.TestCase):
    def test_actual_sdt_is_not_matched_twice(self) -> None:
        """``sdt-ts*.xml`` sẽ nuốt cả file actual — phải liệt kê tường minh."""
        cmd = B.build(_plan(), start_time=T0)
        args = [a for a in cmd if a.startswith("build/sdt-")]
        self.assertEqual(args, ["build/sdt-ts8.xml=1000",
                                "build/sdt-ts3.xml=5000",
                                "build/sdt-ts1000.xml=5000"])
        self.assertFalse(any("sdt-ts*" in a for a in cmd))

    def test_actual_ts_cannot_also_be_other(self) -> None:
        with self.assertRaises(B.PipelineError):
            _plan(other_ts_ids=(3, 8))


class TestRefusesBadInput(unittest.TestCase):
    def test_naive_start_time(self) -> None:
        with self.assertRaises(B.PipelineError):
            B.build(_plan(), start_time=datetime(2026, 9, 11, 10, 0))

    def test_zero_interval(self) -> None:
        with self.assertRaises(B.PipelineError):
            B.Injection("x.xml", 0).argument()


class TestShellRendering(unittest.TestCase):
    def test_the_one_remaining_wildcard_is_quoted(self) -> None:
        """Không quote thì shell bung ký tự đại diện trước khi tsp thấy.

        Chỉ còn đúng một chỗ được phép mang ký tự đại diện: ``eitinject
        --files``. Tuyến ``inject`` thì không — xem
        ``TestNoWildcardReachesInject``.
        """
        line = B.shell(B.build(_plan(), start_time=T0))
        self.assertIn("'build/eit/*.xml'", line)
        self.assertNotIn("bat-*", line)


class TestMissingOptions(unittest.TestCase):
    def test_detects_absent_option(self) -> None:
        self.assertEqual(B.missing_options("--pid --bitrate", ["--pid", "--poll-files"]),
                         ["--poll-files"])

    def test_nothing_missing(self) -> None:
        self.assertEqual(B.missing_options("--pid --bitrate", ["--pid"]), [])


class TestAgainstInstalledTsduck(unittest.TestCase):
    """Đối chiếu với ``tsp`` thật. Bỏ qua khi chưa cài.

    Đây là chỗ duy nhất trong dự án cần TSDuck có mặt. Khi bạn cài xong, bài
    này tự chạy và sẽ đỏ nếu tôi ghim sai tên tuỳ chọn nào.
    """

    @classmethod
    def setUpClass(cls) -> None:
        tsduck_path.require("tsp")

    def _help(self, flag: str, plugin: str) -> str:
        r = subprocess.run([tsduck_path.require("tsp"), flag, plugin, "--help"],
                           capture_output=True, text=True, timeout=30,
                           env=tsduck_path.on_path())
        return r.stdout + r.stderr

    def test_processor_plugin_options_exist(self) -> None:
        for plugin, wanted in B.USED_OPTIONS.items():
            with self.subTest(plugin=plugin):
                missing = B.missing_options(self._help("-P", plugin), wanted)
                self.assertEqual(missing, [], f"{plugin}: thieu {missing}")

    def test_output_plugin_options_exist(self) -> None:
        for plugin, wanted in B.USED_OUTPUT_OPTIONS.items():
            with self.subTest(plugin=plugin):
                missing = B.missing_options(self._help("-O", plugin), wanted)
                self.assertEqual(missing, [], f"{plugin}: thieu {missing}")

    def test_lazy_schedule_update_is_on_the_command_line(self) -> None:
        """Không có cờ này thì `eitinject` gỡ ngay chương trình vừa kết thúc.

        Đo được: bảng ta sinh ra bắt đầu 00:00 UTC (FR-98) nhưng trên sóng bắt
        đầu 06:45 — đúng chương trình đang chạy lúc thu. 336 trên 802 sự kiện
        không lên sóng.

        Cờ này giữ thêm chương trình **đã kết thúc** trong phân đoạn ba giờ
        đang chạy. Tác dụng thật chưa đo được: phải thu vào cuối một phân đoạn
        mới thấy, xem FR-99.
        """
        self.assertIn("--lazy-schedule-update", B.build(_plan(), start_time=T0))

    def test_interval_really_does_not_exist(self) -> None:
        """Khẳng định ngược, để ghi chú trong module không trôi khỏi sự thật.

        Nếu bài này đỏ thì TSDuck đã thêm ``--interval`` — tin tốt, nhưng
        phải cập nhật phần đầu ``tspbuild.py``.
        """
        self.assertNotIn("--interval", self._help("-P", "inject"))


if __name__ == "__main__":
    unittest.main()


class TestNoWildcardReachesInject(unittest.TestCase):
    """``inject`` KHONG no ky tu dai dien, va khong bao loi khi khong tim thay.

    Lan chay toan trinh dau tien lam lo ra: lenh cu dua ``bat-*.xml`` cho
    ``inject``, ``tsp`` chay binh thuong, PID 17 van co bitrate, NIT va SDT van
    len song — va ca sau BAT bien mat khong mot dong loi.

    ``eitinject --files`` thi nguoc lai, co no ky tu dai dien; bai cuoi ghim su
    khac nhau do lai, vi no la thu de quen nhat.
    """

    def test_every_injected_file_is_a_real_name(self) -> None:
        for x in (_plan().nit,) + _plan().sdt_bat:
            with self.subTest(path=x.path):
                self.assertNotIn("*", x.path)
                self.assertNotIn("?", x.path)

    def test_one_entry_per_bouquet(self) -> None:
        quets = (0x0044, 0x3622, 0x6510)
        paths = [x.path for x in _plan(bouquet_ids=quets).sdt_bat
                 if "bat-" in x.path]
        self.assertEqual(paths, ["build/bat-0044.xml", "build/bat-3622.xml",
                                 "build/bat-6510.xml"])

    def test_the_names_match_what_build_writes(self) -> None:
        """Ten file phai khop chinh xac voi thu `vtcsi build` ghi ra."""
        from vtcsi.config import loader
        goc = Path(__file__).parent.parent / "config"
        cfg = loader.load(goc)
        quets = tuple(sorted(q.bouquet_id for q in cfg.bouquets))
        want = {f"build/bat-{q:04x}.xml" for q in quets}
        got = {x.path for x in _plan(bouquet_ids=quets).sdt_bat if "bat-" in x.path}
        self.assertEqual(got, want)

    def test_eitinject_keeps_its_wildcard(self) -> None:
        """Hai plugin, hai luat — `eitinject` co no, nen giu `*.xml`."""
        self.assertTrue(_plan().eit_files.endswith("*.xml"))


class TestOneCharsetOnAir(unittest.TestCase):
    """Ep mot bang ma duy nhat cho ten su kien.

    Khong dat thi TSDuck chon bang ma cho TUNG CHUOI — phan lon ra 0x15 UTF-8,
    nhung mot so ten ra ISO-8859-15 hay ISO-8859-2. Hop chuan ca, va giai dung
    ca; nhung ban thu song that cho thay Barrowa chi dung 0x15 va de tran.

    Cac bai so byte khong bat duoc chuyen nay: chung bien dich CA HAI ben bang
    cung mot `tstabcomp` voi cung tuy chon, nen bang ma la thu chung khong the
    thay. No chi lo ra khi dua qua `tsp` that.
    """

    def setUp(self) -> None:
        self.cmd = B.build(_plan(), start_time=T0)

    def test_eitinject_is_pinned_to_utf8(self) -> None:
        i = self.cmd.index("--default-charset")
        self.assertEqual(self.cmd[i + 1], "UTF-8")

    def test_it_sits_inside_the_eitinject_block(self) -> None:
        """Dat nham vao `inject` se doi ca SDT/BAT — von dang trung song that."""
        self.assertGreater(self.cmd.index("--default-charset"),
                           self.cmd.index("eitinject"))

    def test_inject_keeps_the_default(self) -> None:
        """Ten dich vu va ten bouquet thuan ASCII: de tran, trung tung byte."""
        khoi = " ".join(self.cmd[:self.cmd.index("eitinject")])
        self.assertNotIn("--default-charset", khoi)

    def test_tsduck_knows_the_option(self) -> None:
        """Ghim ten tuy chon va gia tri vao chinh TSDuck dang cai."""
        tsp = tsduck_path.require("tsp")
        r = subprocess.run([tsp, "-P", "eitinject", "--help"],
                           capture_output=True, text=True, timeout=60,
                           env=tsduck_path.on_path())
        vb = r.stdout + r.stderr
        self.assertIn("--default-charset", vb)
        self.assertIn("UTF-8", vb)

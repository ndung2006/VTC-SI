"""Dòng lệnh ``tsp`` — khoá lại những chỗ trí nhớ dễ sai.

Ba bài quan trọng nhất không kiểm "có chạy không" mà kiểm **đúng ba cái bẫy**
đã tra ra từ tài liệu TSDuck: ``--interval`` không tồn tại, ``--ts-id`` và
``--time`` là bắt buộc vì luồng không có PAT lẫn TDT, và định dạng thời gian
không phải ISO.

``TestAgainstInstalledTsduck`` bỏ qua khi máy chưa cài TSDuck, và tự chạy khi
có — nên phần "chờ cài" thu về đúng một bài test, thay vì chặn cả module.
"""

from __future__ import annotations

import shutil
import subprocess
import unittest
from datetime import datetime, timezone

from vtcsi.pipeline import tspbuild as B

T0 = datetime(2026, 9, 11, 10, 0, tzinfo=timezone.utc)


def _plan(**kw) -> B.Plan:
    args = dict(build_dir="build", eit_dir="build/eit", ts_id=8,
                other_ts_ids=(3, 1000), destination="236.30.232.1:6000",
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
        self.assertEqual(self.cmd[:4], ["tsp", "-I", "null", "-P"])

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
    def test_wildcards_are_quoted(self) -> None:
        """Không quote thì shell bung ký tự đại diện trước khi tsp thấy."""
        line = B.shell(B.build(_plan(), start_time=T0))
        self.assertIn("'build/eit/*.xml'", line)
        self.assertIn("'build/bat-*.xml=5000'", line)


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
        if shutil.which("tsp") is None:
            raise unittest.SkipTest("chua cai TSDuck — bai nay tu chay khi co tsp")

    def _help(self, flag: str, plugin: str) -> str:
        r = subprocess.run(["tsp", flag, plugin, "--help"],
                           capture_output=True, text=True, timeout=30)
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

    def test_interval_really_does_not_exist(self) -> None:
        """Khẳng định ngược, để ghi chú trong module không trôi khỏi sự thật.

        Nếu bài này đỏ thì TSDuck đã thêm ``--interval`` — tin tốt, nhưng
        phải cập nhật phần đầu ``tspbuild.py``.
        """
        self.assertNotIn("--interval", self._help("-P", "inject"))


if __name__ == "__main__":
    unittest.main()

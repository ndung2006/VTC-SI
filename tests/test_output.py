"""Địa chỉ multicast đầu ra — ``model.output`` và ``config.output``.

Hai nhóm bài quan trọng hơn phần còn lại:

* ``TestTheMirrorThatIsNotABackup`` — đường sao chép trùng hoàn toàn đường
  chính là *hỏng*, không phải là dự phòng. Nới luật này ra thì giao diện sẽ vui
  vẻ nhận một cấu hình bắn mỗi gói hai lần ra cùng một sợi dây.
* ``TestItStaysOutOfConfig`` — địa chỉ đầu ra **không** phải báo hiệu. Kéo nó
  vào ``Config`` là kéo nó vào bộ so byte giữa hai máy, nơi nó phải khác nhau.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from vtcsi.config import output as CO
from vtcsi.model import output as O
from vtcsi.model.output import Endpoint, Output


def _ok(ttl: int = 8) -> Output:
    """Một cấu hình đầu ra hợp lệ, đầy đủ — gốc để từng bài bẻ đi một chỗ."""
    return Output(
        primary=Endpoint("236.30.239.1", 6000, "10.10.30.230"),
        mirror=Endpoint("236.30.239.2", 6000, "10.10.31.230"),
        ttl=ttl)


class TestReadingAnAddress(unittest.TestCase):
    def test_four_numbers(self) -> None:
        self.assertEqual(O.parse_ip("236.30.239.1"), (236, 30, 239, 1))

    def test_blank_says_so(self) -> None:
        with self.assertRaises(O.OutputError) as e:
            O.parse_ip("   ")
        self.assertIn("để trống", str(e.exception))

    def test_three_groups_is_not_an_address(self) -> None:
        with self.assertRaises(O.OutputError):
            O.parse_ip("236.30.239")

    def test_over_255(self) -> None:
        with self.assertRaises(O.OutputError) as e:
            O.parse_ip("236.30.239.300")
        self.assertIn("300", str(e.exception))

    def test_leading_zero_is_refused(self) -> None:
        """``010`` là 8 hay 10? Tuỳ thư viện. Chặn ngay, đừng đoán."""
        with self.assertRaises(O.OutputError):
            O.parse_ip("236.30.239.010")

    def test_letters(self) -> None:
        with self.assertRaises(O.OutputError):
            O.parse_ip("236.30.239.x")

    def test_the_multicast_range(self) -> None:
        self.assertTrue(O.is_multicast("224.0.0.1"))
        self.assertTrue(O.is_multicast("239.255.255.255"))
        self.assertFalse(O.is_multicast("223.255.255.255"))
        self.assertFalse(O.is_multicast("240.0.0.1"))
        self.assertFalse(O.is_multicast("10.10.30.230"))

    def test_garbage_is_not_multicast_and_does_not_raise(self) -> None:
        self.assertFalse(O.is_multicast("khong-phai-dia-chi"))


class TestWhatBlocksAir(unittest.TestCase):
    def test_a_good_one_blocks_nothing(self) -> None:
        self.assertEqual(O.check(_ok()), ())
        self.assertFalse(O.blocking(_ok()))

    def test_empty_config_blocks(self) -> None:
        """Máy vừa dựng, chưa ai đặt gì — không được coi là sẵn sàng."""
        self.assertTrue(O.blocking(Output()))

    def test_bad_primary_address(self) -> None:
        out = Output(primary=Endpoint("236.30.239", 6000))
        self.assertTrue(any("Đường chính" in m for m in O.check(out)))

    def test_port_zero(self) -> None:
        out = Output(primary=Endpoint("236.30.239.1", 0))
        self.assertTrue(any("cổng" in m for m in O.check(out)))

    def test_port_over_range(self) -> None:
        out = Output(primary=Endpoint("236.30.239.1", 70000))
        self.assertTrue(any("65535" in m for m in O.check(out)))

    def test_bad_interface_blocks_too(self) -> None:
        out = Output(primary=Endpoint("236.30.239.1", 6000, "10.10.30"))
        self.assertTrue(any("card mạng" in m for m in O.check(out)))

    def test_ttl_out_of_range(self) -> None:
        for xau in (0, 256, -1):
            with self.subTest(ttl=xau):
                self.assertTrue(any("TTL" in m for m in O.check(_ok(ttl=xau))))

    def test_a_broken_mirror_blocks(self) -> None:
        out = Output(primary=Endpoint("236.30.239.1", 6000),
                     mirror=Endpoint("236.30.239", 6000))
        self.assertTrue(any("Đường sao chép" in m for m in O.check(out)))

    def test_no_mirror_at_all_is_allowed(self) -> None:
        """Một đường là *kém*, nhưng vẫn phát được. Lời nhắc, không phải chặn."""
        self.assertEqual(O.check(Output(primary=Endpoint("236.30.239.1", 6000))), ())


class TestTheMirrorThatIsNotABackup(unittest.TestCase):
    """Trùng hoàn toàn đường chính thì không phải dự phòng — là gói trùng."""

    def test_same_address_same_port_same_card_is_blocked(self) -> None:
        e = Endpoint("236.30.239.1", 6000, "10.10.30.230")
        loi = O.check(Output(primary=e, mirror=e))
        self.assertTrue(any("trùng hoàn toàn" in m for m in loi), loi)

    def test_same_address_but_another_card_is_fine(self) -> None:
        """Hai card, cùng nhóm: đó là dự phòng đường truyền thật, không chặn."""
        out = Output(primary=Endpoint("236.30.239.1", 6000, "10.10.30.230"),
                     mirror=Endpoint("236.30.239.1", 6000, "10.10.31.230"))
        self.assertEqual(O.check(out), ())

    def test_same_card_but_another_group_is_fine(self) -> None:
        out = Output(primary=Endpoint("236.30.239.1", 6000, "10.10.30.230"),
                     mirror=Endpoint("236.30.239.2", 6000, "10.10.30.230"))
        self.assertEqual(O.check(out), ())

    def test_another_port_alone_is_enough(self) -> None:
        e = Endpoint("236.30.239.1", 6000, "10.10.30.230")
        out = Output(primary=e, mirror=Endpoint(e.address, 6001, e.interface))
        self.assertEqual(O.check(out), ())


class TestWhatOnlyWarns(unittest.TestCase):
    def test_a_full_good_config_warns_about_nothing(self) -> None:
        self.assertEqual(O.warnings(_ok()), ())

    def test_a_unicast_destination_warns(self) -> None:
        out = Output(primary=Endpoint("10.10.30.9", 6000, "10.10.30.230"),
                     mirror=Endpoint("236.30.239.2", 6000, "10.10.31.230"))
        self.assertTrue(any("multicast" in m for m in O.warnings(out)))

    def test_no_interface_warns(self) -> None:
        out = Output(primary=Endpoint("236.30.239.1", 6000),
                     mirror=Endpoint("236.30.239.2", 6000, "10.10.31.230"))
        self.assertTrue(any("card mạng" in m for m in O.warnings(out)))

    def test_ttl_one_warns(self) -> None:
        self.assertTrue(any("TTL 1" in m for m in O.warnings(_ok(ttl=1))))

    def test_missing_mirror_warns(self) -> None:
        out = Output(primary=Endpoint("236.30.239.1", 6000, "10.10.30.230"))
        self.assertTrue(any("sao chép" in m for m in O.warnings(out)))

    def test_both_on_one_card_warns(self) -> None:
        out = Output(primary=Endpoint("236.30.239.1", 6000, "10.10.30.230"),
                     mirror=Endpoint("236.30.239.2", 6000, "10.10.30.230"))
        self.assertTrue(any("một card mạng" in m for m in O.warnings(out)))

    def test_a_warning_never_blocks(self) -> None:
        """Ranh giới giữa hai danh sách: nhắc thì nhắc, nhưng vẫn lên sóng."""
        out = Output(primary=Endpoint("10.10.30.9", 6000), ttl=1)
        self.assertTrue(O.warnings(out))
        self.assertEqual(O.check(out), ())


class TestOnDisk(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_missing_file_is_not_an_error(self) -> None:
        """Máy mới dựng chưa có file. Giao diện vẫn phải mở được."""
        self.assertEqual(CO.load(self.root), Output())

    def test_round_trip(self) -> None:
        CO.save(_ok(), self.root)
        self.assertEqual(CO.load(self.root), _ok())

    def test_round_trip_without_mirror(self) -> None:
        mot = Output(primary=Endpoint("236.30.239.1", 6000, "10.10.30.230"), ttl=4)
        CO.save(mot, self.root)
        lai = CO.load(self.root)
        self.assertIsNone(lai.mirror)
        self.assertEqual(lai, mot)

    def test_an_empty_mirror_is_not_written(self) -> None:
        """Đường sao chép rỗng và không có đường sao chép là **một** trạng thái."""
        CO.save(Output(primary=Endpoint("236.30.239.1", 6000),
                       mirror=Endpoint()), self.root)
        self.assertNotIn("mirror",
                         CO.path_for(self.root).read_text(encoding="utf-8"))
        self.assertIsNone(CO.load(self.root).mirror)

    def test_the_file_says_why_it_is_not_in_git(self) -> None:
        CO.save(_ok(), self.root)
        dau = CO.path_for(self.root).read_text(encoding="utf-8")
        self.assertIn("git", dau[:400])

    def test_broken_yaml_says_which_file(self) -> None:
        CO.path_for(self.root).write_text("primary: [\n", encoding="utf-8")
        with self.assertRaises(O.OutputError) as e:
            CO.load(self.root)
        self.assertIn(CO.FILE, str(e.exception))

    def test_a_list_at_top_level_is_refused(self) -> None:
        CO.path_for(self.root).write_text("- mot\n- hai\n", encoding="utf-8")
        with self.assertRaises(O.OutputError):
            CO.load(self.root)

    def test_port_must_be_a_number(self) -> None:
        CO.path_for(self.root).write_text(
            "primary:\n  address: 236.30.239.1\n  port: sau-nghin\n",
            encoding="utf-8")
        with self.assertRaises(O.OutputError) as e:
            CO.load(self.root)
        self.assertIn("port", str(e.exception))

    def test_ttl_must_be_a_number(self) -> None:
        CO.path_for(self.root).write_text(
            "primary:\n  address: 236.30.239.1\n  port: 6000\nttl: tam\n",
            encoding="utf-8")
        with self.assertRaises(O.OutputError):
            CO.load(self.root)

    def test_saving_leaves_no_temp_file_behind(self) -> None:
        CO.save(_ok(), self.root)
        con_lai = sorted(p.name for p in self.root.iterdir())
        self.assertEqual(con_lai, [CO.FILE], con_lai)

    def test_hand_written_minimal_file_loads(self) -> None:
        """Đặc tả nói sửa tay cũng được — vậy bản tối giản phải nạp được."""
        CO.path_for(self.root).write_text(
            "primary:\n  address: 236.30.239.1\n  port: 6000\n", encoding="utf-8")
        out = CO.load(self.root)
        self.assertEqual(out.primary.address, "236.30.239.1")
        self.assertEqual(out.ttl, O.TTL_MAC_DINH)
        self.assertEqual(out.primary.interface, "")


class TestItStaysOutOfConfig(unittest.TestCase):
    """Địa chỉ đầu ra không phải báo hiệu, và phải khác nhau giữa hai máy."""

    def test_config_has_no_output_field(self) -> None:
        from dataclasses import fields

        from vtcsi.model.entities import Config
        ten = {f.name for f in fields(Config)}
        for xau in ("output", "dau_ra", "destination", "multicast"):
            self.assertNotIn(xau, ten)

    def test_the_output_file_is_ignored_by_git(self) -> None:
        """Vào git là hai máy cùng bắn một nhóm ra cùng một mạng."""
        goc = Path(__file__).resolve().parent.parent
        bo_qua = (goc / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(CO.FILE, bo_qua)


if __name__ == "__main__":
    unittest.main()

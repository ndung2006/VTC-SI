"""AC-2 thu nhỏ — vòng tròn khép kín trên chuẩn vàng.

``dvb_tables_dump_win.xml`` là luồng SI thuần của Barrowa, thu bằng
``tstables``: 1 NIT, 3 SDT, 6 BAT, 18 EIT p/f. Mười bảng cấu trúc đầu đã được
chứng minh là **trùng khít từng trường với đầu ra mux**, qua bốn bản dump trải
bốn ngày — nên chúng đúng là thứ đầu thu đang nhận.

Phép thử: **dump → mô hình → XML → so với dump**. Đi trọn vòng mà không mất
thông tin nghĩa là mô hình đủ giàu để tái tạo sóng, và bộ ghi phát đúng thứ bộ
đọc thấy. Đây cũng chính là cách gieo cấu hình ở giai đoạn T2: 88 dịch vụ,
87 LCN, 136 mục service list lấy thẳng từ sóng, không gõ tay.
"""

from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

from vtcsi.model.entities import ServiceType
from vtcsi.tables import tsduck as T

GOLDEN = Path(__file__).parent.parent / "Bang mau" / "dvb_tables_dump_win.xml"
MUX_OUT = Path(__file__).parent.parent / "Bang mau" / "dvb_tables_dump2.xml"


def _require(path: Path) -> str:
    if not path.exists():
        raise unittest.SkipTest(f"khong tim thay {path.name}")
    return path.read_text(encoding="utf-8")


class TestReadGolden(unittest.TestCase):
    """Đọc chuẩn vàng ra mô hình, và đối chiếu với những gì đã khảo sát."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.cfg = T.read_dump(_require(GOLDEN))

    def test_network(self) -> None:
        n = self.cfg.network
        self.assertEqual(n.network_id, 12901)
        self.assertEqual(n.name, "VTC")
        self.assertEqual(n.version, 4)
        self.assertTrue(n.actual)
        self.assertEqual(len(n.ts_loops), 3)

    def test_transport_streams(self) -> None:
        loops = {t.ts_id: t for t in self.cfg.network.ts_loops}
        self.assertEqual(sorted(loops), [3, 8, 1000])
        # chi TSID 8 mang ONID cua VTC
        self.assertEqual(loops[8].original_network_id, 12901)
        self.assertEqual(loops[3].original_network_id, 1)
        self.assertEqual(loops[1000].original_network_id, 1)

    def test_delivery_matches_the_byte_vectors(self) -> None:
        """Tham số vệ tinh đọc từ sóng phải khớp vector ở Phụ lục A.3."""
        from vtcsi.tables import delivery

        expected = {
            8: "43 0B 01 09 68 00 13 20 8E 02 88 00 03",
            3: "43 0B 01 10 88 00 13 20 AE 01 87 50 04",
            1000: "43 0B 01 15 89 00 13 20 8E 01 50 00 03",
        }
        for loop in self.cfg.network.ts_loops:
            with self.subTest(ts=loop.ts_id):
                got = " ".join("%02X" % b for b in delivery.encode(loop.delivery))
                self.assertEqual(got, expected[loop.ts_id])

    def test_vicas_linkage_private_data(self) -> None:
        """Khối byte riêng của ViCAS phải qua được vòng đọc mà không suy suyển."""
        lk = [x for x in self.cfg.network.linkages if x.linkage_type == 0x92]
        self.assertEqual(len(lk), 1)
        self.assertEqual(
            " ".join("%02X" % b for b in lk[0].private_data),
            "FF 04 FF 04 FF 00 FF 01 FF 30 32 35 32 FF 02",
        )
        self.assertEqual(lk[0].service_id, 0x0353)

    def test_sdt_shape(self) -> None:
        by_ts = {s.ts_id: s for s in self.cfg.sdts}
        self.assertEqual(sorted(by_ts), [3, 8, 1000])
        self.assertEqual(by_ts[8].version, 9)
        self.assertTrue(by_ts[8].actual)
        self.assertFalse(by_ts[3].actual)
        self.assertEqual(len(by_ts[8].services), 64)
        types = [s.service_type for s in by_ts[8].services]
        self.assertEqual(types.count(ServiceType.DIGITAL_TELEVISION), 44)
        self.assertEqual(types.count(ServiceType.DIGITAL_RADIO_SOUND), 20)

    def test_bouquets(self) -> None:
        by_id = {b.bouquet_id: b for b in self.cfg.bouquets}
        self.assertEqual(
            sorted(by_id), [0x0044, 0x3622, 0x6510, 0x6520, 0x6550, 0x6604]
        )
        self.assertEqual(by_id[0x6510].name, "VTC_FULLHD")
        self.assertEqual(by_id[0x6510].version, 26)

    def test_lcn_is_nordig_and_lives_on_the_bouquet(self) -> None:
        b = {x.bouquet_id: x for x in self.cfg.bouquets}[0x6510]
        total = sum(len(t.lcn) for t in b.ts_loops)
        self.assertEqual(total, 78)
        for loop in b.ts_loops:
            if loop.lcn:
                self.assertEqual(loop.private_data_specifier, "NorDig")

    def test_empty_bouquet_is_read_as_empty(self) -> None:
        """RO-15: bouquet 0x6520 đang phát rỗng. Đọc ra phải thấy đúng thế."""
        b = {x.bouquet_id: x for x in self.cfg.bouquets}[0x6520]
        self.assertEqual(b.name, "VTCHD_Basic")
        self.assertEqual(b.ts_loops, ())
        self.assertEqual(b.linkages, ())

    def test_irdeto_bouquet_linkages(self) -> None:
        b = {x.bouquet_id: x for x in self.cfg.bouquets}[0x3622]
        self.assertEqual(b.private_data_specifier, 0x00362275)
        kinds = sorted({x.linkage_type for x in b.linkages})
        self.assertEqual(kinds, [0x09, 0x80, 0x82])
        # payload 0x80 co dinh, payload 0x82 doi theo dich vu
        p80 = {bytes(x.private_data) for x in b.linkages if x.linkage_type == 0x80}
        self.assertEqual(p80, {b"\x35\x02"})


class TestRoundTrip(unittest.TestCase):
    """dump → mô hình → XML → so với dump, cho cả mười bảng cấu trúc."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.text = _require(GOLDEN)
        cls.root = ET.fromstring(cls.text)
        cls.cfg = T.read_dump(cls.text)

    def _orig(self, tag: str, **attrs) -> ET.Element:
        for el in self.root.findall(tag):
            if all(T.num(el.get(k)) == v for k, v in attrs.items()):
                return el
        self.fail(f"khong tim thay <{tag}> voi {attrs}")

    def test_nit_round_trip(self) -> None:
        orig = self._orig("NIT", network_id=12901)
        self.assertEqual(T.canon(T.write_nit(self.cfg.network)), T.canon(orig))

    def test_sdt_round_trip(self) -> None:
        for sdt in self.cfg.sdts:
            with self.subTest(ts=sdt.ts_id):
                orig = self._orig("SDT", transport_stream_id=sdt.ts_id)
                self.assertEqual(T.canon(T.write_sdt(sdt)), T.canon(orig))

    def test_bat_round_trip(self) -> None:
        for b in self.cfg.bouquets:
            with self.subTest(bouquet=hex(b.bouquet_id)):
                orig = self._orig("BAT", bouquet_id=b.bouquet_id)
                self.assertEqual(T.canon(T.write_bat(b)), T.canon(orig))

    def test_all_ten_structural_tables_covered(self) -> None:
        n = 1 + len(self.cfg.sdts) + len(self.cfg.bouquets)
        self.assertEqual(n, 10)

    def test_model_to_xml_is_deterministic(self) -> None:
        """FR-46 ở quy mô nhỏ: cùng mô hình, cùng cây, mọi lần."""
        first = T.canon(T.write_nit(self.cfg.network))
        for _ in range(20):
            self.assertEqual(T.canon(T.write_nit(self.cfg.network)), first)


class TestMuxIsFaithful(unittest.TestCase):
    """Đầu vào mux và đầu ra mux phải cho ra cùng một mô hình.

    Đây là bằng chứng kịch bản B, viết thành bài test để nó không lặng lẽ
    hỏng: nếu mux bắt đầu sửa bảng, bài này đỏ.
    """

    def test_structural_tables_identical_at_both_ends(self) -> None:
        a = T.read_dump(_require(GOLDEN))
        b = T.read_dump(_require(MUX_OUT))
        self.assertEqual(a.network, b.network)
        self.assertEqual(a.sdts, b.sdts)
        self.assertEqual(a.bouquets, b.bouquets)


class TestComparatorIsStrict(unittest.TestCase):
    """Bộ so sánh phải bắt được sai lệch thật.

    Một phép so quá dễ dãi cũng xanh như một phép so đúng — nên nó phải tự
    chứng minh. Mỗi bài dưới đây cố ý làm hỏng một thứ và đòi ``canon`` nhận
    ra. Nếu ai đó nới lỏng ``canon`` về sau, những bài này đỏ.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.text = _require(GOLDEN)
        cls.root = ET.fromstring(cls.text)
        cls.cfg = T.read_dump(cls.text)
        cls.nit = cls.root.find("NIT")
        cls.bat = next(e for e in cls.root.findall("BAT")
                       if T.num(e.get("bouquet_id")) == 0x6510)

    def _nit_differs(self, net) -> None:
        self.assertNotEqual(T.canon(T.write_nit(net)), T.canon(self.nit))

    def test_baseline_matches(self) -> None:
        """Chốt đối chiếu: bản không sửa gì phải khớp."""
        self.assertEqual(T.canon(T.write_nit(self.cfg.network)), T.canon(self.nit))

    def test_catches_changed_version(self) -> None:
        self._nit_differs(replace(self.cfg.network, version=5))

    def test_catches_changed_network_name(self) -> None:
        self._nit_differs(replace(self.cfg.network, name="VTD"))

    def test_catches_one_byte_of_private_data(self) -> None:
        """Khối byte ViCAS: sai một bit cũng phải lộ."""
        lks = list(self.cfg.network.linkages)
        i = next(j for j, x in enumerate(lks) if x.linkage_type == 0x92)
        pd = bytearray(lks[i].private_data)
        pd[-1] ^= 0x01
        lks[i] = replace(lks[i], private_data=bytes(pd))
        self._nit_differs(replace(self.cfg.network, linkages=tuple(lks)))

    def test_catches_reordered_descriptors(self) -> None:
        """Thứ tự descriptor có ý nghĩa trên sóng, nên đảo là khác."""
        self._nit_differs(replace(self.cfg.network,
                                  linkages=tuple(reversed(self.cfg.network.linkages))))

    def test_catches_missing_service_in_list(self) -> None:
        loops = self.cfg.network.ts_loops
        short = replace(loops[0], services=loops[0].services[1:])
        self._nit_differs(replace(self.cfg.network, ts_loops=(short,) + loops[1:]))

    def test_catches_frequency_off_by_one_step(self) -> None:
        loops = self.cfg.network.ts_loops
        d = loops[0].delivery
        moved = replace(loops[0], delivery=replace(d, frequency_hz=d.frequency_hz + 10_000))
        self._nit_differs(replace(self.cfg.network, ts_loops=(moved,) + loops[1:]))

    def test_catches_changed_lcn(self) -> None:
        b = next(x for x in self.cfg.bouquets if x.bouquet_id == 0x6510)
        loop = b.ts_loops[0]
        lcn = (replace(loop.lcn[0], lcn=999),) + loop.lcn[1:]
        bad = replace(b, ts_loops=(replace(loop, lcn=lcn),) + b.ts_loops[1:])
        self.assertNotEqual(T.canon(T.write_bat(bad)), T.canon(self.bat))

    def test_catches_changed_visible_flag(self) -> None:
        b = next(x for x in self.cfg.bouquets if x.bouquet_id == 0x6510)
        loop = b.ts_loops[0]
        lcn = (replace(loop.lcn[0], visible=False),) + loop.lcn[1:]
        bad = replace(b, ts_loops=(replace(loop, lcn=lcn),) + b.ts_loops[1:])
        self.assertNotEqual(T.canon(T.write_bat(bad)), T.canon(self.bat))


if __name__ == "__main__":
    unittest.main()

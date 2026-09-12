"""Luật linkage và vòng transport — ``model.linkage`` và ``model.topology``.

Hai nhóm bài đáng chú ý:

* ``TestOrderAndDuplicatesSurvive`` — bouquet 0x3622 đang phát **hai mục 0x80
  giống hệt nhau**. Bất kỳ cách sửa nào khoá theo nội dung sẽ gộp chúng lại và
  làm đổi byte trên sóng. Bài này giữ cho điều đó không xảy ra.
* ``TestTheSeededConfigIsAudited`` — luật gặp dữ liệu thật. Nó đếm được **sáu**
  linkage trỏ vào TSID không tồn tại, trong khi RO-8 của đặc tả chỉ ghi năm.
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

import seed
from vtcsi.config import loader
from vtcsi.model import linkage as K
from vtcsi.model import topology as T
from vtcsi.model.entities import (
    BatTsLoop,
    Bouquet,
    Config,
    Linkage,
    Network,
    NitTsLoop,
    SdtTable,
    Service,
    ServiceRef,
    ServiceType,
)

CONFIG = Path(__file__).parent.parent / "config"


def link(kind: int = 0x80, ts: int = 5, onid: int = 1, sid: int = 10,
         data: bytes = b"") -> Linkage:
    return Linkage(linkage_type=kind, ts_id=ts, original_network_id=onid,
                   service_id=sid, private_data=data)


def tiny(linkages: tuple[Linkage, ...] = (),
         loops: tuple[BatTsLoop, ...] = ()) -> Config:
    return Config(
        network=Network(network_id=1, name="N", version=0, ts_loops=(
            NitTsLoop(ts_id=5, original_network_id=1),)),
        sdts=(SdtTable(ts_id=5, original_network_id=1, version=0, actual=True,
                       services=(Service(service_id=10, name="K", provider="V",
                                         service_type=ServiceType(1)),)),),
        bouquets=(Bouquet(bouquet_id=0x0100, name="B", version=0,
                          linkages=linkages, ts_loops=loops),),
    )


# --------------------------------------------------------------------- hex


class TestHex(unittest.TestCase):
    def test_spaced_and_solid_both_parse(self) -> None:
        self.assertEqual(K.parse_hex("FF 04 FF"), K.parse_hex("ff04ff"))

    def test_separators_are_forgiven(self) -> None:
        """Nguoi ta dan tu noi khac vao, va moi cong cu dung mot dau khac."""
        for text in ("ff-04-ff", "ff:04:ff", "FF 04  FF", "\tff04 ff\n"):
            with self.subTest(text=text):
                self.assertEqual(K.parse_hex(text), b"\xff\x04\xff")

    def test_empty_is_empty(self) -> None:
        self.assertEqual(K.parse_hex("   "), b"")

    def test_odd_length_is_refused_with_a_useful_message(self) -> None:
        with self.assertRaises(K.LinkageError) as e:
            K.parse_hex("ff0")
        self.assertIn("hai ký tự", str(e.exception))

    def test_not_hex_is_refused(self) -> None:
        with self.assertRaises(K.LinkageError):
            K.parse_hex("xyz!")

    def test_round_trip_matches_how_the_seed_writes_it(self) -> None:
        self.assertEqual(K.format_hex(K.parse_hex("ff04ff")), "FF 04 FF")

    def test_every_byte_survives(self) -> None:
        raw = bytes(range(256))
        self.assertEqual(K.parse_hex(K.format_hex(raw)), raw)


class TestDescribe(unittest.TestCase):
    def test_a_standard_type_gets_its_name(self) -> None:
        self.assertIn("SSU", K.describe(0x09))

    def test_a_user_defined_type_says_we_have_no_spec(self) -> None:
        self.assertIn("không có đặc tả", K.describe(0x92))
        self.assertTrue(K.is_opaque(0x92))

    def test_a_standard_type_is_not_opaque(self) -> None:
        self.assertFalse(K.is_opaque(0x09))

    def test_reserved_values_are_named_as_such(self) -> None:
        for kind in (0x00, 0xFF):
            with self.subTest(kind=kind):
                self.assertIn("dành riêng", K.describe(kind))


# ----------------------------------------------------------------- kiểm tra


class TestCheck(unittest.TestCase):
    def test_a_sound_linkage_says_nothing(self) -> None:
        self.assertEqual(K.check(tiny((link(),),)), ())

    def test_a_dangling_target_is_reported_not_blocked(self) -> None:
        """Sau muc nhu the dang phat — chan o day la chan ca ban gieo."""
        got = K.check(tiny((link(ts=999),)))
        self.assertEqual(len(got), 1)
        self.assertFalse(got[0].blocking)
        self.assertIn("999", got[0].message)
        self.assertIn("RO-8", got[0].message)

    def test_reserved_type_is_blocking(self) -> None:
        for kind in (0x00, 0xFF):
            with self.subTest(kind=kind):
                self.assertTrue(K.blocking(K.check(tiny((link(kind=kind),)))))

    def test_a_field_beyond_sixteen_bits_is_blocking(self) -> None:
        for field in ("ts_id", "original_network_id", "service_id"):
            with self.subTest(field=field):
                bad = replace(link(), **{field: 70000})
                got = K.blocking(K.check(tiny((bad,))))
                self.assertTrue(any(field in p.message for p in got))

    def test_private_data_too_long_for_a_descriptor_is_blocking(self) -> None:
        got = K.blocking(K.check(tiny((link(data=bytes(K.MAX_PRIVATE_DATA + 1)),))))
        self.assertTrue(any("vượt trần" in p.message for p in got))

    def test_private_data_at_the_ceiling_is_fine(self) -> None:
        """Tran tinh ra tu 255 - 7, khong phai uoc chung."""
        self.assertEqual(K.MAX_PRIVATE_DATA, 255 - 7)
        self.assertEqual(K.check(tiny((link(data=bytes(K.MAX_PRIVATE_DATA)),))), ())

    def test_the_index_is_reported_so_it_can_be_found(self) -> None:
        got = K.check(tiny((link(), link(ts=999))))
        self.assertEqual(got[0].index, 1)
        self.assertIn("BAT 0100", got[0].where)


# ------------------------------------------------------------------ sửa đổi


class TestEditing(unittest.TestCase):
    def setUp(self) -> None:
        self.items = (link(sid=1), link(sid=2), link(sid=3))

    def test_set_at_replaces_in_place(self) -> None:
        out = K.set_at(self.items, 1, link(sid=99))
        self.assertEqual([k.service_id for k in out], [1, 99, 3])

    def test_append_goes_on_the_end(self) -> None:
        out = K.append(self.items, link(sid=4))
        self.assertEqual([k.service_id for k in out], [1, 2, 3, 4])

    def test_remove_at_takes_exactly_one(self) -> None:
        out = K.remove_at(self.items, 0)
        self.assertEqual([k.service_id for k in out], [2, 3])

    def test_an_index_past_the_end_is_refused(self) -> None:
        for i in (3, 99, -1):
            with self.subTest(i=i):
                with self.assertRaises(K.LinkageError):
                    K.set_at(self.items, i, link())
                with self.assertRaises(K.LinkageError):
                    K.remove_at(self.items, i)

    def test_a_refused_edit_changes_nothing(self) -> None:
        before = self.items
        with self.assertRaises(K.LinkageError):
            K.set_at(self.items, 0, link(kind=0xFF))
        self.assertEqual(self.items, before)

    def test_writing_a_reserved_type_is_refused(self) -> None:
        with self.assertRaises(K.LinkageError):
            K.append(self.items, link(kind=0x00))

    def test_writing_an_oversize_field_is_refused(self) -> None:
        with self.assertRaises(K.LinkageError):
            K.append(self.items, replace(link(), ts_id=70000))


class TestOrderAndDuplicatesSurvive(unittest.TestCase):
    """Bouquet 0x3622 phat HAI muc 0x80 giong het nhau. Do la that."""

    def setUp(self) -> None:
        same = link(kind=0x80, ts=8, onid=12901, sid=852, data=b"\x35\x02")
        self.items = (same, link(kind=0x82, sid=51), same)

    def test_duplicates_are_kept_as_two(self) -> None:
        self.assertEqual(len(self.items), 3)
        self.assertEqual(self.items[0], self.items[2])

    def test_editing_one_duplicate_leaves_the_other(self) -> None:
        out = K.set_at(self.items, 0, link(kind=0x80, sid=900))
        self.assertEqual(out[0].service_id, 900)
        self.assertEqual(out[2].service_id, 852)

    def test_removing_one_duplicate_leaves_the_other(self) -> None:
        out = K.remove_at(self.items, 2)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0].service_id, 852)

    def test_the_order_never_shifts(self) -> None:
        out = K.set_at(self.items, 1, link(kind=0x82, sid=77))
        self.assertEqual([k.linkage_type for k in out], [0x80, 0x82, 0x80])


# ----------------------------------------------------------- vòng transport


class TestTransportLoops(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = tiny(loops=(BatTsLoop(ts_id=5, original_network_id=1),))
        self.b = self.cfg.bouquets[0]

    def test_adding_a_loop(self) -> None:
        out = T.add_loop(self.b, 7, 12901)
        self.assertEqual([t.ts_id for t in out.ts_loops], [5, 7])
        self.assertEqual(out.ts_loops[1].original_network_id, 12901)

    def test_a_new_loop_starts_empty(self) -> None:
        """Them vong va chon kenh la hai quyet dinh khac nhau."""
        out = T.add_loop(self.b, 7, 1)
        self.assertEqual(out.ts_loops[1].services, ())
        self.assertEqual(out.ts_loops[1].lcn, ())

    def test_adding_a_loop_that_exists_is_refused(self) -> None:
        with self.assertRaises(T.TopologyError):
            T.add_loop(self.b, 5, 1)

    def test_oversize_identifiers_are_refused(self) -> None:
        with self.assertRaises(T.TopologyError):
            T.add_loop(self.b, 70000, 1)
        with self.assertRaises(T.TopologyError):
            T.add_loop(self.b, 7, 70000)

    def test_removing_an_empty_loop(self) -> None:
        self.assertEqual(T.remove_loop(self.b, 5).ts_loops, ())

    def test_removing_a_loop_with_channels_needs_confirmation(self) -> None:
        """Bo mot vong day la go hang chuc kenh bang mot cu bam."""
        full = replace(self.b, ts_loops=(replace(
            self.b.ts_loops[0], services=(ServiceRef(10, 1),)),))
        with self.assertRaises(T.TopologyError) as e:
            T.remove_loop(full, 5)
        self.assertIn("1 dịch vụ", str(e.exception))
        self.assertEqual(T.remove_loop(full, 5, force=True).ts_loops, ())

    def test_removing_a_loop_that_is_not_there(self) -> None:
        with self.assertRaises(T.TopologyError):
            T.remove_loop(self.b, 99)

    def test_has_loop(self) -> None:
        self.assertTrue(T.has_loop(self.b, 5))
        self.assertFalse(T.has_loop(self.b, 99))

    def test_the_onid_suggestion_comes_from_the_sdt(self) -> None:
        self.assertEqual(T.suggested_onid(self.cfg, 5), 1)
        self.assertIsNone(T.suggested_onid(self.cfg, 99))

    def test_the_pds_suggestion_follows_the_siblings(self) -> None:
        """Vong moi thieu PDS ma co LCN thi dau thu khong hieu descriptor LCN."""
        withpds = replace(self.b, ts_loops=(replace(
            self.b.ts_loops[0], private_data_specifier="NorDig"),))
        cfg = replace(self.cfg, bouquets=(withpds,))
        self.assertEqual(T.suggested_pds(cfg, withpds), "NorDig")

    def test_the_pds_suggestion_reaches_other_bouquets(self) -> None:
        """0x6520 khong co vong nao — chi nhin trong no thi khong goi y duoc gi."""
        donor = Bouquet(bouquet_id=0x0200, name="D", version=0, ts_loops=(
            BatTsLoop(ts_id=5, original_network_id=1,
                      private_data_specifier="NorDig"),))
        bare = Bouquet(bouquet_id=0x0300, name="E", version=0)
        cfg = replace(self.cfg, bouquets=(bare, donor))
        self.assertEqual(T.suggested_pds(cfg, bare), "NorDig")

    def test_no_pds_anywhere_suggests_nothing(self) -> None:
        bare = Bouquet(bouquet_id=0x0300, name="E", version=0)
        cfg = replace(self.cfg, bouquets=(bare,))
        self.assertIsNone(T.suggested_pds(cfg, bare))

    def test_a_bouquet_carrying_only_linkages_is_not_called_empty(self) -> None:
        """0x0044 va 0x3622 mang con tro OTA — do la cach dung hop le."""
        only_links = tiny(linkages=(link(),))
        self.assertEqual(T.says_nothing(only_links), ())

    def test_a_bouquet_with_neither_says_nothing(self) -> None:
        self.assertEqual(T.says_nothing(tiny()), (0x0100,))


# ------------------------------------------------------------ dữ liệu thật


class TestTheSeededConfigIsAudited(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        td = seed.committed_config()
        try:
            cls.cfg = loader.load(Path(td.name) / "config")
        finally:
            td.cleanup()
        cls.problems = K.check(cls.cfg)

    def test_nothing_blocking_is_on_air(self) -> None:
        self.assertEqual([p.text() for p in K.blocking(self.problems)], [])

    def test_six_linkages_point_nowhere_not_five(self) -> None:
        """RO-8 cua dac ta dem thieu mot: muc 0x82 toan so 0 trong NIT."""
        self.assertEqual(len(self.problems), 6,
                         "\n".join(p.text() for p in self.problems))

    def test_one_of_them_is_in_the_nit(self) -> None:
        self.assertTrue(any(p.where == "NIT" for p in self.problems))

    def test_the_bad_targets_are_the_ones_we_expect(self) -> None:
        bad = sorted({int(p.message.split("TS ")[1].split()[0])
                      for p in self.problems})
        self.assertEqual(bad, [0, 9, 16, 12901])

    def test_pds_is_present_exactly_where_channel_numbers_are(self) -> None:
        """Bat bien that tren song, va no chat hon "vong nao cung co PDS".

        `private_data_specifier` chi de gioi han pham vi cho descriptor rieng
        dung ngay sau no. Vong co so kenh thi BAT BUOC co PDS, khong thi dau
        thu khong hieu descriptor LCN. Vong khong co so kenh thi khong can —
        va bouquet 0x6550 dung la khong co, ca ba vong.
        """
        for b in self.cfg.bouquets:
            for t in b.ts_loops:
                with self.subTest(bouquet=f"{b.bouquet_id:04x}", ts=t.ts_id):
                    self.assertEqual(bool(t.lcn),
                                     t.private_data_specifier is not None)

    def test_the_pds_in_use_is_the_string_not_a_number(self) -> None:
        """Go 0x00000029 ra dung byte, nhung YAML se doc thanh 41 va lech han."""
        seen = {t.private_data_specifier
                for b in self.cfg.bouquets for t in b.ts_loops
                if t.private_data_specifier is not None}
        self.assertEqual(seen, {"NorDig"})

    def test_only_one_bouquet_truly_says_nothing(self) -> None:
        self.assertEqual(T.says_nothing(self.cfg), (0x6520,))

    def test_the_transport_streams_do_not_share_one_network_id(self) -> None:
        """Cho rat de go nham: TS 8 mang ONID 12901, TS 3 va 1000 mang ONID 1."""
        self.assertEqual(T.suggested_onid(self.cfg, 8), 12901)
        self.assertEqual(T.suggested_onid(self.cfg, 3), 1)
        self.assertEqual(T.suggested_onid(self.cfg, 1000), 1)

    def test_the_duplicate_pair_in_master_is_still_there(self) -> None:
        b = next(x for x in self.cfg.bouquets if x.bouquet_id == 0x3622)
        self.assertEqual(b.linkages[0], b.linkages[2])


if __name__ == "__main__":
    unittest.main()

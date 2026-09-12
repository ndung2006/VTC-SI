"""Màn hình linkage và vòng transport.

Chạy trên bản sao của cấu hình **đã commit** (xem ``tests/seed.py``), vì các
bài ở đây khẳng định sự thật về bản gieo — trong khi thư mục ``config/`` là
chỗ người vận hành sửa mỗi ngày.

Hai nhóm đáng chú ý:

* ``TestDuplicatesSurviveTheRoundTrip`` — bouquet 0x3622 phát **hai mục 0x80
  giống hệt nhau**. Sửa một mục không được đụng mục kia, và thứ tự không được
  xê dịch: cả hai đều làm đổi byte trên sóng.
* ``TestPrivateDataIsNeverMangled`` — khối byte của Irdeto và ViCAS đi qua
  biểu mẫu HTML rồi quay về phải **giống hệt**. Đây là chỗ dễ mất byte nhất
  trong cả giao diện.
"""

from __future__ import annotations

import filecmp
import shutil
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    TestClient = None  # type: ignore[assignment]

import seed
from vtcsi.config import loader
from vtcsi.model import linkage as K
from vtcsi.model import topology as T

#: Đặt trong ``setUpClass`` từ bản đã commit.
GOC: Path

MASTER = 0x3622   # 10 linkage, trong do co mot cap trung lap
FULLHD = 0x6510   # 3 vong transport, 1 linkage
EMPTY = 0x6520    # khong vong nao, khong linkage nao — RO-15


class WebCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if TestClient is None:
            raise unittest.SkipTest("chua cai fastapi")
        global GOC
        cls._seed = seed.committed_config()
        GOC = Path(cls._seed.name) / "config"

    @classmethod
    def tearDownClass(cls) -> None:
        cls._seed.cleanup()

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.dir = self.root / "config"
        shutil.copytree(GOC, self.dir)
        from vtcsi.web.app import create_app
        # `require_login=False`: cac bai o day kiem viec SUA CAU HINH, khong
        # kiem dang nhap. Bat dang nhap len se bat moi bai phai qua scrypt —
        # cham ~100 ms moi lan dung `setUp` — ma khong kiem them duoc gi.
        # Phan xac thuc co bo bai rieng o `test_web_auth.py`, va o day mac dinh
        # BAT la dieu bai `test_web_auth` ghim lai.
        self.c = TestClient(create_app(self.dir, self.root,
                                       require_login=False))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # -------------------------------------------------------------- tro giup

    def cfg(self):
        return loader.load(self.dir)

    def bouquet(self, bid: int):
        return next(x for x in self.cfg().bouquets if x.bouquet_id == bid)

    def links(self, raw: str):
        if raw == "nit":
            return self.cfg().network.linkages
        return self.bouquet(int(raw, 16)).linkages

    def post(self, url: str, **data):
        return self.c.post(url, data=data, follow_redirects=False)

    def said(self, r) -> str:
        q = parse_qs(urlparse(r.headers.get("location", "")).query)
        return (q.get("note") or q.get("err") or [""])[0]

    def kind(self, r) -> str:
        q = parse_qs(urlparse(r.headers.get("location", "")).query)
        return "note" if "note" in q else ("err" if "err" in q else "?")

    def assertRefused(self, r, fragment: str = "") -> None:
        self.assertEqual(self.kind(r), "err",
                         f"dang le phai tu choi, nhung: {self.said(r)}")
        if fragment:
            self.assertIn(fragment, self.said(r))

    def assertAccepted(self, r) -> None:
        self.assertEqual(self.kind(r), "note", self.said(r))

    def assertNothingWritten(self) -> None:
        def walk(cmp_, prefix=""):
            out = [prefix + f for f in cmp_.diff_files]
            for name, sub in cmp_.subdirs.items():
                out += walk(sub, prefix + name + "/")
            return out
        self.assertEqual(walk(filecmp.dircmp(str(GOC), str(self.dir))), [])

    def save(self, raw: str, index: int, k=None, **over):
        """Gửi biểu mẫu sửa, mặc định lấy y nguyên mục đang có."""
        if k is None and index >= 0:
            k = self.links(raw)[index]
        data = dict(
            index=index,
            linkage_type=f"0x{k.linkage_type:02x}" if k else "0x80",
            ts_id=k.ts_id if k else 8,
            original_network_id=k.original_network_id if k else 12901,
            service_id=k.service_id if k else 1,
            private_data=K.format_hex(k.private_data) if k else "",
        )
        data.update(over)
        return self.post(f"/linkage/{raw}/save", **data)


class TestPagesRender(WebCase):
    def test_the_overview_opens(self) -> None:
        self.assertEqual(self.c.get("/linkage").status_code, 200)

    def test_every_linkage_has_an_edit_page(self) -> None:
        cfg = self.cfg()
        targets = [("nit", len(cfg.network.linkages))]
        targets += [(f"{b.bouquet_id:04x}", len(b.linkages)) for b in cfg.bouquets]
        for raw, n in targets:
            for i in range(n):
                with self.subTest(raw=raw, i=i):
                    self.assertEqual(
                        self.c.get(f"/linkage/{raw}/{i}").status_code, 200)

    def test_the_new_page_opens_everywhere(self) -> None:
        for raw in ("nit", f"{MASTER:04x}", f"{EMPTY:04x}"):
            with self.subTest(raw=raw):
                self.assertEqual(self.c.get(f"/linkage/{raw}/moi").status_code, 200)

    def test_an_unknown_place_redirects(self) -> None:
        self.assertRefused(self.c.get("/linkage/xyz/0", follow_redirects=False))

    def test_an_index_past_the_end_redirects(self) -> None:
        self.assertRefused(
            self.c.get("/linkage/nit/99", follow_redirects=False), "99")

    def test_the_overview_warns_about_dangling_targets(self) -> None:
        """RO-8 — sau muc tro vao TSID khong ton tai."""
        page = self.c.get("/linkage").text
        self.assertIn("RO-8", page)

    def test_the_overview_says_we_have_no_irdeto_spec(self) -> None:
        self.assertIn("không biết", self.c.get("/linkage").text)


class TestEditing(WebCase):
    def test_changing_a_service_id(self) -> None:
        before = self.links("nit")[0]
        self.assertAccepted(self.save("nit", 0, service_id=999))
        self.assertEqual(self.links("nit")[0].service_id, 999)

    def test_the_other_fields_survive(self) -> None:
        before = self.links("nit")[0]
        self.save("nit", 0, service_id=999)
        after = self.links("nit")[0]
        self.assertEqual(after.linkage_type, before.linkage_type)
        self.assertEqual(after.ts_id, before.ts_id)
        self.assertEqual(after.private_data, before.private_data)

    def test_a_reserved_type_is_refused(self) -> None:
        for bad in ("0x00", "0xff", "255", "0"):
            with self.subTest(bad=bad):
                self.assertRefused(self.save("nit", 0, linkage_type=bad),
                                   "dành riêng")
                self.assertNothingWritten()

    def test_a_type_that_is_not_a_number_is_refused(self) -> None:
        self.assertRefused(self.save("nit", 0, linkage_type="irdeto"), "irdeto")
        self.assertNothingWritten()

    def test_decimal_and_hex_both_work(self) -> None:
        self.assertAccepted(self.save("nit", 0, linkage_type="146"))
        self.assertEqual(self.links("nit")[0].linkage_type, 0x92)

    def test_a_field_beyond_sixteen_bits_is_refused(self) -> None:
        self.assertRefused(self.save("nit", 0, ts_id=70000), "16 bit")
        self.assertNothingWritten()

    def test_a_dangling_target_is_allowed_through(self) -> None:
        """Sau muc nhu the dang phat — chan o day la chan ca ban gieo."""
        self.assertAccepted(self.save("nit", 0, ts_id=4242))
        self.assertEqual(self.links("nit")[0].ts_id, 4242)

    def test_adding_to_a_bouquet(self) -> None:
        raw = f"{FULLHD:04x}"
        before = len(self.links(raw))
        self.assertAccepted(self.post(
            f"/linkage/{raw}/save", index=-1, linkage_type="0x09", ts_id=8,
            original_network_id=12901, service_id=852, private_data="12 00 01"))
        self.assertEqual(len(self.links(raw)), before + 1)
        self.assertEqual(self.links(raw)[-1].private_data, b"\x12\x00\x01")

    def test_a_new_one_goes_on_the_end(self) -> None:
        raw = f"{MASTER:04x}"
        before = [k.linkage_type for k in self.links(raw)]
        self.post(f"/linkage/{raw}/save", index=-1, linkage_type="0x05",
                  ts_id=8, original_network_id=12901, service_id=1,
                  private_data="")
        self.assertEqual([k.linkage_type for k in self.links(raw)],
                         before + [0x05])


class TestPrivateDataIsNeverMangled(WebCase):
    """Byte cua Irdeto va ViCAS qua bieu mau HTML roi quay ve phai giong het."""

    def test_the_seeded_bytes_survive_a_no_op_save(self) -> None:
        before = self.links("nit")[0].private_data
        self.assertTrue(before, "ban gieo phai co du lieu rieng de thu")
        self.assertAccepted(self.save("nit", 0))
        self.assertEqual(self.links("nit")[0].private_data, before)

    def test_a_no_op_save_rewrites_nothing_on_disk(self) -> None:
        self.save("nit", 0)
        self.assertNothingWritten()

    def test_solid_hex_is_accepted_too(self) -> None:
        self.assertAccepted(self.save("nit", 0, private_data="deadbeef"))
        self.assertEqual(self.links("nit")[0].private_data, b"\xde\xad\xbe\xef")

    def test_odd_length_hex_is_refused(self) -> None:
        self.assertRefused(self.save("nit", 0, private_data="ff0"), "hai ký tự")
        self.assertNothingWritten()

    def test_rubbish_is_refused(self) -> None:
        self.assertRefused(self.save("nit", 0, private_data="khong phai hex"))
        self.assertNothingWritten()

    def test_it_can_be_cleared(self) -> None:
        self.assertAccepted(self.save("nit", 0, private_data=""))
        self.assertEqual(self.links("nit")[0].private_data, b"")

    def test_every_byte_value_survives(self) -> None:
        """Ca 256 gia tri byte, trong mot khoi dai het muc cho phep."""
        raw = bytes(range(256))[:K.MAX_PRIVATE_DATA]
        self.assertEqual(len(set(raw)), K.MAX_PRIVATE_DATA)
        self.assertAccepted(self.save("nit", 0, private_data=K.format_hex(raw)))
        self.assertEqual(self.links("nit")[0].private_data, raw)

    def test_one_byte_past_the_ceiling_is_refused(self) -> None:
        over = bytes(K.MAX_PRIVATE_DATA + 1)
        self.assertRefused(self.save("nit", 0, private_data=K.format_hex(over)),
                           str(K.MAX_PRIVATE_DATA))
        self.assertNothingWritten()


class TestDuplicatesSurviveTheRoundTrip(WebCase):
    """Bouquet 0x3622 phat hai muc 0x80 giong het nhau — do la that."""

    def setUp(self) -> None:
        super().setUp()
        self.raw = f"{MASTER:04x}"
        items = self.links(self.raw)
        if len(items) < 3 or items[0] != items[2]:
            self.skipTest("ban gieo khong con cap trung lap")

    def test_editing_the_first_leaves_the_third(self) -> None:
        self.assertAccepted(self.save(self.raw, 0, service_id=900))
        after = self.links(self.raw)
        self.assertEqual(after[0].service_id, 900)
        self.assertEqual(after[2].service_id, 852)

    def test_deleting_the_first_leaves_the_third(self) -> None:
        before = len(self.links(self.raw))
        self.assertAccepted(self.post(f"/linkage/{self.raw}/0/delete",
                                      confirm="0x80"))
        after = self.links(self.raw)
        self.assertEqual(len(after), before - 1)
        self.assertEqual(after[1].service_id, 852)

    def test_the_order_of_types_never_shifts(self) -> None:
        before = [k.linkage_type for k in self.links(self.raw)]
        self.save(self.raw, 1, service_id=77)
        self.assertEqual([k.linkage_type for k in self.links(self.raw)], before)


class TestDeleting(WebCase):
    def test_the_wrong_confirmation_keeps_it(self) -> None:
        before = len(self.links("nit"))
        self.assertRefused(self.post("/linkage/nit/0/delete", confirm="0x99"),
                           "gõ đúng loại")
        self.assertEqual(len(self.links("nit")), before)
        self.assertNothingWritten()

    def test_an_empty_confirmation_keeps_it(self) -> None:
        before = len(self.links("nit"))
        self.post("/linkage/nit/0/delete", confirm="")
        self.assertEqual(len(self.links("nit")), before)

    def test_either_spelling_of_the_type_confirms(self) -> None:
        for text in ("0x92", "92", "0X92"):
            with self.subTest(text=text):
                self.setUp()
                self.assertAccepted(
                    self.post("/linkage/nit/0/delete", confirm=text))

    def test_deleting_shifts_the_rest_down(self) -> None:
        raw = f"{MASTER:04x}"
        before = [k.service_id for k in self.links(raw)]
        self.post(f"/linkage/{raw}/0/delete", confirm="0x80")
        self.assertEqual([k.service_id for k in self.links(raw)], before[1:])


class TestTransportLoops(WebCase):
    def loops(self, bid: int):
        return self.bouquet(bid).ts_loops

    def add(self, bid: int, **data):
        return self.post(f"/bouquet/{bid:04x}/ts/add", **data)

    def drop(self, bid: int, **data):
        return self.post(f"/bouquet/{bid:04x}/ts/drop", **data)

    def test_the_empty_bouquet_can_be_given_a_loop(self) -> None:
        """RO-15 — 0x6520 phat mot bang BAT khong noi gi."""
        self.assertEqual(self.loops(EMPTY), ())
        self.assertAccepted(self.add(EMPTY, ts_id=8, original_network_id=12901,
                                     pds="NorDig"))
        self.assertEqual([t.ts_id for t in self.loops(EMPTY)], [8])
        self.assertEqual(T.says_nothing(self.cfg()), ())

    def test_a_new_loop_starts_empty(self) -> None:
        self.add(EMPTY, ts_id=8, original_network_id=12901, pds="NorDig")
        loop = self.loops(EMPTY)[0]
        self.assertEqual(loop.services, ())
        self.assertEqual(loop.lcn, ())

    def test_the_specifier_is_kept_as_typed(self) -> None:
        """Chuoi "NorDig", khong bi doi thanh so."""
        self.add(EMPTY, ts_id=8, original_network_id=12901, pds="NorDig")
        self.assertEqual(self.loops(EMPTY)[0].private_data_specifier, "NorDig")

    def test_an_empty_specifier_means_none(self) -> None:
        self.add(EMPTY, ts_id=8, original_network_id=12901, pds="")
        self.assertIsNone(self.loops(EMPTY)[0].private_data_specifier)

    def test_a_duplicate_loop_is_refused(self) -> None:
        self.assertRefused(self.add(FULLHD, ts_id=8, original_network_id=12901,
                                    pds="NorDig"), "đã có vòng")
        self.assertNothingWritten()

    def test_an_oversize_network_id_is_refused(self) -> None:
        self.assertRefused(self.add(EMPTY, ts_id=8, original_network_id=70000,
                                    pds=""), "16 bit")
        self.assertNothingWritten()

    def test_an_empty_loop_drops_without_ceremony(self) -> None:
        self.add(EMPTY, ts_id=8, original_network_id=12901, pds="")
        self.assertAccepted(self.drop(EMPTY, ts_id=8, confirm=""))
        self.assertEqual(self.loops(EMPTY), ())

    def test_a_full_loop_needs_the_service_count(self) -> None:
        """Bo mot vong day la go hang chuc kenh bang mot cu bam."""
        loop = next(t for t in self.loops(FULLHD) if t.ts_id == 8)
        n = len(loop.services)
        self.assertGreater(n, 10)
        self.assertRefused(self.drop(FULLHD, ts_id=8, confirm=""), str(n))
        self.assertRefused(self.drop(FULLHD, ts_id=8, confirm=str(n - 1)))
        self.assertNothingWritten()

        self.assertAccepted(self.drop(FULLHD, ts_id=8, confirm=str(n)))
        self.assertEqual([t.ts_id for t in self.loops(FULLHD)], [3, 1000])

    def test_dropping_a_loop_that_is_not_there(self) -> None:
        self.assertRefused(self.drop(EMPTY, ts_id=99, confirm=""), "99")

    def test_the_suggested_network_id_matches_the_sdt(self) -> None:
        """TS 8 mang 12901, TS 3 va 1000 mang 1 — khong suy ra tu TSID duoc."""
        cfg = self.cfg()
        self.assertEqual(T.suggested_onid(cfg, 8), 12901)
        self.assertEqual(T.suggested_onid(cfg, 3), 1)

    def test_the_page_offers_the_missing_transport_streams(self) -> None:
        page = self.c.get(f"/bouquet/{EMPTY:04x}").text
        self.assertIn("Thêm một vòng transport", page)
        for ts in (3, 8, 1000):
            with self.subTest(ts=ts):
                self.assertIn(f"TS {ts}", page)


if __name__ == "__main__":
    unittest.main()

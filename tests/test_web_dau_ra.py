"""Trang "Đầu ra" — địa chỉ multicast ra headend.

Trang này khác mọi trang cấu hình khác của giao diện ở một chỗ, và đó là chỗ
đáng canh nhất: các trang kia ghi vào git rồi chờ bấm "áp dụng", nên một bản
nháp sai nằm yên cho tới lúc ai đó xem lại. File này thì ``vtcsi run`` đọc
thẳng lúc khởi động. Ghi một địa chỉ hỏng vào đây là để sẵn một quả mìn cho
lần dựng lại dịch vụ kế tiếp — mà lần đó thường xảy ra lúc nửa đêm, vì một lý
do khác, và không ai nhớ tới trang này.

Vì vậy ``TestABrokenAddressNeverReachesDisk`` là nhóm bài quan trọng nhất ở
đây: **chặn thì không ghi**, và file cũ phải còn nguyên.
"""

from __future__ import annotations

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
from vtcsi.config import output as CO
from vtcsi.model.output import Endpoint, Output
from vtcsi.web import auth as A

NGUOI = "admin"
MAT_KHAU = "mot cau dai de nho 2026"

TOT = {
    "dia_chi": "236.30.239.1", "cong": "6000", "card": "10.10.30.230",
    "sao_dia_chi": "236.30.239.2", "sao_cong": "6000", "sao_card": "10.10.31.230",
    "ttl": "8",
}


class DauRaCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if TestClient is None:
            raise unittest.SkipTest("chua cai fastapi")
        cls._seed = seed.committed_config()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._seed.cleanup()

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.dir = self.root / "config"
        shutil.copytree(Path(self._seed.name) / "config", self.dir)
        self.build = self.root / "build"
        self.auth_file = self.root / ".vtcsi-auth.json"
        A.save(self.auth_file, A.make(NGUOI, MAT_KHAU))

        from vtcsi.web.app import create_app
        self.c = TestClient(
            create_app(self.dir, self.root, auth_file=self.auth_file,
                       build_dir=self.build, eit_dir=self.build / "eit",
                       inbox=self.root / "inbox"),
            follow_redirects=False)
        self.dang_nhap()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # -------------------------------------------------------------- trợ giúp

    def dang_nhap(self) -> None:
        r = self.c.post("/dang-nhap", data={"user": NGUOI, "password": MAT_KHAU})
        self.assertEqual(r.status_code, 303)
        self.c.cookies.update(r.cookies)

    def luu(self, **doi):
        """Gửi biểu mẫu, mặc định là bản hợp lệ, ``doi`` bẻ đi một ô."""
        data = dict(TOT)
        data.update({k: str(v) for k, v in doi.items()})
        return self.c.post("/dau-ra/luu", data=data)

    def said(self, r) -> str:
        q = parse_qs(urlparse(r.headers.get("location", "")).query)
        return (q.get("note") or q.get("err") or [""])[0]

    @property
    def tren_dia(self) -> Output:
        return CO.load(self.dir)

    @property
    def co_file(self) -> bool:
        return CO.path_for(self.dir).exists()


class TestOpeningThePage(DauRaCase):
    def test_it_opens_on_a_machine_that_has_never_saved(self) -> None:
        """Chưa có file là trạng thái bình thường của máy vừa dựng."""
        self.assertFalse(self.co_file)
        r = self.c.get("/dau-ra")
        self.assertEqual(r.status_code, 200)

    def test_an_unset_output_says_it_cannot_go_on_air(self) -> None:
        """Nói rõ là CHƯA PHÁT ĐƯỢC, không chỉ là thiếu vài ô.

        Một máy chưa đặt đầu ra mà giao diện trông như bình thường là cách để
        người trực tưởng hệ đã sẵn sàng.
        """
        self.assertIn("Chưa đủ điều kiện phát sóng",
                      self.c.get("/dau-ra").text)

    def test_it_shows_what_is_on_disk(self) -> None:
        CO.save(Output(primary=Endpoint("236.30.239.7", 6100, "10.10.30.230"),
                       mirror=Endpoint("236.30.239.8", 6100, "10.10.31.230")),
                self.dir)
        t = self.c.get("/dau-ra").text
        for gia_tri in ("236.30.239.7", "6100", "10.10.30.230",
                        "236.30.239.8", "10.10.31.230"):
            self.assertIn(gia_tri, t)

    def test_both_sub_pages_link_to_each_other(self) -> None:
        """Hai trang con phải với được nhau từ cả hai phía."""
        for url in ("/dau-ra", "/epg"):
            with self.subTest(url=url):
                t = self.c.get(url).text
                self.assertIn('href="/epg"', t)
                self.assertIn('href="/dau-ra"', t)

    def test_the_open_sub_page_is_marked(self) -> None:
        self.assertIn('href="/dau-ra" class="day"', self.c.get("/dau-ra").text)
        self.assertIn('href="/epg" class="day"', self.c.get("/epg").text)

    def test_a_broken_file_on_disk_does_not_crash_the_page(self) -> None:
        CO.path_for(self.dir).write_text("primary: [\n", encoding="utf-8")
        r = self.c.get("/dau-ra")
        self.assertIn(r.status_code, (200, 500))
        self.assertIn(CO.FILE, r.text)

    def test_it_tells_whether_the_file_is_out_of_git(self) -> None:
        self.assertIn("Nằm ngoài git", self.c.get("/dau-ra").text)


class TestSavingAGoodOne(DauRaCase):
    def test_it_lands_on_disk(self) -> None:
        r = self.luu()
        self.assertEqual(r.status_code, 303)
        out = self.tren_dia
        self.assertEqual(out.primary, Endpoint("236.30.239.1", 6000, "10.10.30.230"))
        self.assertEqual(out.mirror, Endpoint("236.30.239.2", 6000, "10.10.31.230"))
        self.assertEqual(out.ttl, 8)

    def test_it_says_what_it_saved(self) -> None:
        self.assertIn("236.30.239.1:6000", self.said(self.luu()))

    def test_it_says_the_change_needs_a_restart(self) -> None:
        """Tiến trình phát đọc file lúc khởi động. Nói thẳng, đừng để người ta
        tưởng vừa đổi được đường phát của dòng đang chạy."""
        self.assertIn("khởi động lại", self.said(self.luu()))

    def test_a_blank_mirror_turns_it_off(self) -> None:
        self.luu()
        self.assertIsNotNone(self.tren_dia.mirror)
        self.luu(sao_dia_chi="", sao_cong="", sao_card="")
        self.assertIsNone(self.tren_dia.mirror)

    def test_it_survives_a_round_trip_through_the_page(self) -> None:
        self.luu(dia_chi="239.1.2.3", cong="1234", card="",
                 sao_dia_chi="", sao_cong="", sao_card="", ttl="16")
        t = self.c.get("/dau-ra").text
        self.assertIn("239.1.2.3", t)
        self.assertIn("1234", t)
        self.assertIn('value="16"', t)

    def test_spaces_around_an_address_are_forgiven(self) -> None:
        """Dán từ tài liệu là kéo theo khoảng trắng. Cắt đi, đừng bắt gõ lại."""
        self.luu(dia_chi="  236.30.239.1  ")
        self.assertEqual(self.tren_dia.primary.address, "236.30.239.1")


class TestABrokenAddressNeverReachesDisk(DauRaCase):
    """Chặn thì **không ghi**. Đây là khác biệt so với các trang cấu hình khác."""

    def test_a_bad_address_is_refused(self) -> None:
        r = self.luu(dia_chi="236.30.239")
        self.assertEqual(r.status_code, 303)
        self.assertIn("Đường chính", self.said(r))
        self.assertFalse(self.co_file)

    def test_a_bad_port_is_refused(self) -> None:
        self.luu(cong="70000")
        self.assertFalse(self.co_file)

    def test_an_empty_form_is_refused(self) -> None:
        self.luu(dia_chi="", cong="", card="",
                 sao_dia_chi="", sao_cong="", sao_card="")
        self.assertFalse(self.co_file)

    def test_a_bad_interface_is_refused(self) -> None:
        self.luu(card="10.10.30")
        self.assertFalse(self.co_file)

    def test_a_bad_ttl_is_refused(self) -> None:
        self.luu(ttl="300")
        self.assertFalse(self.co_file)

    def test_a_mirror_identical_to_the_primary_is_refused(self) -> None:
        """Cùng địa chỉ, cùng cổng, cùng card: gói trùng, không phải dự phòng."""
        r = self.luu(sao_dia_chi=TOT["dia_chi"], sao_cong=TOT["cong"],
                     sao_card=TOT["card"])
        self.assertIn("trùng hoàn toàn", self.said(r))
        self.assertFalse(self.co_file)

    def test_a_refusal_leaves_the_previous_file_untouched(self) -> None:
        """Cái đang phát được phải sống sót qua một lần gõ nhầm."""
        self.luu()
        truoc = CO.path_for(self.dir).read_bytes()
        self.luu(dia_chi="khong-phai-dia-chi")
        self.assertEqual(CO.path_for(self.dir).read_bytes(), truoc)

    def test_letters_in_a_port_do_not_crash(self) -> None:
        """Trình duyệt chặn được, `curl` thì không. Vẫn phải là từ chối tử tế."""
        r = self.luu(cong="sau-nghin")
        self.assertEqual(r.status_code, 303)
        self.assertFalse(self.co_file)


class TestWarningsDoNotBlock(DauRaCase):
    def test_a_lone_primary_saves_but_warns(self) -> None:
        r = self.luu(sao_dia_chi="", sao_cong="", sao_card="")
        self.assertEqual(r.status_code, 303)
        self.assertTrue(self.co_file)
        self.assertIn("sao chép", self.c.get("/dau-ra").text)

    def test_a_unicast_destination_saves_but_warns(self) -> None:
        self.luu(dia_chi="10.10.30.9")
        self.assertTrue(self.co_file)
        self.assertIn("multicast", self.c.get("/dau-ra").text)

    def test_both_paths_on_one_card_saves_but_warns(self) -> None:
        self.luu(sao_card=TOT["card"])
        self.assertTrue(self.co_file)
        self.assertIn("một card mạng", self.c.get("/dau-ra").text)


class TestThePreviewCommand(DauRaCase):
    """Dòng lệnh in ra phải là **đúng** dòng sẽ chạy, không phải minh hoạ."""

    def test_a_good_output_shows_the_command(self) -> None:
        self.luu()
        t = self.c.get("/dau-ra").text
        self.assertIn("236.30.239.1:6000", t)
        self.assertIn("--ttl 8", t)

    def test_the_mirror_appears_as_a_forked_tsp(self) -> None:
        self.luu()
        t = self.c.get("/dau-ra").text
        self.assertIn("-P fork", t)
        self.assertIn("236.30.239.2:6000", t)

    def test_without_a_mirror_there_is_no_fork(self) -> None:
        self.luu(sao_dia_chi="", sao_cong="", sao_card="")
        self.assertNotIn("-P fork", self.c.get("/dau-ra").text)

    def test_both_cards_appear(self) -> None:
        self.luu()
        t = self.c.get("/dau-ra").text
        self.assertIn("10.10.30.230", t)
        self.assertIn("10.10.31.230", t)

    def test_no_command_while_something_blocks(self) -> None:
        """In một dòng lệnh cho cấu hình không chạy được là nói dối."""
        self.assertNotIn("-O ip", self.c.get("/dau-ra").text)


class TestTheDoorIsShut(DauRaCase):
    def test_both_routes_need_a_login(self) -> None:
        self.c.cookies.clear()
        for method, url in (("get", "/dau-ra"), ("post", "/dau-ra/luu")):
            with self.subTest(url=url):
                r = getattr(self.c, method)(url, **({"data": TOT}
                                                    if method == "post" else {}))
                self.assertEqual(r.status_code, 303)
                self.assertIn("/dang-nhap", r.headers["location"])

    def test_a_logged_out_post_writes_nothing(self) -> None:
        self.c.cookies.clear()
        self.c.post("/dau-ra/luu", data=TOT)
        self.assertFalse(self.co_file)


if __name__ == "__main__":
    unittest.main()

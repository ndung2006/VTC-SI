"""Thông báo Telegram — lõi, file YAML, đường gửi, và trang cấu hình.

**Không bài nào chạm mạng.** Đường gửi nhận một hàm ``mo`` tiêm vào thay cho
``urlopen``. Một bộ kiểm cần Internet là một bộ kiểm sẽ đỏ vào đúng hôm mạng cơ
quan trục trặc, và rồi không ai tin nó nữa.

Nhóm đáng chú ý nhất là ``TestKhongBaoGioNem``: nó ghim lời hứa quan trọng nhất
của cả tính năng — cảnh báo hỏng thì hệ vẫn phát sóng.
"""

from __future__ import annotations

import json
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
from vtcsi.config import telegram as C
from vtcsi.model import telegram as TG
from vtcsi.notify import telegram as N

TOKEN = "123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyz9"
DU = TG.Cai(token=TOKEN, chat_id="-1001", bat=True, ten_may="máy A")


class TraLoi:
    """Một câu trả lời giả của Bot API."""

    def __init__(self, than: dict) -> None:
        self._than = than

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self) -> bytes:
        return json.dumps(self._than).encode("utf-8")


def mo_ok(_req, timeout=None):
    return TraLoi({"ok": True})


class TestCheToken(unittest.TestCase):
    def test_it_keeps_the_bot_id_and_hides_the_secret(self) -> None:
        """Id giúp biết BOT NÀO và không phải bí mật; phần sau thì phải giấu."""
        che = TG.che(TOKEN)
        self.assertTrue(che.startswith("123456789:"))
        self.assertNotIn("AAH", che)
        self.assertTrue(che.endswith("yz9"))

    def test_an_empty_token_shows_nothing(self) -> None:
        self.assertEqual(TG.che(""), "")

    def test_a_malformed_token_is_still_hidden(self) -> None:
        self.assertNotIn("bimat", TG.che("bimatbimat"))


class TestSoanTin(unittest.TestCase):
    def test_the_machine_name_leads_every_message(self) -> None:
        """Hai máy cùng bắn vào một nhóm — không có tên thì không biết của ai."""
        self.assertTrue(TG.soan("nit", "x", (), "máy A").startswith("[máy A]"))

    def test_without_a_name_it_just_starts_with_the_kind(self) -> None:
        self.assertTrue(TG.soan("nit", "x").startswith(TG.LOAI["nit"]))

    def test_it_is_plain_text_not_markdown(self) -> None:
        """Tên kênh thật có ``_`` và ``*``; Markdown sẽ làm Bot API từ chối cả tin."""
        tin = TG.soan("thay-doi", "SDT ts8 đổi", ("  · kênh *VTC_1* [HD]",))
        self.assertIn("*VTC_1*", tin)
        self.assertIn("[HD]", tin)

    def test_a_very_long_message_is_cut_not_dropped(self) -> None:
        tin = TG.soan("thay-doi", "x", tuple(f"dòng {i}" for i in range(5000)))
        self.assertLessEqual(len(tin), TG.MAX_KY_TU)
        self.assertIn("cắt bớt", tin)


class TestChongDoi(unittest.TestCase):
    def test_the_first_message_always_goes(self) -> None:
        self.assertTrue(TG.nen_gui("k", 1000.0, {}, 5))

    def test_a_repeat_inside_the_window_is_held(self) -> None:
        self.assertFalse(TG.nen_gui("k", 1100.0, {"k": 1000.0}, 5))

    def test_after_the_window_it_goes_again(self) -> None:
        self.assertTrue(TG.nen_gui("k", 1301.0, {"k": 1000.0}, 5))

    def test_a_different_key_is_not_held(self) -> None:
        self.assertTrue(TG.nen_gui("k2", 1100.0, {"k": 1000.0}, 5))

    def test_zero_turns_it_off(self) -> None:
        self.assertTrue(TG.nen_gui("k", 1000.1, {"k": 1000.0}, 0))

    def test_it_does_not_record_anything_itself(self) -> None:
        """Ghi nhận trước khi gửi thành công thì tin hỏng sẽ mất luôn."""
        da = {}
        TG.nen_gui("k", 1000.0, da, 5)
        self.assertEqual(da, {})


class TestBatLoai(unittest.TestCase):
    def test_the_master_switch_silences_everything(self) -> None:
        c = TG.Cai(token=TOKEN, chat_id="-1", bat=False)
        self.assertFalse(any(TG.bat_loai(c, k) for k in TG.LOAI))

    def test_a_missing_token_silences_everything(self) -> None:
        self.assertFalse(TG.bat_loai(TG.Cai(chat_id="-1", bat=True), "nit"))

    def test_each_kind_can_be_turned_off_on_its_own(self) -> None:
        from dataclasses import replace
        c = replace(DU, bao_nit=False)
        self.assertFalse(TG.bat_loai(c, "nit"))
        self.assertTrue(TG.bat_loai(c, "epg"))

    def test_the_hyphenated_kind_maps_to_its_field(self) -> None:
        self.assertTrue(TG.bat_loai(DU, "thay-doi"))


class TestKiemCauHinh(unittest.TestCase):
    def test_on_without_a_token_is_refused(self) -> None:
        with self.assertRaises(TG.TelegramError):
            TG.validate(TG.Cai(bat=True, chat_id="-1"))

    def test_on_without_a_chat_id_is_refused(self) -> None:
        with self.assertRaises(TG.TelegramError):
            TG.validate(TG.Cai(bat=True, token=TOKEN))

    def test_a_token_without_a_colon_is_refused(self) -> None:
        with self.assertRaises(TG.TelegramError) as e:
            TG.validate(TG.Cai(token="khongcodauhaicham"))
        self.assertIn("BotFather", str(e.exception))

    def test_off_and_empty_is_fine(self) -> None:
        TG.validate(TG.Cai())


class TestKhongBaoGioNem(unittest.TestCase):
    """Lời hứa quan trọng nhất: cảnh báo hỏng thì hệ vẫn phát sóng."""

    def test_a_dead_network_returns_false_not_an_exception(self) -> None:
        def no(_req, timeout=None):
            raise OSError("mang hong")
        xong, vi_sao = N.gui(DU, "x", mo=no)
        self.assertFalse(xong)
        self.assertIn("mang hong", vi_sao)

    def test_any_exception_at_all_is_swallowed(self) -> None:
        def no(_req, timeout=None):
            raise RuntimeError("chuyen la")
        self.assertFalse(N.gui(DU, "x", mo=no)[0])

    def test_bot_api_saying_no_is_reported_not_raised(self) -> None:
        def tu_choi(_req, timeout=None):
            return TraLoi({"ok": False, "description": "chat not found"})
        xong, vi_sao = N.gui(DU, "x", mo=tu_choi)
        self.assertFalse(xong)
        self.assertIn("chat not found", vi_sao)

    def test_garbage_back_from_the_server_is_swallowed(self) -> None:
        class Rac(TraLoi):
            def read(self):
                return b"<html>502 bad gateway</html>"
        self.assertFalse(N.gui(DU, "x", mo=lambda r, timeout=None: Rac({}))[0])

    def test_not_configured_sends_nothing(self) -> None:
        goi = []
        N.gui(TG.Cai(), "x", mo=lambda r, timeout=None: goi.append(r))
        self.assertEqual(goi, [])

    def test_the_background_sender_returns_none_when_off(self) -> None:
        self.assertIsNone(N.gui_nen(TG.Cai(), "x"))

    def test_the_background_sender_logs_a_failure(self) -> None:
        ghi = []
        def no(_req, timeout=None):
            raise OSError("hong")
        t = N.gui_nen(DU, "x", ghi=ghi.append, mo=no)
        t.join(timeout=5)
        self.assertTrue(any("telegram" in m for m in ghi))


class TestGuiDung(unittest.TestCase):
    def test_it_posts_the_text_and_chat_id(self) -> None:
        thay = {}
        def bat(req, timeout=None):
            thay["url"] = req.full_url
            thay["than"] = json.loads(req.data.decode("utf-8"))
            return TraLoi({"ok": True})
        self.assertTrue(N.gui(DU, "xin chào", mo=bat)[0])
        self.assertEqual(thay["than"]["chat_id"], "-1001")
        self.assertEqual(thay["than"]["text"], "xin chào")
        self.assertIn(TOKEN, thay["url"])


class TestFileYaml(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_a_missing_file_means_off(self) -> None:
        c = C.load(self.dir)
        self.assertFalse(c.bat)
        self.assertFalse(c.san_sang)

    def test_round_trip(self) -> None:
        C.save(DU, self.dir)
        self.assertEqual(C.load(self.dir), DU)

    def test_an_unknown_key_is_refused(self) -> None:
        C.path_for(self.dir).write_text("khong_hieu: 1\n", encoding="utf-8")
        with self.assertRaises(TG.TelegramError):
            C.load(self.dir)

    def test_saving_an_illegal_config_writes_nothing(self) -> None:
        with self.assertRaises(TG.TelegramError):
            C.save(TG.Cai(bat=True), self.dir)
        self.assertFalse(C.path_for(self.dir).exists())

    def test_the_file_is_kept_out_of_git(self) -> None:
        """Kho này công khai. Token lọt lên đó thì phải thu hồi rồi cấp lại."""
        goc = Path(__file__).resolve().parent.parent
        bo_qua = (goc / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("config/" + C.FILE, bo_qua)


class TestTrangWeb(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if TestClient is None:
            raise unittest.SkipTest("chua cai fastapi")
        cls._seed = seed.committed_config()
        cls.goc = Path(cls._seed.name) / "config"

    @classmethod
    def tearDownClass(cls) -> None:
        cls._seed.cleanup()

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.dir = self.root / "config"
        shutil.copytree(self.goc, self.dir)
        from vtcsi.web.app import create_app
        self.c = TestClient(create_app(self.dir, self.root, require_login=False))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def said(self, r) -> tuple[str, str]:
        q = parse_qs(urlparse(r.headers.get("location", "")).query)
        return (q.get("note") or [""])[0], (q.get("err") or [""])[0]

    def post(self, url="/telegram/luu", **data):
        return self.c.post(url, data=data, follow_redirects=False)

    def test_the_page_explains_how_to_get_a_token(self) -> None:
        html = self.c.get("/telegram").text
        self.assertIn("BotFather", html)
        self.assertIn("getUpdates", html)

    def test_it_saves(self) -> None:
        note, err = self.said(self.post(token=TOKEN, chat_id="-1001",
                                        bat="true", ten_may="máy A"))
        self.assertFalse(err)
        c = C.load(self.dir)
        self.assertTrue(c.bat)
        self.assertEqual(c.chat_id, "-1001")

    def test_an_empty_token_box_keeps_the_saved_one(self) -> None:
        """Mở trang tích một ô rồi Lưu không được làm mất kết nối."""
        C.save(DU, self.dir)
        self.post(token="", chat_id="-1001", bat="true")
        self.assertEqual(C.load(self.dir).token, TOKEN)

    def test_the_raw_token_never_reaches_the_page_body_twice(self) -> None:
        C.save(DU, self.dir)
        html = self.c.get("/telegram").text
        self.assertIn(TG.che(TOKEN), html)

    def test_a_malformed_token_is_refused_in_vietnamese(self) -> None:
        _, err = self.said(self.post(token="khongcodauhaicham",
                                     chat_id="-1", bat="true"))
        self.assertIn("BotFather", err)

    def test_turning_the_master_switch_off_is_allowed_with_a_token(self) -> None:
        C.save(DU, self.dir)
        self.post(chat_id="-1001")          # khong gui `bat`
        self.assertFalse(C.load(self.dir).bat)

    def test_each_kind_switch_round_trips(self) -> None:
        self.post(token=TOKEN, chat_id="-1", bat="true", bao_nit="true")
        c = C.load(self.dir)
        self.assertTrue(c.bao_nit)
        self.assertFalse(c.bao_epg)

    def test_the_test_button_refuses_when_not_configured(self) -> None:
        _, err = self.said(self.c.post("/telegram/thu", follow_redirects=False))
        self.assertIn("chưa bật", err)

    def test_the_admin_page_links_to_it(self) -> None:
        self.assertIn("/telegram", self.c.get("/quan-tri").text)


if __name__ == "__main__":
    unittest.main()

"""Hai lệnh vận hành — ``vtcsi refresh`` và ``vtcsi run``.

Không bài nào phát ra mạng và không bài nào cần ``tsp``: ``run`` chỉ được gọi
ở chế độ ``--dry-run``, còn phần trông chừng đã có ``test_supervise.py`` lo.

Bài đáng giá nhất ở đây là ``TestEmptyEitIsRefused``. Nó canh một kịch bản rất
dễ xảy ra và rất khó nhận ra: hộp thư chỉ còn lịch cũ, ``vtcsi epg`` sinh ra
một EIT rỗng, ghi đè lên file đang phát, và **cả mạng mất EPG** — do đúng một
lệnh chạy định kỳ, không có ai làm gì sai.
"""

from __future__ import annotations

import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import seed
from vtcsi import cli

ROOT = Path(__file__).parent.parent
CONFIG = ROOT / "config"
MAU = ROOT / "Bang mau" / "File xml đầu vào cho EPG.xml"
"""File lịch mẫu **đã commit**, phủ ngày 2026-09-08.

Không dùng ``epg/inbox`` thật. Hộp thư thật là chỗ hệ lập lịch bên ngoài thả
một file mới vào mỗi ngày, nên mọi khẳng định kiểu "tới ngày này thì hết lịch"
đều có hạn sử dụng: bài xanh hôm nay, đỏ vào cái ngày mà hệ bên ngoài gửi
đúng file phủ ngày đó — tức là đỏ vì hệ **chạy đúng**. Đúng bài học của
``tests/seed.py``, lặp lại ở một thư mục khác.
"""

#: Ngay co lich that trong file mau.
WITH_SCHEDULE = "2026-09-08T06:00:00+07:00"
#: Ngay khong con lich nao — file mau chi phu 08/09.
AFTER_SCHEDULE = "2026-09-20T06:00:00+07:00"


def run(*argv: str) -> tuple[int, str]:
    """Chạy lệnh, thu **cả hai luồng** vào một chuỗi.

    Gộp `stderr` vào là cố ý: lời từ chối của `cli` đi ra `stderr`, và một bài
    test chỉ đọc `stdout` sẽ thấy chuỗi rỗng rồi vẫn xanh — nó xác nhận mã
    thoát mà không xác nhận được hệ có nói cho ai biết vì sao. Chuỗi này là
    đúng thứ người vận hành thấy trong terminal.
    """
    out = io.StringIO()
    with redirect_stdout(out), redirect_stderr(out):
        code = cli.main(list(argv))
    return code, out.getvalue()


class CliCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not (CONFIG / "network.yaml").exists():
            raise unittest.SkipTest("chua gieo cau hinh")

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.build = self.tmp / "build"
        self.eit = self.tmp / "build" / "eit"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def config_copy(self) -> Path:
        """Bản gieo **đã commit**, không phải thư mục đang sửa.

        Bài nào khẳng định "moi kenh deu dang bat EPG" mà đọc `config/` sẽ đỏ
        ngay khi người vận hành tắt một kênh — tức đúng lúc họ làm đúng. Xem
        `tests/seed.py`.
        """
        d = self.tmp / "config"
        if not d.exists():
            td = seed.committed_config()
            try:
                shutil.copytree(Path(td.name) / "config", d)
            finally:
                td.cleanup()
        return d

    def inbox_copy(self) -> Path:
        """Hộp thư riêng, chỉ chứa file lịch mẫu đã commit."""
        d = self.tmp / "hopthu"
        if not d.exists():
            d.mkdir(parents=True)
            shutil.copy(MAU, d / "2026-09-08.xml")
        return d


class TestRefresh(CliCase):
    def test_it_writes_every_structural_table(self) -> None:
        code, text = run("--config", str(CONFIG), "refresh",
                         "--out", str(self.build), "--inbox", str(self.tmp / "trong"),
                         "--eit-out", str(self.eit / "eit.xml"))
        self.assertEqual(code, 0, text)
        names = sorted(p.name for p in self.build.glob("*.xml"))
        self.assertIn("nit.xml", names)
        self.assertIn("sdt-ts8.xml", names)
        self.assertEqual(len([n for n in names if n.startswith("bat-")]), 6)

    def test_a_missing_inbox_is_stated_not_fatal(self) -> None:
        """Dung he lan dau thi chua co lich — van phai ra duoc NIT/SDT/BAT."""
        code, text = run("--config", str(CONFIG), "refresh",
                         "--out", str(self.build), "--inbox", str(self.tmp / "trong"),
                         "--eit-out", str(self.eit / "eit.xml"))
        self.assertEqual(code, 0)
        self.assertIn("khong co hop thu", text)
        self.assertTrue((self.build / "nit.xml").exists())

    def test_stale_schedules_do_not_fail_the_whole_refresh(self) -> None:
        """`run` goi lenh nay moi gio; EIT rong khong duoc lam day log bao dong."""
        if not MAU.exists():
            self.skipTest("khong co file lich mau")
        code, text = run("--config", str(CONFIG), "refresh",
                         "--out", str(self.build), "--inbox", str(self.inbox_copy()),
                         "--eit-out", str(self.eit / "eit.xml"),
                         "--now", AFTER_SCHEDULE)
        self.assertEqual(code, 0, "ma thoat cua refresh phai bam theo bang cau truc")
        self.assertIn("KHONG SINH DUOC BANG EIT NAO", text)
        self.assertTrue((self.build / "nit.xml").exists())

    def test_a_real_schedule_produces_eit(self) -> None:
        if not MAU.exists():
            self.skipTest("khong co file lich mau")
        code, text = run("--config", str(CONFIG), "refresh",
                         "--out", str(self.build), "--inbox", str(self.inbox_copy()),
                         "--eit-out", str(self.eit / "eit.xml"),
                         "--now", WITH_SCHEDULE)
        self.assertEqual(code, 0, text)
        self.assertTrue((self.eit / "eit.xml").exists())
        self.assertIn("bang EIT", text)


class TestEmptyEitIsRefused(CliCase):
    """Ghi de mot EIT rong len file dang phat la cach xoa sach EPG ca mang."""

    def setUp(self) -> None:
        super().setUp()
        if not MAU.exists():
            self.skipTest("khong co file lich mau")
        self.target = self.eit / "eit.xml"

    def test_no_events_in_window_is_an_error_exit(self) -> None:
        code, text = run("--config", str(CONFIG), "epg", "--inbox", str(self.inbox_copy()),
                         "--out", str(self.target), "--now", AFTER_SCHEDULE)
        self.assertEqual(code, 1)
        self.assertIn("KHONG SINH DUOC", text)

    def test_it_names_the_likely_cause(self) -> None:
        _, text = run("--config", str(CONFIG), "epg", "--inbox", str(self.inbox_copy()),
                      "--out", str(self.target), "--now", AFTER_SCHEDULE)
        self.assertIn("lich cu", text)
        self.assertIn(str(self.inbox_copy()), text)

    def test_it_does_not_create_an_empty_file(self) -> None:
        run("--config", str(CONFIG), "epg", "--inbox", str(self.inbox_copy()),
            "--out", str(self.target), "--now", AFTER_SCHEDULE)
        self.assertFalse(self.target.exists())

    def test_it_does_not_overwrite_a_good_file(self) -> None:
        """Day la bai quan trong nhat cua ca file."""
        code, _ = run("--config", str(CONFIG), "epg", "--inbox", str(self.inbox_copy()),
                      "--out", str(self.target), "--now", WITH_SCHEDULE)
        self.assertEqual(code, 0)
        good = self.target.read_bytes()
        self.assertGreater(len(good), 1000)

        code, text = run("--config", str(CONFIG), "epg", "--inbox", str(self.inbox_copy()),
                         "--out", str(self.target), "--now", AFTER_SCHEDULE)
        self.assertEqual(code, 1)
        self.assertIn("KHONG ghi de", text)
        self.assertEqual(self.target.read_bytes(), good,
                         "lich cu con hon khong co lich nao")

    def test_an_empty_inbox_is_caught_earlier_and_harder(self) -> None:
        """Hop thu rong da bi `store.build` chan, thoat ma 2 — khong phai 1.

        Hai ca khac nhau that su: hop thu rong la "chua nap lich"; hop thu day
        ma khong su kien nao dung cua so la "lich da cu". Cau tra loi cho nguoi
        van hanh khac nhau, nen ma thoat cung khac nhau.
        """
        empty = self.tmp / "trong"
        empty.mkdir()
        code, _ = run("--config", str(CONFIG), "epg", "--inbox", str(empty),
                      "--out", str(self.target), "--now", AFTER_SCHEDULE)
        self.assertEqual(code, 2)
        self.assertFalse(self.target.exists())


class TestTheEpgSwitchReachesTheAir(CliCase):
    """Công tắc EPG phải **thật sự** chặn EIT, không chỉ đổi cờ trong SDT.

    Cờ ``EIT_schedule_flag`` là *lời khai*: đầu thu vẫn hiện EPG nếu bảng có
    trên sóng. Nếu ``vtcsi epg`` bỏ qua cờ đó thì công tắc trên giao diện là
    một lời hứa suông — người vận hành tắt EPG một kênh, thấy nút chuyển sang
    "Tắt", và kênh đó vẫn có chương trình trên đầu thu.
    """

    def setUp(self) -> None:
        super().setUp()
        if not MAU.exists():
            self.skipTest("khong co file lich mau")
        self.dir_cfg = self.config_copy()
        self.target = self.eit / "eit.xml"

    def sinh(self) -> tuple[int, str]:
        return run("--config", str(self.dir_cfg), "epg", "--inbox", str(self.inbox_copy()),
                   "--out", str(self.target), "--now", WITH_SCHEDULE)

    def so_bang(self) -> int:
        return self.target.read_text(encoding="utf-8").count("<EIT ")

    def cac_kenh(self) -> set[int]:
        """Dich vu nao dang co bang trong file EIT.

        Doc thuoc tinh roi doi ra SO, khong tim chuoi. TSDuck ghi
        `service_id="0x0321"` chu khong phai `"801"`, nen mot phep tim bang so
        thap phan luon **khong khop** — va mot bai test luon dung la mot bai
        test khong kiem gi ca. Cho nay toi da mac dung loi do mot lan.
        """
        import xml.etree.ElementTree as ET
        root = ET.parse(self.target).getroot()
        return {int(e.get("service_id"), 0) for e in root
                if e.get("service_id") is not None}

    def tat(self, ids: set[int]) -> None:
        from dataclasses import replace

        from vtcsi.config import loader
        cfg = loader.load(self.dir_cfg)
        cfg = replace(cfg, sdts=tuple(
            replace(s, services=tuple(
                replace(x, eit_pf=False, eit_schedule=False)
                if x.service_id in ids else x for x in s.services))
            for s in cfg.sdts))
        loader.save(cfg, self.dir_cfg)

    def test_turning_five_channels_off_removes_five_tables(self) -> None:
        code, _ = self.sinh()
        self.assertEqual(code, 0)
        truoc = self.so_bang()
        self.assertGreater(truoc, 10)

        from vtcsi.config import loader
        sdt = next(s for s in loader.load(self.dir_cfg).sdts if s.ts_id == 8)
        bo = {x.service_id for x in sdt.services[:5]}
        self.tat(bo)

        code, text = self.sinh()
        self.assertEqual(code, 0)
        self.assertEqual(self.so_bang(), truoc - len(bo))

        con = self.cac_kenh()
        for sid in bo:
            with self.subTest(sid=sid):
                self.assertNotIn(sid, con)

    def test_it_says_which_channels_it_skipped(self) -> None:
        """Ba thang sau khi ai do hoi 'sao kenh nay khong co chuong trinh'."""
        self.tat({801})
        _, text = self.sinh()
        self.assertIn("tat EPG", text)
        self.assertIn("801", text)

    def test_nothing_is_skipped_when_everything_is_on(self) -> None:
        _, text = self.sinh()
        self.assertNotIn("tat EPG", text)

    def sinh_cu(self) -> tuple[int, str]:
        """Sinh lai o thoi diem lich DA CU — khong con su kien nao trong cua so."""
        return run("--config", str(self.dir_cfg), "epg", "--inbox", str(self.inbox_copy()),
                   "--out", str(self.target), "--now", AFTER_SCHEDULE)

    def test_a_stale_inbox_alone_never_wipes_the_epg(self) -> None:
        """FR-58: hop thu cu ma KHONG ai tat kenh nao thi giu nguyen file."""
        self.sinh()
        cu = self.target.read_bytes()
        code, text = self.sinh_cu()
        self.assertEqual(code, 1)
        self.assertIn("KHONG SINH DUOC", text)
        self.assertEqual(self.target.read_bytes(), cu)

    def test_the_emergency_switch_works_even_with_a_stale_inbox(self) -> None:
        """Bai quan trong nhat cua nhom nay.

        Cong tac EPG la de tat nhanh khi co su co. Neu dung luc do hop thu chi
        con lich cu thi khong sinh lai duoc — va neu ta chi "giu nguyen file cu"
        thi kenh vua tat VAN co chuong trinh tren dau thu. Cong tac khong lam
        duoc viec cua no dung luc can nhat.

        Cach ra: go bang khoi tai lieu cu. Lam duoc ca khi khong co du lieu moi,
        vi ta khong can biet chuong trinh nao dang chay — chi can biet kenh nao
        phai im.
        """
        self.sinh()
        truoc = self.so_bang()
        co_that = [sid for sid in (801, 802, 803) if sid in self.cac_kenh()]
        self.assertTrue(co_that, "ban gieo phai co it nhat mot kenh de tat")

        self.tat(set(co_that))
        code, text = self.sinh_cu()
        self.assertEqual(code, 1)
        self.assertIn("da go", text)

        con = self.cac_kenh()
        self.assertEqual(self.so_bang(), truoc - len(co_that))
        for sid in co_that:
            with self.subTest(sid=sid):
                self.assertNotIn(sid, con)

    def test_the_channels_left_on_keep_their_programmes(self) -> None:
        """Go kenh da tat KHONG duoc keo theo kenh khac."""
        self.sinh()
        giu = [sid for sid in (810, 811, 812) if sid in self.cac_kenh()]
        self.assertTrue(giu, "ban gieo phai co kenh de giu lai")
        self.tat({801})
        self.sinh_cu()
        con = self.cac_kenh()
        for sid in giu:
            with self.subTest(sid=sid):
                self.assertIn(sid, con)

    def test_turning_everything_off_really_does_mean_no_epg(self) -> None:
        """Tat HET la mot quyet dinh cua nguoi, khong phai su co hop thu.

        Nen o day khong con gi de giu: tai lieu ra rong. Khac han ca "hop thu
        cu" o bai tren, noi ma su rong den tu hoan canh chu khong tu y muon.
        """
        self.sinh()
        from vtcsi.config import loader
        moi = {x.service_id for s in loader.load(self.dir_cfg).sdts
               for x in s.services}
        self.tat(moi)

        code, text = self.sinh_cu()
        self.assertEqual(code, 1)
        self.assertIn("da go", text)
        self.assertEqual(self.so_bang(), 0)


class TestRunDryRun(CliCase):
    """Dòng lệnh `tsp` dựng ra, đọc bằng mắt thay vì phát thử.

    Đọc **bản gieo đã commit**, không phải `config/` đang sửa. Lý do giống
    `config_copy`: những bài dưới đây khẳng định TS actual là 8, có đúng sáu
    bouquet, TTL mặc định là 8 — toàn những thứ người vận hành có quyền đổi.
    Bài đọc thư mục làm việc sẽ đỏ ngay lúc họ làm đúng việc của mình, và một
    bài đỏ vì lý do đó thì lần sau không ai tin nữa.
    """

    def command(self, text: str) -> str:
        return next(line for line in text.splitlines() if line.startswith("tsp "))

    def prepare(self) -> None:
        run("--config", str(self.config_copy()), "refresh", "--out", str(self.build),
            "--inbox", str(self.tmp / "trong"),
            "--eit-out", str(self.eit / "eit.xml"))

    def dry(self, *extra: str) -> tuple[int, str]:
        return run("--config", str(self.config_copy()), "run",
                   "--to", "236.30.239.1:6000",
                   "--build", str(self.build), "--eit-dir", str(self.eit),
                   "--dry-run", *extra)

    def test_it_refuses_when_tables_are_missing(self) -> None:
        code, text = self.dry()
        self.assertEqual(code, 1)
        self.assertIn("THIEU", text)
        self.assertIn("vtcsi refresh", text)

    def test_it_prints_a_command_once_tables_exist(self) -> None:
        self.prepare()
        code, text = self.dry()
        self.assertEqual(code, 0, text)
        self.assertTrue(self.command(text)
                        .startswith("tsp --bitrate 2000000 -I null"))

    def test_the_actual_transport_stream_repeats_fastest(self) -> None:
        """TS actual 1 s, cac TS khac 5 s — TS 101 211 §4.4."""
        self.prepare()
        cmd = self.command(self.dry()[1])
        self.assertIn("sdt-ts8.xml=1000", cmd)
        self.assertIn("sdt-ts3.xml=5000", cmd)
        self.assertIn("sdt-ts1000.xml=5000", cmd)

    def test_the_actual_ts_id_comes_from_the_config(self) -> None:
        self.prepare()
        self.assertIn("--ts-id 8", self.command(self.dry()[1]))

    def test_nothing_on_the_inject_line_is_a_wildcard(self) -> None:
        """Hai cai bay khac nhau, cung mot luat.

        ``sdt-ts*.xml`` khop ca file actual va nap no hai lan. ``bat-*.xml``
        thi te hon: ``inject`` **khong no ky tu dai dien** va cung **khong bao
        loi** — sau BAT lang le bien mat khoi song.
        """
        self.prepare()
        cmd = self.command(self.dry()[1])
        tiem = cmd[:cmd.index("-P eitinject")]
        self.assertNotIn("*", tiem)
        for q in ("0044", "3622", "6510", "6520", "6550", "6604"):
            with self.subTest(bouquet=q):
                self.assertIn(f"bat-{q}.xml=5000", cmd)

    def test_the_local_address_reaches_the_command(self) -> None:
        self.prepare()
        cmd = self.command(self.dry("--local-address", "10.10.30.240")[1])
        self.assertIn("--local-address 10.10.30.240", cmd)

    def test_the_default_ttl_survives_a_router(self) -> None:
        """Mac dinh cua he dieu hanh la 1 — chet ngay tai switch dau tien."""
        self.prepare()
        cmd = self.command(self.dry()[1])
        self.assertIn("--ttl 8", cmd)

    def test_a_custom_ttl(self) -> None:
        self.prepare()
        self.assertIn("--ttl 3", self.command(self.dry("--ttl", "3")[1]))

    def test_the_mirror_is_off_unless_asked_for(self) -> None:
        """Không cấu hình đường sao chép thì không có tiến trình `tsp` thứ hai."""
        self.prepare()
        self.assertNotIn("-P fork", self.command(self.dry()[1]))

    def test_dry_run_writes_nothing_and_opens_no_socket(self) -> None:
        self.prepare()
        before = sorted(p.name for p in self.build.rglob("*"))
        self.dry()
        self.assertEqual(sorted(p.name for p in self.build.rglob("*")), before)


class TestTheOutputAddressComesFromItsOwnFile(CliCase):
    """`vtcsi run` đọc `config/dau-ra.yaml` — không còn bắt gõ `--to` mỗi lần.

    Người vận hành đặt địa chỉ một lần trên trang Đầu ra rồi quên đi; lệnh
    chạy dịch vụ không được đòi họ nhớ lại. Nhưng `--to` vẫn phải đè lên được:
    nó là thứ vừa gõ, còn file là thứ đã quên.
    """

    def command(self, text: str) -> str:
        return next(line for line in text.splitlines() if line.startswith("tsp "))

    def dat(self, **kw):
        from vtcsi.config import output as CO
        from vtcsi.model.output import Endpoint, Output
        d = self.config_copy()
        CO.save(Output(**kw), d)
        return d

    def dry(self, d, *extra: str) -> tuple[int, str]:
        run("--config", str(d), "refresh", "--out", str(self.build),
            "--inbox", str(self.tmp / "trong"),
            "--eit-out", str(self.eit / "eit.xml"))
        return run("--config", str(d), "run", "--build", str(self.build),
                   "--eit-dir", str(self.eit), "--dry-run", *extra)

    def test_no_file_and_no_flag_is_a_clear_refusal(self) -> None:
        """Đứng im và nói rõ, chứ không phát vào hư không."""
        code, text = self.dry(self.config_copy())
        self.assertEqual(code, 2)
        self.assertIn("dau-ra.yaml", text)
        self.assertIn("--to", text)

    def test_the_file_alone_is_enough(self) -> None:
        from vtcsi.model.output import Endpoint
        d = self.dat(primary=Endpoint("236.30.239.5", 6100, "10.10.30.240"))
        code, text = self.dry(d)
        self.assertEqual(code, 0, text)
        cmd = self.command(text)
        self.assertIn("236.30.239.5:6100", cmd)
        self.assertIn("--local-address 10.10.30.240", cmd)

    def test_the_ttl_in_the_file_is_used(self) -> None:
        from vtcsi.model.output import Endpoint
        d = self.dat(primary=Endpoint("236.30.239.5", 6100), ttl=16)
        self.assertIn("--ttl 16", self.command(self.dry(d)[1]))

    def test_the_mirror_in_the_file_becomes_a_forked_tsp(self) -> None:
        from vtcsi.model.output import Endpoint
        d = self.dat(primary=Endpoint("236.30.239.5", 6100, "10.10.30.240"),
                     mirror=Endpoint("236.30.239.6", 6100, "10.10.31.240"))
        cmd = self.command(self.dry(d)[1])
        self.assertIn("-P fork", cmd)
        self.assertIn("236.30.239.6:6100", cmd)
        self.assertIn("--local-address 10.10.31.240", cmd)

    def test_the_forked_child_does_not_regulate(self) -> None:
        """Nhịp đã do nhánh cha giữ. Hai bộ điều nhịp trên một dòng thì đánh nhau."""
        from vtcsi.model.output import Endpoint
        d = self.dat(primary=Endpoint("236.30.239.5", 6100),
                     mirror=Endpoint("236.30.239.6", 6100))
        cmd = self.command(self.dry(d)[1])
        con = cmd[cmd.index("-P fork"):cmd.index("-O ip")]
        self.assertNotIn("regulate", con)

    def test_a_flag_beats_the_file(self) -> None:
        from vtcsi.model.output import Endpoint
        d = self.dat(primary=Endpoint("236.30.239.5", 6100))
        cmd = self.command(self.dry(d, "--to", "239.9.9.9:7000")[1])
        self.assertIn("239.9.9.9:7000", cmd)
        self.assertNotIn("236.30.239.5", cmd)

    def test_an_overriding_flag_also_kills_the_mirror(self) -> None:
        """Giữ đường sao chép theo file thì một lần chạy thử sẽ bắn bản sao của
        dòng thử nghiệm ra đúng nhóm multicast đang phát thật."""
        from vtcsi.model.output import Endpoint
        d = self.dat(primary=Endpoint("236.30.239.5", 6100),
                     mirror=Endpoint("236.30.239.6", 6100))
        cmd = self.command(self.dry(d, "--to", "239.9.9.9:7000")[1])
        self.assertNotIn("-P fork", cmd)
        self.assertNotIn("236.30.239.6", cmd)

    def test_a_broken_file_stops_it_before_anything_starts(self) -> None:
        d = self.config_copy()
        (d / "dau-ra.yaml").write_text("primary: [\n", encoding="utf-8")
        code, text = self.dry(d)
        self.assertEqual(code, 2)
        self.assertIn("dau-ra.yaml", text)


if __name__ == "__main__":
    unittest.main()

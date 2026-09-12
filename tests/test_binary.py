"""So **byte thật** — phép thử mạnh nhất, mở khoá khi cài TSDuck.

Mọi bài đối chiếu từ trước tới giờ so ở tầng XML. XML tương đương chưa chắc
byte tương đương: thứ tự descriptor, cách gói section, độ dài trường, CRC — tất
cả nằm dưới tầng đó.

Cách làm: đưa **cả hai** cây XML qua cùng một bộ biên dịch ``tstabcomp`` rồi so
chuỗi byte. Bên A là bảng bóc từ sóng, bên B là bảng ta sinh từ cấu hình. Giống
byte nghĩa là section phát ra sẽ giống hệt thứ đầu thu đang nhận — đó mới là
điều AC-1 và AC-2 thực sự đòi.

Không cần thu thêm gì: chuẩn vàng đã là XML, và ``tstabcomp`` biên dịch được nó.

Bỏ qua khi chưa cài TSDuck. Cài xong là tự chạy.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import seed
import tsduck_path
from vtcsi.config import loader
from vtcsi.tables import tsduck as T

GOLDEN = Path(__file__).parent.parent / "Bang mau" / "dvb_tables_dump_win.xml"
CONFIG = Path(__file__).parent.parent / "config"

HEADER = '<?xml version="1.0" encoding="UTF-8"?>'


def _compile(tmp: Path, name: str, element: ET.Element) -> bytes:
    """Một bảng XML thành section nhị phân, qua ``tstabcomp``."""
    src = tmp / f"{name}.xml"
    ET.indent(element, space="  ")
    src.write_text(
        HEADER + "\n<tsduck>\n" + ET.tostring(element, encoding="unicode") + "</tsduck>\n",
        encoding="utf-8")
    out = src.with_suffix(".bin")
    r = subprocess.run([tsduck_path.require("tstabcomp"), "--compile", str(src),
                        "--output", str(out)],
                       capture_output=True, text=True, timeout=60,
                       env=tsduck_path.on_path())
    if r.returncode != 0 or not out.exists():
        raise AssertionError(
            f"tstabcomp tu choi {name}.xml:\n{r.stdout}\n{r.stderr}")
    return out.read_bytes()


class BinaryCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        tsduck_path.require("tstabcomp")
        if not GOLDEN.exists():
            raise unittest.SkipTest("khong tim thay chuan vang")
        cls.air_xml = ET.fromstring(GOLDEN.read_text(encoding="utf-8"))
        # Ban gieo **da commit**, khong phai thu muc dang sua. Xem `tests/seed.py`:
        # `config/` la cho nguoi van hanh sua moi ngay, nen so no voi song se do
        # len dung luc ho lam dung — va o day, mot bai byte do la tin hieu manh
        # nhat ca du an, khong duoc phep keu bua.
        td = seed.committed_config()
        try:
            cls.cfg = loader.load(Path(td.name) / "config")
        finally:
            td.cleanup()

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()


class TestSchemaIsAccepted(BinaryCase):
    """Trước hết: TSDuck có chấp nhận XML ta sinh không.

    Nếu lược đồ sai, ``tstabcomp`` từ chối ngay — và đó là phản hồi ta chưa hề
    có cho tới lúc này.
    """

    def test_nit_compiles(self) -> None:
        self.assertTrue(_compile(self.tmp, "nit", T.write_nit(self.cfg.network)))

    def test_every_sdt_compiles(self) -> None:
        for s in self.cfg.sdts:
            with self.subTest(ts=s.ts_id):
                self.assertTrue(_compile(self.tmp, f"sdt{s.ts_id}", T.write_sdt(s)))

    def test_every_bat_compiles(self) -> None:
        for b in self.cfg.bouquets:
            with self.subTest(bouquet=hex(b.bouquet_id)):
                self.assertTrue(
                    _compile(self.tmp, f"bat{b.bouquet_id:04x}", T.write_bat(b)))


class TestBytesMatchTheAir(BinaryCase):
    """AC-1 và AC-2 ở tầng byte."""

    def _air(self, tag: str, **attrs) -> ET.Element:
        for el in self.air_xml.findall(tag):
            if all(T.num(el.get(k)) == v for k, v in attrs.items()):
                clone = ET.fromstring(ET.tostring(el, encoding="unicode"))
                meta = clone.find("metadata")
                if meta is not None:
                    clone.remove(meta)
                return clone
        self.fail(f"khong tim thay <{tag}> {attrs}")

    def _same(self, name: str, mine: ET.Element, theirs: ET.Element) -> None:
        a = _compile(self.tmp, name + "-ta", mine)
        b = _compile(self.tmp, name + "-song", theirs)
        if a != b:
            n = min(len(a), len(b))
            at = next((i for i in range(n) if a[i] != b[i]), n)
            self.fail(
                f"{name}: lech tu byte {at} (ta {len(a)} byte, song {len(b)} byte)\n"
                f"  ta   : {a[max(0, at-4):at+8].hex(' ')}\n"
                f"  song : {b[max(0, at-4):at+8].hex(' ')}")

    def test_nit_bytes(self) -> None:
        self._same("nit", T.write_nit(self.cfg.network),
                   self._air("NIT", network_id=12901))

    def test_sdt_bytes(self) -> None:
        for s in self.cfg.sdts:
            with self.subTest(ts=s.ts_id):
                self._same(f"sdt{s.ts_id}", T.write_sdt(s),
                           self._air("SDT", transport_stream_id=s.ts_id))

    def test_bat_bytes(self) -> None:
        for b in self.cfg.bouquets:
            with self.subTest(bouquet=hex(b.bouquet_id)):
                self._same(f"bat{b.bouquet_id:04x}", T.write_bat(b),
                           self._air("BAT", bouquet_id=b.bouquet_id))


class TestCompilerCatchesCorruption(BinaryCase):
    """Phép so byte phải bắt được sai lệch — nếu không thì nó vô dụng."""

    def test_one_changed_lcn_changes_the_bytes(self) -> None:
        from dataclasses import replace
        b = next(x for x in self.cfg.bouquets if x.bouquet_id == 0x6510)
        loop = b.ts_loops[0]
        bad = replace(b, ts_loops=(replace(loop, lcn=(replace(loop.lcn[0], lcn=999),)
                                           + loop.lcn[1:]),) + b.ts_loops[1:])
        good = _compile(self.tmp, "good", T.write_bat(b))
        worse = _compile(self.tmp, "bad", T.write_bat(bad))
        self.assertNotEqual(good, worse)


if __name__ == "__main__":
    unittest.main()

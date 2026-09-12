"""Sinh bảng EIT — đối chiếu với 18 bảng p/f thật trên sóng.

Chuẩn vàng có sẵn 18 bảng ``EIT type="pf"`` với ``short_event_descriptor``,
gồm cả tiêu đề tiếng Việt có dấu. Đủ để nghiệm thu phần mã hoá sự kiện mà
không cần chờ bản thu EIT schedule.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import tsduck_path
from vtcsi.epg.transform import eventid as EID
from vtcsi.epg.transform import parse as P
from vtcsi.epg.transform import window as W
from vtcsi.model.entities import Event, RunningStatus
from vtcsi.tables import eit as E
from vtcsi.tables import tsduck as T

GOLDEN = Path(__file__).parent.parent / "Bang mau" / "dvb_tables_dump_win.xml"
SAMPLE = Path(__file__).parent / "data" / "epg-sample.xml"
UTC = timezone.utc


def _require() -> str:
    if not GOLDEN.exists():
        raise unittest.SkipTest("khong tim thay chuan vang")
    return GOLDEN.read_text(encoding="utf-8")


class TestScalarFormats(unittest.TestCase):
    def test_time(self) -> None:
        dt = datetime(2026, 9, 10, 15, 0, tzinfo=UTC)
        self.assertEqual(E.format_time(dt), "2026-09-10 15:00:00")
        self.assertEqual(E.parse_time("2026-09-10 15:00:00"), dt)

    def test_time_converts_from_other_zone(self) -> None:
        hanoi = datetime(2026, 9, 10, 22, 0, tzinfo=timezone(timedelta(hours=7)))
        self.assertEqual(E.format_time(hanoi), "2026-09-10 15:00:00")

    def test_naive_time_refused(self) -> None:
        with self.assertRaises(E.EitError):
            E.format_time(datetime(2026, 9, 10, 15, 0))

    def test_duration(self) -> None:
        self.assertEqual(E.format_duration(timedelta(hours=1, minutes=59)), "01:59:00")
        self.assertEqual(E.format_duration(timedelta(minutes=14, seconds=59)), "00:14:59")
        self.assertEqual(E.parse_duration("01:59:00"), timedelta(hours=1, minutes=59))

    def test_duration_beyond_bcd_range_refused(self) -> None:
        """BCD HHMMSS chỉ tới 23:59:59 — dài hơn là phải báo, không cắt bừa."""
        with self.assertRaises(E.EitError):
            E.format_duration(timedelta(hours=24))


class TestEncodingIsUniform(unittest.TestCase):
    """XML của TSDuck không mang bảng mã trên từng chuỗi, nên trộn là sai."""

    def _ev(self, enc: int) -> Event:
        return Event(service_id=801, start_utc=datetime(2026, 9, 10, tzinfo=UTC),
                     duration=timedelta(minutes=30), name="x", encoding=enc, event_id=1)

    def test_single_encoding_accepted(self) -> None:
        self.assertEqual(E.check_single_encoding([self._ev(0x15), self._ev(0x15)]), 0x15)

    def test_mixed_encoding_refused(self) -> None:
        with self.assertRaises(E.EitError) as ctx:
            E.check_single_encoding([self._ev(0x15), self._ev(0x01)])
        self.assertIn("0x01", str(ctx.exception))
        self.assertIn("0x15", str(ctx.exception))

    def test_empty_batch_falls_back_to_utf8(self) -> None:
        self.assertEqual(E.check_single_encoding([]), E.ENCODING_UTF8)


class TestRefusesUnassignedEventId(unittest.TestCase):
    def test_event_without_id(self) -> None:
        ev = Event(service_id=801, start_utc=datetime(2026, 9, 10, tzinfo=UTC),
                   duration=timedelta(minutes=30), name="x", encoding=0x15)
        with self.assertRaises(E.EitError) as ctx:
            E.write_eit([ev], service_id=801, ts_id=8, original_network_id=12901)
        self.assertIn("event_id", str(ctx.exception))


class TestRoundTripAgainstAir(unittest.TestCase):
    """18 bảng p/f thật: đọc ra sự kiện, ghi lại, so với bản gốc."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = ET.fromstring(_require())
        cls.eits = cls.root.findall("EIT")

    def test_eighteen_pf_tables_present(self) -> None:
        self.assertEqual(len(self.eits), 18)
        self.assertTrue(all(e.get("type") == "pf" for e in self.eits))

    def test_round_trip_every_table(self) -> None:
        for orig in self.eits:
            sid = T.num(orig.get("service_id"))
            if sid in self._illegal():
                continue        # xem TestIllegalDurationOnAir
            with self.subTest(service=sid):
                events = E.read_eit(orig)
                rebuilt = E.write_eit(
                    events,
                    service_id=sid,
                    ts_id=T.num(orig.get("transport_stream_id")),
                    original_network_id=T.num(orig.get("original_network_id")),
                    version=int(orig.get("version")),
                    actual=orig.get("actual") == "true",
                    table_type=orig.get("type"),
                )
                # last_table_id do TSDuck tu dat khi sinh bang, khong thuoc noi dung
                skip = frozenset({"metadata"})
                a = T.canon(rebuilt, skip)
                b = T.canon(_without(orig, "last_table_id"), skip)
                self.assertEqual(a, b)

    def _illegal(self) -> set[int]:
        """Dịch vụ có sự kiện vượt trần BCD — không tái tạo được, và không nên."""
        bad = set()
        for e in self.eits:
            for ev in E.read_eit(e):
                if ev.duration > W.MAX_EVENT_DURATION:
                    bad.add(ev.service_id)
        return bad

    def test_vietnamese_title_survives(self) -> None:
        names = [ev.name for e in self.eits for ev in E.read_eit(e)]
        self.assertTrue(any("ó" in n or "ệ" in n or "ữ" in n for n in names),
                        "phai co tieu de tieng Viet co dau trong chuan vang")

    def test_empty_text_stays_empty(self) -> None:
        """FR-50: nguồn không có mô tả, trên sóng <text> rỗng."""
        for e in self.eits:
            for ev in E.read_eit(e):
                self.assertEqual(ev.text, "")


def _without(el: ET.Element, attr: str) -> ET.Element:
    clone = ET.fromstring(ET.tostring(el, encoding="unicode"))
    clone.attrib.pop(attr, None)
    return clone


class TestFromRealSchedule(unittest.TestCase):
    """Từ file lịch nguồn tới bảng EIT, đi qua đủ ba mảnh đã dựng."""

    @classmethod
    def setUpClass(cls) -> None:
        sched = P.parse(SAMPLE.read_text(encoding="utf-8"))
        cls.sched = sched
        cls.events = EID.assign_all(sched.events)

    def test_one_table_per_service(self) -> None:
        tables = E.write_all(self.events, ts_id=8, original_network_id=12901)
        self.assertEqual(len(tables), 2)
        ids = [T.num(t.get("service_id")) for t in tables]
        self.assertEqual(ids, sorted(ids), "phai sap theo service_id cho tat dinh")

    def test_events_sorted_by_start(self) -> None:
        table = E.write_all(self.events, ts_id=8, original_network_id=12901)[0]
        times = [e.get("start_time") for e in table.findall("event")]
        self.assertEqual(times, sorted(times))

    def test_times_are_utc_not_local(self) -> None:
        """Nguồn ghi +07:00; trên sóng phải là UTC."""
        table = E.write_all(self.events, ts_id=8, original_network_id=12901)[0]
        first = table.find("event").get("start_time")
        self.assertEqual(first, "2026-09-07 17:00:00")

    def test_document_wrapper(self) -> None:
        doc = E.to_document(E.write_all(self.events, ts_id=8, original_network_id=12901))
        self.assertEqual(doc.tag, "tsduck")
        self.assertEqual(len(doc), 2)

    def test_generation_is_deterministic(self) -> None:
        a = E.to_document(E.write_all(self.events, ts_id=8, original_network_id=12901))
        b = E.to_document(E.write_all(list(reversed(self.events)),
                                      ts_id=8, original_network_id=12901))
        self.assertEqual(T.canon(a), T.canon(b))


class TestIllegalDurationOnAir(unittest.TestCase):
    """RO-22 — một sự kiện đang phát sóng có thời lượng DVB không biểu diễn được.

    Dịch vụ 838 phát sự kiện độn tên *No Information* với ``duration``
    ``48:00:01``. Trường này là BCD ``HHMMSS``, trần 23:59:59. Bốn mươi tám
    giờ không phải giá trị hợp lệ, và hành vi của đầu thu là không xác định.

    Bộ đọc phải **khoan dung** để còn đối chiếu được với sóng; bộ ghi phải
    **nghiêm** để ta không tái tạo lỗi. Hai bài dưới đây khoá đúng thế.
    """

    @classmethod
    def setUpClass(cls) -> None:
        root = ET.fromstring(_require())
        cls.bad = [ev for e in root.findall("EIT") for ev in E.read_eit(e)
                   if ev.duration > W.MAX_EVENT_DURATION]

    def test_the_defect_is_still_there(self) -> None:
        """Nếu bài này đỏ thì vận hành đã sửa — mừng, và cập nhật spec."""
        self.assertEqual(len(self.bad), 1)
        ev = self.bad[0]
        self.assertEqual(ev.service_id, 838)
        self.assertEqual(ev.duration, timedelta(hours=48, seconds=1))
        self.assertEqual(ev.name, "No Information")

    def test_reader_is_tolerant(self) -> None:
        """Đọc được, không ném lỗi — nếu không thì mất khả năng đối chiếu."""
        self.assertTrue(self.bad)

    def test_writer_refuses_to_reproduce_it(self) -> None:
        with self.assertRaises(E.EitError) as ctx:
            E.write_eit(self.bad, service_id=838, ts_id=8, original_network_id=12901)
        self.assertIn("24", str(ctx.exception))


class TestRejectOverlong(unittest.TestCase):
    """Chính sách: loại sự kiện hỏng ra, đừng để nó làm sập EIT của 44 kênh."""

    def _ev(self, hours: int, sid: int = 801) -> Event:
        return Event(service_id=sid, start_utc=datetime(2026, 9, 10, tzinfo=UTC),
                     duration=timedelta(hours=hours), name="x", encoding=0x15, event_id=1)

    def test_splits_into_kept_and_dropped(self) -> None:
        keep, drop = W.reject_overlong((self._ev(2), self._ev(48, sid=838)))
        self.assertEqual(len(keep), 1)
        self.assertEqual(len(drop), 1)
        self.assertEqual(drop[0].service_id, 838)

    def test_boundary_is_inclusive(self) -> None:
        exact = Event(service_id=801, start_utc=datetime(2026, 9, 10, tzinfo=UTC),
                      duration=W.MAX_EVENT_DURATION, name="x", encoding=0x15, event_id=1)
        keep, drop = W.reject_overlong((exact,))
        self.assertEqual((len(keep), len(drop)), (1, 0))

    def test_kept_events_then_encode_cleanly(self) -> None:
        """Sau khi lọc, phần giữ lại phải sinh bảng được — đó là mục đích."""
        root = ET.fromstring(_require())
        events = tuple(ev for e in root.findall("EIT") for ev in E.read_eit(e)
                       if ev.service_id == 838)
        keep, drop = W.reject_overlong(events)
        self.assertTrue(drop)
        E.write_eit(keep, service_id=838, ts_id=8, original_network_id=12901)


if __name__ == "__main__":
    unittest.main()

class TestTsduckActuallyAcceptsIt(unittest.TestCase):
    """Bài học đắt nhất của cả module này.

    ``TABLE_SCHEDULE`` từng là chuỗi ``"schedule"``. Mọi bài kiểm ở trên vẫn
    xanh, vì chúng đọc lại XML bằng ``ElementTree`` — thứ vui vẻ chấp nhận bất
    kỳ chuỗi nào. Chỉ khi đưa cho ``eitinject`` thật thì TSDuck mới từ chối, và
    nó từ chối **cả bảng**: EPG mất sạch trong khi NIT, SDT, BAT vẫn lên sóng
    bình thường.

    Nên bài này không đọc lại XML. Nó gọi TSDuck.
    """

    def setUp(self) -> None:
        self.tstabcomp = tsduck_path.require("tstabcomp")
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def bien_dich(self, table_type: str) -> bytes:
        """Một EIT một sự kiện qua ``tstabcomp``, trả về byte bảng."""
        ev = Event(service_id=801,
                   start_utc=datetime(2026, 9, 12, 4, 30, tzinfo=timezone.utc),
                   duration=timedelta(minutes=30), name="Thử",
                   encoding=E.ENCODING_UTF8, event_id=1)
        doc = E.to_document(E.write_all(
            [ev], ts_id=8, original_network_id=12901, table_type=table_type))
        src = self.tmp / "eit.xml"
        ET.indent(doc, space="  ")
        src.write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                       + ET.tostring(doc, encoding="unicode"), encoding="utf-8")
        out = src.with_suffix(".bin")
        r = subprocess.run([self.tstabcomp, "--compile", str(src),
                            "--output", str(out)],
                           capture_output=True, text=True, timeout=60,
                           env=tsduck_path.on_path())
        if r.returncode != 0 or not out.exists():
            raise AssertionError(f"tstabcomp tu choi type={table_type!r}:\n"
                                 f"{r.stdout}\n{r.stderr}")
        return out.read_bytes()

    def test_the_schedule_type_compiles(self) -> None:
        self.assertTrue(self.bien_dich(E.TABLE_SCHEDULE))

    def test_the_schedule_type_means_table_id_0x50(self) -> None:
        """EIT schedule actual: 0x50–0x5F, moi bang phu bon ngay."""
        self.assertEqual(self.bien_dich(E.TABLE_SCHEDULE)[0], 0x50)

    def test_the_pf_type_means_table_id_0x4e(self) -> None:
        self.assertEqual(self.bien_dich(E.TABLE_PF)[0], 0x4E)

    def test_the_word_schedule_is_not_a_valid_type(self) -> None:
        """Ghim chinh cai bay: chu 'schedule' doc xuoi tai, va TSDuck tu choi."""
        with self.assertRaises(AssertionError):
            self.bien_dich("schedule")

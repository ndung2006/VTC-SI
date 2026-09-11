"""Phân tích file lịch lược đồ ``<PSI>``.

Fixture ``tests/data/epg-sample.xml`` cắt nguyên văn từ file thật của VTC,
giữ nguyên định dạng — hai dịch vụ, tám sự kiện.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from vtcsi.epg.transform import parse as P
from vtcsi.model.entities import RunningStatus

SAMPLE = Path(__file__).parent / "data" / "epg-sample.xml"


class TestScalarParsers(unittest.TestCase):
    def test_duration(self) -> None:
        self.assertEqual(P.parse_duration("PT00H10M00S"), timedelta(minutes=10))
        self.assertEqual(P.parse_duration("PT00H14M59S"), timedelta(minutes=14, seconds=59))
        self.assertEqual(P.parse_duration("PT01H30M00S"), timedelta(hours=1, minutes=30))

    def test_duration_rejects_other_iso_forms(self) -> None:
        for bad in ["PT10M", "PT1H0M0S ", "P1D", "10:00", ""]:
            with self.subTest(value=bad), self.assertRaises(P.ParseError):
                P.parse_duration(bad)

    def test_time_converts_to_utc(self) -> None:
        got = P.parse_time_utc("2026-09-08T00:00:00+07:00")
        self.assertEqual(got, datetime(2026, 9, 7, 17, 0, tzinfo=timezone.utc))
        self.assertEqual(got.tzinfo, timezone.utc)

    def test_time_requires_explicit_offset(self) -> None:
        with self.assertRaises(P.ParseError):
            P.parse_time_utc("2026-09-08T00:00:00")

    def test_encoding_is_read_as_hex(self) -> None:
        """Nguồn ghi '15' và ý là 0x15 — UTF-8. Xem docstring của parse_encoding."""
        self.assertEqual(P.parse_encoding("15"), 0x15)
        self.assertEqual(P.parse_encoding("01"), 0x01)

    def test_encoding_rejects_unknown_table(self) -> None:
        for bad in ["00", "0F", "20", "FF", "zz"]:
            with self.subTest(value=bad), self.assertRaises(P.ParseError):
                P.parse_encoding(bad)


class TestParseSample(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sched = P.parse(SAMPLE.read_text(encoding="utf-8"))

    def test_identifiers(self) -> None:
        self.assertEqual(self.sched.network_id, 12901)
        self.assertEqual(self.sched.ts_id, 8)
        self.assertEqual(self.sched.original_network_id, 12901)

    def test_event_count(self) -> None:
        self.assertEqual(len(self.sched.events), 8)
        self.assertEqual({e.service_id for e in self.sched.events}, {801, 802})

    def test_sorted_deterministically(self) -> None:
        keys = [(e.service_id, e.start_utc) for e in self.sched.events]
        self.assertEqual(keys, sorted(keys))

    def test_first_event_fields(self) -> None:
        ev = self.sched.events[0]
        self.assertEqual(ev.service_id, 801)
        self.assertEqual(ev.start_utc, datetime(2026, 9, 7, 17, 0, tzinfo=timezone.utc))
        self.assertEqual(ev.duration, timedelta(minutes=10))
        self.assertEqual(ev.name, "Tiếp tục chương trình")
        self.assertEqual(ev.encoding, 0x15)
        self.assertTrue(ev.free_ca_mode)
        self.assertEqual(ev.running_status, RunningStatus.RUNNING)
        self.assertEqual(ev.source_event_id, 64000)
        self.assertIsNone(ev.event_id, "parse khong duoc tu cap event_id")

    def test_short_description_is_empty_everywhere(self) -> None:
        """Nguồn có thẻ nhưng luôn rỗng — xem FR-50."""
        self.assertTrue(all(e.text == "" for e in self.sched.events))

    def test_end_time(self) -> None:
        ev = self.sched.events[0]
        self.assertEqual(ev.end_utc, ev.start_utc + ev.duration)

    def test_parse_is_pure_and_repeatable(self) -> None:
        again = P.parse(SAMPLE.read_text(encoding="utf-8"))
        self.assertEqual(again, self.sched)


class TestParseRejectsBadInput(unittest.TestCase):
    def test_wrong_root(self) -> None:
        with self.assertRaises(P.ParseError):
            P.parse("<XMLTV></XMLTV>")

    def test_missing_transport_stream(self) -> None:
        with self.assertRaises(P.ParseError):
            P.parse('<PSI><NETWORK id="12901"></NETWORK></PSI>')

    def test_missing_required_attribute(self) -> None:
        bad = (
            '<PSI><NETWORK id="1"><TRANSPORT_STREAM id="8" on_id="1">'
            '<SERVICE id="801"><EVENT time="2026-09-08T00:00:00+07:00">'
            '<NAME encoding="15">x</NAME></EVENT>'
            "</SERVICE></TRANSPORT_STREAM></NETWORK></PSI>"
        )
        with self.assertRaises(P.ParseError):
            P.parse(bad)  # thieu duration


if __name__ == "__main__":
    unittest.main()

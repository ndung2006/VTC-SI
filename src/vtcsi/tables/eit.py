"""Sự kiện EPG thành bảng EIT dạng XML của TSDuck.

**Phân đoạn không phải việc của module này.** Một sub-table EIT schedule trải
tới 256 section theo 32 segment, mỗi segment ba giờ, mỗi sub-table bốn ngày —
``eitinject`` của TSDuck lo hết, cùng với việc suy ra present/following và giữ
chu kỳ lặp. Việc ở đây chỉ là giao cho nó danh sách sự kiện đúng.

Nhờ vậy phần này **không bị chặn** bởi việc chưa biết Barrowa phân đoạn ra sao.

Một ràng buộc phải nói rõ: lược đồ XML của TSDuck **không mang byte bảng mã
trên từng chuỗi**. Chuỗi là Unicode, còn bảng mã là tuỳ chọn ở mức dòng lệnh
``tsp``. Điều đó hợp với thực tế — cả nguồn lẫn sóng đều dùng một bảng mã duy
nhất — nhưng nghĩa là trộn nhiều bảng mã trong một mẻ là im lặng sai. Ở đây
kiểm tra và ném lỗi thay vì để lọt.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from vtcsi.model.entities import Event, RunningStatus

TABLE_PF = "pf"
TABLE_SCHEDULE = "schedule"

#: Bảng mã duy nhất dùng cho toàn hệ. 0x15 là UTF-8 theo EN 300 468 Annex A.
#: Đặt ở mức ``tsp`` bằng tuỳ chọn bộ ký tự, không đặt trên từng chuỗi.
ENCODING_UTF8 = 0x15

_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

_RUN_OUT = {
    RunningStatus.UNDEFINED: "undefined",
    RunningStatus.NOT_RUNNING: "not-running",
    RunningStatus.STARTS_IN_A_FEW_SECONDS: "starting",
    RunningStatus.PAUSING: "pausing",
    RunningStatus.RUNNING: "running",
}
_RUN_IN = {v: k for k, v in _RUN_OUT.items()}


class EitError(ValueError):
    """Dữ liệu sự kiện không sinh được bảng hợp lệ."""


# ------------------------------------------------------------------ tiện ích

def format_time(dt: datetime) -> str:
    """UTC thành dạng TSDuck đọc được. DVB quy ước mốc EIT luôn là UTC."""
    if dt.tzinfo is None:
        raise EitError("moc thoi gian thieu mui gio")
    return dt.astimezone(timezone.utc).strftime(_TIME_FORMAT)


def parse_time(text: str) -> datetime:
    return datetime.strptime(text.strip(), _TIME_FORMAT).replace(tzinfo=timezone.utc)


def format_duration(d: timedelta) -> str:
    total = int(d.total_seconds())
    if total < 0:
        raise EitError("thoi luong am")
    if total >= 24 * 3600:
        raise EitError(f"thoi luong {d} vuot 24 gio, BCD HHMMSS khong bieu dien duoc")
    return "%02d:%02d:%02d" % (total // 3600, total % 3600 // 60, total % 60)


def parse_duration(text: str) -> timedelta:
    h, m, s = (int(x) for x in text.strip().split(":"))
    return timedelta(hours=h, minutes=m, seconds=s)


def check_single_encoding(events) -> int:
    """Cả mẻ phải dùng chung một bảng mã — xem ghi chú đầu module."""
    found = {e.encoding for e in events}
    if not found:
        return ENCODING_UTF8
    if len(found) > 1:
        raise EitError(
            "mot me su kien dung nhieu bang ma: "
            + ", ".join("0x%02X" % x for x in sorted(found))
            + " — TSDuck dat bang ma o muc dong lenh nen khong tron duoc"
        )
    return found.pop()


# ---------------------------------------------------------------------- ghi

def write_eit(
    events,
    *,
    service_id: int,
    ts_id: int,
    original_network_id: int,
    version: int = 0,
    actual: bool = True,
    table_type: str = TABLE_SCHEDULE,
    language: str = "vie",
) -> ET.Element:
    """Một bảng EIT cho một dịch vụ.

    Sự kiện được sắp theo thời điểm bắt đầu — tất định, và cũng là thứ tự DVB
    mong đợi. ``event_id`` phải đã được cấp; xem ``epg.transform.eventid``.
    """
    ordered = sorted(events, key=lambda e: e.start_utc)
    check_single_encoding(ordered)

    el = ET.Element("EIT", {
        "type": table_type,
        "version": str(version),
        "current": "true",
        "actual": "true" if actual else "false",
        "service_id": "0x%04X" % service_id,
        "transport_stream_id": "0x%04X" % ts_id,
        "original_network_id": "0x%04X" % original_network_id,
    })
    for ev in ordered:
        if ev.event_id is None:
            raise EitError(
                f"dich vu {ev.service_id} luc {ev.start_utc.isoformat()}: "
                "chua duoc cap event_id")
        e = ET.SubElement(el, "event", {
            "event_id": "0x%04X" % ev.event_id,
            "start_time": format_time(ev.start_utc),
            "duration": format_duration(ev.duration),
            "running_status": _RUN_OUT[ev.running_status],
            "CA_mode": "true" if ev.free_ca_mode else "false",
        })
        d = ET.SubElement(e, "short_event_descriptor", {"language_code": language})
        ET.SubElement(d, "event_name").text = ev.name
        ET.SubElement(d, "text").text = ev.text or None
    return el


def write_all(
    events,
    *,
    ts_id: int,
    original_network_id: int,
    version: int = 0,
    actual: bool = True,
    table_type: str = TABLE_SCHEDULE,
    language: str = "vie",
) -> list[ET.Element]:
    """Một bảng cho mỗi dịch vụ, sắp theo ``service_id`` cho tất định."""
    by_service: dict[int, list[Event]] = defaultdict(list)
    for ev in events:
        by_service[ev.service_id].append(ev)
    return [
        write_eit(
            by_service[sid],
            service_id=sid,
            ts_id=ts_id,
            original_network_id=original_network_id,
            version=version,
            actual=actual,
            table_type=table_type,
            language=language,
        )
        for sid in sorted(by_service)
    ]


def to_document(tables: list[ET.Element]) -> ET.Element:
    """Gói nhiều bảng vào một tài liệu ``<tsduck>`` cho ``eitinject`` nạp."""
    root = ET.Element("tsduck")
    root.extend(tables)
    return root


# ---------------------------------------------------------------------- đọc

def read_eit(el: ET.Element, *, encoding: int = ENCODING_UTF8) -> tuple[Event, ...]:
    """Một bảng EIT của TSDuck thành các sự kiện.

    Dùng để đối chiếu với sóng. ``encoding`` phải truyền vào vì XML không mang
    nó — mặc định là UTF-8, đúng thứ đang phát.
    """
    service_id = int(el.get("service_id"), 16) if el.get("service_id", "").lower().startswith("0x") \
        else int(el.get("service_id", "0"))
    out = []
    for e in el.findall("event"):
        d = e.find("short_event_descriptor")
        name = text = ""
        if d is not None:
            n, t = d.find("event_name"), d.find("text")
            name = (n.text or "") if n is not None else ""
            text = (t.text or "") if t is not None else ""
        raw_id = e.get("event_id", "0")
        out.append(Event(
            service_id=service_id,
            start_utc=parse_time(e.get("start_time")),
            duration=parse_duration(e.get("duration")),
            name=name,
            encoding=encoding,
            free_ca_mode=e.get("CA_mode", "false") == "true",
            running_status=_RUN_IN.get(e.get("running_status", "undefined"),
                                       RunningStatus.UNDEFINED),
            text=text,
            event_id=int(raw_id, 16) if raw_id.lower().startswith("0x") else int(raw_id),
        ))
    return tuple(sorted(out, key=lambda x: x.start_utc))

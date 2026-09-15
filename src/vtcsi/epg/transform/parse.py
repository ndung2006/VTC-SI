"""Phân tích file lịch theo lược đồ ``<PSI>`` của DVB.

Nguồn **không phải XMLTV** — nó mang thẳng các trường DVB ở dạng gần cuối.
Đặc tả đầy đủ của lược đồ ở ``spec.md`` Phụ lục C.

Hàm thuần: vào là chuỗi XML, ra là mô hình. Việc đọc đĩa là của ``epg.store``.
Chỉ dùng ``ET.fromstring``; không bao giờ ``ET.parse`` vì hàm đó chạm I/O.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from vtcsi.model.entities import Coverage, Event, RunningStatus, Schedule

_DURATION = re.compile(r"^PT(\d+)H(\d+)M(\d+)S$")

# Byte dẫn bảng mã ký tự, EN 300 468 Annex A. Chỉ nhận những giá trị một byte
# mà ta thực sự hiểu; 0x10 cần dạng ba byte nên chưa hỗ trợ.
_VALID_ENCODINGS = frozenset(range(0x01, 0x0C)) | {0x11, 0x13, 0x14, 0x15}

_RUNNING_STATUS = {
    "undefined": RunningStatus.UNDEFINED,
    "not_running": RunningStatus.NOT_RUNNING,
    "starts_in_a_few_seconds": RunningStatus.STARTS_IN_A_FEW_SECONDS,
    "pausing": RunningStatus.PAUSING,
    "running": RunningStatus.RUNNING,
}


class ParseError(ValueError):
    """Nguồn sai lược đồ. Luôn nói rõ chỗ sai, không nuốt lỗi."""


def parse_duration(text: str) -> timedelta:
    """``PT00H10M00S`` sang ``timedelta``.

    Cố tình chỉ nhận đúng một dạng: nguồn chỉ sinh ra dạng này, và nhận thêm
    dạng khác nghĩa là nhận thêm cả rủi ro hiểu sai.
    """
    m = _DURATION.match(text)
    if not m:
        raise ParseError(f"duration khong dung dang PTxxHxxMxxS: {text!r}")
    h, mi, se = (int(g) for g in m.groups())
    return timedelta(hours=h, minutes=mi, seconds=se)


def parse_encoding(text: str) -> int:
    """Thuộc tính ``encoding`` sang byte dẫn bảng mã.

    Đọc theo **hệ mười sáu**: nguồn ghi ``15`` và ý là ``0x15`` tức UTF-8. Cách
    đọc này khớp với ``charactertable.xml`` của Barrowa, nơi ``vie``, ``chi``,
    ``kor``, ``ara``, ``hin`` đều là ``15`` — toàn những ngôn ngữ cần UTF-8,
    trong khi ``0x0F`` thập phân lại là giá trị dự trữ, vô nghĩa ở đây.

    Đây vẫn là một suy luận, không phải điều đã đo. Bản dump luồng thật ở giai
    đoạn T2 sẽ chốt lại bằng byte đầu tiên thực sự trên sóng.
    """
    try:
        value = int(text, 16)
    except ValueError as exc:
        raise ParseError(f"encoding khong phai so he 16: {text!r}") from exc
    if value not in _VALID_ENCODINGS:
        raise ParseError(f"byte dan bang ma khong ho tro: 0x{value:02X}")
    return value


def parse_time_utc(text: str) -> datetime:
    """``2026-09-08T00:00:00+07:00`` sang UTC.

    Bắt buộc có offset tường minh. Nguồn luôn ghi ``+07:00``; một mốc thiếu
    offset là dữ liệu hỏng chứ không phải mặc định giờ địa phương.
    """
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ParseError(f"moc thoi gian khong doc duoc: {text!r}") from exc
    if dt.tzinfo is None:
        raise ParseError(f"moc thoi gian thieu mui gio: {text!r}")
    return dt.astimezone(timezone.utc)


def _require(el: ET.Element, attr: str) -> str:
    value = el.get(attr)
    if value is None:
        raise ParseError(f"<{el.tag}> thieu thuoc tinh '{attr}'")
    return value


def _text_of(event: ET.Element, tag: str) -> tuple[str, int | None]:
    el = event.find(tag)
    if el is None:
        return "", None
    return (el.text or ""), parse_encoding(_require(el, "encoding"))


def parse(xml_text: str) -> Schedule:
    """Phân tích một file lịch thành ``Schedule``.

    Sự kiện trả về **chưa có** ``event_id``; xem ``eventid.assign_all``.
    Thứ tự trả về sắp theo ``(service_id, start_utc)`` để bảo đảm tất định,
    không phụ thuộc thứ tự phần tử trong file.
    """
    root = ET.fromstring(xml_text)
    if root.tag != "PSI":
        raise ParseError(f"the goc phai la <PSI>, gap <{root.tag}>")

    network = root.find("NETWORK")
    if network is None:
        raise ParseError("thieu <NETWORK>")
    ts = network.find("TRANSPORT_STREAM")
    if ts is None:
        raise ParseError("thieu <TRANSPORT_STREAM>")

    events: list[Event] = []
    coverage: list[Coverage] = []
    for service in ts.findall("SERVICE"):
        service_id = int(_require(service, "id"))
        # Phạm vi đợt giao — xem `Coverage`. Khuyết thì bỏ qua, KHÔNG suy ra
        # từ chính các sự kiện: suy ra là tự cho mình quyền xoá dữ liệu mà
        # nguồn chưa hề tuyên bố phụ trách.
        dau, cuoi = service.get("start_time"), service.get("end_time")
        if dau and cuoi:
            coverage.append(Coverage(
                service_id=service_id,
                start_utc=parse_time_utc(dau),
                end_utc=parse_time_utc(cuoi),
            ))
        for ev in service.findall("EVENT"):
            name, name_enc = _text_of(ev, "NAME")
            if name_enc is None:
                raise ParseError(f"su kien cua service {service_id} thieu <NAME>")
            text, _ = _text_of(ev, "SHORT_DESCRIPTION")

            status_raw = ev.get("running_status", "undefined")
            if status_raw not in _RUNNING_STATUS:
                raise ParseError(f"running_status la: {status_raw!r}")

            events.append(
                Event(
                    service_id=service_id,
                    start_utc=parse_time_utc(_require(ev, "time")),
                    duration=parse_duration(_require(ev, "duration")),
                    name=name,
                    encoding=name_enc,
                    free_ca_mode=ev.get("ca", "false") == "true",
                    running_status=_RUNNING_STATUS[status_raw],
                    text=text,
                    source_event_id=int(ev.get("id")) if ev.get("id") else None,
                )
            )

    events.sort(key=lambda e: (e.service_id, e.start_utc))
    return Schedule(
        network_id=int(_require(network, "id")),
        ts_id=int(_require(ts, "id")),
        original_network_id=int(_require(ts, "on_id")),
        events=tuple(events),
        coverage=tuple(sorted(coverage, key=lambda c: (c.service_id, c.start_utc))),
    )

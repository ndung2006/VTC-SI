"""Gộp nhiều file lịch theo ngày thành cửa sổ 192 giờ — FR-52.

Nguồn phát hành **một ngày mỗi file** (RO-13), trong khi EIT schedule cần giữ
tám ngày cùng lúc. Module này là chỗ ghép chúng lại, và cũng là chỗ tính được
lịch còn sâu bao nhiêu cho cảnh báo ở FR-31.

Hàm thuần. ``now_utc`` **luôn là tham số truyền vào**, không bao giờ gọi đồng
hồ — nếu không thì không test được, và hai thực thể ngang hàng sẽ cắt cửa sổ ở
hai thời điểm khác nhau.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from vtcsi.model.entities import Event

WINDOW_HOURS = 192
"""Tám ngày — độ sâu Barrowa đang dùng, và cũng là dung lượng của hai sub-table
EIT schedule, mỗi cái phủ bốn ngày."""


def _key(ev: Event) -> tuple[int, datetime]:
    """Khoá định danh một sự kiện: cùng dịch vụ, cùng lúc bắt đầu là một."""
    return (ev.service_id, ev.start_utc)


def _sorted(events) -> tuple[Event, ...]:
    """Sắp xếp tất định — không dựa vào thứ tự nạp hay thứ tự file."""
    return tuple(sorted(events, key=lambda e: (e.service_id, e.start_utc)))


def merge(*batches: tuple[Event, ...]) -> tuple[Event, ...]:
    """Gộp nhiều đợt nạp, **đợt sau thắng** khi trùng khoá.

    Đợt sau thắng vì một file phát hành lại thường là bản sửa: đổi giờ, đổi
    tên chương trình. Ai nạp cuối là ai nói lời cuối.
    """
    out: dict[tuple[int, datetime], Event] = {}
    for batch in batches:
        for ev in batch:
            out[_key(ev)] = ev
    return _sorted(out.values())


def clip(
    events: tuple[Event, ...],
    now_utc: datetime,
    depth_hours: int = WINDOW_HOURS,
) -> tuple[Event, ...]:
    """Cắt về cửa sổ quanh ``now_utc``.

    Giữ sự kiện **chưa kết thúc** — sự kiện đang phát dở vẫn cần cho p/f — và
    **bắt đầu trước** mép cuối cửa sổ.
    """
    if now_utc.tzinfo is None:
        raise ValueError("now_utc phai co mui gio")
    end = now_utc + timedelta(hours=depth_hours)
    return _sorted(e for e in events if e.end_utc > now_utc and e.start_utc < end)


def drop_overlaps(events: tuple[Event, ...]) -> tuple[Event, ...]:
    """Thực hiện ``period_overlapping_mode="removeEvent"`` — FR-48.

    Trong một dịch vụ, hai sự kiện không được chồng lấn: DVB coi lịch là một
    dãy liên tiếp. Khi có chồng lấn, giữ sự kiện **bắt đầu sớm hơn** và bỏ cái
    đè lên nó.

    *Điểm cần xác nhận với vận hành*: tên ``removeEvent`` không nói rõ bỏ cái
    nào. Chọn giữ cái sớm hơn vì nó nhất quán với việc quét lịch theo thời
    gian tiến. Dữ liệu thật hiện **không có chồng lấn nào**, nên đây là đường
    phòng thủ chứ chưa phải đường đi hằng ngày.
    """
    per_service: dict[int, list[Event]] = defaultdict(list)
    for ev in _sorted(events):
        per_service[ev.service_id].append(ev)

    kept: list[Event] = []
    for service_events in per_service.values():
        last_end: datetime | None = None
        for ev in service_events:
            if last_end is not None and ev.start_utc < last_end:
                continue
            kept.append(ev)
            last_end = ev.end_utc
    return _sorted(kept)


def build(
    batches: tuple[tuple[Event, ...], ...] | list[tuple[Event, ...]],
    now_utc: datetime,
    depth_hours: int = WINDOW_HOURS,
) -> tuple[Event, ...]:
    """Từ nhiều file lịch tới cửa sổ sẵn sàng sinh EIT.

    Thứ tự ba bước có ý nghĩa: gộp trước để bản sửa ghi đè bản cũ, cắt sau để
    khỏi phải xử lý dữ liệu ngoài cửa sổ, rồi mới khử chồng lấn trên đúng tập
    sẽ lên sóng.
    """
    return drop_overlaps(clip(merge(*batches), now_utc, depth_hours))


def only_services(
    events: tuple[Event, ...], allowed: frozenset[int] | set[int],
) -> tuple[tuple[Event, ...], tuple[int, ...]]:
    """Giữ lại sự kiện của những dịch vụ được phép lên EPG.

    Trả về ``(giữ lại, những dịch vụ bị loại)``. Danh sách bị loại là phần
    quan trọng: tắt EPG một kênh phải **nói ra** ở log, vì ba tháng sau khi ai
    đó hỏi "sao kênh này không có chương trình" thì câu trả lời phải tìm được.

    Cờ ``EIT_schedule_flag`` trong SDT chỉ là *lời khai*; đầu thu vẫn hiển thị
    EIT nếu bảng đó có trên sóng. Muốn tắt EPG một kênh **thật sự** thì phải
    không sinh bảng cho nó — đó là việc của hàm này. Khai một đằng phát một nẻo
    là kiểu sai khó tìm nhất.
    """
    keep = tuple(e for e in events if e.service_id in allowed)
    bo = tuple(sorted({e.service_id for e in events} - set(allowed)))
    return keep, bo


MAX_EVENT_DURATION = timedelta(hours=23, minutes=59, seconds=59)
"""Trần của trường ``duration`` trong EIT: BCD ``HHMMSS``, không quá 23:59:59."""


def reject_overlong(
    events: tuple[Event, ...], limit: timedelta = MAX_EVENT_DURATION
) -> tuple[tuple[Event, ...], tuple[Event, ...]]:
    """Tách sự kiện dài quá mức DVB biểu diễn được.

    Trả về ``(giữ lại, loại ra)`` thay vì ném lỗi: một sự kiện hỏng không được
    phép làm sập cả EIT của 44 kênh. Phần loại ra là đầu vào cho cảnh báo —
    người vận hành cần biết, nhưng sóng vẫn phải chạy.

    Có thật trên sóng: dịch vụ 838 phát một sự kiện độn tên *No Information*
    với ``duration = 48:00:01``. Xem RO-22.
    """
    keep, drop = [], []
    for ev in events:
        (drop if ev.duration > limit else keep).append(ev)
    return _sorted(keep), _sorted(drop)


def depth_by_service(
    events: tuple[Event, ...], now_utc: datetime
) -> dict[int, timedelta]:
    """Mỗi dịch vụ còn lịch tới bao xa — đầu vào cho cảnh báo FR-31.

    Đo tới **sự kiện cuối cùng kết thúc**, không phải tới sự kiện cuối cùng
    bắt đầu: chương trình dài cuối ngày vẫn là lịch còn hiệu lực.
    """
    out: dict[int, timedelta] = {}
    for ev in events:
        end = max(ev.end_utc, now_utc)
        cur = out.get(ev.service_id)
        span = end - now_utc
        if cur is None or span > cur:
            out[ev.service_id] = span
    return out


def services_below(
    events: tuple[Event, ...], now_utc: datetime, hours: int
) -> tuple[int, ...]:
    """Dịch vụ còn lịch mỏng hơn ngưỡng. Barrowa dùng ngưỡng 120 giờ."""
    limit = timedelta(hours=hours)
    depths = depth_by_service(events, now_utc)
    return tuple(sorted(sid for sid, d in depths.items() if d < limit))

"""Cấp ``event_id`` tất định — FR-47, đóng rủi ro RO-12.

**Vì sao không dùng id của nguồn.** Nguồn đánh số lại từ ``64000`` cho *mỗi
dịch vụ*, và một ngày đã dùng hết ``64000``–``64086``. Ngày mai lại bắt đầu từ
64000, nên trong cửa sổ 8 ngày sẽ có nhiều sự kiện cùng dịch vụ trùng
``event_id`` — điều DVB cấm. Mà cứ tăng dần cũng không xong: trần 16 bit chỉ
còn 1 449 chỗ, khoảng 16 ngày là hết.

**Vì sao không dùng bộ đếm.** Hai thực thể ngang hàng phải cấp cùng một số cho
cùng một sự kiện mà không trao đổi gì với nhau. Bộ đếm phụ thuộc thứ tự nạp và
lịch sử tiến trình, nên không tất định. Xem ``spec.md`` §3.3.

**Công thức.** ``event_id = (số phút từ EPOCH đến lúc bắt đầu) mod 65536``.
Chu kỳ quay vòng là 65 536 phút, tức 45,5 ngày — dài hơn cửa sổ 8 ngày rất
nhiều, nên trong cửa sổ không bao giờ có hai sự kiện đụng nhau vì quay vòng.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from vtcsi.model.entities import Event

EPOCH = datetime(2020, 1, 1, tzinfo=timezone.utc)
MODULUS = 1 << 16
_ONE_MINUTE = timedelta(minutes=1)

#: Chu kỳ quay vòng, tính bằng ngày — 45,5. Cửa sổ lịch phải nhỏ hơn con số này.
WRAP_DAYS = MODULUS / (60 * 24)


class EventIdCollision(ValueError):
    """Hai sự kiện cùng dịch vụ rơi vào cùng một ``event_id``.

    Dừng lại và báo, không tự né. Một va chạm im lặng nghĩa là đầu thu bỏ qua
    một chương trình mà không ai biết.
    """


def event_id_for(start_utc: datetime) -> int:
    """Tính ``event_id`` từ thời điểm bắt đầu.

    Cắt xuống phút: nguồn hiện tại luôn bắt đầu tròn phút. Nếu về sau có mốc
    lẻ giây, hai sự kiện cách nhau dưới một phút sẽ đụng nhau — và
    ``assign_all`` sẽ bắt được thay vì để lọt.
    """
    if start_utc.tzinfo is None:
        raise ValueError("start_utc phai co mui gio")
    minutes = (start_utc.astimezone(timezone.utc) - EPOCH) // _ONE_MINUTE
    if minutes < 0:
        raise ValueError(f"thoi diem {start_utc.isoformat()} truoc EPOCH {EPOCH.isoformat()}")
    return minutes % MODULUS


def assign_all(events: tuple[Event, ...] | list[Event]) -> tuple[Event, ...]:
    """Gán ``event_id`` cho cả tập, kiểm tra va chạm trong từng dịch vụ.

    Va chạm chỉ tính trong phạm vi một dịch vụ, vì DVB yêu cầu ``event_id``
    duy nhất theo dịch vụ chứ không phải toàn mạng.
    """
    seen: dict[int, dict[int, Event]] = defaultdict(dict)
    out: list[Event] = []

    for ev in events:
        eid = event_id_for(ev.start_utc)
        bucket = seen[ev.service_id]
        if eid in bucket:
            other = bucket[eid]
            raise EventIdCollision(
                f"service {ev.service_id}: event_id {eid} bi dung boi ca "
                f"{other.start_utc.isoformat()} va {ev.start_utc.isoformat()}"
            )
        bucket[eid] = ev
        out.append(
            Event(
                service_id=ev.service_id,
                start_utc=ev.start_utc,
                duration=ev.duration,
                name=ev.name,
                encoding=ev.encoding,
                free_ca_mode=ev.free_ca_mode,
                running_status=ev.running_status,
                text=ev.text,
                source_event_id=ev.source_event_id,
                event_id=eid,
            )
        )
    return tuple(out)

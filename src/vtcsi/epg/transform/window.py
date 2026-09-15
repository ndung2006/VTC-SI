"""Gộp nhiều file lịch theo ngày thành cửa sổ 192 giờ — FR-52.

Nguồn phát hành từng đợt — mỗi đợt vài ngày, có chồng lấn nhau — trong khi
EIT schedule cần giữ tám ngày cùng lúc. Module này là chỗ ghép chúng lại, và
cũng là chỗ tính được lịch còn sâu bao nhiêu cho cảnh báo ở FR-31.

Chỗ khó duy nhất ở đây là **ai đè ai**, và nó đã từng sai trên sóng. Đọc
``merge`` trước khi sửa bất cứ gì trong file này.

Hàm thuần. ``now_utc`` **luôn là tham số truyền vào**, không bao giờ gọi đồng
hồ — nếu không thì không test được, và hai thực thể ngang hàng sẽ cắt cửa sổ ở
hai thời điểm khác nhau.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timedelta

from vtcsi.model.entities import Coverage, Event

WINDOW_HOURS = 192
"""Tám ngày — dung lượng của hai sub-table EIT schedule, mỗi cái phủ bốn ngày.

Đây là **trần**, không phải độ sâu thật. Bản trước ghi "độ sâu Barrowa đang
dùng"; đo ngày 2026-09-15 thì Barrowa cũng chỉ sâu tới 16:59 cùng ngày, vì nó
đọc đúng file lịch mà ta đọc và file đó dừng ở đấy. Độ sâu thật do bên cấp
lịch quyết định, không do con số này."""


def _key(ev: Event) -> tuple[int, datetime]:
    """Khoá định danh một sự kiện: cùng dịch vụ, cùng lúc bắt đầu là một."""
    return (ev.service_id, ev.start_utc)


def _sorted(events) -> tuple[Event, ...]:
    """Sắp xếp tất định — không dựa vào thứ tự nạp hay thứ tự file."""
    return tuple(sorted(events, key=lambda e: (e.service_id, e.start_utc)))


#: Một đợt giao: các sự kiện, kèm phạm vi đợt đó **tự khai** là mình phụ trách.
Batch = tuple[Event, ...] | tuple[tuple[Event, ...], tuple[Coverage, ...]]


def _tach(batch: Batch) -> tuple[tuple[Event, ...], tuple[Coverage, ...]]:
    """Nhận cả dạng chỉ-sự-kiện lẫn dạng có phạm vi."""
    if (len(batch) == 2 and isinstance(batch[0], tuple)
            and isinstance(batch[1], tuple)):
        return batch  # type: ignore[return-value]
    return batch, ()   # type: ignore[return-value]


def merge(*batches: Batch) -> tuple[Event, ...]:
    """Gộp nhiều đợt giao, **đợt sau thắng**.

    Hai mức thắng, và sự khác nhau giữa chúng là chỗ đã gây lỗi trên sóng.

    **Mức yếu — trùng khoá.** Cùng dịch vụ, cùng giờ bắt đầu thì bản sau đè lên
    bản trước. Đủ cho việc sửa tên chương trình, nhưng **không** đủ cho việc
    dời giờ: dời giờ thì bản cũ và bản mới thành hai khoá khác nhau, cả hai
    cùng sống. Sau đó ``drop_overlaps`` giữ cái bắt đầu sớm hơn — tức giữ đúng
    bản **cũ** và vứt bản mới. Đo ngày 2026-09-15 trên máy phát: 290 trong 670
    sự kiện lên sóng không còn tồn tại trong đợt giao mới nhất, trong khi
    Barrowa đọc cùng nguồn chỉ lệch 31 trên 740.

    **Mức mạnh — theo phạm vi tự khai.** Đợt nào khai ``start_time``/
    ``end_time`` trên ``<SERVICE>`` thì nó **thay trọn** khoảng đó cho dịch vụ
    đó: mọi sự kiện cũ nằm trong khoảng bị gỡ trước khi đổ sự kiện mới vào.
    Đây mới đúng nghĩa "đây là lịch của kênh này cho khoảng này", và cũng là
    cách Barrowa làm — nó tách ra ``schedule_<kênh>.xml`` rồi thay nguyên file.

    Đợt **không** khai phạm vi thì chỉ được mức yếu. Cố ý: suy phạm vi ra từ
    chính các sự kiện là tự cho mình quyền xoá dữ liệu mà nguồn chưa hề tuyên
    bố phụ trách, và một file lỗi chỉ còn ba sự kiện sẽ quét sạch cả ngày.
    """
    out: dict[tuple[int, datetime], Event] = {}
    for batch in batches:
        events, coverage = _tach(batch)
        if coverage:
            out = {k: ev for k, ev in out.items()
                   if not any(c.chua(ev) for c in coverage)}
        for ev in events:
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


def remap(batch: Batch, mapping: dict[int, int]) -> Batch:
    """Đổi số dịch vụ của **file lịch** sang số trên **sóng** — xem ``Service.epg_source_id``.

    Phải làm **trước** mọi thứ khác. Bên cấp lịch đánh số theo sổ của họ: kênh
    Quảng Trị lên sóng là ``825`` nhưng trong file lịch là ``875``. Đổi muộn
    hơn thì hỏng theo hai đường — ``merge`` sẽ coi hai nguồn của cùng một kênh
    là hai kênh khác nhau, và ``drop_overlaps`` không thấy chồng lấn giữa
    chúng, nên hai lịch của cùng một kênh cùng lên sóng.

    Đổi cả phạm vi tự khai, không riêng sự kiện: bỏ sót phạm vi thì đợt mới
    không còn thay được đợt cũ của chính kênh đó.
    """
    events, coverage = _tach(batch)
    if not mapping:
        return events, coverage
    doi = lambda sid: mapping.get(sid, sid)   # noqa: E731
    return (
        tuple(replace(e, service_id=doi(e.service_id)) for e in events),
        tuple(replace(c, service_id=doi(c.service_id)) for c in coverage),
    )


def build(
    batches: tuple[Batch, ...] | list[Batch],
    now_utc: datetime,
    depth_hours: int = WINDOW_HOURS,
    mapping: dict[int, int] | None = None,
) -> tuple[Event, ...]:
    """Từ nhiều file lịch tới cửa sổ sẵn sàng sinh EIT.

    Thứ tự bốn bước có ý nghĩa: đổi số trước để mọi bước sau làm việc trên số
    của sóng, gộp để đợt mới đè đợt cũ, cắt để khỏi xử lý dữ liệu ngoài cửa
    sổ, rồi mới khử chồng lấn trên đúng tập sẽ lên sóng.
    """
    if mapping:
        batches = [remap(b, mapping) for b in batches]
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


KHOANG_TRONG = timedelta(days=2)
"""Khoảng trống đủ dài để nghi phần lịch sau nó là rác — xem ``far_future``."""


def far_future(
    events: tuple[Event, ...], now_utc: datetime,
    gap: timedelta = KHOANG_TRONG,
) -> tuple[Event, ...]:
    """Sự kiện nằm **sau một khoảng trống dài** trong lịch. Nghi là lỗi nguồn.

    Trả về phần đáng ngờ để báo ra, **không** tự vứt — cùng khuôn với
    ``reject_overlong`` và ``only_services``, và vì lý do như nhau: một phép
    đoán không được phép lặng lẽ xoá lịch thật.

    Có thật, file lịch ngày 2026-09-14: 292 sự kiện đề ngày 2 và 3 tháng 10,
    **toàn bộ thuộc dịch vụ 838**, mỗi cái lặp bốn lần, trong khi từ 16/9 tới
    1/10 không có gì. Bên cấp lịch xác nhận đó là lỗi nhập liệu. Cửa sổ 192
    giờ che được hôm nay, nhưng **chỉ tới khoảng 24/9**: từ hôm đó ngày 2/10
    lọt vào cửa sổ và rác lên sóng như lịch thật.

    Vì sao đo trên **toàn mạng** chứ không từng kênh: một kênh nghỉ hai ngày
    là chuyện bình thường, còn *cả mười tám kênh* cùng không có gì trong hai
    ngày thì không.

    Đo trước khi cắt cửa sổ, nếu không thì phần đáng ngờ đã bị cắt mất và cảnh
    báo chỉ hiện ra đúng hôm nó lên sóng — muộn mất tám ngày.

    Chỉ xét phần **chưa kết thúc**. Hộp thư giữ cả lịch cũ, nên quá khứ đầy
    khoảng trống hợp lệ — hộp thư thật có file ngày 24/8 rồi nhảy sang 8/9.
    Lấy khoảng trống đầu tiên trên toàn bộ dữ liệu thì cảnh báo kêu 7101 sự
    kiện trên cả 45 kênh, tức là kêu về mọi thứ, tức là không nói gì. Lịch đã
    qua thì dù có thủng cũng không lên sóng được nữa.
    """
    if now_utc.tzinfo is None:
        raise ValueError("now_utc phai co mui gio")
    xs = sorted((e for e in events if e.end_utc > now_utc),
                key=lambda e: e.start_utc)
    for i in range(1, len(xs)):
        if xs[i].start_utc - xs[i - 1].start_utc >= gap:
            return _sorted(xs[i:])
    return ()


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

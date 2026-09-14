"""Lưới lịch phát sóng một ngày, cho màn giám sát — lõi thuần.

Màn này trả lời đúng một câu: **đầu thu sẽ thấy gì**. Nên nó không vẽ những gì
có trong hộp thư, mà vẽ những gì thật sự lên sóng.

Kênh **tắt EPG** vẫn có một dòng — nó vẫn là một kênh của transport stream này,
và một màn giám sát bỏ hẳn nó đi thì người trực không còn cách nào thấy nó tồn
tại. Nhưng dòng đó **rỗng**, kể cả khi hộp thư có đầy lịch cho nó: kênh tắt
không có bảng EIT nào được sinh ra, nên vẽ chương trình lên đó sẽ là một lời
nói dối tử tế — và lời nói dối tử tế trong màn giám sát còn tệ hơn không có màn
nào. Dòng rỗng vì **tắt** khác hẳn dòng rỗng vì **thiếu lịch**, nên hai thứ
được đếm riêng và tô khác nhau.

Mốc thời gian tính bằng **số phút kể từ 00:00 giờ địa phương**, không gửi chuỗi
giờ. Giao diện đặt một ô ở toạ độ ``phút × px`` là xong, không phải phân tích
lại chuỗi — và mọi phép so sánh "đang phát" chỉ là so hai số nguyên.

Lỗ hổng tính **giữa hai sự kiện**, không tính hai đầu ngày. Một kênh bắt đầu
phát lúc 05:00 không có "lỗ hổng năm tiếng" — nó chỉ chưa lên sóng. Đếm cả hai
đầu sẽ làm mọi kênh đều có lỗ hổng, và một con số luôn khác không là một con số
không ai nhìn.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from vtcsi.model.entities import Event

VN = timezone(timedelta(hours=7))
"""Giờ Việt Nam. Cố định, không có giờ mùa hè — nên một hằng số là đủ."""

MIN_GAP = 5
"""Dưới 5 phút thì không gọi là lỗ hổng.

Chênh một hai phút giữa hai chương trình là chuyện thường của biên tập, và đầu
thu không hiện gì khác biệt. Đặt ngưỡng ở đây để cột "lỗ hổng lịch" đếm thứ
đáng đi tìm.
"""

DAY = 24 * 60


@dataclass(frozen=True, slots=True)
class Slot:
    """Một chương trình trên lưới."""

    start: int
    """Phút kể từ 00:00 giờ địa phương. Có thể âm nếu chương trình bắt đầu từ
    hôm trước — giao diện tự cắt ở mép trái."""

    minutes: int
    title: str
    text: str = ""

    @property
    def end(self) -> int:
        return self.start + self.minutes


@dataclass(frozen=True, slots=True)
class Row:
    service_id: int
    name: str
    radio: bool
    epg: bool = True
    """Kênh có bật EPG không. Tắt thì ``slots`` luôn rỗng."""

    slots: tuple[Slot, ...] = ()
    gaps: tuple[tuple[int, int], ...] = ()
    """Từng cặp ``(phút bắt đầu, số phút)``."""

    @property
    def empty(self) -> bool:
        """Rỗng vì **thiếu lịch**. Kênh tắt EPG không tính vào đây."""
        return self.epg and not self.slots


@dataclass(frozen=True, slots=True)
class Board:
    day: date
    rows: tuple[Row, ...] = ()

    @property
    def events(self) -> int:
        return sum(len(r.slots) for r in self.rows)

    @property
    def with_schedule(self) -> int:
        return sum(1 for r in self.rows if r.slots)

    @property
    def empty(self) -> int:
        """Kênh đang bật EPG mà không có lịch — con số đáng báo động."""
        return sum(1 for r in self.rows if r.empty)

    @property
    def off(self) -> int:
        """Kênh tắt EPG. Có dòng, nhưng dòng rỗng, và rỗng là đúng."""
        return sum(1 for r in self.rows if not r.epg)

    @property
    def gaps(self) -> int:
        return sum(len(r.gaps) for r in self.rows)


def local_day(moment: datetime, tz: timezone = VN) -> date:
    """Ngày địa phương của một mốc UTC."""
    return moment.astimezone(tz).date()


def minutes_into_day(moment: datetime, day: date, tz: timezone = VN) -> int:
    """Phút kể từ 00:00 của ``day``. Âm nếu mốc nằm trước ngày đó."""
    here = moment.astimezone(tz)
    mid = datetime(day.year, day.month, day.day, tzinfo=tz)
    return int((here - mid).total_seconds() // 60)


def touches(event: Event, day: date, tz: timezone = VN) -> bool:
    """Sự kiện có chạm vào ngày này không.

    Chạm, không phải *bắt đầu trong*: một chương trình 23:30–00:30 thuộc về cả
    hai ngày, và bỏ nó khỏi ngày sau sẽ tạo ra một lỗ hổng không có thật lúc
    nửa đêm.
    """
    start = minutes_into_day(event.start_utc, day, tz)
    return start < DAY and start + max(1, int(event.duration.total_seconds() // 60)) > 0


def find_gaps(slots: tuple[Slot, ...], min_gap: int = MIN_GAP) -> tuple[tuple[int, int], ...]:
    """Khoảng trống giữa hai chương trình liên tiếp.

    Dùng ``max`` của mốc kết thúc đã gặp chứ không phải mốc của ô liền trước:
    lịch thật có chương trình lồng nhau và chồng lấn, và so với ô liền trước
    sẽ đẻ ra lỗ hổng âm rồi báo bừa.
    """
    if not slots:
        return ()
    out: list[tuple[int, int]] = []
    reached = slots[0].end
    for s in slots[1:]:
        if s.start - reached >= min_gap:
            out.append((reached, s.start - reached))
        reached = max(reached, s.end)
    return tuple(out)


def build(
    events,
    services,
    day: date,
    tz: timezone = VN,
) -> Board:
    """Dựng lưới một ngày.

    ``services`` là danh sách ``(service_id, tên, là_phát_thanh)``, hoặc
    ``(service_id, tên, là_phát_thanh, bật_EPG)`` nếu muốn nói rõ. Thiếu phần
    tử thứ tư thì coi như đang bật — nhờ vậy nơi gọi nào không quan tâm tới
    công tắc EPG vẫn viết y như cũ.

    Kênh **tắt EPG** ra một dòng rỗng, và sự kiện của nó bị bỏ ngay tại đây
    chứ không phải ở nơi gọi. Đặt luật ở một chỗ duy nhất: quên lọc thì cả
    công tắc trên giao diện thành lời hứa suông.

    Kênh có trong danh sách mà không có sự kiện nào cũng ra một dòng **rỗng** —
    chính những dòng rỗng mới là thứ đáng nhìn. Đó là kênh sẽ hiện "Không có
    thông tin" trên đầu thu.
    """
    by_service: dict[int, list[Slot]] = {}
    for e in events:
        if not touches(e, day, tz):
            continue
        by_service.setdefault(e.service_id, []).append(Slot(
            start=minutes_into_day(e.start_utc, day, tz),
            minutes=max(1, int(e.duration.total_seconds() // 60)),
            title=e.name,
            text=e.text,
        ))

    rows = []
    for item in services:
        service_id, name, radio, *con_lai = item
        epg = bool(con_lai[0]) if con_lai else True
        slots = () if not epg else tuple(
            sorted(by_service.get(service_id, []),
                   key=lambda s: (s.start, s.minutes)))
        rows.append(Row(service_id=service_id, name=name, radio=radio,
                        epg=epg, slots=slots, gaps=find_gaps(slots)))
    return Board(day=day, rows=tuple(rows))

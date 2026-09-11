"""Quy tắc ``version_number`` — 5 bit, quay vòng, và chỉ đổi khi người quyết định.

Trường này rộng **5 bit**: giá trị hợp lệ 0–31, sau 31 quay về 0. DVB không
định nghĩa thứ tự trên nó — đầu thu chỉ phát hiện *khác*, không phát hiện *mới
hơn*. Nên "lùi version" không phải khái niệm có sẵn trên sóng; nó là khái niệm
**vận hành**, và ở đây định nghĩa bằng một quy tắc kỷ luật: mỗi lần đổi là
**cộng đúng một**, quay vòng sau 31.

Quy tắc đó làm hai việc cùng lúc. Nó khớp với chính sách thủ công của VTC —
version chỉ đổi khi có người quyết định. Và nó biến "lùi" thành thứ kiểm tra
được mà không cần đếm ngoài dải: bất kỳ bước nhảy nào khác +1 đều đáng ngờ.

Bảng phán quyết ở ``classify`` mới là phần đáng đọc kỹ. Ô nguy hiểm nhất là
**nội dung khác mà version giống**: đầu thu không nhận ra có thay đổi và giữ
nguyên dữ liệu cũ, im lặng, cho tới khi có người gọi điện.
"""

from __future__ import annotations

from enum import Enum

BITS = 5
MODULUS = 1 << BITS
MAX = MODULUS - 1


class VersionError(ValueError):
    """Giá trị version không hợp lệ."""


class Verdict(Enum):
    """Kết luận khi so một bảng trong cấu hình với chính nó trên sóng."""

    IN_SYNC = "khop"
    """Nội dung giống, version giống. Không có gì đang chờ áp."""

    READY = "san sang"
    """Nội dung khác, version là bước kế tiếp. Đây là một thay đổi đúng cách."""

    POINTLESS_BUMP = "tang thua"
    """Nội dung giống nhưng version đã tăng. Đầu thu sẽ dò lại kênh mà chẳng
    nhận được gì mới — tốn công cả mạng cho một thay đổi rỗng."""

    SILENT_CHANGE = "doi ngam"
    """**Nguy hiểm nhất.** Nội dung khác mà version giữ nguyên: đầu thu không
    biết có gì đổi và tiếp tục dùng dữ liệu cũ."""

    UNEXPECTED_JUMP = "nhay bat thuong"
    """Version không phải bước kế tiếp. Có thể ai đó gõ nhầm, hoặc cấu hình đã
    trôi khỏi sóng nhiều nhịp."""


#: Những phán quyết không được phép phát ra sóng.
BLOCKING = frozenset({Verdict.SILENT_CHANGE, Verdict.UNEXPECTED_JUMP})


def validate(value: int, what: str = "version") -> int:
    """Kiểm tra một giá trị nằm trong dải 5 bit."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise VersionError(f"{what}: phai la so nguyen, gap {value!r}")
    if not 0 <= value <= MAX:
        raise VersionError(
            f"{what}: {value} ngoai dai 0..{MAX}. Truong nay rong {BITS} bit — "
            f"sau {MAX} quay ve 0, khong phai tang toi {MODULUS}."
        )
    return value


def next_version(value: int) -> int:
    """Bước kế tiếp, quay vòng sau 31.

    Đây là **cách duy nhất** được phép sinh giá trị mới. Không cộng tay, không
    băm nội dung — xem phần mở đầu module và FR-15.
    """
    return (validate(value) + 1) % MODULUS


def is_successor(candidate: int, current: int) -> bool:
    """``candidate`` có đúng là bước ngay sau ``current`` không."""
    return validate(candidate, "candidate") == next_version(current)


def classify(*, config_version: int, air_version: int, content_same: bool) -> Verdict:
    """Phán quyết cho một bảng. Xem bảng ở đầu module."""
    validate(config_version, "config_version")
    validate(air_version, "air_version")

    if config_version == air_version:
        return Verdict.IN_SYNC if content_same else Verdict.SILENT_CHANGE
    if is_successor(config_version, air_version):
        return Verdict.READY if not content_same else Verdict.POINTLESS_BUMP
    return Verdict.UNEXPECTED_JUMP


def explain(verdict: Verdict, *, config_version: int, air_version: int) -> str:
    """Câu giải thích cho người vận hành đọc, không phải cho máy phân nhánh."""
    v, a = config_version, air_version
    if verdict is Verdict.IN_SYNC:
        return f"khop o version {a}"
    if verdict is Verdict.READY:
        return f"san sang ap: {a} -> {v}"
    if verdict is Verdict.POINTLESS_BUMP:
        return (f"version tang {a} -> {v} nhung noi dung khong doi; "
                f"ca mang se do lai kenh ma khong nhan duoc gi moi")
    if verdict is Verdict.SILENT_CHANGE:
        return (f"noi dung da doi nhung version van la {a}; "
                f"dau thu se giu du lieu cu ma khong bao gi. Tang len {next_version(a)}.")
    return (f"version tren song la {a}, cau hinh la {v} — khong phai buoc ke tiep "
            f"({next_version(a)}). Kiem tra lai truoc khi phat.")

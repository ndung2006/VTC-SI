"""Tăng version SDT và BAT tự động — FR-92.

Vì sao cần: ô nguy hiểm nhất trong bảng phán quyết của ``model.version`` là
**nội dung đổi mà version giữ nguyên**. Đầu thu không nhận ra có thay đổi nên
giữ dữ liệu cũ, im lặng, cho tới khi có người gọi điện. Đó không phải rủi ro
lý thuyết: ngày 2026-09-13 kênh 877 được thêm vào bouquet 0x6510 qua giao
diện, nội dung đi từ 78 lên 79 dịch vụ, và version đứng yên ở 26.

Vì sao **không** phải "cộng một mỗi lần bấm Lưu": hai máy ngang hàng phải sinh
ra cùng byte từ cùng một commit. Một bộ đếm theo thao tác sẽ lệch ngay khi số
lần bấm khác nhau — và lệch theo kiểu tệ nhất, cùng một version mang hai nội
dung khác nhau. Lúc mux chuyển nguồn, đầu thu thấy version quen thuộc nên
không đọc lại, rồi giữ nguyên dữ liệu sai.

Nên mốc so là **bản đã commit**, và quy tắc nằm trong ``version.auto_next``.

**NIT không nằm trong phạm vi này, có chủ ý.** Đổi NIT là cả mạng dò lại kênh,
nên bắt phải có người quyết định là đúng. Đổi lại, ``vtcsi preflight`` phải
tiếp tục canh NIT thật gắt: nội dung NIT đổi mà version không đổi thì **mất
kênh**, hậu quả nặng hơn hẳn SDT hay BAT.
"""

from __future__ import annotations

from dataclasses import replace

from vtcsi.model.entities import Config
from vtcsi.model.version import auto_next
from vtcsi.tables import tsduck as T
from vtcsi.version.preflight import _strip_version, _tables, _versions

NIT = "NIT"
"""Tên bảng nằm ngoài phạm vi tự động. Xem docstring của module."""


def plan(now: Config, committed: Config) -> dict[str, int]:
    """Những bảng cần tăng version, và tăng lên bao nhiêu.

    Dùng **đúng** phép so của ``preflight``: chuẩn hoá cây XML rồi bỏ thuộc
    tính ``version`` ra ngoài. Hai bên phải dùng chung một phép so, nếu không
    sẽ có lúc bên này tăng còn bên kia vẫn kêu — và người trực không biết tin
    bên nào.
    """
    nay, truoc = _tables(now), _tables(committed)
    v_nay, v_truoc = _versions(now), _versions(committed)

    ra: dict[str, int] = {}
    for ten in sorted(nay):
        if ten == NIT or ten not in truoc:
            # Bảng mới chưa từng commit thì không có mốc nào để so. Version của
            # nó là con số người ta vừa đặt, và đó là câu trả lời đúng.
            continue
        same = (T.canon(_strip_version(nay[ten]))
                == T.canon(_strip_version(truoc[ten])))
        moi = auto_next(on_disk=v_nay[ten], committed=v_truoc[ten],
                        content_same=same)
        if moi is not None:
            ra[ten] = moi
    return ra


def apply(cfg: Config, ke_hoach: dict[str, int]) -> Config:
    """Trả về cấu hình mới mang version đã tăng. Không sửa cái đưa vào."""
    if not ke_hoach:
        return cfg

    sdts = tuple(
        replace(s, version=ke_hoach.get(f"SDT ts{s.ts_id}", s.version))
        for s in cfg.sdts)
    bouquets = tuple(
        replace(b, version=ke_hoach.get(f"BAT {b.bouquet_id:04x}", b.version))
        for b in cfg.bouquets)
    return replace(cfg, sdts=sdts, bouquets=bouquets)


def describe(ke_hoach: dict[str, int]) -> str:
    """Một dòng cho người trực đọc. Rỗng nghĩa là không có gì tăng."""
    if not ke_hoach:
        return ""
    phan = ", ".join(f"{ten} → {v}" for ten, v in sorted(ke_hoach.items()))
    return f"tự tăng version: {phan}"

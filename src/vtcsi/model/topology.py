"""Vòng transport — bouquet phủ những TS nào. Lõi thuần.

Tách khỏi ``model.lcn`` vì hai tầng khác nhau: ``lcn`` lo *bên trong* một vòng
transport (kênh nào ở trong gói, mang số mấy), còn đây lo **có vòng đó hay
không**. Nhầm hai tầng là cách sinh ra bouquet 0x6520 — một bảng BAT phát ra
sóng mà không có vòng transport nào, tức không nói được điều gì (RO-15).

Một điều dễ tưởng là chi tiết nhưng không phải: ``original_network_id``
**không suy ra được** từ ``ts_id``, và ở VTC thì đúng là không suy được thật —
TS 8 mang ONID **12901**, còn TS 3 và TS 1000 mang ONID **1**. Gõ nhầm ô này
là tạo ra một vòng transport trỏ vào một mạng không tồn tại. Nên ta **gợi ý**
giá trị lấy từ SDT cùng ``ts_id``, và gợi ý đó là thứ đáng tin duy nhất ở đây.
"""

from __future__ import annotations

from dataclasses import replace

from vtcsi.model.entities import BatTsLoop, Bouquet, Config


class TopologyError(ValueError):
    """Thao tác vòng transport bị từ chối."""


def has_loop(bouquet: Bouquet, ts_id: int) -> bool:
    return any(t.ts_id == ts_id for t in bouquet.ts_loops)


def suggested_onid(cfg: Config, ts_id: int) -> int | None:
    """ONID của TS đó theo SDT, nếu biết. Chỉ để điền sẵn vào biểu mẫu."""
    for s in cfg.sdts:
        if s.ts_id == ts_id:
            return s.original_network_id
    return None


def suggested_pds(cfg: Config, bouquet: Bouquet) -> str | int | None:
    """PDS nên điền sẵn cho một vòng transport mới.

    Vòng mới thiếu PDS mà lại có LCN thì đầu thu **không hiểu descriptor LCN**,
    vì ``private_data_specifier`` phải đứng ngay trước nó.

    Tìm theo ba vòng, rộng dần: các vòng khác của chính bouquet này, rồi PDS
    khai ở cấp bouquet, rồi bất kỳ vòng nào trong cấu hình. Vòng thứ ba là
    vòng quan trọng: bouquet 0x6520 không có vòng nào cả, nên nếu chỉ nhìn
    trong nó thì không gợi ý được gì — trong khi cả sáu vòng đang phát đều
    dùng cùng một giá trị.

    Giá trị đó là chuỗi ``"NorDig"``, **không phải** số. Ghi ``0x00000029``
    cũng ra đúng byte, nhưng YAML sẽ đọc thành ``41`` và lệch hẳn với phần còn
    lại của cấu hình — thứ khiến người sau phải dừng lại tra xem có gì khác
    nhau không.
    """
    for t in bouquet.ts_loops:
        if t.private_data_specifier is not None:
            return t.private_data_specifier
    if bouquet.private_data_specifier is not None:
        return bouquet.private_data_specifier
    for other in cfg.bouquets:
        for t in other.ts_loops:
            if t.private_data_specifier is not None:
                return t.private_data_specifier
    return None


def add_loop(bouquet: Bouquet, ts_id: int, original_network_id: int,
             private_data_specifier: str | int | None = None) -> Bouquet:
    """Thêm một vòng transport rỗng vào bouquet.

    Rỗng là đúng: thêm vòng và chọn kênh là hai quyết định khác nhau, và gộp
    chúng lại sẽ đẻ ra cái nút "thêm tất cả kênh" mà không ai thực sự muốn
    bấm. Chọn kênh làm ở ``model.lcn.add_member``.
    """
    if has_loop(bouquet, ts_id):
        raise TopologyError(
            f"bouquet {bouquet.bouquet_id:#06x} đã có vòng TS {ts_id}")
    if not 0 <= ts_id <= 0xFFFF:
        raise TopologyError(f"ts_id = {ts_id} không nằm trong 16 bit")
    if not 0 <= original_network_id <= 0xFFFF:
        raise TopologyError(
            f"original_network_id = {original_network_id} không nằm trong 16 bit")
    return replace(bouquet, ts_loops=bouquet.ts_loops + (BatTsLoop(
        ts_id=ts_id,
        original_network_id=original_network_id,
        private_data_specifier=private_data_specifier,
    ),))


def remove_loop(bouquet: Bouquet, ts_id: int, *, force: bool = False) -> Bouquet:
    """Bỏ cả một vòng transport khỏi bouquet.

    Từ chối khi vòng đó còn kênh, trừ khi ``force``. Đây không phải sự cẩn thận
    thừa: bỏ một vòng đầy là gỡ hàng chục kênh khỏi gói bằng một cú bấm, và
    hậu quả — hàng chục kênh biến mất khỏi danh sách của khách — chỉ lộ ra sau
    lần dò kế tiếp.
    """
    loop = next((t for t in bouquet.ts_loops if t.ts_id == ts_id), None)
    if loop is None:
        raise TopologyError(
            f"bouquet {bouquet.bouquet_id:#06x} không có vòng TS {ts_id}")
    if loop.services and not force:
        raise TopologyError(
            f"vòng TS {ts_id} còn {len(loop.services)} dịch vụ — bỏ từng kênh "
            f"trước, hoặc xác nhận bỏ cả vòng")
    return replace(bouquet, ts_loops=tuple(
        t for t in bouquet.ts_loops if t.ts_id != ts_id))


def says_nothing(cfg: Config) -> tuple[int, ...]:
    """Bouquet nào phát ra sóng mà **không nói gì cả** — RO-15.

    Không vòng transport **và** không linkage. Hai vế, không phải một: bouquet
    0x0044 ``MA QR`` và 0x3622 ``Master`` cũng không có vòng transport nào,
    nhưng chúng mang lần lượt 1 và 10 linkage — đó là các con trỏ OTA nâng cấp
    đầu thu, và một BAT chỉ mang linkage là cách dùng hoàn toàn hợp lệ.

    Báo cả ba sẽ là báo động giả cho hai trong ba trường hợp, và một cảnh báo
    luôn kêu là một cảnh báo đã bị tắt — cùng bài học đã rút FR-54.
    """
    return tuple(b.bouquet_id for b in cfg.bouquets
                 if not b.ts_loops and not b.linkages)

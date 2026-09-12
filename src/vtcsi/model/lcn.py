"""Luật số kênh — lõi thuần.

``model.plain`` chỉ kiểm tra được thứ làm cấu hình **không đọc nổi**. Số kênh
thì khác: một bouquet có hai kênh cùng số vẫn nạp được, vẫn sinh ra XML hợp lệ,
vẫn phát ra sóng — rồi đầu thu tự chọn một trong hai. Không có gì hỏng để mà
bắt; chỉ có khách hàng bấm số 7 và ra nhầm kênh.

Nên các luật ở đây **không** nằm trong ``from_plain``: chúng không chặn việc
nạp, chúng chỉ báo. Lý do rất cụ thể — cấu hình đã gieo từ sóng phải nạp được
nguyên trạng kể cả khi sóng đang sai, nếu không ta mất luôn khả năng so byte.
Thấy sai thì nói ra, và để người quyết định có sửa hay không.

Chuẩn: ``nordig_logical_channel_descriptor_v1`` dành **10 bit** cho số kênh,
nên 1…1023. Số 0 theo thông lệ nghĩa là "không gán", và ta từ chối nó — muốn
giấu một kênh thì hạ cờ ``visible``, đó mới là cách đúng.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from vtcsi.model.entities import Bouquet, Config, LcnEntry, ServiceRef

MIN_LCN = 1
MAX_LCN = 1023
"""Mười bit trong descriptor NorDig v1."""


class LcnError(ValueError):
    """Thao tác số kênh bị từ chối. Thông điệp đi thẳng ra giao diện."""


@dataclass(frozen=True, slots=True)
class Problem:
    """Một điều đáng nói về số kênh.

    ``blocking`` phân biệt *sai* với *đáng ngờ*: hai kênh cùng số là sai và
    phải sửa; một kênh không có số thì có thể là chủ ý — kênh barker hoặc kênh
    chỉ dùng cho OTA không cần xuất hiện trong danh sách.
    """

    bouquet_id: int
    message: str
    blocking: bool = False

    def text(self) -> str:
        mark = "!!" if self.blocking else " ·"
        return f"{mark} bouquet {self.bouquet_id:#06x}: {self.message}"


# ------------------------------------------------------------------- kiểm tra


def check(cfg: Config) -> tuple[Problem, ...]:
    """Soi toàn bộ số kênh của mọi bouquet.

    Bốn điều được soi, theo thứ tự mức độ:

    1. **Trùng số** trong cùng một bouquet — chặn. Đầu thu chỉ giữ một kênh.
    2. **Số ngoài khoảng** 1…1023 — chặn. Không mã hoá nổi vào 10 bit.
    3. **Có số mà không có mặt** trong danh sách dịch vụ của bouquet — chặn.
       Số trỏ vào hư không.
    4. **Vòng có số kênh mà không khai PDS** — chặn. Xem chú thích trong thân
       hàm; đây là kiểu hỏng im lặng nhất trong cả module.
    5. **Có mặt mà không có số** — chỉ báo, và **chỉ khi bouquet đó có đánh số
       ở đâu đó**. Bouquet không có lấy một số kênh nào không phải là danh sách
       kênh: 0x6550 ``VTC_BLOCKEDFTA`` gom 48 dịch vụ thuần tuý để khoá mã.
       Báo cả 48 dòng ở đó là báo động giả, và một cảnh báo luôn kêu thì chẳng
       mấy chốc không ai đọc nữa — đúng lý do FR-54 bị rút khỏi đặc tả.
    """
    out: list[Problem] = []
    in_sdt = {(s.ts_id, x.service_id) for s in cfg.sdts for x in s.services}

    for b in cfg.bouquets:
        numbers_anywhere = any(t.lcn for t in b.ts_loops)
        seen: dict[int, list[tuple[int, int]]] = {}
        for t in b.ts_loops:
            members = {r.service_id for r in t.services}
            numbered = {e.service_id for e in t.lcn}

            # PDS phai dung ngay TRUOC descriptor LCN de gioi han pham vi cua
            # no. Thieu PDS thi dau thu khong biet `0x83` la descriptor cua ai
            # va bo qua ca khoi — ca bang so kenh bien mat, im lang.
            if t.lcn and t.private_data_specifier is None:
                out.append(Problem(
                    b.bouquet_id,
                    f"vòng TS {t.ts_id} có {len(t.lcn)} số kênh nhưng không khai "
                    f"private_data_specifier — đầu thu sẽ bỏ qua cả descriptor LCN",
                    blocking=True))

            for e in t.lcn:
                seen.setdefault(e.lcn, []).append((t.ts_id, e.service_id))

                if not MIN_LCN <= e.lcn <= MAX_LCN:
                    out.append(Problem(
                        b.bouquet_id,
                        f"dịch vụ {e.service_id} có số kênh {e.lcn}, ngoài khoảng "
                        f"{MIN_LCN}…{MAX_LCN}", blocking=True))
                if e.service_id not in members:
                    out.append(Problem(
                        b.bouquet_id,
                        f"số kênh {e.lcn} trỏ tới dịch vụ {e.service_id} không có "
                        f"trong bouquet", blocking=True))
                elif (t.ts_id, e.service_id) not in in_sdt:
                    out.append(Problem(
                        b.bouquet_id,
                        f"số kênh {e.lcn} trỏ tới dịch vụ {e.service_id} không có "
                        f"trong SDT của TS {t.ts_id}", blocking=True))

            for sid in sorted(members - numbered) if numbers_anywhere else ():
                out.append(Problem(
                    b.bouquet_id,
                    f"dịch vụ {sid} (TS {t.ts_id}) có trong bouquet nhưng không "
                    f"có số kênh"))

        for number, holders in sorted(seen.items()):
            if len(holders) > 1:
                who = ", ".join(f"{sid} (TS {ts})" for ts, sid in holders)
                out.append(Problem(
                    b.bouquet_id,
                    f"số kênh {number} bị {len(holders)} dịch vụ dùng chung: {who}",
                    blocking=True))

    return tuple(out)


def blocking(problems: tuple[Problem, ...]) -> tuple[Problem, ...]:
    return tuple(p for p in problems if p.blocking)


def next_after_last(bouquet: Bouquet) -> int:
    """Số ngay sau số cao nhất đang dùng — gợi ý mặc định khi thêm kênh.

    Khác ``next_free``, cái này **không** lấp lỗ hổng ở giữa. Một lỗ hổng
    thường là chỗ để dành, không phải chỗ trống.
    """
    used = {e.lcn for t in bouquet.ts_loops for e in t.lcn}
    return next_free(bouquet, (max(used) + 1) if used else MIN_LCN)


def next_free(bouquet: Bouquet, after: int = MIN_LCN) -> int:
    """Số kênh trống đầu tiên từ ``after`` trở lên, trong cả bouquet.

    Dùng để gợi ý khi thêm kênh. Gợi ý thôi — người vẫn sửa được, vì thứ tự
    số kênh là quyết định biên tập chứ không phải kỹ thuật.
    """
    used = {e.lcn for t in bouquet.ts_loops for e in t.lcn}
    n = max(after, MIN_LCN)
    while n in used:
        n += 1
    if n > MAX_LCN:
        raise LcnError(f"hết số kênh trong khoảng {MIN_LCN}…{MAX_LCN}")
    return n


# -------------------------------------------------------------------- sửa đổi


def _loop(bouquet: Bouquet, ts_id: int):
    for t in bouquet.ts_loops:
        if t.ts_id == ts_id:
            return t
    raise LcnError(f"bouquet {bouquet.bouquet_id:#06x} không có TS {ts_id}")


def _put(bouquet: Bouquet, ts_id: int, new_loop) -> Bouquet:
    return replace(bouquet, ts_loops=tuple(
        new_loop if t.ts_id == ts_id else t for t in bouquet.ts_loops))


def set_numbers(bouquet: Bouquet, ts_id: int,
                numbers: dict[int, int],
                visible: dict[int, bool] | None = None) -> Bouquet:
    """Đặt lại số kênh cho một vòng transport, nguyên khối.

    ``numbers`` là toàn bộ bảng mới: dịch vụ nào không có trong đó thì **mất
    số**. Cố ý làm vậy — biểu mẫu gửi lên cả bảng, nên xoá một ô là một hành
    động rõ ràng chứ không phải bỏ sót.

    Từ chối ngay tại đây nếu trùng số hoặc ngoài khoảng, vì sau khi ghi vào
    YAML thì không còn ai chặn nữa.
    """
    loop = _loop(bouquet, ts_id)
    members = {r.service_id for r in loop.services}
    was = {e.service_id: e.visible for e in loop.tcn} if False else \
        {e.service_id: e.visible for e in loop.lcn}
    vis = visible or {}

    for sid, n in numbers.items():
        if sid not in members:
            raise LcnError(f"dịch vụ {sid} không có trong bouquet này")
        if not MIN_LCN <= n <= MAX_LCN:
            raise LcnError(
                f"dịch vụ {sid}: số kênh {n} ngoài khoảng {MIN_LCN}…{MAX_LCN}")

    # Trung so tinh tren CA bouquet, khong chi mot vong transport: khach hang
    # bam so 7 tren dieu khien, ho khong biet TS la gi.
    elsewhere = {e.lcn: (t.ts_id, e.service_id)
                 for t in bouquet.ts_loops if t.ts_id != ts_id
                 for e in t.lcn}
    taken: dict[int, int] = {}
    for sid, n in sorted(numbers.items()):
        if n in taken:
            raise LcnError(f"số kênh {n} đặt cho cả dịch vụ {taken[n]} và {sid}")
        if n in elsewhere:
            other_ts, other_sid = elsewhere[n]
            raise LcnError(
                f"số kênh {n} đã thuộc dịch vụ {other_sid} ở TS {other_ts} "
                f"trong cùng bouquet này")
        taken[n] = sid

    entries = tuple(
        LcnEntry(service_id=sid, lcn=numbers[sid],
                 visible=vis.get(sid, was.get(sid, True)))
        for sid in sorted(numbers))
    return _put(bouquet, ts_id, replace(loop, lcn=entries))


def add_member(bouquet: Bouquet, ts_id: int, ref: ServiceRef,
               number: int | None = None) -> Bouquet:
    """Thêm một dịch vụ vào bouquet, kèm số kênh nếu có.

    Gọi hai lần với cùng dịch vụ là lỗi, không phải thao tác rỗng: nếu ai đó
    bấm hai lần thì họ đang nhầm, và im lặng bỏ qua sẽ giấu mất cái nhầm đó.
    """
    loop = _loop(bouquet, ts_id)
    if any(r.service_id == ref.service_id for r in loop.services):
        raise LcnError(f"dịch vụ {ref.service_id} đã có trong bouquet này")

    # Noi vao CUOI, khong sap xep lai ca danh sach.
    #
    # Thu tu trong `service_list_descriptor` khong doi nghia voi dau thu, nhung
    # no doi BYTE — va khop tung byte voi song la AC-1. Tren song, vong TS 8
    # cua bouquet 0x6510 dang la [815, 856, 826, 829, …], khong theo thu tu nao
    # ca. Sap lai cho dep se lam 64 muc doi cho, `git diff` phinh len 106 dong,
    # va phep so byte hong — doi lay dung mot thu: cam giac ngan nap.
    loop = replace(loop, services=loop.services + (ref,))
    out = _put(bouquet, ts_id, loop)
    if number is None:
        return out
    numbers = {e.service_id: e.lcn for e in loop.lcn}
    numbers[ref.service_id] = number
    return set_numbers(out, ts_id, numbers)


def remove_member(bouquet: Bouquet, ts_id: int, service_id: int) -> Bouquet:
    """Bỏ một dịch vụ khỏi bouquet, **và** bỏ số kênh của nó.

    Bỏ sót vế thứ hai là cách tạo ra đúng lỗi mà ``check`` bắt ở mục 3.
    """
    loop = _loop(bouquet, ts_id)
    if not any(r.service_id == service_id for r in loop.services):
        raise LcnError(f"dịch vụ {service_id} không có trong bouquet này")
    return _put(bouquet, ts_id, replace(
        loop,
        services=tuple(r for r in loop.services if r.service_id != service_id),
        lcn=tuple(e for e in loop.lcn if e.service_id != service_id)))


def forget_service(cfg: Config, ts_id: int, service_id: int) -> Config:
    """Gỡ một dịch vụ khỏi **mọi** bouquet — dùng khi xoá hẳn kênh.

    Có mặt ở đây thay vì trong vỏ web để chỗ nào xoá dịch vụ cũng gỡ giống
    nhau, kể cả dòng lệnh về sau.
    """
    out = []
    for b in cfg.bouquets:
        loops = tuple(
            replace(t,
                    services=tuple(r for r in t.services
                                   if r.service_id != service_id),
                    lcn=tuple(e for e in t.lcn if e.service_id != service_id))
            if t.ts_id == ts_id else t
            for t in b.ts_loops)
        out.append(replace(b, ts_loops=loops))
    return replace(cfg, bouquets=tuple(out))

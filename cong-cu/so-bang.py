# -*- coding: utf-8 -*-
"""So bảng cấu trúc — NIT, SDT, BAT — giữa hai phía, và chỉ ra CHỖ lệch.

``preflight`` chỉ nói *"lệch"*. Cái này nói lệch ở **thuộc tính nào, phần tử
nào**.

Mỗi phía là một **thư mục cấu hình** hoặc một **bản thu đã trích ra XML**, trộn
lẫn thoải mái. Nhờ vậy một công cụ trả lời được ba câu hỏi khác nhau::

    # cau hinh cua ta  so voi  song cua Barrowa
    python3 cong-cu/so-bang.py /repo/config /vtc/nit-brw.xml

    # hai ban thu: song cua ta  so voi  song cua Barrowa
    python3 cong-cu/so-bang.py /vtc/nit-si.xml /vtc/nit-brw.xml

    # chi mot bang, khi da biet no lech
    python3 cong-cu/so-bang.py /repo/config /vtc/nit-brw.xml "SDT ts8"

Trích bảng ra XML **không** dùng ``--pack-and-flush``::

    tsp -I file ban-thu.ts -P tables --pid 16 --pid 17 --xml ra.xml -O drop

Chỗ này ngược hẳn với ``so-eit.py``, và phải ngược. ``--pack-and-flush`` đóng
gói cả những bảng còn **thiếu section**; với EIT thì chấp nhận được vì ta chỉ
đếm sự kiện, nhưng với NIT/SDT/BAT thì một bảng thiếu section sẽ hiện ra thành
"thiếu mấy chục dịch vụ" — một khác biệt **không có thật**, và là loại sai tệ
nhất: nó khiến người trực đi sửa cấu hình đang đúng. Bảng cấu trúc phát lại vài
giây một lần, nên thu đủ lâu là có đủ.

``version`` được bỏ qua khi so nội dung, rồi in riêng ở cuối: hai hệ đánh số
phiên bản độc lập với nhau nên lệch version là chuyện bình thường, còn lệch nội
dung thì không.
"""

from __future__ import annotations

import sys
from pathlib import Path
from xml.etree import ElementTree as ET

try:
    from vtcsi.config import loader
except ModuleNotFoundError:  # chay tay tu kho nguon, ngoai container
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from vtcsi.config import loader

from vtcsi.model.entities import Config
from vtcsi.tables import tsduck as T
from vtcsi.version.preflight import _strip_version, _tables, _versions


def nap(duong: str) -> Config:
    """Thư mục thì đọc như cấu hình, file thì đọc như bản thu."""
    p = Path(duong)
    if p.is_dir():
        return loader.load(p)
    if not p.exists():
        raise SystemExit(f"khong co {p}")
    return T.read_dump(p.read_text(encoding="utf-8"))


def duyet(a: ET.Element, b: ET.Element, ten_a: str, ten_b: str,
          duong: str = "") -> None:
    """So hai cây, in ra từng chỗ khác."""
    if a.tag != b.tag:
        print(f"  {duong}: the khac nhau — {ten_a}={a.tag} {ten_b}={b.tag}")
        return
    kh_a = {k: v for k, v in a.attrib.items() if k != "version"}
    kh_b = {k: v for k, v in b.attrib.items() if k != "version"}
    for k in sorted(set(kh_a) | set(kh_b)):
        va, vb = kh_a.get(k), kh_b.get(k)
        if va != vb:
            print(f"  {duong}/{a.tag}.{k}:  {ten_a}={va!r}   {ten_b}={vb!r}")
    ca = [c for c in a if c.tag != "metadata"]
    cb = [c for c in b if c.tag != "metadata"]
    if len(ca) != len(cb):
        print(f"  {duong}/{a.tag}: so phan tu con khac — "
              f"{ten_a}={len(ca)} {ten_b}={len(cb)}")
        t_a = [c.tag for c in ca]
        t_b = [c.tag for c in cb]
        for t in sorted(set(t_a) | set(t_b)):
            na, nb = t_a.count(t), t_b.count(t)
            if na != nb:
                print(f"      {t}: {ten_a}={na} {ten_b}={nb}")
    for i, (x, y) in enumerate(zip(ca, cb)):
        duyet(x, y, ten_a, ten_b, f"{duong}/{a.tag}[{i}]")


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    # Nhan lay tu chinh duong dan. Goi "A" va "B" thi doc bao cao xong van
    # phai ngoi nho ben nao la ben nao.
    ten_a, ten_b = Path(sys.argv[1]).name[:12], Path(sys.argv[2]).name[:12]
    a, b = nap(sys.argv[1]), nap(sys.argv[2])
    chi_mot = sys.argv[3] if len(sys.argv) > 3 else None

    ta, song = _tables(a), _tables(b)
    v_ta, v_song = _versions(a), _versions(b)
    moi_ten = sorted(set(ta) | set(song))
    if chi_mot:
        if chi_mot not in moi_ten:
            print(f"khong co bang {chi_mot!r}. Co: {moi_ten}")
            return 1
        moi_ten = [chi_mot]

    lech: list[str] = []
    print(f"{'bang':<16}{ten_a:>13}{ten_b:>13}   noi dung")
    for ten in moi_ten:
        if ten not in ta or ten not in song:
            ben = f"chi co o {ten_a}" if ten in ta else f"chi co o {ten_b}"
            print(f"{ten:<16}{'':>13}{'':>13}   {ben}")
            lech.append(ten)
            continue
        same = (T.canon(_strip_version(ta[ten]))
                == T.canon(_strip_version(song[ten])))
        print(f"{ten:<16}{v_ta[ten]:>13}{v_song[ten]:>13}   "
              f"{'khop' if same else 'LECH'}")
        if not same:
            lech.append(ten)

    if not lech:
        print(f"\n{len(moi_ten)}/{len(moi_ten)} bang khop noi dung "
              f"(bo qua version).")
        return 0

    for ten in lech:
        if ten not in ta or ten not in song:
            continue
        print(f"\n=== {ten} — lech o dau ===")
        duyet(_strip_version(ta[ten]), _strip_version(song[ten]), ten_a, ten_b)
    print(f"\n{len(lech)}/{len(moi_ten)} bang lech.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

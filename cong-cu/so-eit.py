# -*- coding: utf-8 -*-
"""So EPG của ta với EPG trên sóng, từ hai bản thu.

``preflight`` không đụng tới EIT — nó so mười bảng cấu trúc, và đó là chủ ý:
EIT thay đổi theo từng phút, nên so byte không có nghĩa. Nhưng vẫn cần trả lời
được ba câu, và đó là việc của công cụ này:

* Ta phủ **những dịch vụ nào**, sóng phủ những dịch vụ nào, bên nào thiếu?
* Ta phát **những loại bảng nào** — p/f, lịch ngày 0–3, lịch ngày 4–7?
* Lịch của ta **sâu bao nhiêu** so với sóng?

Trích EIT ra XML **phải** có hai cờ này::

    tsp -I file ban-thu.ts -P tables --pid 18 --fill-eit --pack-and-flush         --xml eit.xml -O drop

    python3 cong-cu/so-eit.py eit-ta.xml eit-br.xml

Vì sao hai cờ đó. ``-P tables`` chỉ xuất bảng **đầy đủ mọi section**. EIT p/f
khai hai section — ``0`` chương trình đang phát, ``1`` chương trình kế tiếp —
và bảng lịch phân đoạn thường không truyền các section rỗng ở cuối. Thiếu cờ
thì file XML ra **rỗng**, và một luồng EIT hoàn toàn tốt trông y hệt một luồng
không có EIT.

``--all-sections`` thì **không** dùng được ở đây: TSDuck từ chối nó khi đầu ra
là XML hoặc JSON. Nó chỉ dành cho đầu ra dạng văn bản.

Bảng do ``--pack-and-flush`` đóng gói có thể thiếu section — chỉ dùng để
**phân tích**, đừng bao giờ phát lại chúng.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

#: table_id của EIT, theo ETSI EN 300 468.
LOAI = {
    0x4E: "p/f actual", 0x4F: "p/f other",
}
for _t in range(0x50, 0x60):
    LOAI[_t] = f"lich actual ngay {(_t - 0x50) * 4}-{(_t - 0x50) * 4 + 3}"
for _t in range(0x60, 0x70):
    LOAI[_t] = f"lich other ngay {(_t - 0x60) * 4}-{(_t - 0x60) * 4 + 3}"


def _table_id(eit: ET.Element) -> int:
    """``table_id`` thật của một phần tử ``<EIT>``.

    Lược đồ EIT của TSDuck **không** ghi ``table_id``; nó ghi ``type="pf|uint4"``
    cộng ``actual="bool"``. Chỗ này từng sai một lần: ``int("0", 0)`` thành công
    nên ``type="0"`` bị đọc thành ``table_id 0x00`` thay vì bảng lịch 0x50 —
    mọi bảng lịch biến mất khỏi báo cáo mà không có lỗi nào.
    """
    tid = eit.get("table_id")
    if tid is not None:
        return int(tid, 0)
    actual = (eit.get("actual", "true").lower() in ("true", "1", "yes"))
    t = (eit.get("type") or "pf").strip()
    if t == "pf":
        return 0x4E if actual else 0x4F
    return (0x50 if actual else 0x60) + int(t)


def doc(p: Path) -> dict:
    """Gom EIT trong một file XML thành số liệu đọc được."""
    if not p.exists():
        return {"loi": f"khong co file {p}"}
    goc = ET.parse(p).getroot()
    bang: dict[int, int] = defaultdict(int)
    su_kien: dict[int, set[str]] = defaultdict(set)
    moc: list[str] = []
    for eit in goc.iter("EIT"):
        n = _table_id(eit)
        bang[n] += 1
        sid = int(eit.get("service_id", "0"), 0)
        for e in eit.iter("event"):
            t = e.get("start_time")
            if t:
                su_kien[sid].add(f"{t}|{e.get('duration','')}")
                moc.append(t)
    return {"bang": dict(bang), "su_kien": su_kien,
            "som": min(moc) if moc else None, "muon": max(moc) if moc else None}


def in_mot_ben(ten: str, d: dict) -> None:
    print(f"--- {ten} ---")
    if "loi" in d:
        print(f"   {d['loi']}")
        return
    if not d["bang"]:
        print("   khong co bang EIT nao."
              " Thieu --all-sections luc trich? Xem docstring.")
        return
    for tid in sorted(d["bang"]):
        print(f"   {LOAI.get(tid, f'table_id {tid:#04x}'):<24} {d['bang'][tid]:>4} bang")
    tong = sum(len(v) for v in d["su_kien"].values())
    print(f"   {len(d['su_kien'])} dich vu · {tong} su kien")
    print(f"   lich tu {d['som']}  den  {d['muon']}")


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    ta, song = doc(Path(sys.argv[1])), doc(Path(sys.argv[2]))
    in_mot_ben("EPG CUA TA", ta)
    print()
    in_mot_ben("EPG TREN SONG", song)

    if "loi" in ta or "loi" in song:
        return 1
    print()
    print("--- SO SANH ---")
    a, b = set(ta["su_kien"]), set(song["su_kien"])
    thieu, thua = sorted(b - a), sorted(a - b)
    print(f"   song co, ta THIEU : {thieu or 'khong'}")
    print(f"   ta co, song khong : {thua or 'khong'}")

    chung = sorted(a & b)
    if chung:
        print(f"   {len(chung)} dich vu ca hai cung co — so su kien ta/song:")
        for sid in chung[:12]:
            na, nb = len(ta["su_kien"][sid]), len(song["su_kien"][sid])
            dau = "  <-- lech nhieu" if nb and (na < nb * 0.5) else ""
            print(f"      {sid}: {na:>4} / {nb:<4}{dau}")
        if len(chung) > 12:
            print(f"      ... va {len(chung) - 12} dich vu nua")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

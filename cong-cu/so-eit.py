# -*- coding: utf-8 -*-
"""So EPG của ta với EPG trên sóng, từ hai bản thu.

``preflight`` không đụng tới EIT — nó so mười bảng cấu trúc, và đó là chủ ý:
EIT thay đổi theo từng phút, nên so byte không có nghĩa. Nhưng vẫn cần trả lời
được ba câu, và đó là việc của công cụ này:

* Ta phủ **những dịch vụ nào**, sóng phủ những dịch vụ nào, bên nào thiếu?
* Ta phát **những loại bảng nào** — p/f, lịch ngày 0–3, lịch ngày 4–7?
* Lịch của ta **sâu bao nhiêu** so với sóng?

Trích EIT ra XML **phải** có hai cờ này::

    tsp -I file ban-thu.ts -P tables --pid 18 --fill-eit --pack-and-flush \\
        --xml eit.xml -O drop

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
    if goc.tag.upper() == "PSI":
        return _doc_nguon(p)
    bang: dict[str, int] = defaultdict(int)
    su_kien: dict[int, set[str]] = defaultdict(set)
    ngay: dict[str, set[str]] = defaultdict(set)
    moc: list[str] = []
    for eit in goc.iter("EIT"):
        n = _table_id(eit)
        bang[LOAI.get(n, f"table_id {n:#04x}")] += 1
        sid = int(eit.get("service_id", "0"), 0)
        for e in eit.iter("event"):
            t = e.get("start_time")
            if t:
                khoa = f"{t}|{e.get('duration','')}"
                su_kien[sid].add(khoa)
                # Gom theo ngay, moi su kien dem MOT lan du nhieu dich vu.
                ngay[t.split(" ")[0]].add(f"{sid}|{khoa}")
                moc.append(t)
    return {"bang": dict(bang), "su_kien": su_kien, "ngay": ngay,
            "som": min(moc) if moc else None, "muon": max(moc) if moc else None}


def _doc_nguon(p: Path) -> dict:
    """Đọc **file lịch nguồn** (lược đồ ``<PSI>``), không phải bảng EIT.

    Lý do đáng để công cụ này biết hai định dạng thay vì tách thành hai công
    cụ: so ta với Barrowa chỉ cho biết **có** lệch, không cho biết **ai** sai.
    Cùng một file nguồn đi vào cả hai hệ, nên đo cả hai so với nó mới quy được
    trách nhiệm. Mà muốn so được thì ba bên phải ra cùng một khuôn số liệu.

    Khoá sự kiện dựng đúng như ``doc``: ``"YYYY-MM-DD HH:MM:SS|HH:MM:SS"``.
    Cả hai đầu đều là UTC — ``parse`` chuẩn hoá về UTC, và ``start_time`` của
    EIT theo DVB vốn là UTC — nên khoá khớp nhau từng ký tự, và phép so là so
    **từng sự kiện**, không phải so hai con số tổng.
    """
    try:
        from vtcsi.epg.transform.parse import parse
    except ModuleNotFoundError:
        # Chay tay tu kho nguon, ngoai container: `src/` chua nam tren
        # sys.path. Cong cu nay de nguoi truc go luc dang co su co, nen no
        # phai chay duoc o ca hai cho.
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
        from vtcsi.epg.transform.parse import parse

    lich = parse(p.read_text(encoding="utf-8"))
    su_kien: dict[int, set[str]] = defaultdict(set)
    ngay: dict[str, set[str]] = defaultdict(set)
    moc: list[str] = []
    for e in lich.events:
        giay = int(e.duration.total_seconds())
        khoa = (f"{e.start_utc:%Y-%m-%d %H:%M:%S}"
                f"|{giay // 3600:02d}:{giay // 60 % 60:02d}:{giay % 60:02d}")
        t = khoa.split("|")[0]
        su_kien[e.service_id].add(khoa)
        ngay[t.split(" ")[0]].add(f"{e.service_id}|{khoa}")
        moc.append(t)
    return {"bang": {"file lich nguon": 1}, "su_kien": su_kien, "ngay": ngay,
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
    for nhan in sorted(d["bang"]):
        print(f"   {nhan:<24} {d['bang'][nhan]:>4} bang")
    tong = sum(len(v) for v in d["su_kien"].values())
    print(f"   {len(d['su_kien'])} dich vu · {tong} su kien")
    print(f"   lich tu {d['som']}  den  {d['muon']}")
    if d["ngay"]:
        # Do SAU cua lich. Mot con so tong khong phan biet duoc "day du mot
        # ngay" voi "thua thot tam ngay" — cot theo ngay thi phan biet duoc.
        print("   sau theo ngay:")
        dinh = max(len(v) for v in d["ngay"].values()) or 1
        for ng in sorted(d["ngay"]):
            n = len(d["ngay"][ng])
            print(f"      {ng}  {n:>5}  {'#' * max(1, round(n * 40 / dinh))}")


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    ta, song = doc(Path(sys.argv[1])), doc(Path(sys.argv[2]))
    # Cong cu nay khong chi dung de so ta voi Barrowa. So BANG SINH RA voi
    # BAN THU CUA CHINH TA tra loi mot cau khac han — mat mat nam o khau soan
    # lich hay khau phat — nen hai cai nhan phai doi duoc.
    ten_a = sys.argv[3] if len(sys.argv) > 3 else "EPG CUA TA"
    ten_b = sys.argv[4] if len(sys.argv) > 4 else "EPG TREN SONG"
    in_mot_ben(ten_a, ta)
    print()
    in_mot_ben(ten_b, song)

    if "loi" in ta or "loi" in song:
        return 1
    print()
    print("--- SO SANH ---")
    a, b = set(ta["su_kien"]), set(song["su_kien"])
    thieu, thua = sorted(b - a), sorted(a - b)
    print(f"   {ten_b} co, {ten_a} KHONG : {thieu or 'khong'}")
    print(f"   {ten_a} co, {ten_b} KHONG : {thua or 'khong'}")

    chung = sorted(a & b)
    if chung:
        # In HET, khong cat bot. Ban cat o 12 dong tung giau mat nua danh
        # sach dung luc dang can doc no.
        print(f"   {len(chung)} dich vu ca hai cung co — so su kien:")
        print(f"      {'dich vu':<10}{'A':>6}{'B':>7}   ti le")
        for sid in chung:
            na, nb = len(ta["su_kien"][sid]), len(song["su_kien"][sid])
            ti = f"{na / nb:.2f}" if nb else "—"
            dau = "  <-- lech nhieu" if nb and (na < nb * 0.5) else ""
            print(f"      {sid:<10}{na:>6}{nb:>7}   {ti}{dau}")

        # Hai ben co the cung 40 su kien ma khong su kien nao trung nhau. So
        # dem bang nhau khong chung minh duoc gi; so KHOA moi chung minh duoc.
        # Khoa PHAI kem service_id. Bo no di thi hai chuong trinh khac kenh
        # ma cung gio cung thoi luong gop lam mot, va so trung khop bi thoi
        # phong len. Dau hieu nhan ra: trung + chi-A + chi-B khong bang tong
        # su kien hai ben. Da xay ra that, tren du lieu that.
        ka = {(sid, k) for sid in chung for k in ta["su_kien"][sid]}
        kb = {(sid, k) for sid in chung for k in song["su_kien"][sid]}
        trung, chi_a, chi_b = len(ka & kb), len(ka - kb), len(kb - ka)
        print(f"   tren {len(chung)} dich vu chung:"
              f" {trung} su kien TRUNG KHOP (kenh + gio bat dau + thoi luong),"
              f" {chi_a} chi {ten_a} co, {chi_b} chi {ten_b} co")
        # Phep tinh nay phai khop. Neu khong thi khoa dang bi gop nham lan nua.
        assert trung + chi_a == len(ka) and trung + chi_b == len(kb)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

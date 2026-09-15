# -*- coding: utf-8 -*-
"""So một bảng của ta với cùng bảng đó trên sóng, chỉ ra CHỖ lệch.

`preflight` chỉ nói "lệch". Cái này nói lệch ở thuộc tính nào, phần tử nào.
Chạy trong container, cần gắn cả /data (bản thu) lẫn /repo (cấu hình).
"""
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

from vtcsi.config import loader
from vtcsi.tables import tsduck as T
from vtcsi.version.preflight import _strip_version, _tables

TEN = sys.argv[1] if len(sys.argv) > 1 else "NIT"
DUMP = sys.argv[2] if len(sys.argv) > 2 else "/data/barrowa.xml"

cfg = loader.load(Path("/repo/config"))
air = T.read_dump(Path(DUMP).read_text(encoding="utf-8"))

ta, song = _tables(cfg), _tables(air)
if TEN not in ta or TEN not in song:
    print(f"khong co bang {TEN!r}. Co: {sorted(set(ta) | set(song))}")
    raise SystemExit(1)


def duyet(a, b, duong=""):
    """So hai cây, in ra từng chỗ khác."""
    if a.tag != b.tag:
        print(f"  {duong}: the khac nhau — ta={a.tag} song={b.tag}")
        return
    kh_a = {k: v for k, v in a.attrib.items() if k != "version"}
    kh_b = {k: v for k, v in b.attrib.items() if k != "version"}
    for k in sorted(set(kh_a) | set(kh_b)):
        va, vb = kh_a.get(k), kh_b.get(k)
        if va != vb:
            print(f"  {duong}/{a.tag}.{k}:  ta={va!r}   song={vb!r}")
    ca = [c for c in a if c.tag != "metadata"]
    cb = [c for c in b if c.tag != "metadata"]
    if len(ca) != len(cb):
        print(f"  {duong}/{a.tag}: so phan tu con khac — "
              f"ta={len(ca)} song={len(cb)}")
        ten_a = [c.tag for c in ca]
        ten_b = [c.tag for c in cb]
        for t in sorted(set(ten_a) | set(ten_b)):
            na, nb = ten_a.count(t), ten_b.count(t)
            if na != nb:
                print(f"      {t}: ta={na} song={nb}")
    for i, (x, y) in enumerate(zip(ca, cb)):
        duyet(x, y, f"{duong}/{a.tag}[{i}]")


print(f"=== {TEN}: cau hinh cua ta  so voi  bang tren song ===")
A, B = _strip_version(ta[TEN]), _strip_version(song[TEN])
if T.canon(A) == T.canon(B):
    print("  khong lech gi (bo qua version)")
else:
    duyet(A, B)
print()
print(f"  version — ta: {ta[TEN].get('version')}   song: {song[TEN].get('version')}")

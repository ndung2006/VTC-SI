"""``vtccmp`` — bộ so sánh, tiến trình riêng.

**Nó quan sát, không điều khiển.** Không có quyền dừng hay chặn tiến trình phát
nào; giết nó thì hai nguồn vẫn chạy bình thường, chỉ mất khả năng phát hiện
lệch (§3.4 của ``spec.md``). Cài đặt được trên máy thứ ba.

Ba lệnh:

* ``compare`` — so nhiều nguồn với nhau và với cấu hình.
* ``patch``   — soạn bản vá đưa cấu hình về khớp sóng (FR-43).
* ``capture`` — in dòng lệnh ``tstables`` để thu một luồng.

``patch`` là lệnh trả giá nhiều nhất cho công viết: ở giai đoạn chuyển tiếp,
mỗi thay đổi phải áp hai nơi — git và Barrowa — và lệnh này bỏ đi phần chép
tay, chỉ còn phần xem rồi đồng ý.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from vtcsi.config import loader
from vtcsi.model import diff as D
from vtcsi.model import plain
from vtcsi.tables import tsduck as T
from vtcsi.version import preflight

# ------------------------------------------------------------------- thu luong

#: Tuỳ chọn ``tstables`` mà ta dùng; ``--all-sections`` là bài học từ RO-20.
CAPTURE_OPTIONS = ["--ip-udp", "--xml-output", "--all-sections", "--pid"]


def capture_command(
    *,
    source: str,
    out: str,
    pids: tuple[int, ...] = (16, 17, 18),
    seconds: int | None = 120,
    all_sections: bool = True,
) -> list[str]:
    """Dòng lệnh thu một luồng thành XML.

    ``--all-sections`` mặc định **bật**: không có nó, ``tstables`` chỉ xuất
    bảng hoàn chỉnh, và EIT schedule — chiếm 87 % tải SI — biến mất khỏi bản
    thu mà không báo gì. Đó đúng là cái bẫy đã làm tôi kết luận nhầm một lần.
    """
    cmd = ["tstables", "--ip-udp", source, "--xml-output", out]
    for pid in pids:
        cmd += ["--pid", str(pid)]
    if all_sections:
        cmd += ["--all-sections"]
    if seconds:
        cmd += ["--duration", str(seconds)]
    return cmd


# ---------------------------------------------------------------------- lệnh

def _read(path: str):
    return T.read_dump(Path(path).read_text(encoding="utf-8"))


def cmd_compare(args) -> int:
    sources = {Path(p).stem: _read(p) for p in args.dumps}
    names = list(sources)

    worst = 0
    if args.config:
        cfg = loader.load(Path(args.config))
        for name in names:
            report = preflight.check(cfg, sources[name])
            print(f"== cau hinh vs {name}")
            print(report.text())
            worst = max(worst, 0 if report.ok else 2)
            print()

    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            deltas = D.diff(plain.to_plain(sources[a]), plain.to_plain(sources[b]))
            print(f"== {a} vs {b}: {D.summarise(deltas)}")
            if deltas:
                print(D.render(deltas))
                worst = max(worst, 1)
            print()
    return worst


def cmd_patch(args) -> int:
    cfg = loader.load(Path(args.config))
    air = _read(args.dump)
    mine, theirs = plain.to_plain(cfg), plain.to_plain(air)
    deltas = D.diff(mine, theirs)

    if not deltas:
        print("cau hinh da khop song, khong can va gi.")
        return 0

    print(f"{D.summarise(deltas)} — de dua cau hinh ve khop song:")
    print(D.render(deltas))

    if not args.apply:
        print("\nChay lai voi --apply de ghi. Nho xem lai truoc khi commit: "
              "song co the dang sai, khong phai cau hinh.")
        return 1

    written = loader.save(plain.from_plain(theirs), Path(args.config))
    print(f"\nda ghi {len(written)} file. Xem `git diff` roi commit.")
    return 0


def cmd_capture(args) -> int:
    cmd = capture_command(source=args.source, out=args.out, seconds=args.duration)
    print(" ".join(cmd))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="vtccmp", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("compare", help="so nhieu ban dump voi nhau va voi cau hinh")
    s.add_argument("dumps", nargs="+")
    s.add_argument("--config", default=None)
    s.set_defaults(fn=cmd_compare)

    s = sub.add_parser("patch", help="soan ban va dua cau hinh ve khop song")
    s.add_argument("dump")
    s.add_argument("--config", default="config")
    s.add_argument("--apply", action="store_true")
    s.set_defaults(fn=cmd_patch)

    s = sub.add_parser("capture", help="in dong lenh tstables de thu mot luong")
    s.add_argument("source", help="vi du udp://236.30.230.1:6000")
    s.add_argument("--out", default="capture.xml")
    s.add_argument("--duration", type=int, default=120)
    s.set_defaults(fn=cmd_capture)

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except (plain.ConfigError, T.TsduckError, yaml.YAMLError) as exc:
        print("loi:", exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Dòng lệnh ``vtcsi``.

Hiện có bảy lệnh, đủ cho giai đoạn T2 và T4:

* ``seed``     — gieo cấu hình từ một bản dump ``tstables``. Chạy một lần.
* ``validate`` — đọc cấu hình và kiểm tra, không phát gì.
* ``build``    — sinh XML bảng cho TSDuck.
* ``diff``      — so cấu hình với một bản dump từ sóng.
* ``preflight`` — kiểm tra version và nội dung trước khi đấu vào mux.
* ``epg``       — hộp thư file lịch thành XML EIT cho ``eitinject``.
* ``web``       — giao diện nhập liệu, ghi thẳng vào cùng thư mục cấu hình.

``seed`` là lệnh đặc biệt: nó chỉ dùng **một lần** lúc dựng hệ. Sau đó cấu
hình trong git là nguồn sự thật, còn bản dump chỉ còn để đối chiếu. Xem §3
của ``spec.md`` về vì sao gieo một lần khác soi liên tục.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

from vtcsi.config import loader
from vtcsi.epg import store
from vtcsi.epg.transform import window
from vtcsi.tables import eit
from vtcsi.model.entities import Config
from vtcsi.model.plain import ConfigError
from vtcsi.tables import tsduck as T
from vtcsi.version import preflight


def _indent(el: ET.Element) -> str:
    ET.indent(el, space="  ")
    return ET.tostring(el, encoding="unicode")


def _tables(cfg: Config) -> list[tuple[str, ET.Element]]:
    """Mọi bảng cấu trúc, theo thứ tự tất định."""
    out = [("nit", T.write_nit(cfg.network))]
    out += [(f"sdt-ts{s.ts_id}", T.write_sdt(s)) for s in cfg.sdts]
    out += [(f"bat-{b.bouquet_id:04x}", T.write_bat(b)) for b in cfg.bouquets]
    return out


def _summary(cfg: Config) -> str:
    services = sum(len(s.services) for s in cfg.sdts)
    lcn = sum(len(t.lcn) for b in cfg.bouquets for t in b.ts_loops)
    return (
        f"mang {cfg.network.network_id} '{cfg.network.name}' v{cfg.network.version} · "
        f"{len(cfg.network.ts_loops)} TS · {services} dich vu · "
        f"{len(cfg.bouquets)} bouquet · {lcn} LCN"
    )


# ------------------------------------------------------------------- lệnh

def cmd_seed(args) -> int:
    cfg = T.read_dump(Path(args.dump).read_text(encoding="utf-8"))
    root = Path(args.config)
    if root.exists() and any(root.iterdir()) and not args.force:
        print(f"loi: {root} da co noi dung. Dung --force neu that su muon ghi de.",
              file=sys.stderr)
        return 2
    written = loader.save(cfg, root)
    print(_summary(cfg))
    for p in written:
        print("  ghi", p)
    print(f"\n{len(written)} file. Gio cau hinh trong git la nguon su that, "
          f"khong phai ban dump.")
    return 0


def cmd_validate(args) -> int:
    cfg = loader.load(Path(args.config))
    print("cau hinh hop le:", _summary(cfg))
    return 0


def cmd_build(args) -> int:
    cfg = loader.load(Path(args.config))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, el in _tables(cfg):
        path = out / f"{name}.xml"
        path.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<tsduck>\n'
                        + _indent(el) + "</tsduck>\n", encoding="utf-8")
        print("  ghi", path)
    return 0


def cmd_diff(args) -> int:
    cfg = loader.load(Path(args.config))
    air = T.read_dump(Path(args.dump).read_text(encoding="utf-8"))

    mine = {n: T.canon(el) for n, el in _tables(cfg)}
    theirs = {n: T.canon(el) for n, el in _tables(air)}

    bad = 0
    for name in sorted(set(mine) | set(theirs)):
        if name not in mine:
            print(f"  THIEU trong cau hinh : {name}")
            bad += 1
        elif name not in theirs:
            print(f"  THIEU tren song      : {name}")
            bad += 1
        elif mine[name] != theirs[name]:
            print(f"  LECH                 : {name}")
            bad += 1

    total = len(set(mine) | set(theirs))
    if bad:
        print(f"\n{bad}/{total} bang lech.")
        return 1
    print(f"{total}/{total} bang khop. Cau hinh tai tao dung thu dang tren song.")
    return 0


def cmd_epg(args) -> int:
    """Hộp thư file lịch thành XML EIT cho ``eitinject``.

    Đây là **ranh giới duy nhất** mà đồng hồ được phép gọi: lõi nhận
    ``now_utc`` như tham số, xem luật code số 2.
    """
    now = (datetime.fromisoformat(args.now).astimezone(timezone.utc)
           if args.now else datetime.now(timezone.utc))

    result = store.build(Path(args.inbox), now, depth_hours=args.depth)
    tables = eit.write_all(
        result.events,
        ts_id=result.ts_id,
        original_network_id=result.original_network_id,
        table_type=eit.TABLE_SCHEDULE,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                   + _indent(eit.to_document(tables)), encoding="utf-8")

    thin = window.services_below(result.events, now, hours=args.alarm_below)
    print(f"moc thoi gian : {now.isoformat()}")
    print(f"doc           : {len(result.files)} file")
    print(f"su kien       : {len(result.events)} tren {len(result.services)} dich vu")
    print(f"ghi           : {out}  ({len(tables)} bang EIT)")
    if result.rejected:
        print(f"\nLOAI RA {len(result.rejected)} su kien vuot tran duration "
              f"{window.MAX_EVENT_DURATION} (xem RO-22):")
        for e in result.rejected[:5]:
            print(f"   dich vu {e.service_id}  {e.start_utc:%Y-%m-%d %H:%M}  "
                  f"{e.duration}  {e.name[:40]!r}")
    if thin:
        print(f"\nCANH BAO: {len(thin)} dich vu con lich duoi {args.alarm_below} gio:")
        print("   " + ", ".join(str(s) for s in thin[:20]))
    return 0


def cmd_preflight(args) -> int:
    cfg = loader.load(Path(args.config))
    report = preflight.check_against_dump(
        cfg, Path(args.dump).read_text(encoding="utf-8"))
    print(report.text())
    return 0 if report.ok else 1


def cmd_web(args) -> int:
    """Mở giao diện nhập liệu.

    Nạp cấu hình một lần trước khi mở cổng: thà báo lỗi ở terminal còn hơn để
    mọi trang trả về 500. Sau đó mỗi lượt truy cập tự đọc lại file, nên sửa
    YAML bằng tay ở cửa sổ khác vẫn thấy ngay — không có bộ nhớ đệm nào để mà
    lệch pha.
    """
    try:
        import uvicorn
    except ImportError:
        print("chua cai giao dien: pip install 'fastapi' 'uvicorn[standard]' "
              "'jinja2' 'python-multipart'", file=sys.stderr)
        return 2

    from vtcsi.web.app import create_app

    config_dir = Path(args.config).resolve()
    cfg = loader.load(config_dir)
    print(_summary(cfg))
    print(f"\ngiao dien:  http://{args.host}:{args.port}/")
    print(f"ghi vao  :  {config_dir}")
    print("Ctrl-C de dung.\n")

    app = create_app(config_dir, Path(args.repo or config_dir.parent).resolve())
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="vtcsi", description=__doc__.splitlines()[0])
    p.add_argument("--config", default="config", help="thu muc cau hinh")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("seed", help="gieo cau hinh tu ban dump tstables")
    s.add_argument("dump")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_seed)

    s = sub.add_parser("validate", help="doc va kiem tra cau hinh")
    s.set_defaults(fn=cmd_validate)

    s = sub.add_parser("build", help="sinh XML bang cho TSDuck")
    s.add_argument("--out", default="build")
    s.set_defaults(fn=cmd_build)

    s = sub.add_parser("epg", help="hop thu file lich thanh XML EIT")
    s.add_argument("--inbox", default="epg/inbox")
    s.add_argument("--out", default="build/eit.xml")
    s.add_argument("--now", help="moc thoi gian ISO; mac dinh la bay gio")
    s.add_argument("--depth", type=int, default=window.WINDOW_HOURS)
    s.add_argument("--alarm-below", type=int, default=120)
    s.set_defaults(fn=cmd_epg)

    s = sub.add_parser("preflight", help="kiem tra cau hinh truoc khi dau vao mux")
    s.add_argument("dump")
    s.set_defaults(fn=cmd_preflight)

    s = sub.add_parser("web", help="giao dien nhap lieu")
    s.add_argument("--host", default="127.0.0.1",
                   help="0.0.0.0 de may khac trong mang truy cap duoc")
    s.add_argument("--port", type=int, default=8080)
    s.add_argument("--repo", help="goc kho git; mac dinh la thu muc cha cua --config")
    s.set_defaults(fn=cmd_web)

    s = sub.add_parser("diff", help="so cau hinh voi mot ban dump tu song")
    s.add_argument("dump")
    s.set_defaults(fn=cmd_diff)

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except (ConfigError, T.TsduckError, store.StoreError, eit.EitError) as exc:
        print("loi:", exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

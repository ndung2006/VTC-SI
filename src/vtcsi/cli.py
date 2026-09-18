"""Dòng lệnh ``vtcsi``.

Hiện có mười lệnh, đủ cho giai đoạn T2 và T4:

* ``seed``     — gieo cấu hình từ một bản dump ``tstables``. Chạy một lần.
* ``validate`` — đọc cấu hình và kiểm tra, không phát gì.
* ``build``    — sinh XML bảng cho TSDuck.
* ``diff``      — so cấu hình với một bản dump từ sóng.
* ``preflight`` — kiểm tra version và nội dung trước khi đấu vào mux.
* ``epg``       — hộp thư file lịch thành XML EIT cho ``eitinject``.
* ``web``       — giao diện nhập liệu, ghi thẳng vào cùng thư mục cấu hình.
* ``refresh``   — sinh lại bảng **và** EIT trong một lượt.
* ``run``       — dựng ``tsp`` và trông chừng nó. Đây là lệnh chạy thật.
* ``passwd``    — đặt hoặc đổi mật khẩu của giao diện.

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

from vtcsi.config import git, loader
from vtcsi.epg import store
from vtcsi.epg.transform import window
from vtcsi.pipeline import tspbuild
from vtcsi.tables import eit
from vtcsi.model.entities import Config
from vtcsi.model.plain import ConfigError
from vtcsi.tables import tsduck as T
from vtcsi.version import preflight


def _write(path: Path, text: str) -> None:
    """Ghi van ban voi ket thuc dong LF tren moi he dieu hanh.

    Cung ly do nhu ``config.loader._dump``: XML sinh ra phai giong het
    nhau tren Windows va Linux thi phep so hash giua hai nguon moi co
    nghia (AC-12).
    """
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


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
        _write(path, '<?xml version="1.0" encoding="UTF-8"?>\n<tsduck>\n'
                      + _indent(el) + "</tsduck>\n")
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

    # Doc cau hinh TRUOC khi dung cua so.
    #
    # Bang doi so dich vu (`epg_source_id`) phai co mat tu buoc dau, vi
    # `window.build` doi so truoc khi gop — xem `window.remap`.
    cfg = None
    try:
        cfg = loader.load(Path(args.config))
    except ConfigError as exc:
        print(f"khong doc duoc cau hinh ({exc}) — sinh EIT cho moi dich vu",
              file=sys.stderr)

    anh_xa = {x.epg_source_id: x.service_id
              for s_ in (cfg.sdts if cfg else ()) for x in s_.services
              if x.epg_source_id is not None} or None

    result = store.build(Path(args.inbox), now, depth_hours=args.depth,
                         mapping=anh_xa)

    # Ton trong cong tac EPG trong SDT.
    #
    # `EIT_schedule_flag` chi la LOI KHAI; dau thu van hien EIT neu bang do co
    # tren song. Nen tat EPG mot kenh that su nghia la **khong sinh bang** cho
    # no — khai mot dang phat mot neo la kieu sai kho tim nhat.
    events = result.events
    tat = ()
    cho_phep = None
    if cfg is not None:
        cho_phep = {x.service_id for s_ in cfg.sdts for x in s_.services
                    if x.eit_schedule}
        events, tat = window.only_services(events, cho_phep)

    tables = eit.write_all(
        events,
        ts_id=result.ts_id,
        original_network_id=result.original_network_id,
        table_type=eit.TABLE_SCHEDULE,
    )
    # Khong co bang nao thi KHONG ghi de.
    #
    # Ghi mot EIT rong len file cu la cach chac chan nhat de xoa sach EPG cua
    # ca mang bang mot lenh chay dinh ky. Nguyen nhan thuong gap nhat lai rat
    # tam thuong: hop thu chi con lich cu. Giu file cu — lich hom qua con hon
    # khong co lich nao — va bao that to.
    out = Path(args.out)
    if not tables:
        print(f"moc thoi gian : {now.isoformat()}")
        print(f"doc           : {len(result.files)} file")
        print(f"su kien       : 0")
        if tat:
            print(f"tat EPG       : {len(tat)} dich vu bi TAT trong SDT")
        print()
        # Hop thu rong da bi `store.build` chan tu truoc va thoat voi ma 2,
        # nen toi day chac chan la co file ma khong su kien nao dung cua so.
        print("KHONG SINH DUOC BANG EIT NAO.")
        print(f"  Doc duoc {len(result.files)} file nhung khong su kien nao "
              f"roi vao cua so {args.depth} gio ke tu bay gio.")
        print("  Gan nhu chac chan la hop thu chi con lich cu. "
              "Nap file lich moi vao " + str(args.inbox) + ".")
        if not out.exists():
            return 1

        # Giu file cu, NHUNG van go nhung kenh vua bi tat.
        #
        # Cong tac EPG la de tat nhanh khi co su co. Neu luc do hop thu chi con
        # lich cu thi khong sinh lai duoc — va "giu nguyen file cu" nghia la
        # kenh do VAN co chuong trinh tren dau thu. Cong tac khong lam duoc viec
        # cua no dung luc can nhat.
        #
        # Go bang khoi tai lieu cu thi lam duoc ca khi khong co du lieu moi: ta
        # khong can biet chuong trinh nao dang chay, chi can biet kenh nao phai im.
        if cho_phep is None:
            print(f"  KHONG ghi de {out} — giu nguyen ban cu de con EPG ma phat.")
            return 1
        try:
            cu = ET.fromstring(out.read_text(encoding="utf-8"))
        except ET.ParseError as exc:
            print(f"  KHONG doc duoc {out} ({exc}) — giu nguyen.", file=sys.stderr)
            return 1
        moi, da_go = eit.drop_services(cu, cho_phep)
        if not da_go:
            print(f"  KHONG ghi de {out} — giu nguyen ban cu de con EPG ma phat.")
            return 1
        _write(out, '<?xml version="1.0" encoding="UTF-8"?>' + chr(10) + _indent(moi))
        print(f"  Giu ban EIT cu NHUNG da go {len(da_go)} kenh vua tat: "
              + ", ".join(str(x) for x in da_go[:20]))
        print(f"  Con {len(list(moi))} bang trong {out}.")
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    _write(out, '<?xml version="1.0" encoding="UTF-8"?>\n'
                 + _indent(eit.to_document(tables)))

    thin = window.services_below(events, now, hours=args.alarm_below)
    print(f"moc thoi gian : {now.isoformat()}")
    print(f"doc           : {len(result.files)} file")
    print(f"su kien       : {len(events)} tren "
          f"{len({e.service_id for e in events})} dich vu")
    if tat:
        print(f"tat EPG       : {len(tat)} dich vu bi TAT trong SDT — "
              + ", ".join(str(x) for x in tat[:20])
              + ("…" if len(tat) > 20 else ""))
    print(f"ghi           : {out}  ({len(tables)} bang EIT)")
    if result.rejected:
        print(f"\nLOAI RA {len(result.rejected)} su kien vuot tran duration "
              f"{window.MAX_EVENT_DURATION} (xem RO-22):")
        for e in result.rejected[:5]:
            print(f"   dich vu {e.service_id}  {e.start_utc:%Y-%m-%d %H:%M}  "
                  f"{e.duration}  {e.name[:40]!r}")
    if result.suspect:
        # Bao ra, KHONG tu vut. Xem `window.far_future`.
        #
        # Canh bao nay noi ve phan lich NGOAI cua so, nen no im lang trong
        # nhieu ngay roi bong keu — dung hom phan rac do sap lot vao cua so.
        # Do la chu y: keu som thi nguoi truc con kip bao ben cap lich.
        theo_kenh: dict[int, int] = {}
        for e in result.suspect:
            theo_kenh[e.service_id] = theo_kenh.get(e.service_id, 0) + 1
        dau = min(e.start_utc for e in result.suspect)
        print(f"\nCANH BAO: {len(result.suspect)} su kien nam SAU mot khoang "
              f"trong dai trong lich, som nhat {dau:%Y-%m-%d %H:%M} UTC.")
        print("   theo dich vu: "
              + ", ".join(f"{k}={v}" for k, v in sorted(theo_kenh.items())))
        print("   Gan nhu chac chan la loi nhap lieu ben cap lich. Chung CHUA "
              "len song vi nam ngoai cua so,")
        print(f"   nhung se lot vao khi ngay do con cach hien tai duoi "
              f"{args.depth} gio. Bao ben cap lich truoc do.")
    if thin:
        # Nguong phai dat DUOI do sau thuc te dang co. Neu khong, canh bao keu
        # cho moi kenh, moi gio, mai mai — va mot canh bao luon keu la mot
        # canh bao da bi tat. Cung bai hoc da rut FR-54.
        print(f"\nCANH BAO: {len(thin)} dich vu con lich duoi {args.alarm_below} gio:")
        print("   " + ", ".join(str(s) for s in thin[:20]))
    return 0


def cmd_preflight(args) -> int:
    cfg = loader.load(Path(args.config))
    report = preflight.check_against_dump(
        cfg, Path(args.dump).read_text(encoding="utf-8"))
    print(report.text())
    return 0 if report.ok else 1


def cmd_refresh(args) -> int:
    """Sinh lại bảng và EIT trong một lượt.

    Tách thành lệnh riêng thay vì để ``run`` gọi hai lệnh con, vì ``run`` chỉ
    cần biết **một** dòng lệnh để chạy định kỳ. Dùng tay cũng tiện: đây đúng
    là hai việc luôn phải làm cùng nhau sau khi sửa cấu hình.

    EIT hỏng **không** làm hỏng cả lượt: bảng cấu trúc đã ghi xong vẫn ở lại
    trên đĩa và ``tsp`` vẫn phát chúng. Mất EPG khó chịu; mất NIT là mất kênh.
    """
    rc = cmd_build(args)
    if rc:
        return rc
    if not Path(args.inbox).is_dir():
        print(f"bo qua EIT: khong co hop thu {args.inbox}")
        return 0
    # cmd_build va cmd_epg cung doc `args.out` nhung ghi vao hai cho khac nhau.
    args.out = args.out_eit
    try:
        cmd_epg(args)
    except (store.StoreError, eit.EitError) as exc:
        print("EIT that bai:", exc, file=sys.stderr)
    # Ma thoat cua `refresh` bam theo BANG CAU TRUC, khong bam theo EIT.
    # `run` goi lenh nay moi gio; de EIT rong lam ca luot do thanh that bai thi
    # log se day bao dong trong khi NIT/SDT/BAT van dang phat dung.
    return 0


def cmd_run(args) -> int:
    """Dựng ``tsp`` và trông chừng. Đây là lệnh chạy thật, chạy mãi."""
    from vtcsi.config import output as config_output
    from vtcsi.model import output as model_output
    from vtcsi.model.output import OutputError
    from vtcsi.pipeline import supervise
    from vtcsi.pipeline.tspbuild import plan_from_config

    cfg = loader.load(Path(args.config))
    actual = [s for s in cfg.sdts if s.actual]
    if len(actual) != 1:
        print(f"loi: can dung mot SDT actual, dang co {len(actual)}", file=sys.stderr)
        return 2

    # Dia chi dau ra: file truoc, co tham so thi tham so de len tren.
    #
    # Thu tu nay khong tuy tien. File la thu nguoi van hanh dat mot lan qua
    # giao dien roi quen di; tham so la thu ai do vua go **ngay bay gio**, va
    # thu vua go thi bao gio cung y hon thu da quen. Nho vay `--to` van dung
    # de thu mot dich khac trong mot lan chay, ma khong dong vao file.
    try:
        ra = config_output.load(Path(args.config))
    except OutputError as exc:
        print(f"loi: {exc}", file=sys.stderr)
        return 2

    dich = args.to or (model_output.format_endpoint(ra.primary)
                       if not ra.primary.empty else "")
    if not dich:
        print("loi: chua co dia chi dau ra.\n"
              f"  dat trong giao dien o trang Dau ra, hoac ghi {args.config}/"
              f"{config_output.FILE}, hoac truyen --to",
              file=sys.stderr)
        return 2

    card = args.local_address or ra.primary.interface or None
    sao = (model_output.format_endpoint(ra.mirror)
           if ra.mirror is not None and not ra.mirror.empty else None)
    sao_card = (ra.mirror.interface or None) if ra.mirror is not None else None
    # `--to` chi doi duong CHINH. Giu duong sao chep theo file thi se bat mot
    # ban sao cua dong thu nghiem ra dung nhom multicast dang phat that.
    if args.to:
        sao = sao_card = None
    ttl = args.ttl if args.ttl is not None else ra.ttl

    # Toc do va nhip lap. Thieu file thi dung mac dinh — bo so dang chay tren
    # song — nen mot he chua tung mo trang do van phat y nhu truoc.
    from vtcsi.config import toc_do as config_toc_do
    from vtcsi.model.toc_do import TocDoError
    try:
        td = config_toc_do.load(Path(args.config))
    except TocDoError as exc:
        print(f"loi: {exc}", file=sys.stderr)
        return 2

    plan = plan_from_config(
        repetition_ms=td.repetition_ms(),
        bitrates={"bitrate_nit": td.bitrate_nit,
                  "bitrate_sdt_bat": td.bitrate_sdt_bat,
                  "bitrate_eit": td.bitrate_eit,
                  "total_bitrate": td.tong,
                  "eit_poll_ms": td.eit_poll_ms},
        build_dir=args.build,
        eit_dir=args.eit_dir,
        ts_id=actual[0].ts_id,
        other_ts_ids=tuple(sorted(s.ts_id for s in cfg.sdts if not s.actual)),
        bouquet_ids=tuple(sorted(q.bouquet_id for q in cfg.bouquets)),
        destination=dich,
        local_address=card,
        mirror=sao,
        mirror_local_address=sao_card,
        ttl=ttl,
    )

    if args.dry_run:
        print(_summary(cfg))
        print()
        print(tspbuild.shell(tspbuild.build(
            plan, start_time=datetime.now(timezone.utc))))
        gap = supervise.missing_inputs(plan, lambda q: Path(q).exists())
        if gap:
            print()
            print("THIEU: " + ", ".join(gap))
            print("chay `vtcsi refresh` truoc.")
            return 1
        return 0

    refresh: tuple[str, ...] = ()
    if not args.no_refresh:
        refresh = (sys.executable, "-m", "vtcsi.cli",
                   "--config", str(args.config), "refresh",
                   "--out", args.build, "--inbox", args.inbox,
                   "--eit-out", str(Path(args.eit_dir) / "eit.xml"),
                   "--alarm-below", str(args.alarm_below))

    print(_summary(cfg))
    sup = supervise.Supervisor(
        plan=plan, refresh=refresh, refresh_every=args.refresh_every,
        # Theo doi ca hop thu lich lan thu muc cau hinh: file moi ve hoac ai do
        # sua YAML bang tay deu phai len song ngay, khong cho het gio.
        watch=(Path(args.inbox), Path(args.config)),
        watch_every=args.watch_every)
    return sup.run()


def cmd_passwd(args) -> int:
    """Đặt hoặc đổi mật khẩu của giao diện.

    Chỉ đặt được từ terminal, không có đường tương đương trên web. Lý do đầy
    đủ ở ``vtcsi.web.auth``; tóm tắt: người có quyền shell trên máy phát mới
    là chủ hợp pháp, và đó là ranh giới sẵn có nên dùng lại.
    """
    import getpass

    from vtcsi.web import auth

    root = Path(args.repo or Path(args.config).resolve().parent).resolve()
    where = Path(args.auth_file) if args.auth_file else auth.path_for(root)

    try:
        dang_co = auth.load(where)
    except auth.AuthError as exc:
        if not args.force:
            print("loi:", exc, file=sys.stderr)
            print("chay lai voi --force de ghi de file hong.", file=sys.stderr)
            return 2
        dang_co = None

    def hoi(nhac: str) -> str:
        try:
            return getpass.getpass(nhac)
        except (EOFError, KeyboardInterrupt):
            print()
            raise SystemExit(1)

    if dang_co is not None and not args.force:
        print(f"dang co tai khoan '{dang_co.user}' tai {where}")
        cu = hoi("Mat khau hien tai: ")
        moi = hoi("Mat khau moi     : ")
        lai = hoi("Go lai           : ")
        if moi != lai:
            print("loi: hai lan go khong giong nhau", file=sys.stderr)
            return 2
        try:
            auth.save(where, auth.change(dang_co, cu, moi))
        except auth.AuthError as exc:
            print("loi:", exc, file=sys.stderr)
            return 2
        print("da doi mat khau. Moi phien dang mo deu bi dang xuat.")
        return 0

    if dang_co is not None:
        print(f"--force: ghi de tai khoan '{dang_co.user}' tai {where}")
    goi_y = auth.DEFAULT_USER
    user = (args.user or input(f"Ten dang nhap [{goi_y}]: ")).strip() or goi_y
    moi = hoi("Mat khau   : ")
    lai = hoi("Go lai     : ")
    if moi != lai:
        print("loi: hai lan go khong giong nhau", file=sys.stderr)
        return 2
    try:
        auth.save(where, auth.make(user, moi))
    except auth.AuthError as exc:
        print("loi:", exc, file=sys.stderr)
        return 2

    print(f"da ghi {where}")
    if git.status(root).is_repo:
        ngoai = git.is_ignored(root, where)
        if ngoai is False:
            print(file=sys.stderr)
            print("CANH BAO: file nay DANG nam trong tam cua git.", file=sys.stderr)
            print(f"  Them '{where.name}' vao .gitignore truoc khi commit —",
                  file=sys.stderr)
            print("  bam mat khau vao git la nam trong lich su MAI MAI.",
                  file=sys.stderr)
            return 1
    return 0


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

    root = Path(args.repo or config_dir.parent).resolve()
    if args.no_auth:
        print("CANH BAO: --no-auth — ai mo duoc cong nay la sua duoc cau hinh",
              file=sys.stderr)
        print("          dang phat song. Chi dung khi chay thu tren may minh.",
              file=sys.stderr)
    app = create_app(config_dir, root,
                     auth_file=Path(args.auth_file) if args.auth_file else None,
                     require_login=not args.no_auth,
                     build_dir=Path(args.build), eit_dir=Path(args.eit_dir),
                     inbox=Path(args.inbox))
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

    s = sub.add_parser("refresh", help="sinh lai bang va EIT trong mot luot")
    s.add_argument("--out", default="build")
    s.add_argument("--inbox", default="epg/inbox")
    s.add_argument("--eit-out", dest="out_eit", default="build/eit/eit.xml")
    s.add_argument("--now", help="moc thoi gian ISO; mac dinh la bay gio")
    s.add_argument("--depth", type=int, default=window.WINDOW_HOURS)
    s.add_argument("--alarm-below", type=int, default=120)
    s.set_defaults(fn=cmd_refresh)

    s = sub.add_parser("run", help="dung tsp va trong chung — chay that")
    s.add_argument("--to", metavar="DIA-CHI:CONG",
                   help="dich multicast, vi du 236.30.239.1:6000. Mac dinh lay "
                        "tu config/dau-ra.yaml (trang Dau ra cua giao dien). "
                        "Dat o day thi TAT duong sao chep — dung de thu mot dich "
                        "khac ma khong dong vao file")
    s.add_argument("--local-address", help="card mang phat ra; may nhieu card thi bat buoc")
    s.add_argument("--ttl", type=int, default=None,
                   help="mac dinh he dieu hanh la 1, chet ngay tai switch dau tien; "
                        "de trong thi lay theo config/dau-ra.yaml")
    s.add_argument("--build", default="build", help="thu muc bang XML")
    s.add_argument("--eit-dir", default="build/eit", help="thu muc XML EIT")
    s.add_argument("--inbox", default="epg/inbox", help="hop thu file lich")
    s.add_argument("--watch-every", type=float, default=5.0,
                   help="giay giua hai lan ngo hop thu lich va thu muc cau hinh; "
                        "co gi doi la sinh lai NGAY")
    s.add_argument("--refresh-every", type=float, default=3600.0,
                   help="luoi an toan: sinh lai dinh ky du khong co gi doi, vi "
                        "cua so EIT troi theo thoi gian")
    s.add_argument("--alarm-below", type=int, default=120,
                   help="keu khi lich mot kenh mong hon ngan nay gio; dat thap "
                        "hon do sau thuc te, neu khong no keu mai va se bi ngo lo")
    s.add_argument("--no-refresh", action="store_true",
                   help="khong tu sinh lai; cua so EIT se can dan")
    s.add_argument("--dry-run", action="store_true",
                   help="in dong lenh roi thoat, khong phat gi")
    s.set_defaults(fn=cmd_run)

    s = sub.add_parser("web", help="giao dien nhap lieu")
    s.add_argument("--host", default="127.0.0.1",
                   help="0.0.0.0 de may khac trong mang truy cap duoc")
    s.add_argument("--port", type=int, default=8080)
    s.add_argument("--repo", help="goc kho git; mac dinh la thu muc cha cua --config")
    s.add_argument("--auth-file", help="file dang nhap; mac dinh <repo>/.vtcsi-auth.json")
    s.add_argument("--no-auth", action="store_true",
                   help="TAT dang nhap — chi de chay thu tren may minh")
    s.add_argument("--build", default="build",
                   help="thu muc bang XML — phai TRUNG voi cua `vtcsi run`")
    s.add_argument("--eit-dir", default="build/eit", help="thu muc XML EIT")
    s.add_argument("--inbox", default="epg/inbox", help="hop thu file lich")
    s.set_defaults(fn=cmd_web)

    s = sub.add_parser("passwd", help="dat hoac doi mat khau cua giao dien")
    s.add_argument("--user", help="ten dang nhap; mac dinh la admin")
    s.add_argument("--repo", help="goc kho git; mac dinh la thu muc cha cua --config")
    s.add_argument("--auth-file", help="file dang nhap; mac dinh <repo>/.vtcsi-auth.json")
    s.add_argument("--force", action="store_true",
                   help="ghi de tai khoan dang co, khong hoi mat khau cu")
    s.set_defaults(fn=cmd_passwd)

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

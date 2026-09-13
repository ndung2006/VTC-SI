"""Giao diện nhập liệu — FR-34…41.

Server-rendered, không phải SPA. Mỗi thao tác là một lượt POST rồi chuyển
hướng, nên bấm F5 không gửi lại biểu mẫu và nút Back luôn hoạt động.

**Giao diện ghi thẳng vào chính các file YAML trong git**, không giữ một kho dữ
liệu song song. Nó là một cách sinh commit dễ hơn gõ tay, không phải một nguồn
sự thật thứ hai. Vì vậy mọi thứ sửa ở đây đều xem được bằng ``git diff`` và
quay lui được bằng ``git revert`` — điều mà giao diện của Barrowa không cho.

Hai chỗ cố tình làm cho khó, vì chúng nguy hiểm:

* **Tăng version** là thao tác riêng, có xác nhận, nói rõ hệ quả là cả mạng dò
  lại kênh. Không gộp vào nút lưu.
* **Xoá kênh** đòi gõ lại đúng tên kênh. Xoá nhầm một dịch vụ nghĩa là nó biến
  mất khỏi đầu thu sau lần dò kế tiếp.
"""

from __future__ import annotations

from pathlib import Path

import time

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from vtcsi.config import git, loader
from vtcsi.config import output as CO
from vtcsi.web import auth as A
from vtcsi.model import lcn as L
from vtcsi.model import output as OUT
from vtcsi.model import linkage as K
from vtcsi.model import topology as TOPO
from vtcsi.model import version as V
from vtcsi.version import autobump
from vtcsi.model.entities import (
    Config,
    Linkage,
    epg_mismatch,
    epg_on,
    set_epg,
    RunningStatus,
    Service,
    ServiceRef,
    ServiceType,
)
from vtcsi.model.plain import ConfigError

BASE = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE / "templates"))


def create_app(config_dir: Path, repo_root: Path | None = None, *,
               auth_file: Path | None = None, require_login: bool = True,
               build_dir: Path | None = None, eit_dir: Path | None = None,
               inbox: Path | None = None) -> FastAPI:
    """Dựng ứng dụng.

    ``require_login=False`` **chỉ** dành cho test và cho việc chạy thử trên máy
    của mình. Nó không phải một lựa chọn vận hành: giao diện này sửa được cấu
    hình đang phát sóng, nên mở toang nó là mở toang cả mạng.
    """
    # Tat ca ba tuyen duong tu dong cua FastAPI: `/docs`, `/redoc` va
    # `/openapi.json`. Tat hai cai dau ma de cai thu ba la van phoi nguyen so
    # do API ra ngoai, chi khac la kho doc hon — mot kieu "tat" khong that.
    app = FastAPI(title="vtcsi", docs_url=None, redoc_url=None, openapi_url=None)
    root = repo_root or config_dir.parent
    where = auth_file or A.path_for(root)
    gate = A.Gate()
    build = build_dir or (root / "build")
    eit_out = (eit_dir or (build / "eit")) / "eit.xml"
    hop_thu = inbox or (root / "epg" / "inbox")

    def cho_len_song() -> bool:
        """Cấu hình có mới hơn bảng đã sinh không.

        So mốc sửa file, không giữ cờ trong bộ nhớ: tiến trình web khởi động
        lại là mất cờ, mà mốc trên đĩa thì không.
        """
        moc = build / "nit.xml"
        if not moc.exists():
            return True
        cu = moc.stat().st_mtime
        return any(f.stat().st_mtime > cu for f in config_dir.rglob("*.yaml"))

    def cred() -> A.Credentials | None:
        """Đọc lại file mỗi lượt, giống cách đọc lại cấu hình.

        Chạy `vtcsi passwd` ở terminal là có hiệu lực ngay, không phải dựng
        lại tiến trình — và một tiến trình đang chạy không giữ được mật khẩu
        cũ sau khi nó đã bị đổi.
        """
        return A.load(where)

    def _ve(request: Request) -> str:
        """Vé máy, đọc từ header.

        Nhận cả ``Authorization: Bearer …`` lẫn ``X-VTCSI-Token: …``. Hai cách
        vì hai loại người gọi: thư viện HTTP nào cũng có chỗ đặt ``Authorization``,
        còn vài hệ cũ thì chỉ cho thêm header tuỳ ý.

        **Không** nhận vé trong query string: URL nằm trong log của mọi proxy
        trên đường đi, và một cái vé đã vào log là một cái vé đã lộ.
        """
        raw = request.headers.get("authorization", "")
        if raw.lower().startswith("bearer "):
            return raw[7:].strip()
        return request.headers.get("x-vtcsi-token", "").strip()

    def ai(request: Request) -> str | None:
        """Tên người đang đăng nhập, hoặc ``None``."""
        if not require_login:
            return "(không yêu cầu đăng nhập)"
        c = cred()
        if c is None:
            return None
        return A.read(c, request.cookies.get(A.COOKIE, ""), now=time.time())

    def load() -> Config:
        return loader.load(config_dir)

    def page(request: Request, name: str, **ctx) -> HTMLResponse:
        ctx.setdefault("git", git.status(root))
        ctx.setdefault("config_dir", config_dir)
        ctx.setdefault("nguoi_dung", ai(request))
        ctx.setdefault("can_dang_nhap", require_login)
        try:
            ctx.setdefault("cho_len_song", cho_len_song())
        except OSError:  # pragma: no cover
            ctx.setdefault("cho_len_song", False)
        return templates.TemplateResponse(request, name, ctx)

    def back(to: str, note: str = "", err: str = "") -> RedirectResponse:
        from urllib.parse import urlencode
        q = urlencode({k: v for k, v in (("note", note), ("err", err)) if v})
        return RedirectResponse(f"{to}?{q}" if q else to, status_code=303)

    CONG_MO = ("/dang-nhap", "/dang-xuat")
    API = "/api/"

    @app.middleware("http")
    async def canh_cong(request: Request, call_next):
        """Chặn ở **một chỗ duy nhất**, không rải decorator lên từng tuyến.

        Rải ra từng tuyến nghĩa là thêm một tuyến mới mà quên gắn là mở toang
        một lối vào, và không gì nhắc. Chặn ở giữa thì mặc định là *đóng*, và
        mở là việc phải nói ra.
        """
        if not require_login or request.url.path in CONG_MO:
            return await call_next(request)

        # API cho MAY: ve trong header, khong phai cookie. Van chan o day chu
        # khong chan trong tung tuyen — mac dinh la dong, mo la viec phai noi ra.
        if request.url.path.startswith(API):
            try:
                c = cred()
            except A.AuthError as exc:
                return JSONResponse({"loi": str(exc)}, status_code=500)
            if c is None:
                return JSONResponse(
                    {"loi": "chua dat mat khau — chay `vtcsi passwd` tren may chu"},
                    status_code=503)
            if not A.token_ok(c, _ve(request)):
                return JSONResponse({"loi": "ve khong dung"}, status_code=401)
            return await call_next(request)
        try:
            c = cred()
        except A.AuthError as exc:
            return templates.TemplateResponse(
                request, "loi.html",
                {"loi": str(exc), "git": git.status(root),
                 "config_dir": config_dir, "nguoi_dung": None,
                 "can_dang_nhap": require_login}, status_code=500)
        if c is None:
            return templates.TemplateResponse(
                request, "chua-dat-mat-khau.html",
                {"git": git.status(root), "config_dir": config_dir,
                 "auth_file": where, "nguoi_dung": None,
                 "can_dang_nhap": require_login}, status_code=503)
        if A.read(c, request.cookies.get(A.COOKIE, ""), now=time.time()) is None:
            tiep = request.url.path
            if request.url.query:
                tiep += "?" + request.url.query
            from urllib.parse import quote
            return RedirectResponse(f"/dang-nhap?tiep={quote(tiep, safe='')}",
                                    status_code=303)
        return await call_next(request)

    # --------------------------------------------------------- đăng nhập

    @app.get("/dang-nhap", response_class=HTMLResponse)
    def trang_dang_nhap(request: Request, tiep: str = "/", err: str = ""):
        try:
            c = cred()
        except A.AuthError as exc:
            return page(request, "loi.html", loi=str(exc))
        if c is None:
            return page(request, "chua-dat-mat-khau.html", auth_file=where)
        if A.read(c, request.cookies.get(A.COOKIE, ""), now=time.time()):
            return RedirectResponse("/", status_code=303)
        return page(request, "dang-nhap.html", tiep=tiep, err=err,
                    khoa=gate.locked_for(time.time()))

    @app.post("/dang-nhap")
    def lam_dang_nhap(user: str = Form(""), password: str = Form(""),
                      tiep: str = Form("/")):
        from urllib.parse import quote
        now = time.time()
        con = gate.locked_for(now)
        if con > 0:
            return back("/dang-nhap",
                        err=f"sai quá nhiều lần — thử lại sau {con:.0f} giây")
        try:
            c = cred()
        except A.AuthError as exc:
            return back("/dang-nhap", err=str(exc))
        if c is None:
            return RedirectResponse("/dang-nhap", status_code=303)

        if not A.verify(c, user, password):
            gate.fail(now)
            # Khong noi sai ten hay sai mat khau: noi ra la xac nhan ho mot nua.
            return back("/dang-nhap", err="tên đăng nhập hoặc mật khẩu không đúng")

        gate.succeed()
        di = tiep if tiep.startswith("/") and not tiep.startswith("//") else "/"
        r = RedirectResponse(di, status_code=303)
        r.set_cookie(A.COOKIE, A.issue(c, now=now), max_age=A.MAX_AGE,
                     httponly=True, samesite="lax", path="/")
        return r

    @app.post("/dang-xuat")
    def dang_xuat():
        r = RedirectResponse("/dang-nhap", status_code=303)
        r.delete_cookie(A.COOKIE, path="/")
        return r

    # ---------------------------------------------------------- quản trị

    @app.get("/quan-tri", response_class=HTMLResponse)
    def quan_tri(request: Request, note: str = "", err: str = ""):
        c = cred()
        ignored = None
        if git.status(root).is_repo:
            ignored = git.is_ignored(root, where)
        return page(request, "quan-tri.html", cred=c, auth_file=where,
                    ignored=ignored, note=note, err=err,
                    doi_luc=(time.strftime("%Y-%m-%d %H:%M",
                                           time.localtime(c.changed_at))
                             if c else ""),
                    phien_gio=A.MAX_AGE // 3600, toi_thieu=A.MIN_LENGTH)

    @app.post("/quan-tri/doi-mat-khau")
    def doi_mat_khau(request: Request, cu: str = Form(""), moi: str = Form(""),
                     lai: str = Form("")):
        try:
            c = cred()
        except A.AuthError as exc:
            return back("/quan-tri", err=str(exc))
        if c is None:
            return RedirectResponse("/dang-nhap", status_code=303)
        if moi != lai:
            return back("/quan-tri", err="hai ô mật khẩu mới không giống nhau")
        try:
            A.save(where, A.change(c, cu, moi))
        except A.AuthError as exc:
            return back("/quan-tri", err=str(exc))
        # Khoa ky phien da doi, nen ve cu het hieu luc — ke ca ve cua chinh
        # trinh duyet nay. Dua ho ve trang dang nhap thay vi de gap loi la.
        r = RedirectResponse("/dang-nhap", status_code=303)
        r.delete_cookie(A.COOKIE, path="/")
        return r

    @app.exception_handler(ConfigError)
    def cau_hinh_hong(request: Request, exc: ConfigError):
        """Cấu hình không nạp được thì ra **trang**, không ra stack trace.

        Giao diện đọc lại YAML ở mỗi lượt truy cập, nên chỉ cần một file hỏng —
        thường là sửa tay rồi lệch thụt đầu dòng — là mọi trang chết. Ném stack
        trace Python vào mặt người trực lúc hai giờ sáng không giúp được gì; câu
        họ cần là *hỏng ở đâu* và *quay lui bằng lệnh nào*.
        """
        return templates.TemplateResponse(
            request, "loi.html",
            {"loi": str(exc), "git": git.status(root), "config_dir": config_dir},
            status_code=500)

    # ---------------------------------------------------------------- trang

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request, note: str = "", err: str = ""):
        cfg = load()
        return page(request, "home.html", cfg=cfg, note=note, err=err,
                    problems=L.check(cfg),
                    counts={
                        "services": sum(len(s.services) for s in cfg.sdts),
                        "lcn": sum(len(t.lcn) for b in cfg.bouquets for t in b.ts_loops),
                    })

    @app.get("/ts/{ts_id}", response_class=HTMLResponse)
    def transport_stream(request: Request, ts_id: int, note: str = "", err: str = ""):
        cfg = load()
        sdt = next((s for s in cfg.sdts if s.ts_id == ts_id), None)
        loop = next((t for t in cfg.network.ts_loops if t.ts_id == ts_id), None)
        if sdt is None or loop is None:
            return back("/", err=f"không có TS {ts_id}")
        # LCN cua tung dich vu, gom tu moi bouquet — mot kenh co the co nhieu so.
        lcn: dict[int, list[tuple[str, int]]] = {}
        for b in cfg.bouquets:
            for t in b.ts_loops:
                if t.ts_id != ts_id:
                    continue
                for e in t.lcn:
                    lcn.setdefault(e.service_id, []).append((b.name, e.lcn))
        return page(request, "ts.html", cfg=cfg, sdt=sdt, nit=loop, lcn=lcn,
                    note=note, err=err)

    @app.get("/ts/{ts_id}/service/{service_id}", response_class=HTMLResponse)
    def edit_service(request: Request, ts_id: int, service_id: int, err: str = ""):
        cfg = load()
        sdt = next((s for s in cfg.sdts if s.ts_id == ts_id), None)
        svc = next((x for x in sdt.services if x.service_id == service_id), None) \
            if sdt else None
        if svc is None:
            return back(f"/ts/{ts_id}", err=f"không có dịch vụ {service_id}")
        return page(request, "service.html", cfg=cfg, sdt=sdt, svc=svc, err=err,
                    new=False)

    @app.get("/ts/{ts_id}/new", response_class=HTMLResponse)
    def new_service(request: Request, ts_id: int, err: str = ""):
        cfg = load()
        sdt = next((s for s in cfg.sdts if s.ts_id == ts_id), None)
        if sdt is None:
            return back("/", err=f"không có TS {ts_id}")
        blank = Service(service_id=0, name="", provider="",
                        service_type=ServiceType.DIGITAL_TELEVISION)
        return page(request, "service.html", cfg=cfg, sdt=sdt, svc=blank, err=err,
                    new=True)

    # ---------------------------------------------------------------- ghi

    def _apply() -> str:
        """Sinh lại bảng và EIT. Trả về dòng tóm tắt, hoặc lời giải thích lỗi."""
        import argparse
        import contextlib
        import io as _io

        from vtcsi import cli
        from vtcsi.epg.transform import window as _w

        args = argparse.Namespace(
            config=str(config_dir), out=str(build), inbox=str(hop_thu),
            out_eit=str(eit_out), now=None, depth=_w.WINDOW_HOURS,
            alarm_below=0,   # canh bao lich mong la viec cua `run`, khong phai o day
        )
        ghi = _io.StringIO()
        try:
            with contextlib.redirect_stdout(ghi):
                cli.cmd_refresh(args)
        except Exception as exc:  # noqa: BLE001 — bao ra trang, khong nem 500
            return f"sinh lại thất bại: {exc}"
        text = ghi.getvalue()
        bang = len(list(build.glob("*.xml")))
        if "KHONG SINH DUOC BANG EIT NAO" in text:
            if "da go" in text:
                return (f"{bang} bảng cấu trúc · EIT không sinh lại được "
                        f"(hộp thư chỉ còn lịch cũ) nhưng đã gỡ kênh vừa tắt")
            return (f"{bang} bảng cấu trúc · EIT giữ nguyên bản cũ "
                    f"(hộp thư chỉ còn lịch cũ)")
        so = text.split("(")[-1].split(" bang")[0] if "bang EIT" in text else "?"
        return f"{bang} bảng cấu trúc, {so} bảng EIT"

    def _save(cfg: Config) -> list[str]:
        """Ghi cấu hình **và sinh lại bảng ngay**.

        Sinh lại ngay chứ không chờ chu kỳ, vì công tắc EPG là để tắt nhanh khi
        có sự cố — sửa xong mà chờ tới một giờ thì không còn là "nhanh". Cả lượt
        tốn khoảng nửa giây, và ``tsp`` đọc lại file trong khoảng nửa giây nữa
        nhờ ``--poll-files``; **không** phải dựng lại tiến trình nào, nên không
        có lần chớp nguồn nào.

        Sinh lại hỏng thì **không** làm hỏng việc ghi cấu hình: file YAML đã
        nằm trên đĩa, và dải cảnh báo "chưa lên sóng" sẽ hiện ra kèm nút bấm
        lại. Mất bảng mới khó chịu; mất cả thay đổi vừa gõ thì tệ hơn.
        """
        cfg, tang = _tu_tang(cfg)
        loader.save(cfg, config_dir)
        try:
            _apply()
        except Exception:  # noqa: BLE001 — dai canh bao se hien ra
            pass
        return tang

    def _tu_tang(cfg: Config) -> tuple[Config, str]:
        """Tăng version SDT và BAT nếu nội dung đã rời khỏi bản đã commit.

        Mốc so là **HEAD**, không phải lần lưu trước — xem ``version.autobump``.
        Nhờ đó một chu kỳ commit chỉ tăng đúng một lần, và hai máy ngang hàng
        ra cùng một số dù số lần bấm Lưu khác nhau.

        Không đọc được HEAD thì **không tăng gì cả**. Không có mốc mà vẫn tăng
        là tăng dựa trên một con số tưởng tượng, tệ hơn là không tăng: nó tạo
        ra chênh lệch giữa hai máy mà không ai thấy.
        """
        td = git.config_at_head(root)
        if td is None:
            return cfg, ""
        try:
            truoc = loader.load(Path(td.name) / "config")
        except (ConfigError, OSError):
            return cfg, ""
        finally:
            td.cleanup()
        ke = autobump.plan(cfg, truoc)
        return autobump.apply(cfg, ke), autobump.describe(ke)

    def _kem(note: str, tang: str) -> str:
        """Ghép lời báo tăng version vào thông báo của thao tác vừa rồi.

        Version đổi mà không nói ra thì đúng là thứ hệ này sinh ra để chống.
        """
        return f"{note} · {tang}" if tang else note

    @app.post("/ts/{ts_id}/service/save")
    def save_service(
        ts_id: int,
        service_id: int = Form(...),
        name: str = Form(""),
        provider: str = Form(""),
        service_type: int = Form(1),
        epg: bool = Form(False),
        free_ca_mode: bool = Form(False),
        creating: bool = Form(False),
    ):
        cfg = load()
        sdt = next((s for s in cfg.sdts if s.ts_id == ts_id), None)
        if sdt is None:
            return back("/", err=f"không có TS {ts_id}")

        existing = {x.service_id for x in sdt.services}
        if creating and service_id in existing:
            return back(f"/ts/{ts_id}/new", err=f"dịch vụ {service_id} đã tồn tại")
        if not creating and service_id not in existing:
            return back(f"/ts/{ts_id}", err=f"không có dịch vụ {service_id}")
        if not name.strip():
            where = f"/ts/{ts_id}/new" if creating else \
                f"/ts/{ts_id}/service/{service_id}"
            return back(where, err="tên dịch vụ không được để trống")

        # Mot cong tac dat CA HAI co. Xem `entities.set_epg` ve ly do khong
        # cho tach chung ra.
        made = Service(
            service_id=service_id, name=name.strip(), provider=provider.strip(),
            service_type=ServiceType(service_type),
            running_status=RunningStatus.RUNNING,
            free_ca_mode=free_ca_mode, eit_pf=epg, eit_schedule=epg,
        )
        others = [x for x in sdt.services if x.service_id != service_id]
        services = tuple(sorted(others + [made], key=lambda x: x.service_id))

        from dataclasses import replace
        cfg = replace(cfg, sdts=tuple(
            replace(s, services=services) if s.ts_id == ts_id else s for s in cfg.sdts))
        try:
            tang = _save(_rebuild_nit(cfg))
        except ConfigError as exc:
            return back(f"/ts/{ts_id}", err=str(exc))
        verb = "thêm" if creating else "sửa"
        return back(f"/ts/{ts_id}",
                    note=_kem(f"đã {verb} dịch vụ {service_id}", tang))

    @app.post("/ts/{ts_id}/eit")
    async def save_eit_flags(request: Request, ts_id: int):
        """Bật/tắt EPG cho từng kênh, gửi cả bảng một lượt.

        Một công tắc đặt **cả hai** cờ ``eit_pf`` và ``eit_schedule``, vì câu
        hỏi người vận hành đang trả lời là "kênh này có EPG hay không" chứ
        không phải "khai cờ nào trong SDT". Cần tách riêng hai cờ thì vào trang
        của từng dịch vụ.

        Và công tắc này **có tác dụng thật**: ``vtcsi epg`` không sinh bảng cho
        dịch vụ đã tắt. Nếu chỉ đổi cờ trong SDT thì đầu thu vẫn hiện EPG, vì
        cờ đó chỉ là lời khai.
        """
        from dataclasses import replace

        cfg = load()
        sdt = next((s for s in cfg.sdts if s.ts_id == ts_id), None)
        if sdt is None:
            return back("/", err=f"không có TS {ts_id}")

        form = await request.form()
        bat = {int(k[4:]) for k in form.keys() if k.startswith("eit_")}
        services = tuple(set_epg(x, x.service_id in bat) for x in sdt.services)
        doi = sum(1 for a, b in zip(sdt.services, services) if a != b)
        if not doi:
            return back(f"/ts/{ts_id}", err="không có kênh nào đổi trạng thái EPG")

        cfg = replace(cfg, sdts=tuple(
            replace(s, services=services) if s.ts_id == ts_id else s
            for s in cfg.sdts))
        tang = _save(cfg)
        tat = len(services) - len(bat)
        return back(f"/ts/{ts_id}",
                    note=_kem(f"đã đổi EPG của {doi} kênh — {len(bat)} bật, "
                              f"{tat} tắt", tang))

    @app.post("/ts/{ts_id}/service/{service_id}/delete")
    def delete_service(ts_id: int, service_id: int, confirm_name: str = Form("")):
        cfg = load()
        sdt = next((s for s in cfg.sdts if s.ts_id == ts_id), None)
        svc = next((x for x in sdt.services if x.service_id == service_id), None) \
            if sdt else None
        if svc is None:
            return back(f"/ts/{ts_id}", err=f"không có dịch vụ {service_id}")
        if confirm_name.strip() != svc.name:
            return back(f"/ts/{ts_id}/service/{service_id}",
                        err="gõ đúng tên kênh để xác nhận xoá")

        from dataclasses import replace
        kept = tuple(x for x in sdt.services if x.service_id != service_id)
        cfg = replace(cfg, sdts=tuple(
            replace(s, services=kept) if s.ts_id == ts_id else s for s in cfg.sdts))
        # Gỡ khỏi mọi bouquet — cả tư cách thành viên lẫn số kênh. Bỏ sót vế
        # nào cũng tạo ra đúng lỗi mà ``lcn.check`` bắt.
        cfg = L.forget_service(cfg, ts_id, service_id)

        tang = _save(_rebuild_nit(cfg))
        return back(f"/ts/{ts_id}",
                    note=_kem(f"đã xoá dịch vụ {service_id} '{svc.name}' "
                              f"khỏi TS và mọi bouquet", tang))

    # ------------------------------------------------------------- version

    @app.post("/version/set")
    def set_version(table: str = Form(...), version: int = Form(...),
                    confirm: str = Form("")):
        """Đặt version **bằng tay**, không phải tăng tự động.

        Đặt được số bất kỳ trong 0…31, kể cả **nhỏ hơn** số hiện tại. Đó không
        phải sự dễ dãi: đầu thu phát hiện version *đổi* chứ không phải *tăng*
        — trường 5 bit vốn quay vòng nên không có thứ tự tuyệt đối. Tăng nhầm
        rồi đặt lại số cũ là cách sửa đúng, và nếu chỉ cho tăng thì cách duy
        nhất để về chỗ cũ là bấm thêm 31 lần.

        Hàng rào là **gõ lại đúng con số muốn đặt**. Cùng ý với việc gõ lại tên
        kênh để xoá: buộc mắt phải nhìn vào giá trị, không phải bấm vào một cái
        nút theo thói quen.
        """
        cfg = load()
        from dataclasses import replace

        try:
            V.validate(version, "version")
        except V.VersionError as exc:
            return back("/", err=str(exc))

        if confirm.strip() != str(version):
            return back("/", err=f"gõ lại đúng số {version} để xác nhận")

        if table == "nit":
            now = cfg.network.version
            cfg = replace(cfg, network=replace(cfg.network, version=version))
            what = f"NIT {V.describe_move(now, version)}"
        elif table.startswith("sdt:"):
            ts_id = int(table.split(":")[1])
            found = next((x for x in cfg.sdts if x.ts_id == ts_id), None)
            if found is None:
                return back("/", err=f"không có SDT của TS {ts_id}")
            now = found.version
            cfg = replace(cfg, sdts=tuple(
                replace(x, version=version) if x.ts_id == ts_id else x
                for x in cfg.sdts))
            what = f"SDT ts{ts_id} {V.describe_move(now, version)}"
        elif table.startswith("bat:"):
            bid = int(table.split(":")[1], 16)
            found = next((x for x in cfg.bouquets if x.bouquet_id == bid), None)
            if found is None:
                return back("/", err=f"không có bouquet {bid:#06x}")
            now = found.version
            cfg = replace(cfg, bouquets=tuple(
                replace(x, version=version) if x.bouquet_id == bid else x
                for x in cfg.bouquets))
            what = f"BAT {bid:04x} {V.describe_move(now, version)}"
        else:
            return back("/", err=f"không biết bảng nào tên '{table}'")

        if now == version:
            return back("/", err=f"bảng đó đang ở version {version} rồi")
        _save(cfg)
        return back("/", note=f"đã đặt version {what}")   # dat tay thi khong tu tang

    # ------------------------------------------------------------ bouquet

    def _bouquet(cfg: Config, raw: str):
        try:
            bid = int(raw, 16)
        except ValueError:
            return None, None
        return bid, next((b for b in cfg.bouquets if b.bouquet_id == bid), None)

    @app.get("/bouquet/{raw}", response_class=HTMLResponse)
    def bouquet(request: Request, raw: str, note: str = "", err: str = ""):
        cfg = load()
        bid, b = _bouquet(cfg, raw)
        if b is None:
            return back("/", err=f"không có bouquet {raw}")

        # Moi vong transport kem: ten kenh lay tu SDT, so kenh hien co, va
        # danh sach kenh CHUA o trong bouquet de them vao.
        by_ts = {s.ts_id: {x.service_id: x for x in s.services} for s in cfg.sdts}
        loops = []
        for t in b.ts_loops:
            names = by_ts.get(t.ts_id, {})
            numbers = {e.service_id: e for e in t.lcn}
            inside = {r.service_id for r in t.services}
            members = [
                {"service_id": r.service_id,
                 "svc": names.get(r.service_id),
                 "entry": numbers.get(r.service_id)}
                for r in t.services
            ]
            members.sort(key=lambda m: (m["entry"].lcn if m["entry"] else 1 << 20,
                                        m["service_id"]))
            outside = [x for sid, x in sorted(names.items()) if sid not in inside]
            loops.append({"ts": t, "members": members, "outside": outside})

        try:
            suggestion = L.next_after_last(b)
        except L.LcnError:
            suggestion = None

        # TS nao chua co vong trong bouquet nay — de moi them.
        spare = [{"ts_id": x.ts_id, "onid": x.original_network_id,
                  "services": len(x.services)}
                 for x in cfg.sdts if not TOPO.has_loop(b, x.ts_id)]

        return page(request, "bouquet.html", cfg=cfg, b=b, loops=loops,
                    numbered=any(t.lcn for t in b.ts_loops),
                    problems=[p for p in L.check(cfg) if p.bouquet_id == bid],
                    link_problems=[p for p in K.check(cfg)
                                   if p.where == f"BAT {b.bouquet_id:04x}"],
                    spare=spare, suggested_pds=TOPO.suggested_pds(cfg, b),
                    describe=K.describe, as_hex=K.format_hex,
                    suggestion=suggestion, note=note, err=err)

    def _swap(cfg: Config, made) -> Config:
        from dataclasses import replace
        return replace(cfg, bouquets=tuple(
            made if x.bouquet_id == made.bouquet_id else x for x in cfg.bouquets))

    @app.post("/bouquet/{raw}/ts/{ts_id}/lcn")
    async def save_numbers(request: Request, raw: str, ts_id: int):
        """Luu ca bang so kenh cua mot vong transport, mot luot.

        Gui nguyen bang chu khong tung o. Hai ly do: xoa mot so thanh hanh dong
        ro rang thay vi bo sot, va kiem tra trung so chi co nghia khi nhin ca
        bang cung luc.
        """
        cfg = load()
        bid, b = _bouquet(cfg, raw)
        if b is None:
            return back("/", err=f"không có bouquet {raw}")

        form = await request.form()
        numbers: dict[int, int] = {}
        visible: dict[int, bool] = {}
        for key, value in form.multi_items():
            if key.startswith("lcn_"):
                sid = int(key[4:])
                text = str(value).strip()
                if not text:
                    continue  # o de trong = bo so kenh, co y
                try:
                    numbers[sid] = int(text)
                except ValueError:
                    return back(f"/bouquet/{raw}",
                                err=f"dịch vụ {sid}: '{text}' không phải số")
            elif key.startswith("vis_"):
                visible[int(key[4:])] = True
        # Checkbox khong tich thi trinh duyet khong gui gi — nen mac dinh la an.
        for sid in numbers:
            visible.setdefault(sid, False)

        try:
            made = L.set_numbers(b, ts_id, numbers, visible)
        except L.LcnError as exc:
            return back(f"/bouquet/{raw}", err=str(exc))
        tang = _save(_swap(cfg, made))
        return back(f"/bouquet/{raw}",
                    note=_kem(f"đã lưu {len(numbers)} số kênh ở TS {ts_id}", tang))

    @app.post("/bouquet/{raw}/ts/{ts_id}/add")
    def add_to_bouquet(raw: str, ts_id: int,
                       service_id: int = Form(...), number: str = Form("")):
        cfg = load()
        bid, b = _bouquet(cfg, raw)
        if b is None:
            return back("/", err=f"không có bouquet {raw}")
        sdt = next((s for s in cfg.sdts if s.ts_id == ts_id), None)
        svc = next((x for x in sdt.services if x.service_id == service_id), None) \
            if sdt else None
        if svc is None:
            return back(f"/bouquet/{raw}",
                        err=f"TS {ts_id} không có dịch vụ {service_id}")

        want = None
        if number.strip():
            try:
                want = int(number)
            except ValueError:
                return back(f"/bouquet/{raw}", err=f"'{number}' không phải số")
        try:
            made = L.add_member(
                b, ts_id, ServiceRef(service_id, int(svc.service_type)), want)
        except L.LcnError as exc:
            return back(f"/bouquet/{raw}", err=str(exc))
        tang = _save(_swap(cfg, made))
        what = f" với số kênh {want}" if want else " (chưa có số kênh)"
        return back(f"/bouquet/{raw}",
                    note=_kem(f"đã thêm '{svc.name}'{what}", tang))

    @app.post("/bouquet/{raw}/ts/{ts_id}/remove")
    def remove_from_bouquet(raw: str, ts_id: int, service_id: int = Form(...)):
        cfg = load()
        bid, b = _bouquet(cfg, raw)
        if b is None:
            return back("/", err=f"không có bouquet {raw}")
        try:
            made = L.remove_member(b, ts_id, service_id)
        except L.LcnError as exc:
            return back(f"/bouquet/{raw}", err=str(exc))
        tang = _save(_swap(cfg, made))
        return back(f"/bouquet/{raw}",
                    note=_kem(f"đã bỏ dịch vụ {service_id} khỏi bouquet", tang))

    # ------------------------------------------------- vòng transport

    @app.post("/bouquet/{raw}/ts/add")
    def add_loop(raw: str, ts_id: int = Form(...),
                 original_network_id: int = Form(...), pds: str = Form("")):
        cfg = load()
        bid, b = _bouquet(cfg, raw)
        if b is None:
            return back("/", err=f"không có bouquet {raw}")
        try:
            made = TOPO.add_loop(b, ts_id, original_network_id,
                                 pds.strip() or None)
        except TOPO.TopologyError as exc:
            return back(f"/bouquet/{raw}", err=str(exc))
        tang = _save(_swap(cfg, made))
        return back(f"/bouquet/{raw}",
                    note=_kem(f"đã thêm vòng TS {ts_id} (chưa có kênh nào)", tang))

    @app.post("/bouquet/{raw}/ts/drop")
    def drop_loop(raw: str, ts_id: int = Form(...), confirm: str = Form("")):
        """``ts_id`` lay tu than bieu mau chu khong tu duong dan.

        De duong dan thi phai co JavaScript sua URL truoc khi gui, va trang se
        gui nham khi JS khong chay. Mot man hinh van hanh khong duoc phu thuoc
        vao dieu do.
        """
        cfg = load()
        bid, b = _bouquet(cfg, raw)
        if b is None:
            return back("/", err=f"không có bouquet {raw}")
        loop = next((t for t in b.ts_loops if t.ts_id == ts_id), None)
        if loop is None:
            return back(f"/bouquet/{raw}", err=f"không có vòng TS {ts_id}")
        # Vong day doi go dung so kenh — mot con so phai nhin moi biet, nen
        # khong bam nham duoc.
        force = bool(loop.services) and confirm.strip() == str(len(loop.services))
        if loop.services and not force:
            return back(f"/bouquet/{raw}",
                        err=f"vòng TS {ts_id} còn {len(loop.services)} dịch vụ — "
                            f"gõ đúng số đó để xác nhận bỏ cả vòng")
        try:
            made = TOPO.remove_loop(b, ts_id, force=force)
        except TOPO.TopologyError as exc:
            return back(f"/bouquet/{raw}", err=str(exc))
        tang = _save(_swap(cfg, made))
        return back(f"/bouquet/{raw}",
                    note=_kem(f"đã bỏ cả vòng TS {ts_id}", tang))

    # ------------------------------------------------------------ linkage

    def _scope(cfg: Config, raw: str):
        """``"nit"`` hoac ma bouquet dang hex. Tra ve (ten, danh sach, bouquet)."""
        if raw == "nit":
            return "NIT " + cfg.network.name, cfg.network.linkages, None
        bid, b = _bouquet(cfg, raw)
        if b is None:
            return None, None, None
        return f"BAT {b.bouquet_id:04x} {b.name}", b.linkages, b

    def _put_linkages(cfg: Config, b, items) -> Config:
        from dataclasses import replace
        if b is None:
            return replace(cfg, network=K.on_network(cfg.network, items))
        return _swap(cfg, K.on_bouquet(b, items))

    @app.get("/linkage", response_class=HTMLResponse)
    def linkages(request: Request, note: str = "", err: str = ""):
        cfg = load()
        problems = K.check(cfg)
        groups = [{"raw": "nit", "title": "NIT — " + cfg.network.name,
                   "items": cfg.network.linkages, "where": "NIT"}]
        for b in cfg.bouquets:
            groups.append({"raw": f"{b.bouquet_id:04x}",
                           "title": f"BAT 0x{b.bouquet_id:04x} — {b.name}",
                           "items": b.linkages,
                           "where": f"BAT {b.bouquet_id:04x}"})
        ts_ids = sorted(s.ts_id for s in cfg.sdts)
        return page(request, "linkage.html", cfg=cfg, groups=groups,
                    problems=problems, ts_ids=ts_ids,
                    describe=K.describe, is_opaque=K.is_opaque,
                    as_hex=K.format_hex, note=note, err=err)

    @app.get("/linkage/{raw}/{index}", response_class=HTMLResponse)
    def edit_linkage(request: Request, raw: str, index: str, err: str = ""):
        cfg = load()
        title, items, b = _scope(cfg, raw)
        if items is None:
            return back("/linkage", err=f"không biết chỗ nào tên '{raw}'")

        new = index == "moi"
        if new:
            k = Linkage(linkage_type=0x80, ts_id=0, original_network_id=0,
                        service_id=0)
            i = -1
        else:
            try:
                i = int(index)
            except ValueError:
                return back("/linkage", err=f"chỉ số không hợp lệ: {index}")
            if not 0 <= i < len(items):
                return back("/linkage", err=f"{title} không có linkage thứ {i}")
            k = items[i]

        return page(request, "linkage-edit.html", cfg=cfg, raw=raw, title=title,
                    index=i, new=new, k=k, as_hex=K.format_hex,
                    describe=K.describe, is_opaque=K.is_opaque,
                    known=sorted(K.KNOWN_TYPES.items()),
                    ts_ids=sorted(s.ts_id for s in cfg.sdts), err=err)

    @app.post("/linkage/{raw}/save")
    def save_linkage(raw: str, index: int = Form(...),
                     linkage_type: str = Form(...), ts_id: int = Form(...),
                     original_network_id: int = Form(...),
                     service_id: int = Form(...), private_data: str = Form("")):
        cfg = load()
        title, items, b = _scope(cfg, raw)
        if items is None:
            return back("/linkage", err=f"không biết chỗ nào tên '{raw}'")

        where = f"/linkage/{raw}/" + ("moi" if index < 0 else str(index))
        try:
            kind = int(linkage_type, 0)
        except ValueError:
            return back(where, err=f"loại linkage không hợp lệ: {linkage_type}")
        try:
            data = K.parse_hex(private_data)
        except K.LinkageError as exc:
            return back(where, err=str(exc))

        made = Linkage(linkage_type=kind, ts_id=ts_id,
                       original_network_id=original_network_id,
                       service_id=service_id, private_data=data)
        try:
            items = (K.append(items, made) if index < 0
                     else K.set_at(items, index, made))
        except K.LinkageError as exc:
            return back(where, err=str(exc))

        tang = _save(_put_linkages(cfg, b, items))
        verb = "thêm" if index < 0 else "sửa"
        return back("/linkage",
                    note=_kem(f"đã {verb} linkage {kind:#04x} ở {title}", tang))

    @app.post("/linkage/{raw}/{index}/delete")
    def delete_linkage(raw: str, index: int, confirm: str = Form("")):
        cfg = load()
        title, items, b = _scope(cfg, raw)
        if items is None:
            return back("/linkage", err=f"không biết chỗ nào tên '{raw}'")
        if not 0 <= index < len(items):
            return back("/linkage", err=f"{title} không có linkage thứ {index}")

        k = items[index]
        # Doi go lai dung loai. Voi linkage user-defined thi day la duong OTA
        # nang cap dau thu — xoa nham la cat duong nang cap cua ca mang.
        if confirm.strip().lower() not in (f"{k.linkage_type:#04x}".lower(),
                                           f"{k.linkage_type:02x}".lower()):
            return back(f"/linkage/{raw}/{index}",
                        err=f"gõ đúng loại linkage ({k.linkage_type:#04x}) để xác nhận")
        tang = _save(_put_linkages(cfg, b, K.remove_at(items, index)))
        return back("/linkage",
                    note=_kem(f"đã xoá linkage {k.linkage_type:#04x} thứ "
                              f"{index} ở {title}", tang))

    # --------------------------------------------------------- áp dụng

    @app.post("/ap-dung")
    def ap_dung():
        """Sinh lại bằng tay.

        Bình thường không cần bấm: mỗi lần lưu cấu hình đã tự sinh lại. Nút này
        cho hai trường hợp còn lại — lần tự sinh vừa rồi hỏng, hoặc thư mục
        ``build`` bị xoá hay lệch pha vì lý do nào đó.
        """
        ket_qua = _apply()
        if ket_qua.startswith("sinh lại thất bại"):
            return back("/", err=ket_qua)
        return back("/", note=f"đã áp dụng: {ket_qua} — tsp đọc lại trong "
                              f"khoảng nửa giây")

    # ---------------------------------------------------------- giám sát

    def _luoi(ngay_raw: str) -> dict:
        """Lưới lịch một ngày, đúng những gì đầu thu sẽ thấy.

        Một phép lọc duy nhất: **chỉ TS actual**. ``eitinject`` chạy với
        ``--actual --ts-id N``, nên kênh ở transport stream khác không hề có
        bảng EIT nào từ hệ này; vẽ chúng lên rồi ghi "trống" là đổ lỗi nhầm
        chỗ.

        Kênh **tắt EPG** thì vẫn có dòng. Nó vẫn là một kênh của transport
        stream này, và bỏ hẳn nó đi thì người trực không còn cách nào thấy nó
        tồn tại — màn giám sát mà giấu bớt kênh là một màn giám sát phải tin
        chứ không kiểm được. Nhưng dòng đó **rỗng**: kênh tắt không có bảng
        EIT nào, nên hiển thị chương trình cho chúng là thông tin sai lệch so với
        nội dung thực phát. Việc bỏ sự kiện
        nằm trong ``timeline.build``, không phải ở đây — một luật, một chỗ.

        Trả về **một hình dạng duy nhất** cho mọi nhánh. Hàm trả tuple dài ngắn
        khác nhau tuỳ nhánh là một lỗi chờ xảy ra ở nơi gọi.
        """
        from datetime import date, datetime, timezone

        from vtcsi.epg import store as _store
        from vtcsi.epg.transform import timeline as _tl
        from vtcsi.model.entities import epg_on

        bay_gio = datetime.now(timezone.utc).astimezone(_tl.VN)
        try:
            ngay = date.fromisoformat(ngay_raw) if ngay_raw else bay_gio.date()
        except ValueError:
            ngay = bay_gio.date()

        ra = {"ngay": ngay, "bay_gio": bay_gio, "board": None,
              "canh_bao": "", "loi": "", "ts_id": None}

        cfg = load()
        actual = next((x for x in cfg.sdts if x.actual), None)
        if actual is None:
            ra["loi"] = "cấu hình không có SDT actual nào"
            return ra

        ra["ts_id"] = actual.ts_id
        dich_vu = [(x.service_id, x.name, int(x.service_type) == 2, epg_on(x))
                   for x in actual.services]

        try:
            nap = _store.load_all(hop_thu)
        except _store.StoreError as exc:
            ra["canh_bao"] = str(exc)
            ra["board"] = _tl.build((), dich_vu, ngay)
            return ra

        su_kien = tuple(e for x in nap for e in x.events)
        ra["board"] = _tl.build(su_kien, dich_vu, ngay)
        return ra

    @app.get("/giam-sat", response_class=HTMLResponse)
    def giam_sat(request: Request, ngay: str = ""):
        k = _luoi(ngay)
        if k["board"] is None:
            return back("/", err=k["loi"])
        return page(request, "giam-sat.html", ngay=k["ngay"].isoformat(),
                    hom_nay=k["bay_gio"].date().isoformat(), ts_id=k["ts_id"],
                    so_tat=k["board"].off, canh_bao=k["canh_bao"])

    @app.get("/giam-sat/du-lieu")
    def giam_sat_du_lieu(ngay: str = ""):
        """Dữ liệu cho lưới. Mốc thời gian là **số phút kể từ 00:00**.

        Không gửi chuỗi giờ: giao diện đặt một ô ở ``phút × px`` là xong, và
        phép so "đang phát" chỉ còn là so hai số nguyên.
        """
        k = _luoi(ngay)
        board, bay_gio = k["board"], k["bay_gio"]
        if board is None:
            return JSONResponse({"loi": k["loi"]}, status_code=400)

        return JSONResponse({
            "ngay": k["ngay"].isoformat(),
            "hom_nay": k["ngay"] == bay_gio.date(),
            "phut_hien_tai": bay_gio.hour * 60 + bay_gio.minute,
            "gio_may_chu": bay_gio.strftime("%H:%M"),
            "ts_id": k["ts_id"],
            "canh_bao": k["canh_bao"],
            "dong": [{
                "id": r.service_id,
                "ten": r.name,
                "radio": r.radio,
                "epg": r.epg,
                "muc": [{"s": x.start, "p": x.minutes, "t": x.title, "m": x.text}
                        for x in r.slots],
                "ho": [list(g) for g in r.gaps],
            } for r in board.rows],
            "tong": {
                "kenh": len(board.rows),
                "co_lich": board.with_schedule,
                "trong": board.empty,
                "su_kien": board.events,
                "lo_hong": board.gaps,
                "tat_epg": board.off,
            },
        })

    # ------------------------------------------------------- hộp thư lịch

    def _doc_hop_thu():
        """Mỗi file trong hộp thư, kèm những gì đọc được từ nó.

        File hỏng **không** làm sập trang: nó hiện ra kèm lý do. Trang này
        chính là chỗ người ta tới khi nghi ngờ một file vừa nhận về có vấn đề.
        """
        from vtcsi.epg.transform import parse as _p

        ra = []
        if not hop_thu.is_dir():
            return ra
        for f in sorted(hop_thu.glob("*.xml")):
            st = f.stat()
            muc = {"ten": f.name, "byte": st.st_size, "luc": st.st_mtime,
                   "loi": "", "so_dich_vu": 0, "so_su_kien": 0,
                   "tu": None, "den": None, "ts_id": None}
            try:
                sched = _p.parse(f.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001 — moi loi deu hien ra trang
                muc["loi"] = str(exc)[:200]
            else:
                muc["ts_id"] = sched.ts_id
                muc["so_dich_vu"] = len({e.service_id for e in sched.events})
                muc["so_su_kien"] = len(sched.events)
                if sched.events:
                    muc["tu"] = min(e.start_utc for e in sched.events)
                    muc["den"] = max(e.end_utc for e in sched.events)
            ra.append(muc)
        return ra

    @app.get("/epg", response_class=HTMLResponse)
    def trang_epg(request: Request, note: str = "", err: str = ""):
        c = cred()
        return page(request, "epg.html", files=_doc_hop_thu(), inbox=hop_thu,
                    token=(c.token if c else ""), note=note, err=err)

    def _nhan_xml(raw: bytes, ten: str = "") -> tuple[bool, str, dict]:
        """Kiểm rồi ghi một file lịch vào hộp thư.

        **Kiểm trước khi ghi.** Một file hỏng nằm trong hộp thư sẽ làm hỏng lần
        sinh EIT kế tiếp, mà lần đó xảy ra vài giây sau và không ai đang nhìn.
        Từ chối ngay lúc nhận thì bên gửi biết ngay, còn ta thì không bao giờ
        có file hỏng trên đĩa.

        Tên file mặc định lấy theo **ngày của sự kiện sớm nhất**. Nhờ vậy gửi
        lại cùng một ngày là ghi đè đúng file cũ — không phát sinh bản trùng
        lặp. Và
        ``load_all`` sắp theo tên nên thứ tự ngày cũng là thứ tự nạp.
        """
        from vtcsi.epg.transform import parse as _p

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            return False, f"không phải UTF-8: {exc}", {}
        try:
            sched = _p.parse(text)
        except Exception as exc:  # noqa: BLE001 — loi nao cung tra ve cho ben gui
            return False, f"không phân tích được: {exc}", {}
        if not sched.events:
            return False, "file hợp lệ nhưng không có sự kiện nào", {}

        dat = ten.strip() or (min(e.start_utc for e in sched.events)
                              .astimezone().strftime("%Y-%m-%d") + ".xml")
        if "/" in dat or chr(92) in dat or dat.startswith("."):
            return False, f"tên file không hợp lệ: {dat!r}", {}
        if not dat.endswith(".xml"):
            dat += ".xml"

        hop_thu.mkdir(parents=True, exist_ok=True)
        tam = hop_thu / (dat + ".tam")
        with tam.open("w", encoding="utf-8", newline=chr(10)) as fh:
            fh.write(text)
        tam.replace(hop_thu / dat)     # thay the nguyen khoi, khong bao gio nua voi

        tom = {
            "ten": dat,
            "ts_id": sched.ts_id,
            "so_dich_vu": len({e.service_id for e in sched.events}),
            "so_su_kien": len(sched.events),
            "tu": min(e.start_utc for e in sched.events).isoformat(),
            "den": max(e.end_utc for e in sched.events).isoformat(),
        }
        return True, "", tom

    @app.post("/api/epg")
    async def api_epg(request: Request):
        """Nhận một file lịch từ hệ lập lịch bên ngoài.

        Thân yêu cầu là **chính nội dung XML**, không bọc JSON. Bên gửi đã có
        sẵn file; bắt họ mã hoá base64 rồi nhét vào một trường JSON chỉ thêm
        một khâu có thể phát sinh lỗi.

        Tên file đặt bằng ``?ten=``, hoặc để trống thì suy từ ngày của sự kiện
        sớm nhất trong file.
        """
        raw = await request.body()
        if not raw:
            return JSONResponse({"loi": "thân yêu cầu rỗng"}, status_code=400)
        ok, vi_sao, tom = _nhan_xml(raw, request.query_params.get("ten", ""))
        if not ok:
            return JSONResponse({"loi": vi_sao}, status_code=400)

        # Nhan xong la sinh lai NGAY — day la ca ly do ton tai cua tuyen nay.
        tom["sinh_lai"] = _apply()
        return JSONResponse({"nhan": True, **tom})

    @app.post("/epg/tai-len")
    async def tai_len(request: Request):
        """Nạp file bằng tay từ trình duyệt — cùng đường đi với API."""
        form = await request.form()
        f = form.get("file")
        if f is None or not getattr(f, "filename", ""):
            return back("/epg", err="chưa chọn file nào")
        ok, vi_sao, tom = _nhan_xml(await f.read(), str(form.get("ten", "")))
        if not ok:
            return back("/epg", err=vi_sao)
        return back("/epg", note=f"đã nhận {tom['ten']}: {tom['so_su_kien']} sự kiện "
                              f"trên {tom['so_dich_vu']} dịch vụ · {_apply()}")

    @app.post("/epg/xoa")
    def xoa_lich(ten: str = Form(...)):
        f = hop_thu / ten
        if "/" in ten or chr(92) in ten or not f.is_file():
            return back("/epg", err=f"không có file {ten}")
        f.unlink()
        return back("/epg", note=f"đã xoá {ten} · {_apply()}")

    @app.post("/epg/ve-moi")
    def ve_moi():
        """Cấp vé mới cho hệ bên ngoài. Vé cũ chết ngay."""
        from dataclasses import replace as _r
        c = cred()
        if c is None:
            return RedirectResponse("/dang-nhap", status_code=303)
        A.save(where, _r(c, token=A.new_token()))
        return back("/epg", note="đã cấp vé mới — hệ bên ngoài phải cập nhật, "
                                 "vé cũ không dùng được nữa")

    # ----------------------------------------------------------- git

    # ------------------------------------------------------- đầu ra

    def _lenh_ra(out: OUT.Output) -> str:
        """Dựng đúng dòng `tsp` mà cấu hình này sẽ sinh ra.

        Không phải để trang trí. Địa chỉ đầu ra là thứ người ta gõ một lần rồi
        tin mãi, và một con số sai ở đây thì không có triệu chứng nào ngoài
        "headend không thấy gì" — đọc được dòng lệnh là kiểm được mà không
        phải phát thử.
        """
        from datetime import datetime, timezone

        from vtcsi.pipeline import tspbuild

        try:
            cfg = load()
        except (ConfigError, OSError):
            return ""
        actual = [x for x in cfg.sdts if x.actual]
        if len(actual) != 1:
            return ""
        plan = tspbuild.plan_from_config(
            build_dir=build,
            eit_dir=eit_out.parent,
            ts_id=actual[0].ts_id,
            other_ts_ids=tuple(sorted(x.ts_id for x in cfg.sdts if not x.actual)),
            bouquet_ids=tuple(sorted(q.bouquet_id for q in cfg.bouquets)),
            destination=OUT.format_endpoint(out.primary),
            local_address=out.primary.interface or None,
            mirror=(OUT.format_endpoint(out.mirror)
                    if out.mirror and not out.mirror.empty else None),
            mirror_local_address=(out.mirror.interface
                                  if out.mirror and out.mirror.interface else None),
            ttl=out.ttl,
        )
        return tspbuild.shell(tspbuild.build(
            plan, start_time=datetime.now(timezone.utc)))

    @app.get("/dau-ra", response_class=HTMLResponse)
    def trang_dau_ra(request: Request, note: str = "", err: str = ""):
        try:
            out = CO.load(config_dir)
        except OUT.OutputError as exc:
            return page(request, "loi.html", loi=str(exc))
        f = CO.path_for(config_dir)
        ngoai_git = None
        if git.status(root).is_repo:
            ngoai_git = git.is_ignored(root, f)
        chan = OUT.check(out)
        return page(request, "dau-ra.html", out=out, chan=chan,
                    nhac=OUT.warnings(out), file=f, ten_file=CO.FILE,
                    co_file=f.exists(), ngoai_git=ngoai_git,
                    ttl_mac_dinh=OUT.TTL_MAC_DINH,
                    dat=("" if chan else OUT.format_endpoint(out.primary)),
                    dat_sao=(OUT.format_endpoint(out.mirror)
                             if out.mirror and not out.mirror.empty else ""),
                    lenh=("" if chan else _lenh_ra(out)),
                    note=note, err=err)

    @app.post("/dau-ra/luu")
    def luu_dau_ra(dia_chi: str = Form(""), cong: str = Form(""),
                   card: str = Form(""), sao_dia_chi: str = Form(""),
                   sao_cong: str = Form(""), sao_card: str = Form(""),
                   ttl: str = Form("")):
        """Lưu địa chỉ đầu ra.

        **Chặn thì không ghi.** Khác với các trang cấu hình báo hiệu, nơi một
        bản nháp sai vẫn nằm yên trong git cho tới lúc bấm áp dụng — file này
        được `vtcsi run` đọc thẳng lúc khởi động. Ghi một địa chỉ hỏng vào đây
        là để sẵn một quả mìn cho lần dựng lại dịch vụ kế tiếp, mà lần đó
        thường xảy ra lúc nửa đêm và vì một lý do khác.
        """
        def so(raw: str) -> int:
            raw = raw.strip()
            return int(raw) if raw.lstrip("-").isdigit() else 0

        sao_dia_chi = sao_dia_chi.strip()
        sao = None
        if sao_dia_chi or so(sao_cong):
            sao = OUT.Endpoint(sao_dia_chi, so(sao_cong), sao_card.strip())

        out = OUT.Output(
            primary=OUT.Endpoint(dia_chi.strip(), so(cong), card.strip()),
            mirror=sao,
            ttl=so(ttl) or OUT.TTL_MAC_DINH,
        )
        loi = OUT.check(out)
        if loi:
            return back("/dau-ra", err=" · ".join(loi))
        CO.save(out, config_dir)
        cai = OUT.format_endpoint(out.primary)
        if sao is not None:
            cai += " và " + OUT.format_endpoint(sao)
        return back("/dau-ra", note=f"đã lưu đầu ra: {cai} · có hiệu lực từ "
                                    "lần khởi động lại tiến trình phát")

    # ----------------------------------------------------------- git

    @app.get("/thay-doi", response_class=HTMLResponse)
    def changes(request: Request, note: str = "", err: str = ""):
        return page(request, "changes.html", diff=git.diff(root), note=note, err=err)

    @app.post("/thay-doi/commit")
    def do_commit(author: str = Form(""), message: str = Form("")):
        rel = str(config_dir.relative_to(root)) if config_dir.is_relative_to(root) \
            else str(config_dir)
        ok, info = git.commit(root, message, author, [rel])
        return back("/thay-doi", note=info if ok else "", err="" if ok else info)

    return app


def _rebuild_nit(cfg: Config) -> Config:
    """Dựng lại ``service_list`` trong NIT từ danh sách dịch vụ — FR-3.

    Không làm bước này thì thêm kênh vào SDT mà NIT không biết, và đầu thu sẽ
    không lưu kênh đó sau khi dò. Đúng lỗi đã làm Barrowa mất 26 kênh.
    """
    from dataclasses import replace

    from vtcsi.model.entities import ServiceRef

    by_ts = {s.ts_id: s for s in cfg.sdts}
    loops = []
    for loop in cfg.network.ts_loops:
        sdt = by_ts.get(loop.ts_id)
        if sdt is not None:
            loop = replace(loop, services=tuple(
                ServiceRef(s.service_id, int(s.service_type)) for s in sdt.services))
        loops.append(loop)
    return replace(cfg, network=replace(cfg.network, ts_loops=tuple(loops)))

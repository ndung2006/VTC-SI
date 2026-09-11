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

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from vtcsi.config import git, loader
from vtcsi.model import version as V
from vtcsi.model.entities import Config, RunningStatus, Service, ServiceType
from vtcsi.model.plain import ConfigError

BASE = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE / "templates"))


def create_app(config_dir: Path, repo_root: Path | None = None) -> FastAPI:
    app = FastAPI(title="vtcsi", docs_url=None, redoc_url=None)
    root = repo_root or config_dir.parent

    def load() -> Config:
        return loader.load(config_dir)

    def page(request: Request, name: str, **ctx) -> HTMLResponse:
        ctx.setdefault("git", git.status(root))
        ctx.setdefault("config_dir", config_dir)
        return templates.TemplateResponse(request, name, ctx)

    def back(to: str, note: str = "", err: str = "") -> RedirectResponse:
        from urllib.parse import urlencode
        q = urlencode({k: v for k, v in (("note", note), ("err", err)) if v})
        return RedirectResponse(f"{to}?{q}" if q else to, status_code=303)

    # ---------------------------------------------------------------- trang

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request, note: str = "", err: str = ""):
        cfg = load()
        return page(request, "home.html", cfg=cfg, note=note, err=err,
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
            return back("/", err=f"khong co TS {ts_id}")
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
            return back(f"/ts/{ts_id}", err=f"khong co dich vu {service_id}")
        return page(request, "service.html", cfg=cfg, sdt=sdt, svc=svc, err=err,
                    new=False)

    @app.get("/ts/{ts_id}/new", response_class=HTMLResponse)
    def new_service(request: Request, ts_id: int, err: str = ""):
        cfg = load()
        sdt = next((s for s in cfg.sdts if s.ts_id == ts_id), None)
        if sdt is None:
            return back("/", err=f"khong co TS {ts_id}")
        blank = Service(service_id=0, name="", provider="",
                        service_type=ServiceType.DIGITAL_TELEVISION)
        return page(request, "service.html", cfg=cfg, sdt=sdt, svc=blank, err=err,
                    new=True)

    # ---------------------------------------------------------------- ghi

    def _save(cfg: Config) -> list[str]:
        written = loader.save(cfg, config_dir)
        return [str(p.relative_to(root)) for p in written]

    @app.post("/ts/{ts_id}/service/save")
    def save_service(
        ts_id: int,
        service_id: int = Form(...),
        name: str = Form(""),
        provider: str = Form(""),
        service_type: int = Form(1),
        eit_pf: bool = Form(False),
        eit_schedule: bool = Form(False),
        free_ca_mode: bool = Form(False),
        creating: bool = Form(False),
    ):
        cfg = load()
        sdt = next((s for s in cfg.sdts if s.ts_id == ts_id), None)
        if sdt is None:
            return back("/", err=f"khong co TS {ts_id}")

        existing = {x.service_id for x in sdt.services}
        if creating and service_id in existing:
            return back(f"/ts/{ts_id}/new", err=f"dich vu {service_id} da ton tai")
        if not creating and service_id not in existing:
            return back(f"/ts/{ts_id}", err=f"khong co dich vu {service_id}")
        if not name.strip():
            where = f"/ts/{ts_id}/new" if creating else \
                f"/ts/{ts_id}/service/{service_id}"
            return back(where, err="ten dich vu khong duoc de trong")

        made = Service(
            service_id=service_id, name=name.strip(), provider=provider.strip(),
            service_type=ServiceType(service_type),
            running_status=RunningStatus.RUNNING,
            free_ca_mode=free_ca_mode, eit_pf=eit_pf, eit_schedule=eit_schedule,
        )
        others = [x for x in sdt.services if x.service_id != service_id]
        services = tuple(sorted(others + [made], key=lambda x: x.service_id))

        from dataclasses import replace
        cfg = replace(cfg, sdts=tuple(
            replace(s, services=services) if s.ts_id == ts_id else s for s in cfg.sdts))
        try:
            _save(_rebuild_nit(cfg))
        except ConfigError as exc:
            return back(f"/ts/{ts_id}", err=str(exc))
        verb = "them" if creating else "sua"
        return back(f"/ts/{ts_id}", note=f"da {verb} dich vu {service_id}")

    @app.post("/ts/{ts_id}/service/{service_id}/delete")
    def delete_service(ts_id: int, service_id: int, confirm_name: str = Form("")):
        cfg = load()
        sdt = next((s for s in cfg.sdts if s.ts_id == ts_id), None)
        svc = next((x for x in sdt.services if x.service_id == service_id), None) \
            if sdt else None
        if svc is None:
            return back(f"/ts/{ts_id}", err=f"khong co dich vu {service_id}")
        if confirm_name.strip() != svc.name:
            return back(f"/ts/{ts_id}/service/{service_id}",
                        err="go dung ten kenh de xac nhan xoa")

        from dataclasses import replace
        kept = tuple(x for x in sdt.services if x.service_id != service_id)
        cfg = replace(cfg, sdts=tuple(
            replace(s, services=kept) if s.ts_id == ts_id else s for s in cfg.sdts))
        # Bo khoi moi bouquet, neu khong from_plain se tu choi.
        bouquets = []
        for b in cfg.bouquets:
            loops = []
            for t in b.ts_loops:
                if t.ts_id == ts_id:
                    t = replace(
                        t,
                        services=tuple(r for r in t.services if r.service_id != service_id),
                        lcn=tuple(e for e in t.lcn if e.service_id != service_id))
                loops.append(t)
            bouquets.append(replace(b, ts_loops=tuple(loops)))
        cfg = replace(cfg, bouquets=tuple(bouquets))

        _save(_rebuild_nit(cfg))
        return back(f"/ts/{ts_id}",
                    note=f"da xoa dich vu {service_id} '{svc.name}' khoi TS va moi bouquet")

    # ------------------------------------------------------------- version

    @app.post("/version/bump")
    def bump(table: str = Form(...), confirm: str = Form("")):
        if confirm != "TANG":
            return back("/", err="go TANG de xac nhan")
        cfg = load()
        from dataclasses import replace
        if table == "nit":
            cfg = replace(cfg, network=replace(
                cfg.network, version=V.next_version(cfg.network.version)))
            what = f"NIT -> {cfg.network.version}"
        elif table.startswith("sdt:"):
            ts_id = int(table.split(":")[1])
            cfg = replace(cfg, sdts=tuple(
                replace(s, version=V.next_version(s.version)) if s.ts_id == ts_id else s
                for s in cfg.sdts))
            what = f"SDT ts{ts_id}"
        elif table.startswith("bat:"):
            bid = int(table.split(":")[1], 16)
            cfg = replace(cfg, bouquets=tuple(
                replace(b, version=V.next_version(b.version)) if b.bouquet_id == bid else b
                for b in cfg.bouquets))
            what = f"BAT {bid:04x}"
        else:
            return back("/", err=f"bang la: {table}")
        _save(cfg)
        return back("/", note=f"da tang version {what}")

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

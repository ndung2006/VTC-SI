"""Trông chừng tiến trình ``tsp`` — vỏ, với phần quyết định là hàm thuần.

Phạm vi hẹp hơn cái tên gợi ý, và điều đó là cố ý.

**Nó không làm gì với hệ ngang hàng.** Hai hệ không nói chuyện với nhau: chuyển
nguồn là việc của mux, còn đồng bộ là việc của git (§3.3 ``spec.md``). Mọi
giao thức cụm — bầu vai trò, heartbeat, chống hai máy cùng phát — đều vắng mặt
ở đây vì chúng chính là thứ đẻ ra tình trạng *"Config changed on both"* của
Barrowa. Cái gì không có thì không hỏng được.

**Nó cũng không khởi động lại khi nội dung đổi.** Đây là điểm dễ hiểu sai nhất.
``inject --poll-files`` và ``eitinject --poll-interval`` tự đọc lại file XML
khi file thay đổi, nên sửa tên kênh, sửa số kênh, nạp lịch mới — tất cả đều
**không cần** dựng lại tiến trình. Chỉ khi *dòng lệnh* đổi (thêm TS, đổi địa
chỉ phát, đổi trần bitrate) mới phải khởi động lại. Phân biệt được hai thứ đó
là khác biệt giữa một lần sửa kênh êm ru và một lần chớp nguồn làm mux nhảy
sang hệ kia.

Vậy nó làm gì:

* Dựng ``tsp``, trông, và dựng lại khi chết — có giãn cách tăng dần.
* **Tính lại ``--time`` mỗi lần dựng.** ``eitinject`` lấy mốc thời gian từ đối
  số dòng lệnh vì luồng ta không có TDT/TOT. Dùng lại mốc cũ sau ba ngày nghĩa
  là phát EPG lệch ba ngày — hỏng im lặng, đúng loại tệ nhất.
* Từ chối dựng khi thiếu file đầu vào, thay vì để ``tsp`` chết rồi thử lại mãi.
* Chạy định kỳ lệnh sinh lại bảng và EIT, nếu được giao. Không có bước này thì
  cửa sổ 8 ngày cạn dần rồi hết sạch — lại một kiểu hỏng im lặng.
* Ghi lại mọi lần chuyển trạng thái. Câu hỏi *"đêm qua nó có chớp không"* phải
  trả lời được bằng cách đọc log, không phải bằng cách đoán.

**Không bao giờ bỏ cuộc.** Một thiết bị dự phòng ngừng thử là thiết bị tệ hơn
một thiết bị thử chậm. Giãn cách chặn trên ở 30 giây và cứ thế mãi; cái thay
đổi khi hỏng liên tục là **mức ồn của log** và trạng thái báo ra ngoài, không
phải việc có thử nữa hay không.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from vtcsi.pipeline.tspbuild import Plan, build, shell

# ---------------------------------------------------------------------------
# Phần thuần — quyết định. Không đọc đồng hồ, không chạm tiến trình.
# ---------------------------------------------------------------------------

MIN_HEALTHY_SECONDS = 30.0
"""Chạy được quá ngần này thì coi là đã dựng thành công.

Ranh giới giữa "chết khi khởi động" và "chết lúc đang chạy". Cái đầu gần như
luôn là lỗi cấu hình và sẽ lặp lại; cái sau thường là sự cố nhất thời. Hai
loại đó đáng được đối xử khác nhau, và đây là chỗ phân biệt.
"""

BACKOFF_STEPS = (1.0, 2.0, 4.0, 8.0, 16.0, 30.0)
"""Giãn cách giữa các lần thử, chặn trên ở 30 giây.

Không cho tăng vô hạn: mux đã lo phần bảo vệ khán giả, việc còn lại của ta là
thử mãi mà không chớp. Một giãn cách 10 phút chỉ khiến hệ dự phòng vắng mặt
đúng lúc cần.
"""

CRASH_LOOP_AFTER = 5
"""Số lần chết-khi-khởi-động liên tiếp trước khi đổi giọng báo động."""


class Outcome(Enum):
    """Vì sao một lần chạy kết thúc."""

    RAN_THEN_DIED = "chay roi chet"
    DIED_ON_STARTUP = "chet khi khoi dong"
    STOPPED_BY_US = "ta dung"


class Health(Enum):
    STARTING = "dang dung"
    RUNNING = "dang chay"
    RETRYING = "dang thu lai"
    CRASH_LOOPING = "chet lap"
    STOPPED = "da dung"


@dataclass(frozen=True, slots=True)
class Attempt:
    """Một lần chạy đã kết thúc."""

    started_at: float
    ended_at: float
    exit_code: int | None
    outcome: Outcome

    @property
    def lifetime(self) -> float:
        return self.ended_at - self.started_at


def classify(started_at: float, ended_at: float, exit_code: int | None,
             stopped_by_us: bool) -> Attempt:
    """Xếp loại một lần chạy vừa kết thúc. Thuần: mốc thời gian truyền vào."""
    if stopped_by_us:
        outcome = Outcome.STOPPED_BY_US
    elif ended_at - started_at >= MIN_HEALTHY_SECONDS:
        outcome = Outcome.RAN_THEN_DIED
    else:
        outcome = Outcome.DIED_ON_STARTUP
    return Attempt(started_at, ended_at, exit_code, outcome)


def consecutive_startup_failures(history: Sequence[Attempt]) -> int:
    """Đếm ngược từ cuối, dừng ở lần chạy nào sống đủ lâu.

    Một lần chạy khoẻ **xoá sạch** bộ đếm. Nếu không thì một hệ chạy tốt sáu
    tháng rồi chết hai lần sẽ bị xếp cùng loại với một hệ không bao giờ dựng
    nổi, và giãn cách sẽ dài vô lý đúng lúc cần nhanh.
    """
    n = 0
    for attempt in reversed(history):
        if attempt.outcome is not Outcome.DIED_ON_STARTUP:
            break
        n += 1
    return n


def backoff(failures: int) -> float:
    """Chờ bao lâu trước lần thử kế tiếp."""
    if failures <= 0:
        return 0.0
    return BACKOFF_STEPS[min(failures, len(BACKOFF_STEPS)) - 1]


def health(history: Sequence[Attempt], running: bool) -> Health:
    if running:
        return Health.RUNNING
    failures = consecutive_startup_failures(history)
    if failures >= CRASH_LOOP_AFTER:
        return Health.CRASH_LOOPING
    if failures:
        return Health.RETRYING
    return Health.STOPPED if history else Health.STARTING


def command_changed(old: Sequence[str] | None, new: Sequence[str]) -> bool:
    """Dòng lệnh có khác tới mức phải dựng lại không.

    Bỏ qua ``--time``: mốc đó tính lại mỗi lần dựng nên **luôn** khác, và nếu
    tính cả nó thì mọi lần soi đều bảo "phải khởi động lại" — tiến trình sẽ bị
    dựng lại liên tục, đúng thứ ta muốn tránh nhất.
    """
    if old is None:
        return True
    return _without_time(old) != _without_time(new)


def _without_time(cmd: Sequence[str]) -> list[str]:
    out: list[str] = []
    skip = False
    for arg in cmd:
        if skip:
            skip = False
            continue
        if arg == "--time":
            skip = True
            continue
        out.append(arg)
    return out


def missing_inputs(plan: Plan, exists: Callable[[str], bool]) -> list[str]:
    """File bảng nào đang thiếu. ``exists`` truyền vào để test không cần đĩa.

    Mẫu có ký tự đại diện được bỏ qua: ``bat-*.xml`` và ``eit/*.xml`` do
    ``tsp`` tự nở, và một thư mục EIT rỗng là hợp lệ — hệ vẫn phát NIT/SDT/BAT
    đúng, chỉ là không có chương trình. Thà lên sóng thiếu EPG còn hơn không
    lên sóng.
    """
    wanted = [plan.nit.path] + [i.path for i in plan.sdt_bat]
    return [p for p in wanted if "*" not in p and "?" not in p and not exists(p)]


# ---------------------------------------------------------------------------
# Vỏ — chạy thật.
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Child:
    """Tiến trình con đang chạy, cùng dòng lệnh đã dựng nó."""

    process: subprocess.Popen
    command: list[str]
    started_at: float


def _stamp() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def log(message: str, *, stream=None) -> None:
    """Một dòng, có mốc thời gian, ra stderr.

    stderr chứ không phải stdout: Docker và Coolify gom cả hai, nhưng khi ai đó
    chạy tay và chuyển hướng stdout vào file thì phần nhật ký vẫn phải thấy
    được trên màn hình.
    """
    print(f"{_stamp()}  {message}", file=stream or sys.stderr, flush=True)


@dataclass(slots=True)
class Supervisor:
    """Vòng đời của một tiến trình ``tsp``.

    Mọi hiệu ứng phụ đi qua bốn thứ tiêm vào — ``spawn``, ``now``, ``sleep``,
    ``exists`` — nên toàn bộ vòng lặp test được mà không cần dựng tiến trình
    thật, không cần chờ thật, và không cần đĩa. Đó là lý do ``tests/test_supervise``
    chạy trong mấy phần nghìn giây.
    """

    plan: Plan
    refresh: tuple[str, ...] = ()
    """Lệnh sinh lại bảng và EIT. Rỗng nghĩa là không tự sinh lại."""

    watch: tuple[Path, ...] = ()
    """Thư mục cần theo dõi — hộp thư lịch và thư mục cấu hình.

    Có gì đổi trong đó là **sinh lại ngay**, không chờ chu kỳ. Đây mới là cách
    đúng: file lịch mới bàn giao về lúc 8 giờ sáng thì phải lên sóng lúc 8 giờ
    sáng, không phải lúc 9 giờ.
    """

    watch_every: float = 5.0
    """Bao lâu ngó thư mục một lần. Rẻ: chỉ đọc mốc sửa file, không đọc nội dung."""

    refresh_every: float = 3600.0
    """Lưới an toàn, không phải cơ chế chính.

    Cửa sổ EIT trôi theo thời gian ngay cả khi **không** có file mới: ngày cũ
    rụng khỏi đầu cửa sổ, ngày mới lọt vào cuối. Một giờ là đủ dày cho chuyện
    đó. Việc bắt file mới là của ``watch``.
    """

    restart_grace: float = 2.0
    """Chờ ``tsp`` tự thoát trước khi giết."""

    spawn: Callable[[list[str]], subprocess.Popen] = None  # type: ignore[assignment]
    now: Callable[[], float] = time.monotonic
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    sleep: Callable[[float], None] = time.sleep
    exists: Callable[[str], bool] = lambda p: Path(p).exists()
    run_refresh: Callable[[tuple[str, ...]], tuple[int, str]] = None  # type: ignore[assignment]

    history: list[Attempt] = field(default_factory=list)
    child: Child | None = None
    stopping: bool = False
    _last_refresh: float = 0.0
    _last_look: float = 0.0
    _fingerprint: tuple = ()

    def __post_init__(self) -> None:
        if self.spawn is None:
            self.spawn = _spawn
        if self.run_refresh is None:
            self.run_refresh = _run_refresh

    # ------------------------------------------------------------ trạng thái

    @property
    def state(self) -> Health:
        return health(self.history, self.child is not None)

    def command(self) -> list[str]:
        """Dòng lệnh cho **lần dựng này**, với mốc thời gian tính lại."""
        return build(self.plan, start_time=self.clock())

    # ------------------------------------------------------------ vòng đời

    def start(self) -> bool:
        """Dựng ``tsp``. Trả về ``False`` nếu chưa đủ điều kiện để dựng."""
        gap = missing_inputs(self.plan, self.exists)
        if gap:
            log(f"KHONG DUNG: thieu {len(gap)} file bang — "
                + ", ".join(gap[:3]) + ("…" if len(gap) > 3 else ""))
            log("  chay `vtcsi build --out <thu muc>` truoc.")
            return False

        cmd = self.command()
        log(f"dung tsp · {self.plan.output.destination}")
        log(f"  {shell(cmd)}")
        self.child = Child(self.spawn(cmd), cmd, self.now())
        return True

    def reap(self) -> Attempt | None:
        """Con đã chết chưa. Không chặn."""
        if self.child is None:
            return None
        code = self.child.process.poll()
        if code is None:
            return None
        attempt = classify(self.child.started_at, self.now(), code, self.stopping)
        self.history.append(attempt)
        self.child = None
        log(f"tsp ket thuc · ma {code} · {attempt.outcome.value} · "
            f"song {attempt.lifetime:.0f}s")
        return attempt

    def stop(self) -> None:
        """Dừng con, lịch sự trước rồi mới cứng rắn."""
        if self.child is None:
            return
        self.stopping = True
        proc = self.child.process
        log("dung tsp…")
        try:
            proc.terminate()
            proc.wait(timeout=self.restart_grace)
        except subprocess.TimeoutExpired:
            log("tsp khong tu thoat — giet")
            proc.kill()
            try:
                proc.wait(timeout=self.restart_grace)
            except subprocess.TimeoutExpired:  # pragma: no cover
                log("CANH BAO: khong giet duoc tsp")
        except Exception as exc:  # pragma: no cover
            log(f"loi khi dung tsp: {exc}")
        self.reap()
        self.stopping = False

    # ------------------------------------------------------------ sinh lại

    def _look(self) -> tuple:
        """Dấu vân tay của những thư mục đang theo dõi.

        Số file, mốc sửa mới nhất, tổng dung lượng. Không băm nội dung: đọc
        vài megabyte XML mỗi năm giây là lãng phí, và ba con số này đã đủ bắt
        mọi thay đổi thật. Trường hợp duy nhất lọt là ghi đè một file bằng nội
        dung khác mà **cùng dung lượng và cùng mốc thời gian** — chu kỳ một
        giờ lo nốt.
        """
        so, moi_nhat, tong = 0, 0.0, 0
        for thu_muc in self.watch:
            try:
                for f in thu_muc.rglob("*"):
                    if not f.is_file():
                        continue
                    st = f.stat()
                    so += 1
                    moi_nhat = max(moi_nhat, st.st_mtime)
                    tong += st.st_size
            except OSError:
                continue
        return (so, moi_nhat, tong)

    def maybe_refresh(self) -> bool:
        """Chạy lệnh sinh lại nếu cần. Trả về ``True`` nếu vừa chạy.

        Ba lý do để chạy, theo thứ tự quan trọng:

        1. **Chưa chạy lần nào** — phải có bảng trước khi dựng ``tsp``.
        2. **Có gì đổi trong thư mục đang theo dõi** — file lịch mới về, hoặc
           ai đó sửa YAML bằng tay. Lên sóng trong vòng ``watch_every`` giây.
        3. **Tới hạn chu kỳ** — cửa sổ EIT trôi theo thời gian dù không có file
           mới nào.

        Thất bại **không** làm dừng phát sóng: file cũ vẫn còn trên đĩa và
        ``tsp`` vẫn phát chúng. Bảng hôm qua còn hơn không có bảng nào.
        """
        if not self.refresh:
            return False
        t = self.now()
        lan_dau = not self._last_refresh

        vi_sao = ""
        if lan_dau:
            vi_sao = "lan dau"
        else:
            if self.watch and t - self._last_look >= self.watch_every:
                self._last_look = t
                dau = self._look()
                if dau != self._fingerprint:
                    self._fingerprint = dau
                    vi_sao = "co thay doi trong thu muc theo doi"
            if not vi_sao and t - self._last_refresh >= self.refresh_every:
                vi_sao = "toi han chu ky"
        if not vi_sao:
            return False

        self._last_refresh = t
        if lan_dau:
            self._last_look = t
            self._fingerprint = self._look()
        code, output = self.run_refresh(self.refresh)
        if code == 0:
            log(f"sinh lai bang va EIT ({vi_sao}): xong")
        else:
            log(f"CANH BAO: sinh lai that bai, ma {code} ({vi_sao}) — "
                f"van phat file cu")
            for line in output.strip().splitlines()[-5:]:
                log(f"  {line}")
        return True

    # ------------------------------------------------------------ vòng lặp

    def run(self, *, until: Callable[[], bool] | None = None) -> int:
        """Vòng lặp chính.

        ``until`` trả về ``True`` thì thoát; test truyền vào để chạy đúng vài
        vòng. Khi không truyền, chỉ tín hiệu hệ điều hành mới dừng được.
        """
        self._asked_to_stop = False
        self._install_signals()
        stop_now = until or (lambda: self._asked_to_stop)

        self.maybe_refresh()

        while not stop_now():
            if self.child is None:
                if not self.start():
                    # Thieu file dau vao. Doi theo dung thang giãn cách như
                    # khi tsp chet, chu khong quay vong khong — quay vong
                    # khong se lam day log va an het CPU.
                    self.history.append(
                        classify(self.now(), self.now(), None, False))
                    self._wait(backoff(consecutive_startup_failures(self.history)),
                               stop_now)
                continue

            attempt = self.reap()
            if attempt is None:
                self.maybe_refresh()
                self._wait(min(1.0, self.watch_every), stop_now)
                continue

            if attempt.outcome is Outcome.STOPPED_BY_US:
                break

            failures = consecutive_startup_failures(self.history)
            if failures == CRASH_LOOP_AFTER:
                log(f"CHET LAP: {failures} lan chet khi khoi dong lien tiep. "
                    f"Van se thu tiep mai, nhung hay xem lai cau hinh.")
            delay = backoff(failures)
            if delay:
                log(f"thu lai sau {delay:.0f}s (lan hong lien tiep thu {failures})")
            self._wait(delay, stop_now)

        self.stop()
        log(f"da dung han · {len(self.history)} lan chay trong phien nay")
        return 0

    def _wait(self, seconds: float, stop_now: Callable[[], bool]) -> None:
        """Ngủ thành lát mỏng để tín hiệu dừng không phải chờ hết giãn cách."""
        left = seconds
        while left > 0 and not stop_now():
            step = min(0.5, left)
            self.sleep(step)
            left -= step

    _asked_to_stop: bool = False

    def _install_signals(self) -> None:
        def handler(signum, _frame):  # pragma: no cover — khó test cho tử tế
            log(f"nhan tin hieu {signum} — dung tu te")
            self._asked_to_stop = True

        for name in ("SIGTERM", "SIGINT", "SIGBREAK"):
            sig = getattr(signal, name, None)
            if sig is None:
                continue
            try:
                signal.signal(sig, handler)
            except (ValueError, OSError):  # pragma: no cover
                pass  # khong phai luong chinh — bo qua


def _spawn(cmd: list[str]) -> subprocess.Popen:
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=None,
                            env={**os.environ})


def _run_refresh(cmd: tuple[str, ...]) -> tuple[int, str]:
    r = subprocess.run(list(cmd), capture_output=True, text=True, timeout=600,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")

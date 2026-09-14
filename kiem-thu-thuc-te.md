# Kiểm thử thực tế — năm bậc, tăng dần theo rủi ro

> Đi kèm `spec.md` 1.0. Nguyên tắc xuyên suốt: **mỗi bậc chỉ leo khi bậc dưới đã xanh**,
> và mỗi bậc đều có đường lui rõ ràng.

Hai bậc đầu **không đụng gì tới hệ đang chạy**. Chúng cũng là hai bậc bắt được
nhiều lỗi nhất. Đừng vội nhảy lên bậc ba.

---

## Bậc 0 — không đụng mạng, không đụng mux

Chỉ cần một máy Linux và TSDuck. Đây là bậc **quan trọng nhất** vì nó mở khoá
phép so byte, thứ mọi bài test hiện tại chưa làm được.

### 0.0 Giao diện nhập liệu

Không đụng mạng, không cần TSDuck. Làm trước tất cả, vì đây là chỗ ta sẽ ngồi
mỗi lần thêm kênh.

```bash
git init && git add . && git commit -m "gieo cau hinh tu song"   # LAM TRUOC
pip install -e ".[web]"
vtcsi passwd                   # dat mat khau — BAT BUOC, chi lam tu terminal
vtcsi web                      # http://127.0.0.1:8080
```

Không có mật khẩu thì giao diện **không phục vụ gì**, chỉ hiện hướng dẫn. Cũng
không có trang "tạo tài khoản lần đầu" trên web: trang đó nghĩa là *ai chạm tới
cổng trước thì người đó làm chủ*. Quyền shell trên máy phát mới là ranh giới thật.

Quên mật khẩu thì `vtcsi passwd --force`. Không có đường phục hồi qua trình duyệt.

`git init` **trước**, không phải sau. Bản gieo từ sóng là thứ duy nhất ta biết
chắc là đúng; chưa commit nó thì không còn chỗ nào để quay về.

Thử đúng một vòng như thật:

| Bước | Kỳ vọng |
|---|---|
| Đổi tên một kênh rồi lưu | `Thay đổi` hiện đúng **một** file `services/tsN.yaml` |
| Thêm một kênh | Xuất hiện ở SDT **và** ở `service_list` của NIT — FR-3 |
| Xoá kênh đó, gõ sai tên | Bị từ chối, kênh còn nguyên |
| Xoá kênh đó, gõ đúng tên | Biến khỏi SDT, khỏi NIT, khỏi mọi bouquet |
| `vtcsi preflight <dump>.xml` | Báo **cả NIT lẫn SDT** cần tăng version |
| Tăng hai version ở trang tổng quan | `10/10 bảng không có vấn đề` |
| `git diff` | Đọc được, không nhiễu — chỉ đúng chỗ đã sửa |

**Chỗ đáng nghi ngờ nhất:** lưu lại một kênh mà *không đổi gì* phải khiến
`git diff` **trống**. Nếu nó xáo file, `git diff` thành vô dụng, và cơ chế đồng
bộ giữa hai hệ thống mất tác dụng theo. `tests/test_web.py` canh điều này, nhưng
hãy tự mắt nhìn một lần.

**Rủi ro:** không, nếu đã `git init`. **Lui về:** `git checkout -- config`.

---

### 0.1 Cài TSDuck và chạy lại bộ test

```bash
# Debian/Ubuntu — xem tsduck.io cho bản đúng với bản phân phối
sudo apt install tsduck        # hoặc build tu nguon, xem muc B10 spec.md

pytest
```

**Đã đạt — 11/09/2026.** Mười bài đó nay xanh: `562 passed, 0 skipped`.
NIT, ba SDT và sáu BAT sinh từ cấu hình **giống từng byte** với bảng bóc từ
sóng. Đó là AC-1 và AC-2, chứng minh ở mức byte chứ không phải mức XML.

**Bài học đắt nhất của bước này:** TSDuck đã cài sẵn từ đầu, nhưng
`shutil.which("tstabcomp")` không thấy vì nó nằm ngoài `PATH` của Git Bash —
PowerShell thì thấy. Bảy bài quan trọng nhất đã **ngủ yên nhiều phiên** vì thế,
và trong báo cáo pytest chúng in ra chữ `s` xám y hệt như khi chưa cài gì.
Nay `tests/tsduck_path.py` tự tìm ở những chỗ TSDuck thường nằm, và khi không
thấy thì nói rõ đã tìm ở đâu.

**Đạt khi:** 10 bài đang `skipped` chuyển thành `passed`. Bảy bài so **byte thật**
giữa bảng ta sinh và bảng bóc từ sóng; ba bài kiểm mọi tuỳ chọn dòng lệnh tôi
đã ghim có tồn tại thật trong `tsp` hay không.

**Nếu đỏ:** đó là tin tốt — nghĩa là có sai lệch mà tầng XML không thấy. Thông báo
lỗi chỉ đúng **byte thứ mấy** bắt đầu lệch, kèm 12 byte quanh đó của cả hai bên.

### 0.2 Sinh bảng và bắt TSDuck biên dịch

```bash
vtcsi build --out build
tstabcomp --compile build/nit.xml --output build/nit.bin
```

**Đạt khi:** biên dịch trót lọt, không cảnh báo. Đây là lần đầu TSDuck nói cho ta
biết lược đồ XML của ta có hợp lệ không.

### 0.3 Sinh EIT từ file lịch

```bash
mkdir -p epg/inbox && cp "<file lịch>.xml" epg/inbox/2026-09-08.xml
vtcsi epg --inbox epg/inbox --out build/eit/eit.xml
```

**Đạt khi:** ra đúng số bảng bằng số kênh có lịch trong file. Chú ý dòng cảnh báo
cuối — với một file một ngày thì cả 44 kênh đều dưới ngưỡng 120 giờ, và đó là
đúng.

### 0.35 Để `vtcsi run` dựng dòng lệnh thay bạn

```bash
vtcsi refresh --out build --inbox epg/inbox --eit-out build/eit/eit.xml
vtcsi run --to 236.30.239.1:6000 --local-address 10.10.30.240 --dry-run
```

`--dry-run` **in dòng lệnh rồi thoát**, không mở socket nào. Số TS actual, danh
sách TS khác và chu kỳ lặp đều lấy từ cấu hình, nên không còn chỗ để gõ nhầm.

**Đạt khi:** dòng lệnh in ra có `sdt-ts8.xml=1000` (actual, 1 s) và
`sdt-ts3.xml=5000` cùng `sdt-ts1000.xml=5000` (các TS khác, 5 s), và **không**
có `sdt-ts*` ở đâu cả — ký tự đại diện đó sẽ nuốt luôn file actual và nạp nó
hai lần.

Nếu thiếu file bảng, lệnh báo `THIEU: …` và thoát mã 1 thay vì dựng `tsp` để
nó chết.

### 0.4 Chạy pipeline ra **file**, không ra mạng

Lấy dòng lệnh từ `tspbuild`, đổi `-O ip ...` thành `-O file`:

```bash
tsp -I null \
    -P inject --pid 16 --bitrate 20000 --poll-files build/nit.xml=2000 \
    -P inject --pid 17 --bitrate 60000 --poll-files \
       build/sdt-ts8.xml=1000 build/sdt-ts3.xml=5000 build/sdt-ts1000.xml=5000 \
       'build/bat-*.xml=5000' \
    -P eitinject --pid 18 --files 'build/eit/*.xml' --ts-id 8 \
       --time 2026/09/11:10:00:00 --actual --wait-first-batch \
    -P regulate --bitrate 2000000 \
    -O file build/thu-nghiem.ts
```

Để chạy chừng hai phút rồi `Ctrl-C`.

### 0.5 Vòng khép kín hoàn toàn ngoại tuyến

```bash
tsanalyze build/thu-nghiem.ts
tstables build/thu-nghiem.ts --all-sections --xml-output build/doc-lai.xml
vtccmp compare build/doc-lai.xml "Bang mau/dvb_tables_dump_win.xml"
```

**Đây là phép thử đáng giá nhất của cả giai đoạn.** Ta sinh ra một luồng, đọc
ngược nó bằng đúng công cụ đã dùng để đo sóng thật, rồi so với sóng thật —
toàn bộ trên một máy, không ảnh hưởng ai.

**Đạt khi:**

| Kiểm | Ngưỡng |
|---|---|
| `vtccmp compare` | **khớp** |
| Số PID trong luồng | đúng 4: `16`, `17`, `18`, `0x1FFF` |
| Bitrate PID 16 | ≈ **2,9 kbps** |
| Bitrate PID 17 | ≈ **18,8 kbps** |
| Bitrate PID 18 | ≈ **139 kbps** |
| Lỗi TR 101 290 mức 1 | **0**, trừ "thiếu PAT" — cái đó là cố ý |
| Lỗi continuity counter | **0** |

Nếu bitrate lệch xa, chỉnh `--bitrate` của `inject` tương ứng. Đó là **trần**,
không phải mục tiêu; chật quá thì section bị hoãn, rộng quá thì chỉ tốn null.

**Rủi ro:** không. **Lui về:** xoá `build/`.

---

## Bậc 1 — phát ra mạng, chưa ai nhận

```bash
# thay -O file bang -O ip, dia chi CHUA AI DUNG
... -O ip --packet-burst 7 --enforce-burst \
          --local-address 10.10.30.240 --ttl 8 236.30.239.1:6000
```

Từ **một máy khác** trong cùng mạng:

```bash
tstables --ip-udp 236.30.239.1:6000 --pid 16 --pid 17 --pid 18 \
         --all-sections --xml-output thu-tu-mang.xml --duration 120
vtccmp compare thu-tu-mang.xml "Bang mau/dvb_tables_dump_win.xml"
```

**Đạt khi:** vẫn khớp, và máy thứ hai thu được — chứng tỏ multicast thật sự ra
khỏi máy.

**Ba cái bẫy ở bậc này**, đều đã ghi trong `spec.md` B6: container Docker phải
`network_mode: host`; `--local-address` phải đúng card; TTL mặc định của hệ điều
hành là **1** nên không qua nổi router đầu tiên.

**Rủi ro:** thấp — chỉ thêm ~170 kbps multicast vào mạng. Chọn địa chỉ chưa ai
dùng và hỏi bên mạng trước. **Lui về:** `Ctrl-C`.

---

## Bậc 2 — đầu thu thật, trong phòng lab

Cần một đường ra sóng thử: một bộ điều chế DVB-S2 trong lab, hoặc một mux thử
ghép luồng SI của ta với vài kênh A/V.

Đây là bậc duy nhất trả lời được những câu mà không máy móc nào thay thế được:

| Kiểm | Đạt khi |
|---|---|
| Dò kênh | Ra đủ **64 dịch vụ** trên TSID 8 |
| Số kênh | LCN đúng thứ tự, kênh 1 là `HA NOI 1` |
| Tên kênh | Không lỗi phông, không ký tự lạ |
| **Tiêu đề EPG tiếng Việt** | Hiện đúng dấu — đây là chỗ rủi ro `0x15` ở RO-3 |
| EPG now/next | Đúng chương trình đang phát |
| EPG 8 ngày | Có, không thủng đoạn |
| Gói kênh | Bouquet hiện đúng |

**Làm trên đúng những model đầu thu đang lưu hành**, không phải trên phần mềm
giả lập. Ghi lại model nào thử rồi, kết quả ra sao — đó là bảng chứng cứ cho
quyết định chuyển đổi sau này.

**Rủi ro:** không ảnh hưởng khách hàng. **Lui về:** tắt máy phát thử.

---

## Bậc 3 — đấu vào mux làm input thứ hai, chưa chuyển sang

Cấu hình ProStream nhận địa chỉ multicast của ta làm **input dự phòng**. Nguồn
chính vẫn là Barrowa. Chưa chuyển.

**Trước khi đấu, bắt buộc:**

```bash
vtccmp capture udp://236.30.230.1:6000 --out truoc-khi-dau.xml   # in lenh
# ... chay lenh do, roi:
vtcsi preflight truoc-khi-dau.xml
```

**Đạt khi:** `10/10 bảng không có vấn đề`. Nếu có dòng nào `!!` thì **dừng** —
đặc biệt là `đổi ngầm`, vì đó đúng là tình huống làm đầu thu giữ dữ liệu cũ.

Sau khi đấu, để chạy song song ít nhất **một tuần** và theo dõi:

```bash
vtccmp compare barrowa.xml cua-ta.xml mux-ra.xml --config config
```

**Ba tham số của mux cần chốt ở bậc này** (RO-5): ngưỡng phát hiện mất nguồn;
có tự quay về input ưu tiên không; mux có đánh lại continuity counter ở đầu ra
không.

**Rủi ro:** trung bình. Mux có thể chuyển sang nguồn ta **ngoài ý muốn** nếu
nguồn chính chớp tắt. Vì thế bậc 3 chỉ leo khi bậc 2 đã xanh hết.
**Lui về:** gỡ input dự phòng khỏi cấu hình mux.

---

## Bậc 4 — chuyển đổi thật

Giờ thấp điểm. Có người trực. Có đầu thu thật đang mở để quan sát.

1. Ghi lại trạng thái trước: `vtccmp capture` cả hai nguồn.
2. Rút cáp nguồn chính.
3. Quan sát đầu thu **liên tục trong 15 phút**.
4. Cắm lại. Quan sát tiếp 15 phút.

**Đạt khi — cả bốn điều, không phải ba:**

| | |
|---|---|
| Đầu thu **không** dò lại kênh | Đây là điều quan trọng nhất |
| EPG **không** mất | Cả now/next lẫn lịch dài |
| Hình **không** gián đoạn | |
| Chuyển **ngược lại** cũng sạch như vậy | Nhiều hệ chỉ thử một chiều rồi gặp sự cố ở chiều kia |

**Rủi ro:** cao — ảnh hưởng khách hàng thật. **Lui về:** cắm lại cáp nguồn chính;
nếu mux không tự quay về thì đổi input ưu tiên bằng tay.

---

## Ghi chép — thứ quyết định lần sau có dễ hơn không

Mỗi lần thử, ghi lại bốn thứ vào git cùng ngày giờ: **lệnh đã chạy**, **bản dump
thu được**, **số đo** (bitrate từng PID, lỗi TR 101 290), và **model đầu thu**
đã quan sát.

Bản dump đặc biệt đáng giữ: nó thành chuẩn vàng mới, và `vtccmp compare` dùng
được ngay. Bốn bản dump hiện có trong `Bang mau/` đã đủ để tìm ra ba lỗi đang
phát sóng — bản thứ năm sẽ tìm ra lỗi thứ tư.

---

## Chạy thật bằng `vtcsi run`

Từ bậc 1 trở đi, đừng gõ `tsp` bằng tay nữa — dùng `vtcsi run` không có
`--dry-run`. Nó dựng `tsp`, trông chừng, và dựng lại khi chết.

**Ba điều cần biết trước khi giao cho nó:**

**Sửa nội dung không làm nó khởi động lại.** Đổi tên kênh, đổi số kênh, nạp
lịch mới — `tsp` tự đọc lại file XML. Chỉ khi *dòng lệnh* đổi (thêm TS, đổi
địa chỉ phát) mới phải dựng lại, và lúc đó phải làm bằng tay. Đây là điểm
quan trọng nhất: một lần dựng lại là một lần chớp nguồn, và mux sẽ nhảy sang
hệ kia.

**Nó tự chạy `vtcsi refresh` mỗi giờ.** Không có bước này thì cửa sổ EIT 8 ngày
cạn dần rồi hết sạch. Tắt bằng `--no-refresh` nếu bạn muốn tự lo bằng cron.

**Nó không bao giờ bỏ cuộc.** Giãn cách tăng 1 → 2 → 4 → 8 → 16 → 30 giây rồi
dừng ở đó mãi. Sau 5 lần chết-khi-khởi-động liên tiếp, log đổi giọng thành
`CHET LAP` nhưng **vẫn thử tiếp**. Một thiết bị dự phòng ngừng thử tệ hơn một
thiết bị thử chậm.

**Kiểm tra log sau một đêm:**

```bash
docker logs vtcsi-si 2>&1 | grep -E "dung tsp|ket thuc|CHET LAP|CANH BAO"
```

**Đạt khi:** đúng **một** dòng `dung tsp` từ lúc khởi động, không dòng nào
khác. Mỗi cặp `ket thuc` + `dung tsp` là một lần chớp nguồn.

---

## Chạy thẳng trên Ubuntu hay qua Coolify?

**Dùng Docker, nhưng để Coolify ngoài vòng đời của dịch vụ phát.** Cụ thể:
`docker compose` chạy từ `/srv/vtcsi/repo`, systemd lo việc lên sau khi khởi
động máy. Coolify vẫn chạy song song quản các dịch vụ khác trên cùng máy.

**Vì sao Docker chứ không cài thẳng lên host.** Hai máy ngang hàng phải sinh
ra cùng byte, mà điều đó đòi **cùng một phiên bản TSDuck**. Ảnh container ghim
`3.44-4676` là cách chắc chắn nhất để hai máy không lệch; cài thẳng lên host
cũng ghim được, nhưng một lần `apt upgrade` vô ý trên một máy là hỏng phép so
byte — im lặng, và chỉ lộ ra đúng lúc mux chuyển nguồn.

Docker còn chữa một cái bẫy đã gặp thật: **sửa mã `.py` mà không dựng lại tiến
trình thì code cũ vẫn chạy**, và triệu chứng trông y hệt "tính năng chưa làm".
`docker compose up -d --build` luôn dựng lại.

**Vì sao không giao vòng đời cho Coolify.** Coolify sinh ra cho ứng dụng web
theo mô hình *đẩy code là triển khai lại*. Hệ này ngược hẳn: nó là một nguồn
tín hiệu chạy 24/7, và **mỗi lần dựng lại là một lần chớp nguồn** khiến mux
nhảy sang máy kia. Nút Redeploy nằm sẵn đó là một cú bấm nhầm chờ xảy ra.

Thêm nữa Coolify tự clone kho và `reset --hard` mỗi lần triển khai, trong khi
giao diện thì **commit vào chính kho đó**. Hai mô hình đánh nhau trực tiếp.

Với dịch vụ `si`, Coolify gần như không thêm gì: `restart: unless-stopped` đã
tự dựng lại, `docker logs` đã xem được log. Thứ nó thêm chủ yếu là rủi ro.

Nếu vẫn muốn dùng giao diện Coolify để xem log và bật tắt, thêm nó dưới dạng
**Docker Compose resource với tự động triển khai TẮT**, và đừng nối webhook
của kho.

---

## Dựng trên Ubuntu 24.04

Bản phân phối của máy chủ **không liên quan** tới TSDuck: ảnh container mang
userland riêng (nền `debian:trixie`, vì TSDuck 3.44 chỉ phát hành gói
`debian13`). Thứ duy nhất dùng chung với máy chủ là nhân Linux, và multicast
UDP là tính năng của nhân.

**Không cần cài TSDuck lên máy chủ.** Hệ này không đụng phần cứng nào — đầu
vào là `-I null`, đầu ra là một socket UDP. Không card DVB, không `/dev/dvb`,
không `--privileged`. Chỉ cài lên máy chủ nếu muốn dùng `tsp -I ip` để soi
luồng do máy *khác* phát, mà việc đó `docker compose exec si tsp …` cũng làm
được.

**Phiên bản TSDuck phải ghim, và ghim giống nhau ở cả hai máy.** Hai nguồn
ngang hàng chỉ có nghĩa khi chúng sinh ra cùng byte. Một máy chạy TSDuck trong
ảnh còn máy kia chạy bản từ `apt` là phép so byte hết đúng — im lặng, cho tới
lúc mux chuyển nguồn.

### Ba chỗ phải đúng, không thì hỏng lặng

**`network_mode: host` cho dịch vụ `si`.** Multicast không đi ra đúng cách qua
mạng bridge của Docker: NAT không xử lý multicast, và `--local-address` — thứ
chọn card nguồn — trong bridge chỉ thấy veth của container chứ không thấy card
thật của máy. Đổi sang bridge thì luồng biến mất khỏi mạng **trong khi
container vẫn xanh và log vẫn sạch**.

**Kho cấu hình phải nằm NGOÀI thư mục Coolify tự quản.** Coolify clone kho vào
thư mục của nó và `reset --hard` mỗi lần triển khai lại; giao diện thì commit
vào chính kho ấy. Để mặc định nghĩa là mỗi lần bấm Redeploy là xoá việc người
trực vừa làm. Đặt biến `VTCSI_REPO` trỏ ra một clone do bạn làm chủ.

**`web` và `si` phải trỏ cùng thư mục.** `vtcsi web` nhận `--build` và
`--inbox` mặc định *tương đối*, giải theo `WORKDIR`. Lệch thì giao diện ghi
file lịch vào một chỗ mà `vtcsi run` không bao giờ đọc: trình duyệt báo *đã
nhận*, màn giám sát trống trơn, EPG không lên sóng, không lỗi nào được ném.
`tests/test_docker.py` canh chỗ này.

### Các bước

**1. Kho cấu hình — do bạn làm chủ, ngoài tầm Coolify**

```bash
sudo mkdir -p /srv/vtcsi
sudo git clone https://github.com/ndung2006/VTC-SI /srv/vtcsi/repo
cd /srv/vtcsi/repo
git fetch --tags          # the `gieo` la moc so byte; clone thuong da keo san
git tag -l                # phai thay: gieo
```

**2. Ghim tuyến multicast vào netplan**

`ip route add` chỉ sống trong bộ nhớ. Không ghim thì sau một lần khởi động
lại, báo hiệu lặng lẽ đi ra card quản trị và mux không thấy gì.

Sửa `/etc/netplan/*.yaml`, thêm vào giao diện phát:

```yaml
    eno1:
      addresses: [192.168.20.200/24]
      routes:
        - to: 224.0.0.0/4
          scope: link
```

```bash
sudo netplan try                   # tu lui lai sau 120 giay neu mat ket noi
ip route get 236.30.239.1          # phai thay: dev eno1 src 192.168.20.200
```

**3. Dựng ảnh và bật GIAO DIỆN trước — chưa phát gì**

```bash
cd /srv/vtcsi/repo
export VTCSI_REPO=/srv/vtcsi/repo
docker compose build
docker compose up -d web           # CHI `web`. Khong phai `si`.
docker compose ps
```

**Cổng 8080 bận thì đổi cổng phía máy.** Trên máy đã chạy Coolify, 8080 thường
đã có chủ. Cổng bên trong container giữ nguyên; chỉ cổng phía máy đổi:

```bash
ss -ltnp | grep ':8080'            # xem ai dang giu
echo "VTCSI_PORT=8090" >> /srv/vtcsi/repo/.env
docker compose up -d web
```

`.env` nằm cạnh `docker-compose.yml` và đã có trong `.gitignore`, nên mỗi máy
tự giữ cổng của mình — giống cách `config/dau-ra.yaml` hoạt động.

**4. Đặt mật khẩu**

Không có đường đặt qua trình duyệt, và đó là chủ ý: quyền quản trị trên máy
phát mới là ranh giới thật.

```bash
docker compose exec web vtcsi --config=/repo/config passwd --repo=/repo
```

**5. Khai địa chỉ đầu ra**

Mở `http://192.168.90.10:8080/` → **Quản lý PSI/SI → Đầu ra**:

| Ô | Giá trị cho máy này |
|---|---|
| Địa chỉ đích | nhóm multicast headend cấp, ví dụ `236.30.239.1` |
| Cổng UDP | ví dụ `6000` |
| Card mạng phát ra | `192.168.20.200` |
| TTL | `8` |

Ghi vào `config/dau-ra.yaml`, **nằm ngoài git** — máy kia không bị đụng, và
đó là điểm mấu chốt của cặp máy dự phòng.

**6. Bậc 0 và bậc 1 — trước khi phát thật**

Xem hai mục đầu của tài liệu này. Đừng nhảy thẳng xuống bước 7.

**7. Bật dịch vụ phát**

```bash
docker compose up -d si
docker compose logs -f si
```

**8. Cho systemd lo việc lên sau khi khởi động máy**

`restart: unless-stopped` chỉ dựng lại container khi Docker đang chạy; nó
không tự bật stack sau khi máy khởi động lại nếu stack chưa từng được `up`.
Tạo `/etc/systemd/system/vtcsi.service`:

```ini
[Unit]
Description=VTC-SI — nguon bao hieu PSI/SI
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/srv/vtcsi/repo
Environment=VTCSI_REPO=/srv/vtcsi/repo
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose stop

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now vtcsi
```

**9. Máy thứ hai**

Làm lại từ bước 1, **chỉ khác đúng một chỗ**: địa chỉ đầu ra ở bước 5. Cấu
hình báo hiệu đồng bộ qua `git pull`; địa chỉ đầu ra thì không, vì nó nằm
ngoài git. Hai máy cùng phát một nhóm multicast ra cùng một mạng là đúng cái
hỏng mà cặp máy sinh ra để tránh.

### Xác nhận ngay sau lần triển khai đầu

```bash
docker inspect vtcsi-si --format '{{.HostConfig.NetworkMode}}'   # phai la: host
docker compose exec si tsp --version                             # phai la: 3.44-4676
docker compose exec si ls /repo/config/dau-ra.yaml               # phai co
```

Vài bản Coolify tự chèn cấu hình mạng vào compose. Dòng đầu **không** trả về
`host` thì luồng sẽ không tới được mux, và đó là thứ phải sửa trước mọi việc
khác — chứ không phải đi dò xem mux hỏng ở đâu.

---

## Bốn điều đã biết trước sẽ gặp

Ghi ở đây để lúc gặp thì không hoảng.

**Mọi bộ phân tích sẽ báo thiếu PAT.** Luồng ta phát không có PAT — mux sinh nó.
StreamXpert đã báo *"No services found"* với luồng Barrowa suốt bao năm nay.
Đó là thiết kế, không phải lỗi.

**Dịch vụ 838 có một sự kiện `duration = 48:00:01`** khi hết lịch — RO-22. Hệ
mới **loại nó ra kèm cảnh báo** chứ không tái tạo. Nếu thấy kênh đó thiếu một
mục trong EPG, đó là chủ ý.

**Dịch vụ 877 `CAO BANG RADIO` không có số kênh** — RO-23. Mười chín kênh phát
thanh kia liền mạch 397…415; chỗ trống đúng bằng 416. Bản gieo **giữ nguyên** để
khớp byte. Sửa được ngay ở màn hình bouquet, nhưng nhớ tăng version BAT 0x6510.

**Ba linkage trỏ vào TSID không tồn tại** — RO-8: TSID 16 ba lần gồm cả kênh
barker, TSID 9 một lần, và `0x3265` một lần do đặt nhầm `network_id` vào ô
`transport_stream_id`. Cấu hình đã gieo **giữ nguyên** chúng để khớp byte với
sóng. Sửa là một quyết định nghiệp vụ riêng, kèm tăng version NIT.

# Đặc tả hệ thống PSI/SI dự phòng — VTC DVB-S

| | |
|---|---|
| **Mã dự án** | `vtc-si` |
| **Vai trò** | Thiết bị dự phòng cho Barrowa SunDial 6.5.4.2, mục tiêu thoát phụ thuộc bản quyền |
| **Lõi** | TSDuck (BSD 2-Clause) + lớp điều khiển Python |
| **Phạm vi truyền dẫn** | Thuần vệ tinh, DVB-S2, Vinasat-1 132,0°E |
| **Đích ghép** | Harmonic ProStream 9100, một multicast UDP |
| **Nhân lực** | Một người |
| **Phiên bản đặc tả** | 2.8 — 2026-09-15 |

> Tài liệu này nói **xây cái gì**. Phần khảo sát hiện trạng, lý do lựa chọn và phân tích rủi ro nằm ở tài liệu thiết kế riêng.

**Thay đổi ở 0.2** — sau buổi rà soát nghiệp vụ 45 mệnh đề:

| Mã rà soát | Thay đổi |
|---|---|
| `D5`, `O2` | **Giao diện nhập liệu vào phạm vi.** Thêm §4.8, thêm giai đoạn T6, ước lượng tăng lên 11–16 tuần. |
| `B1` | **TDT/TOT thành tuỳ chọn** thay vì loại hẳn. Thêm FR-33, kèm điều kiện bật. |
| `E3` | **Sửa số liệu dịch vụ.** VTC sở hữu 64 kênh trên TSID 8; 24 kênh còn lại thuộc ONID 1. Xem A.2. |
| `R10` | **Phát hiện lỗi tồn đọng**: linkage kênh barker trỏ vào đích không còn tồn tại. Xem RO-8. |

**Thay đổi ở 2.8** — **`eitinject` không bao giờ quên (FR-94).** Đo trên máy phát: bảng sinh ra còn 17 dịch vụ, trên sóng vẫn 40 — 17 hiện tại cộng đúng 23 kênh đã bị rút khỏi lịch. Xoá lịch **không** rút kênh khỏi sóng; chỉ khởi động lại `si` mới rút được. Đây là khác biệt cốt lõi giữa đường EIT và đường NIT/SDT/BAT, và nó đảo ngược lời khuyên mặc định "đừng dựng lại dịch vụ" trong đúng một trường hợp.

**Thay đổi ở 2.7** — **sửa một con số sai trong chính đặc tả này (FR-93).** Bản trước ghi thay đổi lên sóng sau *nửa giây*. Đo thật trên máy phát: **67 giây** cho NIT/SDT/BAT. Con số cũ là suy đoán lúc viết chú thích, không phải phép đo, và nó dẫn người trực tới chỗ dựng lại dịch vụ vì tưởng hệ hỏng — mà dựng lại mới là thứ gây chớp nguồn.

**Thay đổi ở 2.6** — **tăng version SDT/BAT tự động (FR-92).** Sinh ra từ một ca thật: ngày 13/09 kênh 877 được thêm vào bouquet 0x6510 qua giao diện, nội dung đi từ 78 lên 79 dịch vụ, version đứng yên ở 26 — đúng ô `SILENT_CHANGE` mà `model/version.py` gọi là *nguy hiểm nhất*, và không ai phát hiện cho tới khi tình cờ mở `git status`.

**Thay đổi ở 2.5** — **triển khai container, và một bài học về chuẩn vàng.** Thêm FR-89…91. Commit thật đầu tiên của người vận hành làm đỏ 15 bài, trong đó có cả bảy bài so byte — không phải vì có lỗi, mà vì mốc đối chiếu của chúng là HEAD, thứ vừa thôi không còn là bản gieo. Ghim bằng thẻ `gieo`. Cùng lúc, đọc lại `docker-compose.yml` tìm ra hai lỗi im lặng: `web` trỏ nhầm thư mục nên XML nạp qua trình duyệt không bao giờ lên sóng, và `--to` ghim sẵn trong compose làm tắt vĩnh viễn đường sao chép.

**Thay đổi ở 2.4** — **quản lý đầu ra.** Thêm FR-86…88, trang con *Đầu ra*, lõi thuần `model.output` và file `config/dau-ra.yaml`. Đây là mẩu cấu hình **duy nhất** cố ý nằm ngoài git: mọi thứ khác giống nhau giữa hai máy là cơ chế đồng bộ, riêng địa chỉ đầu ra thì phải khác — hai máy cùng bắn một nhóm multicast ra cùng một mạng là đúng cái hỏng mà cặp máy sinh ra để tránh. Kèm theo là đường sao chép: một `tsp` con sau `-P fork`, đã chứng minh bằng phép chạy thật trùng từng byte trên 7 520 000 byte.

**Thay đổi ở 2.3** — **màn giám sát liệt kê đủ kênh.** Trước bản này, kênh tắt EPG bị bỏ hẳn khỏi lưới; giờ nó có dòng, dòng rỗng, và mang nhãn TẮT. Người trực cần thấy kênh đó **tồn tại và đang tắt** — biến mất khỏi màn giám sát trông y hệt như không được cấu hình. Sửa FR-79, thêm FR-79b.

**Thay đổi ở 2.2** — **lần chạy toàn trình đầu tiên.** Nạp file lịch thật của ngày 12/09 qua API, sinh bảng, dựng dòng TS bằng `tsp`, rồi đọc ngược và đối chiếu từng sự kiện với file gốc. Bốn lỗi lộ ra, cả bốn đều **im lặng** và cả bốn đều nằm ở đoạn giữa `vtcsi` và TSDuck — đoạn duy nhất mà các bài kiểm trước đó chỉ so chuỗi chứ chưa bao giờ chạy thật. Thêm FR-81…85.

**Thay đổi ở 2.1** — **màn giám sát.** Thêm FR-78…80 và lõi thuần `epg.transform.timeline`. Dựng theo màn *Giám sát* của hệ nhập liệu, nhưng phạm vi khác hẳn: hệ đó vẽ những gì đã lập lịch, hệ này vẽ những gì **sẽ ra sóng** — nên nó bỏ kênh tắt EPG và kênh ngoài TS actual.

**Thay đổi ở 2.0** — **ranh giới với hệ lập lịch bên ngoài.** Thêm FR-73…77 và trang *Hộp thư lịch*. Trước bản này, file XML phải chép tay vào thư mục; giờ hệ bên ngoài đẩy qua HTTPS và EIT lên sóng sau **nửa giây**. Ranh giới giữa hai hệ là một file XML — thứ kiểm được, lưu được, gửi lại được.

**Thay đổi ở 1.9** — **EPG phản ứng tức thì.** Thêm FR-70…72. Chu kỳ sinh lại một giờ là sai từ đầu: file lịch bàn giao lúc 8 giờ phải lên sóng lúc 8 giờ, và công tắc EPG khẩn cấp mà chờ 60 phút thì không còn là khẩn.

**Thay đổi ở 1.8** — **AC-1 và AC-2 đã chứng minh ở MỨC BYTE.** TSDuck có sẵn trên máy từ đầu; `shutil.which` không thấy vì nó nằm ngoài `PATH` của Git Bash. Bảy bài so byte — phép thử mạnh nhất của dự án — **đã ngủ yên nhiều phiên vì lý do đó**, và một bài bị bỏ qua vì môi trường trông giống hệt một bài bị bỏ qua vì chưa cài gì. Nay: **562 test xanh, 0 bỏ qua**. NIT, ba SDT và sáu BAT sinh từ cấu hình **giống từng byte** với bảng bóc từ sóng, sau khi cả hai đi qua cùng `tstabcomp`.

**Thay đổi ở 1.7** — **bật/tắt EPG từng kênh.** Thêm FR-69. Đáng chú ý: trước bản này `vtcsi epg` **bỏ qua hoàn toàn** cờ EIT trong SDT — nó không nạp cấu hình. Nghĩa là mọi cách tắt EPG một kênh đều chỉ là đổi lời khai.

**Thay đổi ở 1.6** — **giao diện có xác thực.** Thêm FR-65…68 và lệnh `vtcsi passwd`. Trước bản này, ai mở được cổng của giao diện là sửa được cấu hình đang phát sóng — một lỗ hổng chưa từng được ghi nhận trong đặc tả vì giao diện ra đời sau phần lớn nội dung đặc tả.

**Thay đổi ở 1.5** — **version nhập tay, lùi lại được.** Thêm FR-64; `/version/bump` thành `/version/set`. Đây là điều đã chốt từ buổi khảo sát đầu tiên — *"NIT version phải được cập nhật bằng tay"* — mà bản 1.0 chỉ làm được một nửa.

**Thay đổi ở 1.4** — **giao diện nói tiếng Việt, và không chết vì một file YAML hỏng.** Thêm FR-62, FR-63.

**Thay đổi ở 1.3** — **sửa được linkage và vòng transport.** Thêm FR-59, FR-60, FR-61. Hai lõi thuần mới: `model.linkage` và `model.topology`. Đếm lại RO-8: **sáu** mục trỏ vào TSID không tồn tại chứ không phải năm. Và một bất biến mới được phát hiện rồi canh luôn — PDS có mặt đúng ở những vòng có số kênh (FR-61).

**Thay đổi ở 1.2** — **chạy được thật.** `vtcsi run` dựng và trông chừng `tsp`; `vtcsi refresh` sinh lại bảng và EIT; `Dockerfile` cùng `docker-compose.yml` đã có. Thêm FR-58 và NFR-9. Một lỗ hổng nghiêm trọng được bịt khi viết phần này: hộp thư chỉ còn lịch cũ thì `vtcsi epg` sinh EIT rỗng rồi ghi đè lên file đang phát — mất EPG cả mạng, do một lệnh định kỳ, không ai làm gì sai.

**Thay đổi ở 1.1** — **giao diện nhập liệu chạy được, và kho git đã dựng.** Thêm FR-57 (soi số kênh). Luật số kênh nằm ở lõi thuần `model.lcn`, không nằm trong `from_plain`: cấu hình gieo từ sóng phải nạp được **nguyên trạng kể cả khi sóng đang sai**, nếu không mất luôn khả năng so byte. Chính luật này tìm ra RO-23 ngay lần chạy đầu.

**Thay đổi ở 1.0** — **giai đoạn T2 xong.** Cấu hình đã gieo từ sóng vào `config/` và chứng minh tái tạo đúng 10/10 bảng. Thêm FR-55 và FR-56. Bắt thêm một lỗi đang phát sóng khi viết bộ sinh EIT — xem RO-22.

**Thay đổi ở 0.9** — **rút lại kết luận sai ở 0.8.** EIT schedule **có trên sóng**: ảnh phân tích Dektec StreamXpert của chính luồng SI đó cho thấy `EIT-actual schedule` với `day 0..3` và `day 4..7`, PID 18 ở **139 kbps / 86,5 %**, đủ 18 dịch vụ. Bản dump `tstables` trống phần schedule là **hiện tượng của công cụ**, không phải của sóng — xem RO-20 đã viết lại. RO-21 (nghi có hồi quy) bị **xoá bỏ**: không có hồi quy nào.

**Thay đổi ở 0.8** — **đã dump được luồng SI thuần của Barrowa.** Mux được chứng minh là trung thực tuyệt đối: đầu vào và đầu ra khớp nhau ở mọi bảng và mọi version. Điều này vẫn đứng vững và là kết quả giá trị nhất của bản 0.8. *Phần kết luận về EIT schedule ở bản đó đã bị rút lại — xem 0.9.*

**Thay đổi ở 0.7** — **bốn bản dump cho thấy EPG gần như không lên sóng.** Chỉ 18 trên 44 kênh truyền hình có EIT, và **không có EIT schedule nào** trong bốn phút thu trải ba ngày. Truy được nguyên nhân của phần thứ nhất: `epgsource.xml` chỉ gán nguồn EPG cho đúng 18 dịch vụ. Xem RO-19 và RO-20 — đây là phát hiện có giá trị nghiệp vụ lớn nhất tới giờ.

**Thay đổi ở 0.6** — **đã có bản dump đầu ra mux** (`dvb_tables_dump.xml`, 9,3 MB, 26 660 bảng, cửa sổ 56 giây). Kịch bản B được chứng minh bằng thực nghiệm, không còn suy đoán. Giải xong: LCN là **NorDig v1** chứ không phải PDS `0x31` như tôi suy từ cấu hình; mux sinh TDT nhưng **không có TOT**; EIT **không mang** `0x50`. Bắt được ba lỗi đang phát sóng — xem RO-8, RO-15, RO-16. Version trên sóng đã cập nhật ở A.5.

**Thay đổi ở 0.5** — **nguồn EPG không phải XMLTV.** Đã phân tích file thật: đó là lược đồ DVB gốc `<PSI>`, mang thẳng các trường DVB. Bỏ toàn bộ lớp ánh xạ XMLTV. Lộ ra hai vấn đề thật: `event_id` của nguồn không dùng trực tiếp được cho lịch 8 ngày (RO-12), và file mẫu chỉ có một ngày dữ liệu (RO-13). Thêm §4.10 và Phụ lục C.

**Thay đổi ở 0.4** — **hai hệ ngang hàng.** Bỏ hẳn khái niệm chính/phụ và bỏ luôn enum chế độ. Mỗi nguồn tự sinh luồng đầy đủ từ cấu hình của chính nó và không cần nguồn kia để hoạt động; mux làm việc chọn. Bộ so sánh hạ xuống thành quan sát viên, khoá liên động thành tuỳ chọn hỏng-theo-hướng-mở. Thêm yêu cầu **tất định** (FR-46) vì đó là cơ chế đồng bộ thay cho heartbeat. Xem §3.

**Thay đổi ở 0.3** — **bỏ chế độ gương.** YAML trong git là nguồn sự thật duy nhất ở mọi chế độ; luồng Barrowa chỉ dùng để đối chiếu. Thay vào đó là trạng thái *sẵn sàng thay thế* tính ra được (§3.1) và cơ chế đề xuất bản vá (FR-43). Xem §3.

---

## 1. Phạm vi

### 1.1 Trong phạm vi

Sinh và phát liên tục một transport stream chỉ chứa bảng báo hiệu:

| PID | Bảng | Trạng thái |
|---|---|---|
| 16 · `0x10` | NIT actual | Bắt buộc — một mạng, `network_id` 12901 |
| 17 · `0x11` | SDT actual + SDT other + BAT | Bắt buộc — dùng chung PID theo chuẩn |
| 18 · `0x12` | EIT actual p/f + EIT actual schedule | Bắt buộc — độ sâu 8 ngày |
| 20 · `0x14` | TDT + TOT | **Tuỳ chọn, mặc định tắt.** Xem FR-33 và RO-9 |

Cùng với đó là **giao diện nhập liệu** để vận hành cấu hình mà không phải sửa YAML bằng tay — xem §4.8.

### 1.2 Ngoài phạm vi

| Hạng mục | Ai lo |
|---|---|
| PAT, PMT, CAT | ProStream 9100 |
| TDT | ProStream 9100 — **đã đo: có trên PID 20, chu kỳ 4 s** |
| TOT | **Không ai sinh cả** — xem RO-17 |
| PCR, bitrate stuffing của MPTS | ProStream 9100 |
| Chuyển đổi nguồn khi mất tín hiệu | ProStream 9100, cơ chế dự phòng input |
| DSM-CC object carousel, dữ liệu firmware OTA | Hệ thống khác của VTC |
| Cable, terrestrial, T2, OTT | Không có kế hoạch |
| Đa ngôn ngữ SDT/EIT — descriptor `0x5D`, `0x5E` | Không cần |
| Linkage ViCAS `0x90`, `0x92` | Đã quyết định bỏ |
| Phân quyền nhiều vai trò, luồng duyệt nhiều cấp | Không cần; giao diện ở §4.8 là nhập liệu một người |

---

## 2. Bản đồ hệ thống

Bản đồ toàn cảnh, sơ đồ hai nguồn ngang hàng và đường đi của dữ liệu nằm ở **[`mindmap.md`](mindmap.md)** — tách riêng để một chỗ sửa là một chỗ, không phải hai.

Tóm tắt một đoạn để đọc tiếp được mà không cần mở file kia: hai nguồn báo hiệu ngang hàng, mỗi nguồn đọc cấu hình YAML từ git cùng file lịch, sinh ba bảng NIT / SDT+BAT / EIT bằng TSDuck, rồi phát ra một địa chỉ multicast riêng. Mux nhận cả hai làm input và tự chọn. Không nguồn nào cần nguồn kia — chúng giống nhau vì cùng một commit và cùng một hàm thuần, không phải vì trao đổi với nhau. Một bộ so sánh chạy tách rời, chỉ quan sát và báo động.

---

## 3. Hai nguồn ngang hàng

Mô hình là **hai nguồn báo hiệu ngang hàng**. Mỗi nguồn tự sinh một luồng SI đầy đủ và hợp lệ từ cấu hình của chính nó, phát ra địa chỉ multicast riêng, liên tục. Mux nhận cả hai làm input và tự chọn.

**Không nguồn nào cần nguồn kia để hoạt động.** Đây là ràng buộc kiến trúc, không phải mục tiêu phấn đấu: mọi cơ chế đọc luồng của nguồn khác đều phải hỏng theo hướng mở — mất tham chiếu thì vẫn phát.

### 3.1 Hai giai đoạn

| Giai đoạn | Nguồn A | Nguồn B | Đồng bộ bằng |
|---|---|---|---|
| **Chuyển tiếp** | Barrowa | Hệ mới | Ý định chung: thay đổi ghi vào git, rồi áp tay lên Barrowa qua giao diện của nó |
| **Ổn định** | Hệ mới, thực thể 1 | Hệ mới, thực thể 2 | Cùng một commit git |

Ở giai đoạn chuyển tiếp có một bất đối xứng không thể xoá: Barrowa là sản phẩm đóng, nó không đọc được YAML và không biết hệ mới tồn tại. Nên "ngang hàng" ở đây là ngang hàng **về vận hành** — cả hai đều tự đứng được, cả hai đều là input hợp lệ của mux, mất bên nào bên kia vẫn chạy. Ngang hàng **về phần mềm** chỉ đến ở giai đoạn ổn định.

### 3.2 Vì sao không cần giao thức dự phòng nào cả

Barrowa phải mang cả một giao thức cụm — multicast discovery, cổng 50110/50111/50112, bầu vai trò, chống hai máy cùng phát — vì hai máy của nó **ghi vào cùng một đích**. Chính giao thức đó đẻ ra tình trạng *"Operating on Standalone — Config changed on both"* đang thấy trên hệ đang chạy.

Ở mô hình này **mux làm việc chọn**. Hai nguồn không chia sẻ tài nguyên nào, không tranh nhau đích nào, không cần biết nhau tồn tại. Cả lớp lỗi split-brain biến mất cùng với giao thức, chứ không phải được xử lý.

### 3.3 Cơ chế đồng bộ là tính tất định, không phải heartbeat

Hai thực thể của hệ mới, cùng một commit git và cùng đồng hồ chuẩn, phải cho ra **cùng một chuỗi byte**. Không có kênh liên lạc nào giữa chúng — sự giống nhau đến từ việc cùng đọc một đầu vào và cùng chạy một hàm thuần.

Điều này biến **FR-46 (tất định)** thành yêu cầu cốt lõi chứ không phải mong muốn kỹ thuật, và biến **git** thành cơ chế đồng bộ thật sự của hệ thống.

Ngoại lệ đã biết: `version_number` của EIT tăng độc lập trên từng thực thể nên sẽ trôi khác nhau. Vô hại — đầu thu chỉ đọc lại bảng, không dò lại kênh. Nội dung EIT vẫn giống nhau vì cùng file lịch và cùng đồng hồ.

### 3.4 Bộ so sánh là quan sát viên, không phải bộ điều khiển

Việc đối chiếu tách hẳn thành một tiến trình riêng, chạy ở đâu cũng được, kể cả trên máy thứ ba. Nó đọc các luồng đang trên sóng cùng cấu hình trong git, rồi báo động khi lệch. **Nó không chặn ai, không tắt ai.** Bộ so sánh chết thì hai nguồn vẫn phát bình thường và bạn chỉ mất khả năng phát hiện lệch.

### 3.5 Khoá liên động — tuỳ chọn, và phải hỏng theo hướng mở

Có thể bật một khoá liên động để một nguồn tự rút khỏi địa chỉ sản xuất khi phát hiện mình lệch với luồng kia, tránh việc mux chuyển sang một nguồn đã sai.

Nếu bật thì bắt buộc theo hai quy tắc:

1. **Không đọc được nguồn kia thì vẫn phát.** Mất tham chiếu không phải bằng chứng mình sai — và nếu nguồn kia vừa chết thì đó chính là lúc mình cần phát nhất. Đây là ranh giới giữa *khuyến cáo* và *phụ thuộc*.
2. **Chỉ rút khi có bằng chứng dương tính về sai lệch**, sau ít nhất hai chu kỳ so liên tiếp.

Mặc định của khoá này là **tắt** ở giai đoạn ổn định — khi hai thực thể chạy cùng commit thì lệch nghĩa là có lỗi phần mềm, và rút một nguồn không sửa được lỗi đó.

---

## 4. Yêu cầu chức năng

### 4.1 Sinh bảng

| ID | Yêu cầu |
|---|---|
| **FR-1** | Sinh NIT actual (`table_id` `0x40`) cho `network_id` 12901, tên mạng `VTC`, chứa transport loop của cả ba TS. |
| **FR-2** | Với mỗi transport loop, sinh `satellite_delivery_system_descriptor` `0x43` và `service_list_descriptor` `0x41`. |
| **FR-3** | `service_list_descriptor` `0x41` phải được **sinh tự động** từ danh sách dịch vụ của TS tương ứng. Không cho phép nhập tay. |
| **FR-4** | Sinh SDT actual (`0x42`) cho TSID 8, và SDT other (`0x46`) cho TSID 3 và 1000. |
| **FR-5** | Sinh BAT (`0x4A`) cho từng bouquet đang hoạt động, gồm `bouquet_name_descriptor` `0x47`, `service_list_descriptor` `0x41`, và **`nordig_logical_channel_descriptor_v1`** đặt sau `private_data_specifier_descriptor` `0x5F` mang **PDS của NorDig**. Đo trên sóng cho thấy đúng biến thể NorDig v1, không phải PDS `0x00000031` như tên tham số `lcn_priv_spec` trong `sigprops.dat` gợi ý — `lcn_n1` trong cấu hình Barrowa nghĩa là *NorDig LCN v1*. Vì ta sinh XML cho TSDuck nên **chỉ cần dùng đúng tên phần tử đó và để TSDuck lo giá trị PDS**; không hardcode con số. |
| **FR-6** | Hỗ trợ `linkage_descriptor` `0x4A` với các loại đang dùng: `0x05` kênh barker, `0x09` SSU, `0x80` và `0x82` Irdeto OTA. Payload của `0x82` phải được mô hình hoá theo trường, không phải một khối byte đục. |
| **FR-7** | Sinh EIT actual p/f (`0x4E`) và EIT actual schedule (`0x50`–`0x5F`) với độ sâu 192 giờ. |
| **FR-8** | Descriptor sự kiện phát theo thứ tự cố định `4D`, `4E`, `54`, `55`. |
| **FR-9** | Mã hoá chuỗi theo EN 300 468 Annex A. Tiếng Việt dùng byte dẫn `0x15` (UTF-8). Khi cắt chuỗi vì chạm giới hạn độ dài, **cắt theo ranh giới ký tự, không theo byte**. |

### 4.2 Đầu ra

| ID | Yêu cầu |
|---|---|
| **FR-10** | Phát một transport stream qua UDP multicast tới đúng một địa chỉ đích, 7 gói TS mỗi datagram. |
| **FR-11** | Luồng phải là **CBR liên tục**, chèn null packet PID `0x1FFF`. Mux phát hiện mất nguồn bằng cách đếm gói UDP; luồng đứt quãng có thể kích hoạt chuyển đổi nhầm. |
| **FR-12** | Continuity counter liền mạch riêng cho từng PID. |
| **FR-13** | Luồng chứa **duy nhất** PID 16, 17, 18 — cộng PID 20 nếu bật FR-33 — và null packet. Không phát PAT. |
| **FR-14** | Cho phép chỉ định địa chỉ nguồn (card mạng) và TTL. |

### 4.3 Version

| ID | Yêu cầu |
|---|---|
| **FR-15** | `version_number` của NIT, SDT, BAT **không bao giờ được tự tăng** và **luôn lấy từ YAML**. Khi Barrowa tăng version ở giai đoạn chuyển tiếp, người vận hành cập nhật con số tương ứng trong YAML — FR-43 sinh sẵn bản vá để không phải chép tay. |
| **FR-16** | Version của EIT p/f **phải** tăng mỗi khi sự kiện present hoặc following đổi. Do TSDuck `eitinject` đảm nhiệm. |
| **FR-17** | Trường rộng 5 bit, giá trị hợp lệ 0–31, quay vòng sau 31. Logic tăng phải là `(v + 1) mod 32`. |
| **FR-18** | **Kiểm tra trước khi đấu nối là một lệnh riêng, không phải cổng chặn lúc chạy.** `vtcsi preflight` so version NIT/SDT/BAT trong YAML với luồng đang trên sóng và báo lỗi nếu lệch hoặc nhỏ hơn. Chạy nó trước khi đấu vào mux. **Tiến trình phát không bao giờ tự chặn vì không đọc được luồng tham chiếu** — xem §3.5. Riêng version nhỏ hơn giá trị chính mình đã phát lần trước (FR-45) thì dừng, vì đó là bằng chứng nội bộ, không cần nguồn ngoài. |

### 4.4 Thu nhận EPG

| ID | Yêu cầu |
|---|---|
Nguồn là **một file XML theo lược đồ DVB gốc, không phải XMLTV**. Gốc `<PSI>`, cây `NETWORK → TRANSPORT_STREAM → SERVICE → EVENT`, mang thẳng các trường DVB đã ở dạng cuối. Cấu trúc đầy đủ ở **Phụ lục C**.

| ID | Yêu cầu |
|---|---|
| **FR-19** | Nhập file XML lược đồ `<PSI>` qua thư mục theo dõi và qua HTTP pull. **Bỏ trình phân tích XMLTV khỏi phạm vi.** |
| **FR-20** | **Không cần ánh xạ genre hay parental rating**: nguồn không mang hai trường đó, và không có phần tử `CONTENT` hay `PARENTAL_RATING` nào. Các file ánh xạ của Barrowa không áp dụng cho nguồn này. Hệ quả: EIT không sinh descriptor `0x54` và `0x55`. |
| **FR-21** | Thời gian nguồn mang offset tường minh `+07:00` trên từng mốc; chuyển sang UTC cho trường MJD/UTC của EIT. Duration ISO 8601 `PTxxHxxMxxS` sang BCD `HHMMSS`. |
| **FR-22** | Thuộc tính `encoding` trên từng chuỗi **là byte dẫn bảng mã DVB do nguồn cung cấp** (hiện luôn là `15`, tức UTF‑8). Dùng đúng giá trị đó, không tự suy từ ngôn ngữ. Vẫn giữ FR-9 về cắt chuỗi theo ranh giới ký tự. **Bản dump ủng hộ cách đọc này**: TSDuck giải mã đúng tiếng Việt có dấu từ luồng thật, nghĩa là byte dẫn trên sóng là một mã UTF-8 hợp lệ. |

### 4.5 Thao tác cấu hình

| ID | Yêu cầu |
|---|---|
| **FR-23** | Thêm và xoá transport stream. |
| **FR-24** | Thêm và xoá dịch vụ, đổi tên và nhà cung cấp. |
| **FR-25** | Thêm, xoá, đổi tên bouquet; sửa thành viên bouquet. |
| **FR-26** | Sửa LCN và cờ hiển thị. |
| **FR-27** | Mọi thay đổi là sửa file YAML trong git. Không có giao diện web trong phạm vi này. |

Bảng hệ quả của từng thao tác:

| Thao tác | Version phải tăng | Đầu thu |
|---|---|---|
| Thêm/bớt TS | NIT · SDT mới · BAT liên quan | Dò lại kênh |
| Thêm/bớt kênh | NIT · SDT · BAT | Dò lại kênh |
| Đổi LCN | BAT, và NIT nếu muốn máy đang cắm nhận được | Dò lại kênh |
| Đổi tên kênh | Chỉ SDT | Tự cập nhật, không dò lại |
| Thêm/bớt bouquet | BAT đó | Tuỳ đầu thu |
| Đổi tham số phát của TS | NIT | Dò lại kênh |

### 4.6 Giám sát

| ID | Yêu cầu |
|---|---|
| **FR-28** | Định kỳ dump bảng từ mọi luồng SI đang trên sóng, so sánh với nhau và với cấu hình trong git, báo động khi lệch. |
| **FR-29** | Báo động khi **nội dung bảng khác nhưng version giống** — đây là dấu hiệu quên tăng version. |
| **FR-30** | Báo động khi version lùi. |
| **FR-31** | Theo dõi tuổi EPG từng dịch vụ; báo động khi lịch còn dưới 120 giờ. |
| **FR-32** | Xuất chỉ số dạng Prometheus. Gửi SNMP trap tới NMS của VTC. |

### 4.7 TDT và TOT — tuỳ chọn

| ID | Yêu cầu |
|---|---|
| **FR-33** | Sinh TDT (`0x70`) và TOT (`0x73`) trên PID 20, **mặc định tắt**. TOT mang `local_time_offset_descriptor` `0x58` với offset `+07:00`, không DST. Chu kỳ 30 s. |

> **Điều kiện bật.** Chỉ bật sau khi xác minh mux **không** tự sinh PID 20. Hai nguồn cùng ghi một PID là xung đột chứ không phải dự phòng: hoặc mux ghi đè bảng của ta, hoặc thời gian trên sóng nhảy giữa hai đồng hồ. Phép đo nằm ở giai đoạn T1 — xem RO-9.
>
> Nếu mux đang cấp TDT/TOT thì bật cái này ở hệ mới **không** giúp kiểm tra thời gian; muốn kiểm tra thì đọc PID 20 ở đầu ra mux bằng `tstables`, đó mới là thứ đầu thu thực sự nhận. Chỉ khi mux không cấp thì việc tự sinh mới có nghĩa.

### 4.8 Giao diện nhập liệu

| ID | Yêu cầu |
|---|---|
| **FR-34** | Hiển thị cây Network → Transport stream → Dịch vụ, và danh sách bouquet. |
| **FR-35** | Thêm, sửa, xoá dịch vụ: `service_id`, tên, nhà cung cấp, loại, cờ EIT. |
| **FR-36** | Sửa LCN và cờ hiển thị, theo từng bouquet. |
| **FR-37** | Sửa thành viên bouquet. |
| **FR-38** | Nhập tham số OTA Irdeto: `manufacture_code`, `hardware_version`, `load_sequence_number`. |
| **FR-39** | Tăng NIT version là **một thao tác riêng biệt, có hộp xác nhận**, không lẫn với việc sửa nội dung. Màn hình phải nói rõ hệ quả: toàn bộ đầu thu trên mạng sẽ dò lại kênh. |
| **FR-40** | Xem diff trước khi áp. Khi áp thì ghi thẳng vào file YAML và **commit vào git** kèm tác giả và lý do. Git vẫn là nguồn sự thật duy nhất; giao diện chỉ là một cách sinh commit. |
| **FR-41** | Trang trạng thái: commit git đang chạy, version trên sóng so với version trong cấu hình, danh sách sai lệch giữa các nguồn, tuổi EPG từng dịch vụ. |

**Ràng buộc thiết kế.** Server-rendered, không phải SPA — Python cùng khung web nhẹ và template, để một người bảo trì được và để cùng ngôn ngữ với lớp điều khiển. Chạy trong **container riêng** do Coolify quản bình thường; không đụng gì tới container phát luồng (NFR-3).

> **Giao diện luôn là công cụ điều khiển thật** — vì YAML luôn là nguồn sự thật. Ở giai đoạn chuyển tiếp có một hệ quả cần hiện rõ: một thay đổi commit vào git sẽ được hệ mới áp ngay, nhưng Barrowa thì không — hai nguồn lệch nhau cho tới khi có người áp tay bên kia. Màn hình phải hiện tình trạng lệch hiện tại ngay cạnh nút áp thay đổi, và nhắc rằng thao tác tương ứng trên Barrowa vẫn phải làm.

### 4.9 Đồng bộ giữa các nguồn

| ID | Yêu cầu |
|---|---|
| **FR-42** | **Bộ so sánh là tiến trình riêng.** Đọc các luồng SI đang trên sóng cùng cấu hình trong git, báo động khi lệch. Không có quyền dừng hay chặn tiến trình phát nào. Chạy được trên máy thứ ba. |
| **FR-43** | Khi phát hiện lệch, sinh **bản vá YAML đề xuất** dạng diff sẵn sàng commit. Người vận hành xem rồi chấp nhận; **hệ không bao giờ tự áp**. Giữ đúng quy tắc "version chỉ đổi khi người quyết định" mà vẫn bỏ được việc chép tay. |
| **FR-44** | **Khoá liên động tuỳ chọn**, mặc định tắt. Khi bật: chỉ rút khỏi địa chỉ sản xuất sau ít nhất hai chu kỳ so liên tiếp cho kết quả lệch. **Không đọc được luồng tham chiếu thì vẫn phát** — mất tham chiếu không phải bằng chứng sai. |
| **FR-45** | Lưu bền version cuối cùng đã phát ra đĩa sau mỗi lần đổi, để kiểm tra "không lùi" còn hoạt động sau khi khởi động lại mà không cần nguồn ngoài nào. |
| **FR-46** | **Tất định.** Cùng một commit git phải cho ra cùng một chuỗi byte, trên máy nào cũng vậy. Cấm timestamp sinh, cấm phụ thuộc thứ tự duyệt thư mục, cấm thứ tự lặp của tập hợp không ổn định. Mọi danh sách sắp xếp theo khoá tường minh. Đây là cơ chế giữ hai thực thể giống nhau, thay cho một giao thức đồng bộ. |

### 4.10 Xử lý nguồn EPG

| ID | Yêu cầu |
|---|---|
| **FR-47** | **Tự cấp `event_id`, tất định.** Không dùng `id` của nguồn — xem RO-12. Công thức đề xuất: `event_id = (số phút của thời điểm bắt đầu, tính từ mốc cố định 2020-01-01T00:00Z) mod 65536`. Tất định nên hai thực thể ngang hàng cho ra cùng số (FR-46); ổn định qua các lần nạp lại nên đầu thu không thấy sự kiện "mới"; và không đụng độ trong cửa sổ 8 ngày vì hai sự kiện của cùng một dịch vụ không được chồng lấn. *Giả định cần xác nhận: không có hai sự kiện cùng dịch vụ bắt đầu trong cùng một phút.* |
| **FR-48** | Thực hiện `period_overlapping_mode` do nguồn khai báo. Giá trị đang dùng là `removeEvent`. |
| **FR-49** | `running_status`: **đã đo trên sóng** — EIT p/f mang `running` (4). Bản dump chưa bắt được EIT schedule nên phần schedule vẫn chờ một bản thu dài hơn; đến lúc đó thì khớp đúng giá trị đang phát. |
| **FR-50** | `SHORT_DESCRIPTION` luôn rỗng trong nguồn. Sinh `short_event_descriptor` với `text_length = 0` — khớp hành vi `generate_empty_strings_with_length_zero=true` của Barrowa. Không sinh `extended_event_descriptor` khi không có nội dung. |
| **FR-51** | **Đã đo: EIT trên sóng chỉ có `short_event_descriptor` `0x4D`, không có `0x50`.** Bỏ `AUDIO` và `VIDEO` của nguồn, không sinh component descriptor. `emit_component_descriptor` giữ mặc định `false` và có thể xoá hẳn khỏi cấu hình. |
| **FR-52** | Tích luỹ nhiều file theo ngày thành cửa sổ 192 giờ, khử trùng lặp theo `(service_id, thời điểm bắt đầu)`, và loại sự kiện đã qua. Xem RO-13. |
| ~~**FR-54**~~ | ~~Cảnh báo khi SDT khai `EIT_*=true` mà dịch vụ không có lịch.~~ **Đã rút ở 0.9.** Cả 64 dịch vụ trên TS8 đều khai `EIT_*=true`, gồm 20 kênh phát thanh vốn không bao giờ có lịch — cảnh báo này sẽ kêu vĩnh viễn cho 20 kênh, tức là dạy người ta phớt lờ báo động. Số hiệu giữ trống, không dùng lại. |
| **FR-55** | **Bảng mã đặt ở mức `tsp`, không đặt trên từng chuỗi.** Lược đồ XML của TSDuck mang chuỗi Unicode chứ không mang byte dẫn bảng mã, nên bảng mã là tuỳ chọn dòng lệnh. Hợp với thực tế — nguồn và sóng đều dùng một bảng mã duy nhất — nhưng nghĩa là **trộn nhiều bảng mã trong một mẻ là im lặng sai**: phải kiểm và báo lỗi. |
| **FR-56** | **Đọc khoan dung, ghi nghiêm.** Bộ đọc phải nuốt được dữ liệu sai chuẩn từ sóng, nếu không thì mất khả năng đối chiếu. Bộ ghi phải từ chối sinh ra thứ sai chuẩn. Sự kiện vượt trần `duration` bị **loại ra kèm báo động**, không ném lỗi làm hỏng cả mẻ — xem RO-22. |
| **FR-57** | **Soi số kênh.** Hệ phải phát hiện: hai dịch vụ cùng một số trong một bouquet; số ngoài dải 1…1023 của 10 bit NorDig; số trỏ tới dịch vụ không có trong bouquet hoặc không có trong SDT. Ba điều đó **chặn**. Dịch vụ có mặt mà thiếu số thì **chỉ báo**, và **chỉ trong bouquet có đánh số ở đâu đó** — bouquet không đánh số nào là một *nhóm* (0x6550 gom 48 dịch vụ để khoá mã), báo ở đó là báo động giả. Xem RO-23 và lý do rút FR-54. |
| **FR-58** | **EIT rỗng không được ghi đè EIT đang phát.** Khi không sinh được bảng EIT nào — hầu hết là vì hộp thư chỉ còn lịch cũ — hệ phải **giữ nguyên** file cũ, báo rõ nguyên nhân, và thoát mã 1. Ghi một EIT rỗng lên file đang phát là cách chắc chắn nhất để xoá sạch EPG cả mạng bằng đúng một lệnh chạy định kỳ, không ai làm gì sai. Mã thoát của `vtcsi refresh` thì bám theo **bảng cấu trúc**, không bám theo EIT: mất EPG khó chịu, mất NIT là mất kênh. |
| **FR-59** | **Sửa linkage qua giao diện, có hàng rào.** Sửa tại chỗ theo **chỉ số**, không khoá theo nội dung: bouquet 0x3622 đang phát hai mục 0x80 giống hệt nhau và khoá theo nội dung sẽ gộp chúng lại. ``private_data`` chỉ nhập được ở dạng **hex thô** — không có đặc tả Irdeto/ViCAS thì mọi ô 'thân thiện' đều là bịa. Xoá đòi gõ lại đúng loại linkage. Chặn: loại 0x00/0xFF, trường vượt 16 bit, khối riêng vượt **248** byte (255 − 7 byte đầu của descriptor). Đích trỏ vào TSID không có thì **báo, không chặn** — RO-8. |
| **FR-60** | **Thêm và bỏ vòng transport của bouquet.** Vòng mới ra **rỗng**: thêm vòng và chọn kênh là hai quyết định khác nhau. Bỏ một vòng còn dịch vụ đòi **gõ đúng số dịch vụ** của vòng đó — một con số phải nhìn mới biết. ``original_network_id`` **không suy ra được** từ ``ts_id`` (TS 8 mang 12901, TS 3 và 1000 mang 1) nên giao diện gợi ý từ SDT. |
| **FR-61** | **Vòng có số kênh bắt buộc khai ``private_data_specifier``** — chặn. Thiếu nó thì đầu thu không biết descriptor 0x83 thuộc đặc tả riêng nào và bỏ qua cả khối: **toàn bộ bảng số kênh biến mất, im lặng**. Trên sóng, PDS có mặt đúng ở những vòng có LCN và vắng ở ba vòng của 0x6550 — bất biến đó giờ được canh. |
| **FR-62** | **Cấu hình không nạp được thì ra trang lỗi, không ra stack trace.** Giao diện đọc lại YAML mỗi lượt nên một file hỏng làm mọi trang chết. Trang lỗi nói **hỏng ở đâu** và **quay lui bằng lệnh nào**. Trang `thay-doi` không nạp cấu hình nên vẫn sống — và nó đúng là trang cần dùng để sửa chuyện đó. |
| **FR-63** | **Mọi thông báo tới người vận hành là tiếng Việt có dấu.** Áp cho `model.lcn`, `model.linkage`, `model.topology`, `model.plain`, `config.loader` và cả lớp web. Nửa có dấu nửa không trên cùng một trang đọc như lỗi hiển thị. Đầu ra dòng lệnh giữ nguyên không dấu — nó chạy trong terminal và log, nơi bảng mã không chắc chắn. |
| **FR-64** | **Version đặt bằng tay, và lùi lại được.** Giao diện nhận một số bất kỳ trong 0…31, kể cả **nhỏ hơn** giá trị hiện tại. Đầu thu phát hiện version *đổi* chứ không phải *tăng* — trường 5 bit quay vòng nên không có thứ tự tuyệt đối; đặt nhầm thì gõ lại số cũ là sửa xong, miễn là bảng chưa lên sóng ở giá trị nhầm. Nếu chỉ cho tăng thì cách duy nhất để về chỗ cũ là bấm thêm **31 lần**, mỗi lần cả mạng dò lại kênh. Hàng rào là gõ lại đúng con số muốn đặt, cộng một hộp thoại nói rõ *cũ → mới* và loại bước. Đặt lại đúng giá trị đang có bị **từ chối**, không im lặng bỏ qua. |
| **FR-65** | **Giao diện đòi đăng nhập, mặc định bật.** Mật khẩu băm bằng `hashlib.scrypt` của thư viện chuẩn (n=2¹⁵), muối ngẫu nhiên mỗi lần. Phiên là cookie ký HMAC, `HttpOnly` + `SameSite=Lax`, sống 12 giờ. Chặn ở **một middleware duy nhất**, không rải decorator lên từng tuyến — rải ra thì thêm một tuyến mà quên gắn là mở một lối vào và không gì nhắc. Sai 5 lần khoá 1 phút; **không khoá vĩnh viễn**, vì hệ chỉ có một người dùng và khoá cứng là tự nhốt mình ra ngoài đúng lúc đang có sự cố. |
| **FR-66** | **Mật khẩu đầu tiên chỉ đặt được từ terminal** — `vtcsi passwd`. Không có trang tạo tài khoản lần đầu, vì trang đó nghĩa là *ai chạm tới cổng trước thì người đó làm chủ*. Quyền shell trên máy phát là ranh giới sẵn có và ta dùng lại nó. Quên mật khẩu thì `vtcsi passwd --force`; không có đường phục hồi qua trình duyệt. |
| **FR-67** | **File mật khẩu nằm ngoài git, và điều đó được kiểm bằng git.** Cấu hình báo hiệu *phải* trong git — đó là cơ chế đồng bộ. Băm mật khẩu thì ngược lại: vào git một lần là nằm trong lịch sử **mãi mãi**, kể cả sau khi xoá. Mặc định `.vtcsi-auth.json` ở gốc kho, có trong `.gitignore`, và trang Quản trị kiểm lại bằng `git check-ignore` rồi kêu to nếu sai. |
| **FR-68** | **Đổi mật khẩu là đăng xuất mọi nơi.** Khoá ký phiên sinh lại cùng lúc, nên mọi vé cũ hết hiệu lực — kể cả vé của chính trình duyệt đang thao tác. Đó đúng là điều người ta mong đợi khi họ đổi mật khẩu vì nghi bị lộ. |
| **FR-69** | **Công tắc EPG từng kênh, và nó phải có tác dụng thật.** Cột EPG ở trang TS là một công tắc Bật/Tắt cho mỗi dịch vụ, gửi cả cột một lượt. Tắt thì hạ **cả hai** cờ `EIT_present_following` và `EIT_schedule` trong SDT, **và** `vtcsi epg` không sinh bảng EIT cho dịch vụ đó. Hai việc phải đi cùng nhau: cờ trong SDT chỉ là *lời khai*, đầu thu vẫn hiện EPG nếu bảng có trên sóng — khai một đằng phát một nẻo là kiểu sai khó tìm nhất. Số dịch vụ bị bỏ được **in ra** mỗi lần sinh, vì ba tháng sau sẽ có người hỏi vì sao kênh đó không có chương trình. Khi hai cờ khai khác nhau, cột gắn nhãn *lệch* chứ không làm tròn. |
| **FR-70** | **Một công tắc EPG, không phải hai cờ.** SDT có hai bit riêng nên mô hình giữ đúng hai trường, nhưng **không màn hình nào cho tách chúng ra**. Công tắc này để tắt nhanh khi có sự cố: lúc đó người trực cần một câu hỏi có hai câu trả lời, không phải hai ô để cân nhắc. Hai cờ chỉ lệch được khi sửa YAML bằng tay; khi đó giao diện **báo ra** và lần lưu kế tiếp đưa chúng về một mối. |
| **FR-71** | **Sinh lại NGAY khi có thay đổi, không theo chu kỳ.** Hai nguồn kích hoạt: lưu cấu hình trên web, và có file mới hoặc đổi trong hộp thư lịch / thư mục cấu hình (`vtcsi run` ngó mỗi **5 giây**). Chu kỳ một giờ hạ xuống thành **lưới an toàn** cho việc cửa sổ EIT trôi theo thời gian. Không khởi động lại `tsp` — `--poll-files` tự đọc lại, nên **không có lần chớp nguồn nào**. Sinh lại hỏng thì không làm hỏng việc ghi cấu hình. Về thời gian thực tế, xem FR-93. |
| **FR-93** | **Thay đổi lên sóng sau khoảng một phút, không phải nửa giây.** Đo thật, hai chặng: ghi YAML rồi sinh lại XML mất **1–2,5 giây**; `tsp` nhận ra file đổi mất **67 giây** với plugin `inject` (NIT/SDT/BAT). TSDuck **không cho chỉnh** nhịp poll của `inject` — nó không có tuỳ chọn nào tương đương `--poll-interval` mà `eitinject` có. Đường EIT đi qua `eitinject` với `--poll-interval 500` nên có thể nhanh hơn, **chưa đo**. Bản trước của đặc tả ghi "nửa giây" cho cả hai đường; con số đó là suy đoán lúc viết, không phải phép đo, và nó nguy hiểm theo một cách cụ thể: người trực chờ không thấy đổi sẽ tưởng hệ hỏng rồi dựng lại dịch vụ — mà dựng lại **mới** là thứ gây chớp nguồn, còn sửa nội dung thì không. Một phút là chấp nhận được về vận hành: đầu thu còn mất lâu hơn nhiều để đọc lại bảng. |
| **FR-94** | **Rút một kênh khỏi lịch thì phải khởi động lại `si`.** `eitinject` giữ một bản EPG tích luỹ trong bộ nhớ và **chỉ cộng vào, không bao giờ bớt đi**: file lịch thôi nhắc tới một dịch vụ thì dịch vụ đó vẫn tiếp tục được phát, vô thời hạn. Đo ngày 2026-09-15: `/build/eit/eit.xml` còn **17 dịch vụ**, bản thu trên sóng có **40** — đúng 17 cộng 23 kênh đã rút. Không sự kiện nào trên sóng mà không có trong bảng sinh ra, nên đây thuần tuý là chuyện **thừa**, không phải sai nội dung. Hệ quả vận hành: sửa nội dung NIT/SDT/BAT thì **không** được dựng lại (FR-93), còn rút kênh khỏi EPG thì **bắt buộc** phải dựng lại — hai lời khuyên ngược nhau, nên phải hỏi đúng câu trước khi làm: *thêm hay bớt?* Thêm và sửa thì `--poll-interval` lo được; bớt thì không. Kiểm bằng `cong-cu/so-eit.py` so bảng sinh ra với bản thu: dòng `... PHAT co, ... SINH RA KHONG` phải rỗng. |
| **FR-72** | **Tắt EPG một kênh phải ăn thua cả khi hộp thư đã cũ.** Khi không sinh lại được EIT (hộp thư chỉ còn lịch cũ), hệ **gỡ bảng của kênh vừa tắt khỏi tài liệu EIT cũ** thay vì giữ nguyên. Gỡ bảng làm được mà không cần dữ liệu mới: ta không cần biết chương trình nào đang chạy, chỉ cần biết kênh nào phải im. Không có điều này, công tắc khẩn hỏng đúng lúc cần nhất. FR-58 vẫn nguyên: hộp thư cũ mà **không ai tắt kênh nào** thì file giữ nguyên. |
| **FR-73** | **Tuyến nhận XML từ hệ lập lịch bên ngoài.** `POST /api/epg`, thân yêu cầu là **chính nội dung XML** chứ không bọc JSON — bên gửi đã có sẵn file, bắt họ mã hoá base64 rồi nhét vào một trường JSON chỉ thêm một bước để sai. Trả JSON đủ để bên kia ghi log: tên file đã ghi, TSID, số dịch vụ, số sự kiện, khoảng thời gian, kết quả sinh lại. |
| **FR-74** | **Kiểm trước khi ghi, và không ghi gì khi từ chối.** File hỏng nằm trong hộp thư sẽ làm hỏng lần sinh EIT kế tiếp — mà lần đó xảy ra **vài giây sau** và không ai đang nhìn. Từ chối ngay lúc nhận (mã 400 kèm lý do) là cách duy nhất để không bao giờ có file hỏng trên đĩa. Ghi bằng file tạm rồi `replace`, nên không bao giờ có file nửa vời. Tên file chặn `..`, `/`, `\` và dấu chấm đầu. |
| **FR-75** | **Vé cho máy, tách khỏi mật khẩu của người.** Hệ bên ngoài dùng chuỗi ngẫu nhiên 32 byte trong header `Authorization: Bearer` hoặc `X-VTCSI-Token`. **Không** đọc vé từ query string: URL nằm trong log của mọi proxy trên đường đi. **Đổi mật khẩu không đổi vé** — bắt hệ bên ngoài cấu hình lại mỗi lần người vận hành đổi mật khẩu là cách chắc chắn để có người tắt xác thực cho đỡ phiền. Cấp vé mới thì vé cũ chết ngay. |
| **FR-76** | **Tên file suy từ ngày của sự kiện sớm nhất.** Nhờ vậy gửi lại cùng một ngày là **ghi đè đúng file cũ**, không đẻ ra bản trùng; và vì `load_all` sắp theo tên nên thứ tự ngày cũng là thứ tự nạp, tức "bản sửa gửi sau thắng". Đặt tên tay được bằng `?ten=`. |
| **FR-77** | **Tên đăng nhập mặc định là `admin`.** |
| **FR-78** | **Màn giám sát — lưới lịch sẽ lên sóng.** Một dòng mỗi kênh, trục ngang 24 giờ, ô đỏ là chương trình đang phát, vùng gạch chéo là lỗ hổng lịch. Mốc thời gian truyền đi bằng **số phút kể từ 00:00 giờ địa phương**, không phải chuỗi giờ: giao diện đặt ô ở `phút × px` và phép so "đang phát" chỉ còn là so hai số nguyên. |
| **FR-79** | **Màn giám sát là danh mục đủ của TS actual.** Một phép lọc duy nhất: chỉ **TS actual** — `eitinject --actual --ts-id N` không sinh EIT cho TS khác. Kênh **tắt EPG vẫn có dòng**: nó vẫn là kênh của transport stream này, và một màn giám sát giấu bớt kênh là màn giám sát phải tin chứ không kiểm được. Nhưng dòng đó **rỗng**, kể cả khi hộp thư có đầy lịch cho nó — kênh tắt không có bảng EIT nào trên sóng, nên vẽ chương trình lên đó là nói dối. Việc bỏ sự kiện nằm trong `timeline.build`, **một luật một chỗ**: để nơi gọi tự nhớ thì sớm muộn có nơi quên, và công tắc EPG thành lời hứa suông. |
| **FR-79b** | **Rỗng vì *tắt* đếm riêng với rỗng vì *thiếu lịch*.** Một bên là lựa chọn của người vận hành, một bên là sự cố — gộp lại thì con số mất hết ý nghĩa. Dải thống kê luôn thoả `có lịch + chưa có lịch + tắt EPG = kênh`. Trên lưới, dòng tắt gạch chéo mờ và mang nhãn **TẮT**; dòng thiếu lịch giữ nguyên chữ *Không có thông tin* — đúng thứ đầu thu sẽ hiện. |
| **FR-80** | **Kênh không có chương trình vẫn có một dòng rỗng.** Chính những dòng rỗng mới là thứ đáng nhìn: đó là kênh sẽ hiện "Không có thông tin" trên đầu thu. Lỗ hổng chỉ tính **giữa** hai chương trình, không tính hai đầu ngày — một kênh lên sóng từ 05:00 không có "lỗ hổng năm tiếng", và một con số luôn khác không là một con số không ai nhìn. |
| **FR-81** | **EIT schedule mang `type` là số, không phải chữ.** Lược đồ XML của TSDuck khai `type="pf|uint4"`: chữ `pf` (table_id 0x4E) hoặc **một số 0–15** cộng vào 0x50. Không có chữ `schedule`. Ghi sai thì `eitinject` từ chối **toàn bộ** bảng EIT — mất sạch EPG trong khi NIT, SDT, BAT vẫn lên sóng. Ghim bằng bài kiểm gọi thẳng `tstabcomp`, không đọc lại XML. |
| **FR-82** | **Không một đường dẫn nào ở tuyến `inject` được mang ký tự đại diện.** `inject` của TSDuck **không nở** ký tự đại diện và **không báo lỗi** khi không tìm thấy: `tsp` chạy bình thường, PID 17 vẫn có bitrate, và sáu BAT lặng lẽ biến mất. Mỗi bouquet một tên file tường minh. `eitinject --files` thì ngược lại, **có** nở — hai plugin, hai luật. |
| **FR-83** | **Bitrate khai ở mức `tsp`, trước mọi plugin.** `-I null` không khai bitrate nào, và `inject` cần biết để tính nhịp gói. Chỉ đưa bitrate cho `regulate` — nằm cuối chuỗi — thì `tsp` chết ngay khi khởi động: *input bitrate unknown or too low*. |
| **FR-84** | **Một bảng mã duy nhất cho tên sự kiện: `--default-charset UTF-8`.** Không đặt thì TSDuck chọn bảng mã **cho từng chuỗi**, lấy cái gọn nhất vừa được: phần lớn ra 0x15 UTF-8, nhưng một số ra ISO-8859-15 (0x0B) hoặc ISO-8859-2 (0x10 0x0002). Hợp chuẩn cả, giải đúng cả — nhưng đo bản thu sóng thật cho thấy **Barrowa chưa bao giờ phát hai bảng mã đó**. Đây là hệ dự phòng cho Barrowa, nên chuẩn là những gì Barrowa đang làm. SDT và BAT không cần tuỳ chọn này: tên dịch vụ và tên bouquet đều thuần ASCII nên để trần, trùng từng byte với sóng thật. |
| **FR-85** | **Bài kiểm không được đọc `epg/inbox` thật.** Hộp thư là chỗ hệ lập lịch bên ngoài thả file mới mỗi ngày, nên mọi khẳng định kiểu "tới ngày này thì hết lịch" đều có hạn dùng — bài sẽ đỏ đúng vào ngày hệ chạy **đúng**. Dựng hộp thư riêng từ file mẫu đã commit, y như `tests/seed.py` làm với `config/`. |
| **FR-86** | **Địa chỉ multicast đầu ra nằm ngoài `Config` và ngoài git.** Nó không phải báo hiệu: không một byte nào trong NIT, SDT, BAT hay EIT phụ thuộc vào nó. Quan trọng hơn, nó là **thứ duy nhất trong cả hệ được phép khác nhau giữa hai máy** — cấu hình báo hiệu giống nhau chính là cơ chế đồng bộ, còn hai máy cùng bắn một nhóm multicast ra cùng một mạng là đúng cái hỏng mà cặp máy dự phòng sinh ra để tránh. File riêng `config/dau-ra.yaml`, có trong `.gitignore`, sửa trên trang **Đầu ra** của giao diện. |
| **FR-87** | **Địa chỉ đầu ra hỏng thì không được ghi xuống đĩa.** Khác mọi trang cấu hình khác, nơi một bản nháp sai nằm yên trong git cho tới lúc bấm áp dụng: file này `vtcsi run` đọc thẳng lúc khởi động. Ghi một địa chỉ hỏng vào đây là để sẵn một quả mìn cho lần dựng lại dịch vụ kế tiếp — mà lần đó thường xảy ra lúc nửa đêm và vì một lý do khác. Từ chối thì file cũ phải còn **nguyên vẹn**. |
| **FR-88** | **Đường sao chép là một tiến trình `tsp` con, không phải đích thứ hai.** `-O ip` chỉ nhận một đích và `tsp` chỉ có một plugin đầu ra, nên bản sao đi qua `-P fork` — đặt **trước** `-O ip` vì `fork` là plugin xử lý. Nhánh con **không có `regulate`**: nhịp đã do nhánh cha giữ, hai bộ điều nhịp trên một dòng thì đánh nhau. Sao chép trùng hoàn toàn đường chính (cùng địa chỉ, cùng cổng, cùng card) bị **chặn**: đó là gói trùng, không phải dự phòng. |
| **FR-92** | **Version SDT và BAT tăng tự động; NIT vẫn bằng tay.** Mốc so là **bản đã commit**, không phải lần lưu trước. Chỉ tăng đúng một ô của bảng phán quyết — nội dung đã rời khỏi bản commit mà version còn nguyên (`SILENT_CHANGE`). Nội dung không đổi thì không tăng, kể cả khi người ta đã tự đặt số khác — đó là đường sửa một lần bấm nhầm. Nội dung đổi mà version cũng đã đổi thì tôn trọng con số người ta đặt. Hệ quả của việc lấy HEAD làm mốc: **một lần tăng cho mỗi chu kỳ commit**, và **hai máy ngang hàng ra cùng một số** dù số lần bấm Lưu khác nhau. Một bộ đếm theo thao tác sẽ phá cả hai, và phá theo kiểu tệ nhất — cùng version mang hai nội dung khác nhau, đầu thu không đọc lại. NIT nằm ngoài vì đổi NIT là cả mạng dò lại kênh; đổi lại `preflight` phải canh NIT gắt hơn, vì NIT đổi ngầm thì **mất kênh**. Không đọc được HEAD thì **không tăng gì cả**. |
| **FR-89** | **Mốc đối chiếu của các bài so byte là một THẺ GIT, không phải HEAD.** AC-1 và AC-2 hỏi: *bộ sinh có dựng lại đúng từng byte các bảng bóc từ sóng, từ chính cấu hình đọc ra từ sóng không?* Câu trả lời không được phép đổi, nên mốc phải đứng yên — thẻ `gieo`. Lấy HEAD làm mốc thì commit thay đổi vận hành đầu tiên (tăng version, tắt EPG một kênh) sẽ làm đỏ **15 bài cùng lúc, kể cả bảy bài so byte**, mà không bài nào tìm ra lỗi gì. Thiếu thẻ thì phải **đỏ**, không được bỏ qua: một bài bỏ qua vì môi trường trông y hệt một bài bỏ qua vì chưa cài gì. |
| **FR-90** | **Hai nửa của bộ container phải trỏ cùng thư mục.** `vtcsi web` nhận `--build` và `--inbox` mặc định **tương đối**, giải theo `WORKDIR`. Bỏ trống trong `docker-compose.yml` thì giao diện ghi file lịch vào `/app/epg/inbox` còn `vtcsi run` đọc `/repo/epg/inbox`: trình duyệt báo *đã nhận*, màn giám sát trống trơn, EPG **không bao giờ lên sóng**, và không có lỗi nào được ném. Ghim bằng `tests/test_docker.py`. |
| **FR-91** | **Dịch vụ phát PHẢI chạy `network_mode: host`.** Multicast không đi ra đúng cách qua mạng bridge của Docker: NAT không xử lý multicast, và `--local-address` trong bridge chỉ thấy veth của container chứ không thấy card thật. Đổi sang bridge thì luồng biến mất khỏi mạng trong khi container vẫn xanh và log vẫn sạch. Cũng vì vậy **không đặt hạn ngạch CPU**: cgroup throttling chèn khựng vào đúng chỗ cần đều nhịp, và mux đọc khoảng lặng thành *mất nguồn*. |
| **FR-53** | **Tiêu thụ mọi dịch vụ có trong file lịch**, không cần khai báo từng cái. Đây là điểm khác Barrowa: ở đó phải gán nguồn thủ công cho từng dịch vụ, và 26 kênh bị bỏ quên vì thế (RO-19). Muốn loại một dịch vụ thì phải ghi tường minh vào danh sách loại trừ. |

---

## 5. Yêu cầu phi chức năng

| ID | Yêu cầu |
|---|---|
| **NFR-1** | Chạy Linux, đóng gói Docker. Container phát luồng dùng `network_mode: host` — mạng bridge không cho multicast đi ra đúng cách. |
| **NFR-9** | **Trông chừng không được biến thành chớp nguồn.** Sửa nội dung (tên kênh, số kênh, lịch) **không** được khởi động lại `tsp` — `inject --poll-files` và `eitinject --poll-interval` tự đọc lại file. Chỉ thay đổi *dòng lệnh* mới được dựng lại. Giãn cách khi hỏng có trần 30 giây và **không bao giờ bỏ cuộc**; sau 5 lần chết-khi-khởi-động liên tiếp thì đổi mức báo động chứ không ngừng thử. Mốc `--time` của `eitinject` **tính lại mỗi lần dựng** — luồng ta không có TDT/TOT, dùng lại mốc cũ là phát EPG lệch ngày. |
| **NFR-2** | **Không đặt CPU quota** cho container phát luồng; throttling của cgroup gây giật nhịp. |
| **NFR-3** | Container phát luồng đặt `restart: unless-stopped` và **tách khỏi nhịp deploy** của Coolify. |
| **NFR-4** | Host bắt buộc chạy NTP hoặc chrony **có giám sát**. Lệch giờ làm EIT p/f sai và làm hai nguồn tính ra cặp present/following khác nhau. |
| **NFR-5** | Toàn bộ cấu hình là file văn bản trong git. Mỗi thay đổi có tác giả và lý do. |
| **NFR-6** | Build TSDuck từ nguồn với `NODEKTEC=1 NOVATEK=1 NOSRT=1 NORIST=1 NOPCSC=1` để tránh phụ thuộc đóng của Dektec. Dùng cùng bộ biến cho mọi lệnh make trên cùng bản build. |
| **NFR-7** | Khởi động lại toàn hệ dưới 30 giây. |
| **NFR-8** | Một người đọc repo trong một ngày phải nắm được hệ thống. |

---

## 6. Mô hình cấu hình

Thư mục `config/`, toàn bộ trong git.

### 6.1 `network.yaml`

```yaml
network:
  network_id: 12901          # 0x3265
  name: "VTC"
  actual: true
  version: 28                # THỦ CÔNG — xem FR-15

  descriptors:
    - type: linkage
      linkage_type: 0x09     # SSU
      onid: 12901
      ts_id: 8
      service_id: 0

  transport_streams:
    - ts_id: 8
      original_network_id: 12901
      role: actual
      delivery:
        system: DVB-S2
        modulation: 8PSK
        frequency_hz: 10_968_000_000
        polarization: horizontal
        symbol_rate_sps: 28_800_000
        fec_inner: "3/4"
        roll_off: 0.25
        orbital_position: 132.0
        east: true

    - ts_id: 3
      original_network_id: 1
      role: other
      delivery:
        system: DVB-S2
        modulation: 8PSK
        frequency_hz: 11_088_000_000
        polarization: vertical
        symbol_rate_sps: 18_750_000
        fec_inner: "5/6"
        roll_off: 0.25
        orbital_position: 132.0
        east: true

    - ts_id: 1000
      original_network_id: 1
      role: other
      delivery:
        system: DVB-S2
        modulation: 8PSK
        frequency_hz: 11_589_000_000
        polarization: horizontal
        symbol_rate_sps: 15_000_000
        fec_inner: "3/4"
        roll_off: 0.25
        orbital_position: 132.0
        east: true
```

### 6.2 `services/ts8.yaml`

```yaml
ts_id: 8
original_network_id: 12901
sdt_version: 7               # THỦ CÔNG

services:
  - service_id: 801
    name: "HA NOI 1"
    provider: "VTC"
    type: 0x01               # 0x01 TV số, 0x02 radio
    running_status: 4        # đang chạy
    free_ca_mode: false
    eit_pf: true
    eit_schedule: true
  # ... 64 dịch vụ
```

### 6.3 `bouquets/vtc_fullhd.yaml`

```yaml
bouquet_id: 0x6510           # 25872
name: "VTC_FULLHD"
version: 26                  # THỦ CÔNG

descriptors:
  - type: linkage
    linkage_type: 0x05       # kênh barker
    onid: 12901
    ts_id: 16
    service_id: 1639

members:                     # nguồn sinh service_list 0x41 — FR-3
  - ts_id: 3
    services: [1, 2, 4, 9, 10, 12, 13, 14, 15, 16, 24, 25, 27, 28]
  - ts_id: 8
    services: [801, 802, 803]

lcn:
  private_data_specifier: 0x00000031
  entries:
    - { ts_id: 8, service_id: 801, lcn: 1,  visible: true }
    - { ts_id: 8, service_id: 802, lcn: 2,  visible: true }
    - { ts_id: 3, service_id: 10,  lcn: 52, visible: true }
```

### 6.4 `bouquets/master_irdeto.yaml`

```yaml
bouquet_id: 0x3622           # 13858
name: "Master"
version: 18                  # THỦ CÔNG

private_data_specifier: 0x00362275   # Irdeto

descriptors:
  - type: linkage
    linkage_type: 0x80
    manufacture_code: 0x0000           # ĐIỀN THẬT
  - type: linkage
    linkage_type: 0x82
    ts_id: 0
    service_id: 0
    manufacture_code: 0x0000
    hardware_version: 0
    load_sequence_number: 0            # PHẢI TĂNG mỗi lần nạp firmware
```

> `load_sequence_number` là điểm nối duy nhất với hệ thống DSM-CC bên ngoài. Xem RO-2.

### 6.5 `output.yaml`

```yaml
instance_id: "si-a"          # nhan dinh danh, chi de ghi log va do dac

output:
  destination: "236.30.232.1:6000"   # dia chi RIENG cua thuc the nay
  interface: "10.10.30.240"
  ttl: 8
  bitrate_bps: 2_000_000     # ĐO VÀ KHỚP với Barrowa ở giai đoạn T1
  packets_per_datagram: 7

repetition_ms:
  nit_actual: 2000
  sdt_actual: 1000
  sdt_other: 5000
  bat: 5000
  eit_pf_actual: 1200
  eit_sched_day_1_4: 10000   # Barrowa đang 20000, vượt trần TS 101 211
  eit_sched_day_5_8: 10000

epg:
  source_dir: "/srv/vtcsi/epg/inbox"      # thu muc theo doi
  http_pull: ""                            # tuy chon
  store: "/srv/vtcsi/epg/store"            # kho tich luy, ben qua khoi dong lai
  event_id_epoch: "2020-01-01T00:00:00Z"   # moc cho FR-47
  emit_component_descriptor: false         # 0x50 — bat sau khi xac minh o T2
  schedule_running_status: 0               # 0 = undefined; doi chieu Barrowa o T2

eit:
  depth_hours: 192
  alarm_below_hours: 120

tdt_tot:
  enabled: false             # chỉ bật khi mux KHÔNG sinh PID 20 — xem RO-9
  local_time_offset: "+07:00"
  dst: false
  repetition_ms: 30000

# Khoa lien dong — tuy chon, mac dinh tat. Xem §3.5.
# Bat len thi PHAI hong theo huong mo: mat tham chieu van phat.
interlock:
  enabled: false
  peer_stream: "udp://236.30.231.1:6000"
  compare_interval_s: 30
  withdraw_after_failures: 2
  on_reference_lost: keep_transmitting   # gia tri duy nhat duoc phep
```

Bộ so sánh (FR-42) có file cấu hình riêng vì nó là tiến trình độc lập, chạy được trên máy khác:

```yaml
# compare.yaml
sources:
  - {name: "barrowa", url: "udp://236.30.231.1:6000"}
  - {name: "si-a",    url: "udp://236.30.232.1:6000"}
  - {name: "mux-out", url: "udp://236.30.240.1:6000"}   # dau ra that cua mux
config_repo: "/srv/vtcsi/config"
interval_s: 30
alert:
  snmp_trap: ["10.x.x.x:162"]
  prometheus_port: 9109
```

---

## 7. Chu kỳ lặp

Trần theo ETSI TS 101 211. Con số 25 ms hay bị trích là **khoảng cách tối thiểu giữa hai section**, không phải chu kỳ phát.

| Bảng | Barrowa | Trần chuẩn | Hệ này |
|---|---:|---:|---:|
| NIT actual | 2 000 ms | 10 000 ms | 2 000 ms |
| SDT actual | 1 000 ms | 2 000 ms | 1 000 ms |
| SDT other | 5 000 ms | 10 000 ms | 5 000 ms |
| BAT | 5 000 ms | 10 000 ms | 5 000 ms |
| EIT p/f actual | 1 200 ms | 2 000 ms | 1 200 ms |
| EIT schedule, 8 ngày đầu | 20 000 ms ⚠ | 10 000 ms | **10 000 ms** |
| TDT / TOT | tắt | 30 000 ms | 30 000 ms *nếu bật FR-33* |

⚠ Điểm không tuân thủ duy nhất của hệ hiện tại. Siết về 10 s làm PID 18 tăng khoảng gấp đôi — thêm chừng 135 kbps trên transponder khoảng 60 Mbps, dưới 0,25 %. **Áp ở giai đoạn T4**, sau khi đã khớp bit với chuẩn vàng, để không lẫn hai loại khác biệt.

---

## 8. Pipeline TSDuck

Hình dạng dự kiến. **Tuỳ chọn dòng lệnh cụ thể phải đối chiếu `tsp --help` của đúng bản đang cài** — chúng thay đổi giữa các phiên bản.

```
tsp -I null \
    -P inject <nit.xml>  --pid 16 ... \
    -P inject <sdt_bat.xml> --pid 17 ... \
    -P eitinject --files <eit_dir> ... \
    -P regulate --bitrate <bitrate_bps> \
    -O ip <destination> --local-address <interface> --ttl <ttl>
```

Phân chia trách nhiệm:

| Việc | Ai làm |
|---|---|
| Mã hoá section, CRC-32 | TSDuck |
| Carousel và chu kỳ lặp | TSDuck `inject`, `eitinject` |
| Continuity counter, null stuffing, CBR | TSDuck `regulate` |
| Phát UDP multicast | TSDuck output `ip` |
| Sinh EIT p/f và schedule, quản version EIT | TSDuck `eitinject` |
| YAML → XML bảng | **Lớp điều khiển** |
| File PSI → section EIT, tự cấp `event_id` | **Lớp điều khiển** |
| Quản version NIT/SDT/BAT | **Lớp điều khiển** |
| Đọc ngược, đối chiếu, chốt chặn | **Lớp điều khiển** |

Cần xác minh sớm: `inject` có tuỳ chọn tự nạp lại file khi nội dung đổi trên đĩa hay không — đó là cơ chế cập nhật nóng.

---

## 9. Giao diện dòng lệnh

```
vtcsi validate                  # kiểm tra cấu hình YAML, không phát
vtcsi build                     # sinh XML bảng và section EIT vào build/
vtcsi diff --against-air        # so cấu hình với bảng đang trên sóng
vtcsi versions --read-air       # đọc version NIT/SDT/BAT đang phát
vtcsi patch --from-air          # sinh ban va YAML de xuat tu sai lech (FR-43)
vtcsi preflight                 # kiem tra truoc khi dau vao mux (FR-18)
vtcsi run                       # chay pipeline — khong co tham so che do
                                # dia chi lay tu config/dau-ra.yaml (FR-86)
                                # --to de len tren, va TAT duong sao chep
vtcsi build --check-determinism # build hai lan, so hash (FR-46)

vtccmp run                      # bo so sanh — tien trinh rieng, may nao cung duoc
```

`vtcsi run` phải chạy chốt chặn FR-18 trước khi mở socket.

`--to` đè lên file và **tắt đường sao chép cùng lúc**. Giữ đường sao chép theo file trong một lần chạy thử nghĩa là bắn bản sao của dòng thử nghiệm ra đúng nhóm multicast đang phát thật — một tham số gõ vội không được phép làm việc đó.

---

## 10. Kiểm thử và nghiệm thu

| ID | Phép thử |
|---|---|
| **AC-1** | Vector cố định: encoder sinh đúng ba descriptor `0x43` ở Phụ lục A. |
| **AC-2** | Dump bảng từ luồng của hệ này và từ luồng Barrowa cho kết quả giống nhau ở mọi trường trừ version. Áp cho **cả EIT schedule** — Barrowa có phát, chỉ là phải thu đúng cách (RO-20). |
| **AC-3** | Đầu thu thật quét ra đủ 88 dịch vụ, đúng LCN, đúng bouquet. |
| **AC-4** | EPG 8 ngày trên đầu thu thật khớp lịch nguồn, tiêu đề tiếng Việt có dấu hiển thị đúng. |
| **AC-14** | Nạp file của tám ngày liên tiếp: không có hai sự kiện nào của cùng một dịch vụ trùng `event_id`, và nạp lại cùng một file không làm đổi `event_id` nào. |
| **AC-5** | Chốt chặn khởi động từ chối chạy khi cố ý đặt version lệch. |
| **AC-6** | Rút cáp một nguồn: mux chuyển sang nguồn kia, đầu thu **không** dò lại kênh và **không** mất EPG. Chuyển ngược lại cũng phải sạch. Thử cả hai chiều. |
| **AC-7** | Giám sát phát hiện được trường hợp cố ý sửa nội dung mà giữ nguyên version. |
| **AC-8** | Luồng đầu ra chỉ chứa PID 16, 17, 18 và null — cộng PID 20 khi bật FR-33; bitrate ổn định trong ±1 %. |
| **AC-9** | Một thay đổi thực hiện qua giao diện sinh ra đúng một commit git có tác giả và lý do, và cấu hình sau commit build được không lỗi. |
| **AC-10** | Cố ý sửa lệch một trường trong YAML: bộ so sánh báo động trong vòng một chu kỳ, và `vtcsi patch --from-air` sinh ra đúng bản vá đưa nó về khớp. Tiến trình phát **không** bị dừng. |
| **AC-11** | **Phép thử nguội.** Tắt hẳn nguồn kia, rồi khởi động lại từ trạng thái tắt máy. Phải chạy được và phát đúng bảng, chỉ từ YAML, không cần bất kỳ luồng tham chiếu nào. |
| **AC-12** | **Phép thử tất định.** Build cùng một commit trên hai máy khác nhau: NIT, SDT và BAT sinh ra phải trùng byte, hash giống hệt. |
| **AC-13** | **Phép thử độc lập.** Giết bộ so sánh: cả hai nguồn tiếp tục phát bình thường, không nguồn nào thay đổi hành vi. |

---

## 11. Lộ trình

| Giai đoạn | Thời lượng | Nội dung | Cổng |
|---|---|---|---|
| **T1** | 3–5 ngày | Đo hành vi mux; ghi lại version đang trên sóng | Biết mux phản ứng thế nào khi mất nguồn SI |
| **T2** | 1–2 tuần | Dump toàn bộ bảng ra XML rồi **gieo một lần** thành YAML — vừa là chuẩn vàng vừa là cấu hình khởi đầu; viết bộ so sánh | AC-2 chạy được trên hai bản dump của cùng luồng |
| **T3** | 2–3 tuần | YAML → XML → `inject` → multicast thử | AC-1, AC-2 |
| **T4** | 3–4 tuần | File PSI → `eitinject`; tự cấp `event_id`; tích luỹ cửa sổ 192 giờ; siết EIT schedule về 10 s | AC-4, AC-14 |
| **T5** | 1–2 tuần | Đấu vào mux thành input thứ hai ngang hàng; dựng bộ so sánh độc lập | AC-5, AC-6, AC-7, AC-10, AC-11, AC-13 |
| **T6** | 3–4 tuần | Giao diện nhập liệu §4.8 | AC-9, AC-10 |

Tổng **11–16 tuần** cho một người làm không toàn thời gian.

T6 nằm sau cùng có chủ đích: giao diện chỉ có giá trị khi phần sinh bảng đã đúng, và ở giai đoạn song song thì cấu hình vẫn nhập trên Barrowa. Nếu cần giao diện sớm hơn thì cắt T6 thành hai: một trang **chỉ đọc** hiển thị trạng thái và diff, làm cùng T5 trong khoảng ba ngày, rồi phần nhập liệu làm sau.

---

## 12. Rủi ro đang mở

| ID | Rủi ro | Hướng xử lý |
|---|---|---|
| **RO-1** | Hai nguồn lệch version hoặc nội dung NIT — mỗi lần mux chuyển input là một lần cả mạng dò lại kênh | Bộ so sánh phát hiện và báo động sớm (FR-42), kèm bản vá đề xuất (FR-43). Khoá liên động §3.5 là lớp thứ hai, tuỳ chọn. Ở giai đoạn ổn định thì tính tất định (FR-46) làm rủi ro này gần như biến mất. |
| **RO-2** | `load_sequence_number` của Irdeto phải khớp với hệ DSM-CC bên ngoài; chưa ai định nghĩa luồng thông tin này | Đưa vào quy trình nạp firmware của hệ kia |
| **RO-3** | Mã hoá `0x15` trên đầu thu đời cũ — byte dẫn này chỉ vào chuẩn từ EN 300 468 bản 2006 | Test trên đúng model đang lưu hành. Phạm vi hẹp: tên dịch vụ không dấu, chỉ tiêu đề EIT mới có dấu |
| **RO-4** | Barrowa đang đặt `dvb_default_language=eng`, `dvb_parental_rating_country=GBR` | Đổi sang `vie`/`VNM` nhưng phải kiểm tra hệ quả trên đầu thu trước |
| **RO-5** | Ba tham số dự phòng input của mux chưa biết: ngưỡng phát hiện mất nguồn, có tự quay về input ưu tiên không, có đánh lại continuity counter không | Đo ở T1 |
| **RO-6** | Bỏ linkage ViCAS là thay đổi nội dung NIT | Tăng version NIT khi áp dụng; xác nhận đầu thu ViCAS còn đường cập nhật khác qua linkage `0x09` SSU |
| **RO-10** | Ở giai đoạn chuyển tiếp, mỗi thay đổi phải áp hai nơi: commit vào git, và thao tác tay trên Barrowa. Quên một bên là hai nguồn lệch. | Không tránh được bằng kiến trúc, vì Barrowa không đọc được cấu hình của ta. Giảm bằng FR-43 sinh sẵn bản vá và giao diện §4.8. Đặt chỉ tiêu vận hành: tỉ lệ thời gian hai nguồn khớp nhau trong tháng. Giai đoạn ổn định xoá hẳn rủi ro này. |
| **RO-12** | **`event_id` của nguồn không dùng trực tiếp được.** Nguồn đánh số lại từ `64000` cho **mỗi dịch vụ**, và file một ngày dùng hết `64000–64086`. Nếu ngày mai lại bắt đầu từ `64000` thì trong cửa sổ 8 ngày sẽ có nhiều sự kiện cùng dịch vụ trùng `event_id` — điều DVB cấm. Mà cứ tăng dần thì cũng không xong: trần 16 bit chỉ còn `1449` chỗ, tức khoảng 16 ngày là hết. | Tự cấp `event_id` theo FR-47. Không sửa được ở phía nguồn thì cũng không cần sửa. |
| **RO-13** | **File mẫu chỉ có một ngày dữ liệu** (2026-09-08), trong khi cửa sổ khai báo là hai ngày và yêu cầu độ sâu là tám ngày. | Làm rõ với bên cấp lịch: file được phát hành theo ngày rồi hệ tự tích luỹ, hay có thể xin file nhiều ngày? Nếu tích luỹ thì FR-52 là bắt buộc và phải có kho lịch bền trên đĩa để sống sót qua khởi động lại. |
| **RO-14** | Lịch có lỗ: 46 khoảng trống giữa các sự kiện liên tiếp, lớn nhất 15 phút; 14 trên 44 dịch vụ chỉ phủ dưới 20 giờ mỗi ngày, mỏng nhất là 17 giờ. | Không phải lỗi kỹ thuật mà là chất lượng dữ liệu nguồn. Đầu thu sẽ hiện ô trống. Đưa vào chỉ tiêu giám sát cùng với tuổi EPG (FR-31). |
| **RO-19** | **26 trên 44 kênh truyền hình không có EPG trên sóng — kể cả now/next.** Bốn bản dump trải ba ngày đều cho đúng cùng một tập 18 dịch vụ có EIT. Không ngẫu nhiên. Nguyên nhân đã truy được: `epgsource.xml` của Barrowa **chỉ gán nguồn EPG cho 18 dịch vụ**, trong khi file lịch cung cấp đủ 44. Trùng khớp 17/18 giữa "được gán nguồn" và "lên sóng" — hai chỗ lệch còn lại giải thích được bằng việc bản backup cấu hình cũ hơn sóng. Đồng thời SDT lại khai `EIT_schedule=true` và `EIT_present_following=true` cho **cả 64 dịch vụ**, tức là hứa với đầu thu một thứ không có. | Không phải lỗi mux, và không phải lỗi kỹ thuật khó — là một khoảng trống cấu hình nằm hoàn toàn trong tầm tay VTC. Hệ mới xoá nó bằng cách mặc định tiêu thụ **mọi dịch vụ có trong file lịch** (FR-53). Riêng việc SDT khai `EIT_*=true` cho cả 64 dịch vụ thì **để nguyên**: 20 kênh phát thanh vốn không có lịch, nên mọi cảnh báo dựa trên cờ này sẽ kêu vĩnh viễn. Nếu về sau muốn dọn, cách đúng là *suy* cờ SDT từ việc dịch vụ có lịch hay không, chứ không phải báo động — nhưng đó là thay đổi nội dung trên sóng, phải tăng version và thử trên đầu thu trước. |
| ~~**RO-21**~~ | ~~Nghi có hồi quy: EPG 8 ngày từng chạy rồi hỏng.~~ **Đã rút ở 0.9** — kết luận dựa trên bản dump `tstables` thiếu schedule, mà nguyên nhân là cách thu chứ không phải sóng. Không có hồi quy nào. Số hiệu giữ trống, không dùng lại. |
| **RO-22** | **Một sự kiện trên sóng có `duration` DVB không biểu diễn được.** Dịch vụ 838 phát sự kiện độn tên *No Information* với `duration` **`48:00:01`**. Trường này là BCD `HHMMSS`, trần `23:59:59`. Hành vi đầu thu khi gặp giá trị ngoài dải là không xác định. Cùng dịch vụ đó, ở bản dump ngày 07/09, TSDuck không phân tích nổi bảng EIT — nhiều khả năng cùng một gốc. | Đây là lỗi của hệ đang chạy, chuyển cho vận hành Barrowa. Hệ mới xử lý theo FR-56: **đọc khoan dung, ghi nghiêm** — loại sự kiện hỏng ra và báo động, thay vì để một sự kiện làm sập EIT của cả 44 kênh. |
| **RO-23** | **Một kênh đang phát không có số kênh.** Dịch vụ **877 `CAO BANG RADIO`** nằm trong danh sách dịch vụ của bouquet **0x6510 `VTC_FULLHD`** nhưng không có mục nào trong `nordig_logical_channel_descriptor_v1`. Mười chín kênh phát thanh còn lại chiếm liền mạch **397…415**; chỗ trống đúng bằng **416**. Đầu thu gặp kênh không có LCN thì tự xếp — thường vào cuối danh sách, và không nhất quán giữa các model. | Gán **416**. Đây là thay đổi một dòng, nhưng vẫn phải tăng version BAT 0x6510. Phát hiện bằng `model.lcn.check`, tự động hoá trong FR-57. |
| **RO-20** | **`tstables` không bắt được EIT schedule — cạm bẫy của công cụ, không phải của sóng.** Năm bản dump đều cho `type="schedule"` bằng 0, trong khi StreamXpert soi cùng luồng lại thấy đầy đủ `day 0..3` và `day 4..7` ở 139 kbps. Nguyên nhân gần như chắc chắn: `tstables` mặc định chỉ xuất **bảng hoàn chỉnh**, mà một sub-table EIT schedule trải tới 256 section theo 32 segment — hoặc cửa sổ thu quá ngắn so với chu kỳ 20 s, hoặc bộ ghép section không bao giờ coi sub-table là đủ. Đáng chú ý: schedule là bảng có **chu kỳ dài nhất** và là thứ **duy nhất** vắng mặt, trong khi NIT 2 s, SDT 1 s, BAT 5 s, p/f 1,2 s đều bắt được. | Thu lại bằng `tstables --pid 18 --all-sections`, xuất từng section thay vì chờ bảng hoàn chỉnh, và cho chạy ít nhất hai phút. **Bài học cho `vtccmp`**: bộ so sánh của ta phải làm việc ở mức section, không chờ bảng hoàn chỉnh — nếu không nó sẽ mù đúng ở chỗ EIT schedule, tức 87 % tải SI. |
| **RO-15** | **Bouquet `0x6520` VTCHD_Basic đang phát rỗng.** Version 27, có tên bouquet, nhưng **không có transport loop, không dịch vụ, không LCN, không linkage**. Đầu thu nhận một gói kênh trống. | Xác nhận với vận hành: bouquet này còn dùng không? Nếu không thì bỏ; nếu có thì nó đang hỏng. Bouquet `0x0044` MA QR cũng chỉ có tên và một linkage, không dịch vụ nào. |
| **RO-16** | **Một EIT p/f hỏng đang trên sóng.** Bảng `table_id 0x4E`, `table_id_ext 0x0346` (dịch vụ 838), version 17 — TSDuck từ chối phân tích và xếp vào `generic_long_table` với payload rỗng. 43 dịch vụ khác bình thường. | Thu lại và soi riêng dịch vụ 838. Có thể là section rỗng do lỗi sinh bảng của Barrowa. Hệ mới không được tái tạo lỗi này. |
| **RO-17** | **Không có TOT trên sóng.** TDT có (chu kỳ 4 s, chỉ mang UTC), nhưng không bảng nào mang `local_time_offset_descriptor`. Đầu thu không được báo lệch giờ `+07:00`. | Câu hỏi nghiệp vụ, không phải kỹ thuật: đầu thu đang hiện đúng giờ Việt Nam nhờ đâu — cấu hình cứng trong máy, hay người dùng tự đặt? Nếu là cấu hình cứng thì đây là một phụ thuộc ngầm nên ghi lại. |
| **RO-18** | **Dữ liệu SDT lem nhem.** Trên TS8: 49 dịch vụ ghi provider `VTC`, 14 để trống, và **một dịch vụ ghi đúng chữ `V`** — gần như chắc chắn là gõ nhầm. | Không ảnh hưởng kỹ thuật nhưng hiện lên màn hình đầu thu. Sửa khi gieo YAML ở T2, đừng bê nguyên. |
| **RO-11** | Mất tính tất định — hai thực thể cùng commit lại cho ra byte khác nhau, vì một thư viện đổi thứ tự lặp hoặc lọt một timestamp. | AC-12 chạy trong CI mỗi commit, không phải chỉ khi nghiệm thu. Đây là loại lỗi im lặng cho tới lúc mux chuyển input. |
| **RO-7** | Một người làm, không có người thứ hai hiểu hệ thống | Cấu hình YAML đọc được trong git, pipeline là một dòng `tsp`, code riêng nhỏ |
| **RO-8** | **Ba đích linkage không tồn tại, đang phát sóng thật.** Bản dump xác nhận NIT chỉ có TSID `0x0003`, `0x0008`, `0x03E8`, trong khi linkage trỏ tới: **`0x0010` (TS 16)** ba lần — gồm cả kênh barker `0x05` tới service `0x0667` (1639) trong bouquet 25872 và hai linkage Irdeto; **`0x0009` (TS 9)** một lần; và **`0x3265`** một lần — con số này là *network_id* 12901 bị đặt nhầm vào ô transport_stream_id. Bản backup cũ có TSID 16 với service 1639 là *DIEN BIEN SD*; khi gỡ TS đó đi thì các linkage bị bỏ quên. | Đây là lỗi tồn đọng của hệ hiện tại, **không được bê nguyên khi gieo YAML từ bản dump ở T2**. Cần quyết định nghiệp vụ: trỏ lại một dịch vụ đang sống, hay bỏ hẳn descriptor. Đề xuất trỏ về TSID 8 / service 801 là một đích hợp lệ, nhưng cần xác nhận đó đúng là kênh muốn hiện khi đầu thu chọn dịch vụ không xem được. | **Sửa ở 1.3:** thực tế là **sáu** mục, không phải năm — đếm sót mục `0x82` toàn số 0 trong NIT. `model.linkage.check` liệt kê đủ, và `tests/test_linkage.py` ghim con số đó.
| **RO-9** | **Xung đột PID 20** nếu bật FR-33 trong khi mux cũng sinh TDT/TOT. Hai nguồn cùng ghi một PID không phải dự phòng: hoặc mux ghi đè, hoặc thời gian trên sóng nhảy giữa hai đồng hồ. | Đo PID 20 ở đầu ra mux trong giai đoạn T1 trước khi bật. Nếu mux đang cấp thì giữ FR-33 tắt và kiểm tra thời gian bằng cách đọc đầu ra mux, không bằng cách tự sinh thêm. |

---

## Phụ lục A — Hằng số của VTC

### A.1 Định danh

| Mục | Giá trị |
|---|---|
| `network_id` | 12901 · `0x3265` |
| Tên mạng | `VTC` |
| Vị trí quỹ đạo | 132,0° Đông — Vinasat-1 |
| Kênh barker | `service_id` 1639, TSID 16 — **đích này không còn tồn tại**, xem RO-8 |
| PDS cho LCN | `0x00000031` |
| PDS Irdeto | `0x00362275` |
| Bảng mã tiếng Việt | `0x15` — UTF-8 |
| Thứ tự descriptor sự kiện | `4D`, `4E`, `54`, `55` |

### A.2 Transport stream

| TSID | ONID | Vai trò | Dịch vụ | TV | Radio | Tần số | Pol | Symbol rate | FEC |
|---:|---:|---|---:|---:|---:|---:|---|---:|---|
| **8** | **12901** | **actual — mạng của VTC** | **64** | **44** | **20** | 10 968 MHz | H | 28 800 kS/s | 3/4 |
| 3 | 1 | other | 14 | 14 | 0 | 11 088 MHz | V | 18 750 kS/s | 5/6 |
| 1000 | 1 | other | 10 | 10 | 0 | 11 589 MHz | H | 15 000 kS/s | 3/4 |

Cả ba: DVB-S2, 8PSK, roll-off 0,25.

> **Chỉ TSID 8 mang ONID 12901**, tức là mạng của VTC. Khi nói "kênh của VTC" thì con số là **64 — gồm 44 truyền hình và 20 phát thanh**, không phải 88. 24 dịch vụ trên TSID 3 và TSID 1000 nằm dưới ONID 1 và được VTC báo hiệu như mạng khác qua SDT-other; VTC không sở hữu chúng nhưng vẫn có trách nhiệm báo hiệu đúng.
>
> `ONID 1` đáng kiểm tra lại: đó là một ONID hợp lệ do DVB cấp cho một tổ chức khác. Cần xác nhận đây là giá trị đúng theo thoả thuận, hay là di sản cấu hình từ lâu không ai rà.

### A.3 Vector kiểm thử — `satellite_delivery_system_descriptor`

Payload cố định 11 byte. Dùng cho AC-1.

| TSID | Byte đầy đủ gồm tag và length |
|---:|---|
| 8 | `43 0B 01 09 68 00 13 20 8E 02 88 00 03` |
| 3 | `43 0B 01 10 88 00 13 20 AE 01 87 50 04` |
| 1000 | `43 0B 01 15 89 00 13 20 8E 01 50 00 03` |

Byte thứ 7 nhồi năm trường vào tám bit: `west_east(1) · polarization(2) · roll_off(2) · modulation_system(1) · modulation_type(2)`. Với TSID 8: `1 · 00 · 01 · 1 · 10` → `0x8E`. TSID 3 khác ở phân cực dọc `01` → `0xAE`.

Tần số là BCD 8 chữ số theo GHz, dấu thập phân sau chữ số thứ ba. Symbol rate là BCD 7 chữ số theo MS/s, cũng sau chữ số thứ ba, rồi 4 bit `FEC_inner`.

### A.4 Bouquet

| ID | Hex | Tên | Vai trò |
|---:|---|---|---|
| 13858 | `0x3622` | Master | OTA Irdeto |
| 25872 | `0x6510` | VTC_FULLHD | Dịch vụ hiển thị + LCN + barker |
| 25888 | `0x6520` | VTCHD_Basic | Gói cơ bản |
| 25936 | `0x6550` | VTC_BLOCKEDFTA | Chặn FTA khi không có sản phẩm CA |
| 26113 | `0x6601` | NGHE AN | Theo vùng — tài liệu ghi *not use now* |
| 26116 | `0x6604` | Quang Ninh | Theo vùng — *not use now* |
| 68 | `0x0044` | MA QR | Mã QR |

### A.5 Version đang trên sóng

Đo trên `dvb_tables_dump.xml`, cửa sổ 17:19:14–17:20:10 UTC ngày 2026-09-07.
**Đây là giá trị khởi đầu cho YAML** — không dùng con số trong bản backup cấu hình,
vì bản đó đã cũ so với sóng.

| Bảng | Version | Ghi chú |
|---|---:|---|
| NIT | **4** | Khớp `version="4"` của phần tử `<network>` trong backup |
| SDT TSID 8 | **9** | Backup ghi 7 — SDT đã đổi sau khi backup |
| SDT TSID 3 | **12** | Backup ghi 0 |
| SDT TSID 1000 | **19** | Backup ghi 20 |
| BAT 0x3622 Master | **18** | Khớp backup |
| BAT 0x6510 VTC_FULLHD | **26** | Khớp backup |
| BAT 0x6520 VTCHD_Basic | **27** | Khớp backup — nhưng bảng đang **rỗng**, xem RO-15 |
| BAT 0x6550 VTC_BLOCKEDFTA | **2** | Khớp backup |
| BAT 0x6604 Quang Ninh | **13** | Khớp backup. **Đang phát thật**, 9 dịch vụ, 9 LCN — không phải "not use now" |
| BAT 0x0044 MA QR | **10** | Khớp backup — chỉ có tên và một linkage |
| PAT | 3 | Mux sinh |
| CAT | 17 | Mux sinh |

Bouquet `0x6601` Nghệ An **không xuất hiện trên sóng** — đúng là đã bỏ.

Bốn trên sáu version BAT khớp backup còn SDT thì lệch cả ba: BAT và NIT ít đổi,
SDT đổi thường xuyên hơn. Phù hợp với việc đổi tên kênh chỉ cần tăng version SDT.

### A.6 Địa chỉ mạng

| Vai trò | Địa chỉ |
|---|---|
| Barrowa Server A, đầu ra | `236.30.230.1:6000` |
| Barrowa Server B, đầu ra | `236.30.231.1:6000` |
| Barrowa đầu ra phụ | `239.1.1.1:5900` |
| **Hệ này** | *cấp mới, ví dụ* `236.30.232.1:6000` |
| Card phát của Barrowa | `10.10.30.230` / `10.10.30.231` |

---

## Phụ lục B — Chuẩn tham chiếu

| Chuẩn | Nội dung |
|---|---|
| **ETSI EN 300 468** | Service Information trong DVB. Bảng, descriptor, và Annex A về mã hoá ký tự. Tải miễn phí từ ETSI. |
| **ETSI TS 101 211** | Hướng dẫn triển khai SI. Nguồn của các trần chu kỳ lặp ở mục 7. |
| **ISO/IEC 13818-1** | Cấu trúc gói TS, continuity counter, PSI. |
| **ETSI TR 101 290** | Hướng dẫn đo, ba mức ưu tiên lỗi. |
| **ETSI TS 102 006** | System Software Update, cho linkage `0x09`. |
| **TSDuck** | BSD 2-Clause, Thierry Lelégard. <https://tsduck.io> |

---

## Phụ lục C — Lược đồ file EPG đầu vào

Đo trên `File xml đầu vào cho EPG.xml`, 1,1 MB, dữ liệu ngày 2026-09-08.

### C.1 Cấu trúc

```xml
<PSI lang="vie">
 <NETWORK id="12901">
  <TRANSPORT_STREAM id="8" on_id="12901">
   <SERVICE id="801" start_time="2026-09-08T00:00:00+07:00"
            end_time="2026-09-09T23:59:00+07:00"
            period_overlapping_mode="removeEvent">
    <EVENT id="64000" time="2026-09-08T00:00:00+07:00" duration="PT00H10M00S"
           ca="true" type="schedule" running_status="running">
     <AUDIO lang="vie" audio_encoding="HE-AAC" audio_type="stereo"/>
     <VIDEO video_encoding="H264/AVC" aspect_ratio="16:9"
            frame_rate="25Hz" high_definition="true"/>
     <NAME lang="vie" encoding="15">Tiếp tục chương trình</NAME>
     <SHORT_DESCRIPTION lang="vie" encoding="15"></SHORT_DESCRIPTION>
    </EVENT>
   </SERVICE>
  </TRANSPORT_STREAM>
 </NETWORK>
</PSI>
```

### C.2 Ánh xạ sang DVB

| Nguồn | Trường DVB | Ghi chú |
|---|---|---|
| `NETWORK@id` | `network_id` | 12901 |
| `TRANSPORT_STREAM@id`, `@on_id` | `transport_stream_id`, `original_network_id` | 8 / 12901 |
| `SERVICE@id` | `service_id` | Khoá của bảng EIT |
| `SERVICE@period_overlapping_mode` | — | Chính sách xử lý, không phải trường phát ra |
| `EVENT@id` | `event_id` | **Không dùng trực tiếp** — xem FR-47 và RO-12 |
| `EVENT@time` | `start_time` MJD + UTC BCD | Nguồn ở `+07:00`, phải đổi sang UTC |
| `EVENT@duration` | `duration` BCD `HHMMSS` | ISO 8601 `PTxxHxxMxxS` |
| `EVENT@ca` | `free_CA_mode` | `true` → 1 |
| `EVENT@type` | Chọn bảng | `schedule` → `0x50`–`0x5F` |
| `EVENT@running_status` | `running_status` | Xem FR-49 |
| `NAME` | `short_event_descriptor` `0x4D`, `event_name` | `@encoding` là byte dẫn bảng mã |
| `SHORT_DESCRIPTION` | `short_event_descriptor`, phần `text` | Luôn rỗng — xem FR-50 |
| `AUDIO`, `VIDEO` | `component_descriptor` `0x50` | Ứng viên, xem FR-51 |

### C.3 Số liệu đo được

| Chỉ số | Giá trị |
|---|---|
| Dịch vụ | **44**, liên tục từ 801 đến 844 — đúng bằng số kênh truyền hình trên TSID 8 |
| Kênh phát thanh | **Không có EPG** — 20 dịch vụ radio không xuất hiện trong file |
| Sự kiện | 2 365 |
| Khoảng thời gian dữ liệu | 2026-09-08 00:00 → 23:59:59, tức **một ngày** |
| Cửa sổ khai báo | 2026-09-08 00:00 → 2026-09-09 23:59, tức hai ngày |
| `event_id` | 64000 – 64086, **đánh số lại từ 64000 cho mỗi dịch vụ** |
| Múi giờ | Luôn `+07:00` |
| Chồng lấn | 0 |
| Khoảng trống | 46, lớn nhất 15 phút |
| Phủ dưới 20 giờ/ngày | 14 trên 44 dịch vụ, mỏng nhất 17 giờ |
| `NAME` dài nhất | 230 byte UTF‑8 / 174 ký tự → descriptor `0x4D` dài 238 byte, trần 255 |
| `SHORT_DESCRIPTION` có nội dung | 0 trên 2 365 |

### C.4 Những gì nguồn KHÔNG mang

Không có `CONTENT`, `PARENTAL_RATING`, mô tả mở rộng, đa ngôn ngữ, hay thông tin tập/phần. Hệ quả trực tiếp: **EIT chỉ có `short_event_descriptor` `0x4D`**, và có thể thêm `0x50` nếu FR-51 xác minh là cần. Không có `0x4E`, `0x54`, `0x55`.

Đây là điều tốt cho khối lượng công việc, nhưng cũng là một giới hạn nghiệp vụ đáng đưa ra: EPG trên đầu thu sẽ chỉ có tên chương trình, không có mô tả và không có phân loại thể loại hay độ tuổi.

---

# Kết quả bộ test Transaction: MySQL (InnoDB) vs MongoDB (WiredTiger)

Chạy lúc 2026-11-09T18:15:06 · Linux-6.18.44-fc-v310-x86_64-with-glibc2.39 · 2 CPU · 7.8 GB RAM
- MySQL 8.4.2: isolation REPEATABLE-READ, innodb_flush_log_at_trx_commit=1, sync_binlog=1, log_bin=1
- MongoDB 8.0.23: replica set rs0 (127.0.0.1:27017 PRIMARY; 127.0.0.1:27018 SECONDARY; 127.0.0.1:27019 SECONDARY), transactionLifetimeLimitSeconds=60
- Tham số C2/C3: 5 lần lặp, 1000 đơn/cấu hình (C2), 8 luồng × 100 đơn (C3), 50 đơn chạy nóng

**Tổng: 24 test · PASS 24 · FAIL 0 · ERROR 0 · SKIP 0**

| Test | Hệ | Nội dung | Kiểm tra khớp | Kết luận | Thời gian (s) |
|---|---|---|---|---|---|
| [A1-MY](#a1-my) | MySQL | Đặt 2 bàn Venice khi Showroom Q1 chỉ còn 1: hủy trọn giao dịch ghi nhiều bảng | 7/7 | **PASS** | 1.44 |
| [A1-MG](#a1-mg) | MongoDB | Đặt 2 bàn Venice khi Showroom Q1 chỉ còn 1: abort hủy trọn giao dịch | 8/8 | **PASS** | 0.55 |
| [A2-MY](#a2-my) | MySQL | Lỗi giữa giao dịch nhưng ứng dụng vẫn COMMIT | 6/6 | **PASS** | 1.35 |
| [A2-MG](#a2-mg) | MongoDB | Lỗi giữa giao dịch nhưng ứng dụng vẫn commit | 2/2 | **PASS** | 0.27 |
| [A3-MY](#a3-my) | MySQL | Đổi kho xuất cho riêng một dòng hàng bằng SAVEPOINT | 3/3 | **PASS** | 0.66 |
| [A3-MG](#a3-mg) | MongoDB | Đổi kho xuất cho một dòng hàng khi không có SAVEPOINT | 5/5 | **PASS** | 0.25 |
| [A4-MY](#a4-my) | MySQL | Tạo bảng giữa giao dịch tăng giá 10% rồi ROLLBACK | 2/2 | **PASS** | 0.69 |
| [A4-MG](#a4-mg) | MongoDB | Tạo index / collection giữa giao dịch tăng giá 10% | 3/3 | **PASS** | 0.25 |
| [B1-MY](#b1-my) | MySQL | Tra cứu bàn Venice còn bán khi phiên kia đang giữ chỗ rồi hủy (dirty read) | 2/2 | **PASS** | 1.42 |
| [B1-MG](#b1-mg) | MongoDB | Tra cứu bàn Venice còn bán khi phiên kia đang giữ chỗ rồi hủy (dirty read) | 1/1 | **PASS** | 0.29 |
| [B2-MY](#b2-my) | MySQL | Báo cáo tồn Kho Bình Dương trong lúc có đổi giá và nhập kho (non-repeatable read, phantom) | 3/3 | **PASS** | 2.04 |
| [B2-MG](#b2-mg) | MongoDB | Báo cáo tồn Kho Bình Dương trong lúc có đổi giá và nhập kho | 2/2 | **PASS** | 0.26 |
| [B3-MY](#b3-my) | MySQL | Hai sales cùng giữ chỗ sofa Lawson 240 ở Kho Bình Dương (lost update) | 7/7 | **PASS** | 6.45 |
| [B3-MG](#b3-mg) | MongoDB | Hai sales cùng giữ chỗ sofa Lawson 240 ở Kho Bình Dương (lost update) | 4/4 | **PASS** | 0.55 |
| [B4-MY](#b4-my) | MySQL | Hai yêu cầu lập lịch thanh toán cùng lúc cho đơn #1 (write skew) | 6/6 | **PASS** | 5.36 |
| [B4-MG](#b4-mg) | MongoDB | Hai yêu cầu lập lịch thanh toán cùng lúc cho đơn #1 (write skew) | 4/4 | **PASS** | 0.57 |
| [B5-MY](#b5-my) | MySQL | Hai đơn giữ hai món theo thứ tự ngược nhau; chờ khóa quá hạn | 6/6 | **PASS** | 7.17 |
| [B5-MG](#b5-mg) | MongoDB | Hai đơn giữ hai món theo thứ tự ngược nhau; giới hạn thời gian của transaction | 6/6 | **PASS** | 14.32 |
| [C1-MY](#c1-my) | MySQL | Kill -9 mysqld khi giao dịch Bàn giao đã commit và một đơn khác còn dở dang | 4/4 | **PASS** | 4.24 |
| [C1-MG](#c1-mg) | MongoDB | Kill -9 PRIMARY khi giao dịch Bàn giao đã commit (w: majority) và một đơn khác còn dở dang | 5/5 | **PASS** | 23.36 |
| [C2-MY](#c2-my) | MySQL | Thông lượng giao dịch Đặt hàng tuần tự theo cấu hình độ bền | 3/3 | **PASS** | 41.77 |
| [C2-MG](#c2-mg) | MongoDB | Thông lượng giao dịch Đặt hàng tuần tự theo write concern và có / không transaction | 3/3 | **PASS** | 148.23 |
| [C3-MY](#c3-my) | MySQL | 8 luồng x 100 đơn cùng mua sofa Lawson 240 tại Kho Bình Dương, tồn đúng 800 | 4/4 | **PASS** | 54.4 |
| [C3-MG](#c3-mg) | MongoDB | 8 luồng x 100 đơn cùng mua sofa Lawson 240 tại Kho Bình Dương, tồn đúng 800 | 3/3 | **PASS** | 48.17 |

## Chi tiết từng test

### A1-MY

**Đặt 2 bàn Venice khi Showroom Q1 chỉ còn 1: hủy trọn giao dịch ghi nhiều bảng** (MySQL) · kết luận **PASS** · log: [`logs/A1-MY.log`](logs/A1-MY.log)

*Giả thuyết:* ROLLBACK hủy mọi thay đổi của transaction (orders, order_items, inventory); AUTO_INCREMENT không được trả lại.

| Đại lượng đo | Quan sát | Kỳ vọng | Khớp | Ghi chú |
|---|---|---|---|---|
| Mã lỗi khi giữ chỗ vượt tồn | 3819 | 3819 | ✓ | CHECK chk_inventory_reserved_le_on_hand |
| Số đơn / dòng hàng / phiếu thanh toán sau ROLLBACK | [1, 1, 1] | [1, 1, 1] | ✓ | chỉ còn đơn #1 có sẵn trong dữ liệu mẫu |
| Giữ chỗ 401 @ Showroom Q1 | 0 | 0 | ✓ |  |
| id của đơn kế tiếp | 3 | 3 | ✓ | số 2 đã cấp cho giao dịch bị hủy không được trả lại |
| Lỗi ứng dụng | OUT_OF_STOCK | OUT_OF_STOCK | ✓ | app kiểm tra tồn trước khi UPDATE |
| Giữ chỗ sofa 101 @ Q1 (dòng 1 đã giữ trước khi dòng 2 lỗi) | 0 | 0 | ✓ | ROLLBACK hoàn tác cả lượt giữ chỗ hợp lệ |
| Số đơn / dòng hàng / phiếu thanh toán | [1, 1, 1] | [1, 1, 1] | ✓ |  |

### A1-MG

**Đặt 2 bàn Venice khi Showroom Q1 chỉ còn 1: abort hủy trọn giao dịch** (MongoDB) · kết luận **PASS** · log: [`logs/A1-MG.log`](logs/A1-MG.log)

*Giả thuyết:* Lỗi validator làm abort cả transaction; không dùng transaction thì document đơn hàng đã ghi vẫn còn (đơn ma).

| Đại lượng đo | Quan sát | Kỳ vọng | Khớp | Ghi chú |
|---|---|---|---|---|
| Mã lỗi khi giữ chỗ vượt tồn | 121 | 121 | ✓ | validator của collection inventory |
| Số document orders | 1 | 1 | ✓ |  |
| Giữ chỗ 401 @ Showroom Q1 | 0 | 0 | ✓ |  |
| Mã lỗi | 121 | 121 | ✓ |  |
| Số document orders | 2 | 2 | ✓ | đơn ma: có đơn nhưng không giữ được hàng |
| Lỗi ứng dụng | OUT_OF_STOCK | OUT_OF_STOCK | ✓ |  |
| Giữ chỗ sofa 101 @ Q1 | 0 | 0 | ✓ | abort hoàn tác lượt giữ chỗ của dòng 1 |
| Số document orders | 1 | 1 | ✓ |  |

### A2-MY

**Lỗi giữa giao dịch nhưng ứng dụng vẫn COMMIT** (MySQL) · kết luận **PASS** · log: [`logs/A2-MY.log`](logs/A2-MY.log)

*Giả thuyết:* InnoDB chỉ rollback câu lệnh lỗi, transaction vẫn mở: COMMIT lưu phần còn lại (đơn ma). withTransaction của app và EXIT HANDLER của procedure chặn được.

| Đại lượng đo | Quan sát | Kỳ vọng | Khớp | Ghi chú |
|---|---|---|---|---|
| Lệnh giữ chỗ lỗi, các lệnh khác chạy tiếp | [None, None, None, 3819, None] | [None, None, None, 3819, None] | ✓ |  |
| Số đơn / dòng hàng / phiếu thanh toán được lưu | [2, 2, 2] | [2, 2, 2] | ✓ | đơn ma: có đơn 580 triệu và phiếu cọc nhưng không giữ được chiếc bàn nào |
| Giữ chỗ 401 @ Showroom Q1 | 0 | 0 | ✓ |  |
| Số đơn / dòng hàng / phiếu thanh toán | [1, 1, 1] | [1, 1, 1] | ✓ |  |
| Lỗi trả về ứng dụng | OUT_OF_STOCK | OUT_OF_STOCK | ✓ |  |
| Số đơn / dòng hàng / phiếu thanh toán | [1, 1, 1] | [1, 1, 1] | ✓ |  |

### A2-MG

**Lỗi giữa giao dịch nhưng ứng dụng vẫn commit** (MongoDB) · kết luận **PASS** · log: [`logs/A2-MG.log`](logs/A2-MG.log)

*Giả thuyết:* Lỗi của một thao tác làm server hủy cả transaction; lệnh sau và commit đều báo NoSuchTransaction (251).

| Đại lượng đo | Quan sát | Kỳ vọng | Khớp | Ghi chú |
|---|---|---|---|---|
| Mã lỗi: giữ chỗ / lệnh tiếp theo / commit | [121, 251, 251] | [121, 251, 251] | ✓ |  |
| Số document orders | 1 | 1 | ✓ | không có đơn ma |

### A3-MY

**Đổi kho xuất cho riêng một dòng hàng bằng SAVEPOINT** (MySQL) · kết luận **PASS** · log: [`logs/A3-MY.log`](logs/A3-MY.log)

*Giả thuyết:* ROLLBACK TO SAVEPOINT hủy riêng phần sau điểm đánh dấu, giữ lượt giữ chỗ sofa hợp lệ.

| Đại lượng đo | Quan sát | Kỳ vọng | Khớp | Ghi chú |
|---|---|---|---|---|
| Giữ 2 bàn Venice tại Q1 | 3819 | 3819 | ✓ |  |
| Dòng hàng của đơn mới [biến thể, địa điểm, số lượng] | [[101, 1, 1], [401, 3, 2]] | [[101, 1, 1], [401, 3, 2]] | ✓ |  |
| Giữ chỗ 101@Q1 / 401@Q1 / 401@Kho BD | [1, 0, 2] | [1, 0, 2] | ✓ |  |

### A3-MG

**Đổi kho xuất cho một dòng hàng khi không có SAVEPOINT** (MongoDB) · kết luận **PASS** · log: [`logs/A3-MG.log`](logs/A3-MG.log)

*Giả thuyết:* Không có savepoint: lỗi hủy cả transaction, kể cả lượt giữ sofa hợp lệ. Cập nhật có điều kiện (matched 0, không phát sinh lỗi) cho phép thử kho khác trong cùng transaction.

| Đại lượng đo | Quan sát | Kỳ vọng | Khớp | Ghi chú |
|---|---|---|---|---|
| Mã lỗi: giữ 401@Q1 / thử 401@Kho BD | [121, 251] | [121, 251] | ✓ |  |
| Giữ chỗ sofa 101@Q1 sau khi transaction bị hủy | 0 | 0 | ✓ | mất cả lượt giữ hợp lệ, phải chạy lại từ đầu |
| matched ở Q1 / ở Kho BD | [0, 1] | [0, 1] | ✓ |  |
| Dòng hàng của đơn mới | [[101, 1, 1], [401, 3, 2]] | [[101, 1, 1], [401, 3, 2]] | ✓ |  |
| Giữ chỗ 101@Q1 / 401@Q1 / 401@Kho BD | [1, 0, 2] | [1, 0, 2] | ✓ |  |

### A4-MY

**Tạo bảng giữa giao dịch tăng giá 10% rồi ROLLBACK** (MySQL) · kết luận **PASS** · log: [`logs/A4-MY.log`](logs/A4-MY.log)

*Giả thuyết:* CREATE TABLE gây implicit commit: lệnh tăng giá trước đó đã được commit, ROLLBACK không còn tác dụng.

| Đại lượng đo | Quan sát | Kỳ vọng | Khớp | Ghi chú |
|---|---|---|---|---|
| Giá 101 / 102 sau ROLLBACK | [528000000, 682000000] | [528000000, 682000000] | ✓ | giá mới đã bị commit ngầm |
| Bảng price_audit tồn tại | 1 | 1 | ✓ |  |

### A4-MG

**Tạo index / collection giữa giao dịch tăng giá 10%** (MongoDB) · kết luận **PASS** · log: [`logs/A4-MG.log`](logs/A4-MG.log)

*Giả thuyết:* createIndex trên collection đã có dữ liệu bị từ chối trong transaction và làm transaction bị hủy; collection tạo mới trong transaction được rollback khi abort.

| Đại lượng đo | Quan sát | Kỳ vọng | Khớp | Ghi chú |
|---|---|---|---|---|
| Mã lỗi createIndex / commit | [263, 251] | [263, 251] | ✓ |  |
| Giá 101 / 102 | [480000000, 620000000] | [480000000, 620000000] | ✓ | cả giao dịch tăng giá bị hủy |
| Collection price_audit tồn tại sau abort | False | False | ✓ |  |

### B1-MY

**Tra cứu bàn Venice còn bán khi phiên kia đang giữ chỗ rồi hủy (dirty read)** (MySQL) · kết luận **PASS** · log: [`logs/B1-MY.log`](logs/B1-MY.log)

*Giả thuyết:* READ UNCOMMITTED đọc được giữ chỗ chưa commit (0 rồi 1); READ COMMITTED không (1 và 1).

| Đại lượng đo | Quan sát | Kỳ vọng | Khớp | Ghi chú |
|---|---|---|---|---|
| READ UNCOMMITTED: số bàn còn bán [trước, sau khi A hủy] | [0, 1] | [0, 1] | ✓ | dirty read: thấy chiếc bàn đã hết dù giao dịch của A chưa commit |
| READ COMMITTED: số bàn còn bán [trước, sau khi A hủy] | [1, 1] | [1, 1] | ✓ |  |

### B1-MG

**Tra cứu bàn Venice còn bán khi phiên kia đang giữ chỗ rồi hủy (dirty read)** (MongoDB) · kết luận **PASS** · log: [`logs/B1-MG.log`](logs/B1-MG.log)

*Giả thuyết:* MongoDB không cho đọc thay đổi chưa commit, cả trong lẫn ngoài transaction.

| Đại lượng đo | Quan sát | Kỳ vọng | Khớp | Ghi chú |
|---|---|---|---|---|
| Số bàn còn bán [ngoài transaction, trong transaction] | [1, 1] | [1, 1] | ✓ |  |

### B2-MY

**Báo cáo tồn Kho Bình Dương trong lúc có đổi giá và nhập kho (non-repeatable read, phantom)** (MySQL) · kết luận **PASS** · log: [`logs/B2-MY.log`](logs/B2-MY.log)

*Giả thuyết:* READ COMMITTED thấy giá mới và dòng mới giữa hai lần đọc; REPEATABLE READ không thấy; locking read (FOR SHARE) ở REPEATABLE READ luôn đọc bản mới nhất.

| Đại lượng đo | Quan sát | Kỳ vọng | Khớp | Ghi chú |
|---|---|---|---|---|
| READ COMMITTED [giá lần 1, lần 2 (triệu), (số mã, tổng tồn) lần 1, lần 2] | [480, 520, [3, 13], [4, 14]] | [480, 520, [3, 13], [4, 14]] | ✓ | non-repeatable read và phantom |
| REPEATABLE READ | [480, 480, [3, 13], [3, 13]] | [480, 480, [3, 13], [3, 13]] | ✓ | cùng một read view |
| REPEATABLE READ, lần đọc 2 dùng FOR SHARE | [480, 480, [3, 13], [4, 14]] | [480, 480, [3, 13], [4, 14]] | ✓ | locking read đọc bản mới nhất đã commit |

### B2-MG

**Báo cáo tồn Kho Bình Dương trong lúc có đổi giá và nhập kho** (MongoDB) · kết luận **PASS** · log: [`logs/B2-MG.log`](logs/B2-MG.log)

*Giả thuyết:* Transaction snapshot không thấy thay đổi đã commit sau khi nó bắt đầu đọc; sau commit mới thấy.

| Đại lượng đo | Quan sát | Kỳ vọng | Khớp | Ghi chú |
|---|---|---|---|---|
| Trong transaction [giá lần 1, lần 2, (số mã, tổng tồn) lần 1, lần 2] | [480, 480, [3, 13], [3, 13]] | [480, 480, [3, 13], [3, 13]] | ✓ |  |
| Sau commit (số mã, tổng tồn) | [4, 14] | [4, 14] | ✓ |  |

### B3-MY

**Hai sales cùng giữ chỗ sofa Lawson 240 ở Kho Bình Dương (lost update)** (MySQL) · kết luận **PASS** · log: [`logs/B3-MY.log`](logs/B3-MY.log)

*Giả thuyết:* REPEATABLE READ không chặn lost update kiểu đọc rồi ghi (kết quả 1 thay vì 2). FOR UPDATE, cột version của app và cập nhật có điều kiện đều cho kết quả đúng, nhưng version của app từ chối lượt đến sau.

| Đại lượng đo | Quan sát | Kỳ vọng | Khớp | Ghi chú |
|---|---|---|---|---|
| Đối chứng: giữ chỗ cuối cùng | 1 | 1 | ✓ | lost update: đúng ra phải là 2 |
| Cách 1: thời gian B chờ khóa (s) | 1.50 | ≥ 1,4 | ✓ | A giữ khóa 1,5 s |
| Cách 1: giữ chỗ cuối cùng | 2 | 2 | ✓ |  |
| Cách 2: số dòng B cập nhật được ở lần đầu | 0 | 0 | ✓ | version đã đổi từ 0 thành 1 |
| Cách 2: giữ chỗ sau xung đột / sau khi thử lại | [1, 2] | [1, 2] | ✓ | không mất cập nhật, nhưng lượt đến sau bị từ chối nếu không thử lại |
| Cách 3: B chờ rồi cập nhật được (dòng) | 1 | 1 | ✓ |  |
| Cách 3: giữ chỗ cuối cùng | 2 | 2 | ✓ |  |

### B3-MG

**Hai sales cùng giữ chỗ sofa Lawson 240 ở Kho Bình Dương (lost update)** (MongoDB) · kết luận **PASS** · log: [`logs/B3-MG.log`](logs/B3-MG.log)

*Giả thuyết:* Không dùng transaction: đọc rồi ghi mất cập nhật. Trong transaction, lượt ghi sau bị WriteConflict (112) ngay, không chờ; thử lại cho kết quả đúng.

| Đại lượng đo | Quan sát | Kỳ vọng | Khớp | Ghi chú |
|---|---|---|---|---|
| Đối chứng: giữ chỗ cuối cùng | 1 | 1 | ✓ | lost update: đúng ra phải là 2 |
| Mã lỗi lượt ghi của B và nhãn | [112, ['TransientTransactionError']] | [112, ['TransientTransactionError']] | ✓ |  |
| Thời gian B chờ trước khi nhận lỗi (s) | 0.00 | < 0,1 | ✓ | WiredTiger hủy ngay, không xếp hàng chờ |
| Giữ chỗ cuối cùng sau khi thử lại | 2 | 2 | ✓ |  |

### B4-MY

**Hai yêu cầu lập lịch thanh toán cùng lúc cho đơn #1 (write skew)** (MySQL) · kết luận **PASS** · log: [`logs/B4-MY.log`](logs/B4-MY.log)

*Giả thuyết:* Ràng buộc 'tổng các khoản ≤ order.total, tối đa 1 khoản final' bị phá ở cách app đang làm (không transaction) và ở REPEATABLE READ; SERIALIZABLE chặn bằng deadlock; khóa dòng orders bằng FOR UPDATE chặn bằng chờ khóa.

| Đại lượng đo | Quan sát | Kỳ vọng | Khớp | Ghi chú |
|---|---|---|---|---|
| Như app hiện tại (không transaction): [số khoản final, tổng tiền] | [2, 883500000] | [2, 883500000] | ✓ | write skew: 2 khoản final, vượt order.total 294,5 triệu |
| REPEATABLE READ: [số khoản final, tổng tiền] | [2, 883500000] | [2, 883500000] | ✓ | snapshot không thấy dòng của nhau, INSERT không xung đột |
| SERIALIZABLE: mã lỗi của nạn nhân | [1213] | [1213] | ✓ |  |
| SERIALIZABLE: [số khoản final, tổng tiền] | [1, 589000000] | [1, 589000000] | ✓ |  |
| FOR UPDATE dòng orders: B chờ (s) | 1.51 | ≥ 1,4 | ✓ |  |
| FOR UPDATE dòng orders: [số khoản final, tổng tiền] | [1, 589000000] | [1, 589000000] | ✓ |  |

### B4-MG

**Hai yêu cầu lập lịch thanh toán cùng lúc cho đơn #1 (write skew)** (MongoDB) · kết luận **PASS** · log: [`logs/B4-MG.log`](logs/B4-MG.log)

*Giả thuyết:* Snapshot isolation để lọt write skew khi khoản thanh toán là document riêng; khi nhúng payments[] vào document đơn hàng (mô hình của nhóm), hai giao dịch ghi cùng một document nên WriteConflict chặn được.

| Đại lượng đo | Quan sát | Kỳ vọng | Khớp | Ghi chú |
|---|---|---|---|---|
| Cả hai qua kiểm tra | [True, True] | [True, True] | ✓ |  |
| Collection riêng: [số khoản final, tổng tiền] | [2, 883500000] | [2, 883500000] | ✓ | write skew |
| Nhúng: mã lỗi lượt ghi của B | 112 | 112 | ✓ |  |
| Nhúng: [số khoản final, tổng tiền] | [1, 589000000] | [1, 589000000] | ✓ |  |

### B5-MY

**Hai đơn giữ hai món theo thứ tự ngược nhau; chờ khóa quá hạn** (MySQL) · kết luận **PASS** · log: [`logs/B5-MY.log`](logs/B5-MY.log)

*Giả thuyết:* Deadlock (1213) hủy cả transaction nạn nhân; sắp xếp theo variant_id như app thì không deadlock; lock wait timeout (1205) chỉ hủy câu lệnh đang chờ, phần đã làm của transaction vẫn còn.

| Đại lượng đo | Quan sát | Kỳ vọng | Khớp | Ghi chú |
|---|---|---|---|---|
| Mã lỗi của nạn nhân deadlock | [1213] | [1213] | ✓ |  |
| Giữ chỗ 101 / 401 tại Kho BD | [1, 1] | [1, 1] | ✓ | chỉ còn 2 lượt giữ của bên thắng; lượt giữ đầu của nạn nhân đã bị rollback cùng transaction |
| Không có deadlock: mã lỗi của B | [None, None] | [None, None] | ✓ |  |
| Giữ chỗ 101 / 401 tại Kho BD | [2, 2] | [2, 2] | ✓ |  |
| Mã lỗi và thời gian chờ (s) | [1205, 3.0] | [1205, ≈3] | ✓ |  |
| Giữ chỗ sofa của B vẫn còn sau lỗi / sau COMMIT | [1, 1] | [1, 1] | ✓ | chỉ câu lệnh chờ bị hủy: đơn của B được commit dở dang nếu ứng dụng không ROLLBACK |

### B5-MG

**Hai đơn giữ hai món theo thứ tự ngược nhau; giới hạn thời gian của transaction** (MongoDB) · kết luận **PASS** · log: [`logs/B5-MG.log`](logs/B5-MG.log)

*Giả thuyết:* Không có chờ khóa giữa hai transaction: bên ghi sau bị WriteConflict ngay. Lệnh ghi ngoài transaction thì chờ transaction kia kết thúc. Transaction quá transactionLifetimeLimitSeconds bị server hủy.

| Đại lượng đo | Quan sát | Kỳ vọng | Khớp | Ghi chú |
|---|---|---|---|---|
| Mã lỗi của A và thời gian chờ (s) | [112, 0.001] | [112, < 0,1] | ✓ |  |
| Giữ chỗ 101 / 401 tại Kho BD | [1, 1] | [1, 1] | ✓ |  |
| Lệnh ngoài transaction: chờ (s) | 1.51 | ≥ 1,4 | ✓ |  |
| Giữ chỗ 401 tại Kho BD | 2 | 2 | ✓ |  |
| Mã lỗi khi commit | 251 | 251 | ✓ | server đã hủy transaction quá hạn |
| Giữ chỗ 101 tại Kho BD | 0 | 0 | ✓ |  |

### C1-MY

**Kill -9 mysqld khi giao dịch Bàn giao đã commit và một đơn khác còn dở dang** (MySQL) · kết luận **PASS** · log: [`logs/C1-MY.log`](logs/C1-MY.log)

*Giả thuyết:* Khởi động lại: redo log khôi phục giao dịch đã commit, undo hủy giao dịch chưa commit.

| Đại lượng đo | Quan sát | Kỳ vọng | Khớp | Ghi chú |
|---|---|---|---|---|
| Bàn giao đã commit: [trạng thái đơn, tồn / giữ chỗ 102@Kho BD, total_spent của An] | ['delivered', [2, 0], 1009000000] | ['delivered', [2, 0], 1009000000] | ✓ |  |
| Đơn dở dang của Chi: [số đơn, giữ chỗ 401@Q1] | [0, 0] | [0, 0] | ✓ |  |
| Log có pha redo (áp dụng redo log) | True | True | ✓ |  |
| Log có pha undo / rollback giao dịch chưa commit | True | True | ✓ |  |

### C1-MG

**Kill -9 PRIMARY khi giao dịch Bàn giao đã commit (w: majority) và một đơn khác còn dở dang** (MongoDB) · kết luận **PASS** · log: [`logs/C1-MG.log`](logs/C1-MG.log)

*Giả thuyết:* Replica set bầu PRIMARY mới; giao dịch đã commit với w: majority còn nguyên; giao dịch dở dang bị hủy; node bị kill tự khôi phục từ checkpoint và journal khi khởi động lại.

| Đại lượng đo | Quan sát | Kỳ vọng | Khớp | Ghi chú |
|---|---|---|---|---|
| Bàn giao đã commit: [trạng thái đơn, tồn / giữ chỗ 102@Kho BD, total_spent của An] | ['delivered', [2, 0], 1009000000] | ['delivered', [2, 0], 1009000000] | ✓ |  |
| Commit của B sau failover thất bại | True | True | ✓ |  |
| Đơn dở dang của Chi: [số đơn, giữ chỗ 401@Q1] | [0, 0] | [0, 0] | ✓ |  |
| Thời gian đến khi ghi được trên PRIMARY mới (s) | 10.50 | ≤ 20 | ✓ |  |
| Node bị kill trở lại replica set | True | True | ✓ |  |

### C2-MY

**Thông lượng giao dịch Đặt hàng tuần tự theo cấu hình độ bền** (MySQL) · kết luận **PASS** · log: [`logs/C2-MY.log`](logs/C2-MY.log)

*Giả thuyết:* H1: nới độ bền (flush=2, sync_binlog=0) tăng thông lượng; H2: stored procedure (1 lượt gọi mạng) nhanh hơn câu lệnh từ ứng dụng mà không giảm độ bền.

| Đại lượng đo | Quan sát | Kỳ vọng | Khớp | Ghi chú |
|---|---|---|---|---|
| Mọi lần đo đều đúng (số đơn = số giữ chỗ = số đơn gửi) | True | True | ✓ |  |
| H1: trung vị flush=2 / flush=1 | 1.59 | > 1 | ✓ |  |
| H2: trung vị procedure / câu lệnh từ ứng dụng | 1.66 | > 1 | ✓ |  |

Bảng số liệu: [`C2-MY_raw.csv`](C2-MY_raw.csv), [`C2-MY_summary.csv`](C2-MY_summary.csv)

### C2-MG

**Thông lượng giao dịch Đặt hàng tuần tự theo write concern và có / không transaction** (MongoDB) · kết luận **PASS** · log: [`logs/C2-MG.log`](logs/C2-MG.log)

*Giả thuyết:* H3: w: 1 nhanh hơn w: majority; H4: với w: majority, dùng transaction nhanh hơn không dùng (chỉ chờ nhân bản một lần lúc commit).

| Đại lượng đo | Quan sát | Kỳ vọng | Khớp | Ghi chú |
|---|---|---|---|---|
| Mọi lần đo đều đúng | True | True | ✓ |  |
| H3: trung vị w:1 / w:majority (có transaction) | 1.19 | > 1 | ✓ |  |
| H4: trung vị có / không transaction (w: majority) | 1.38 | > 1 | ✓ |  |

Bảng số liệu: [`C2-MG_raw.csv`](C2-MG_raw.csv), [`C2-MG_summary.csv`](C2-MG_summary.csv)

### C3-MY

**8 luồng x 100 đơn cùng mua sofa Lawson 240 tại Kho Bình Dương, tồn đúng 800** (MySQL) · kết luận **PASS** · log: [`logs/C3-MY.log`](logs/C3-MY.log)

*Giả thuyết:* Cập nhật có điều kiện: 800/800, không thử lại, đơn thứ 801 bị từ chối. Version như app: không bán vượt, nhưng nếu không thử lại thì nhiều đơn bị từ chối dù kho còn hàng.

| Đại lượng đo | Quan sát | Kỳ vọng | Khớp | Ghi chú |
|---|---|---|---|---|
| Cập nhật có điều kiện: [đơn thành công, thử lại, đơn thứ 801] mọi lần | [(800, 0, 'OUT_OF_STOCK')] | [(800, 0, 'OUT_OF_STOCK')] | ✓ |  |
| Version + thử lại: đủ 800 đơn và đơn 801 bị từ chối mọi lần | True | True | ✓ |  |
| Version như app, không thử lại: có đơn bị từ chối dù còn hàng | True | True | ✓ |  |
| Mọi lần: số đơn = số giữ chỗ (không bán vượt, không mất) | True | True | ✓ |  |

Bảng số liệu: [`C3-MY_raw.csv`](C3-MY_raw.csv)

### C3-MG

**8 luồng x 100 đơn cùng mua sofa Lawson 240 tại Kho Bình Dương, tồn đúng 800** (MongoDB) · kết luận **PASS** · log: [`logs/C3-MG.log`](logs/C3-MG.log)

*Giả thuyết:* withTransaction tự thử lại khi WriteConflict: 800/800 đúng, đơn thứ 801 bị từ chối, nhưng nhiều lần thử lại.

| Đại lượng đo | Quan sát | Kỳ vọng | Khớp | Ghi chú |
|---|---|---|---|---|
| Mọi lần: 800 đơn thành công và đơn 801 bị từ chối | True | True | ✓ |  |
| Mọi lần có thử lại do WriteConflict | True | True | ✓ |  |
| Mọi lần: số đơn = số giữ chỗ | True | True | ✓ |  |

Bảng số liệu: [`C3-MG_raw.csv`](C3-MG_raw.csv)


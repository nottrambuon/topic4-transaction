# Topic 4 – Transaction: MySQL (InnoDB) vs MongoDB (WiredTiger)

Bộ thực nghiệm cho mục **3.4 Topic 4 – Transaction** và **Phụ lục C.4** của báo cáo CO3021 (ứng dụng
Luxury Furniture / auren-dbms-application). Gồm **24 test**: 12 tình huống (A1–A4, B1–B5, C1–C3), mỗi tình huống
chạy trên cả MySQL và MongoDB. Mỗi test ghi giả thuyết của lý thuyết trước khi chạy, sau đó tự so đại lượng
quan sát được với dự đoán (tổng cộng 99 đại lượng) và kết luận PASS / FAIL.

Kết quả dùng trong báo cáo nằm ở [`results/2026-11-09_18-15-06/summary.md`](results/2026-11-09_18-15-06/summary.md)
(24/24 PASS, MySQL 8.4.2, MongoDB 8.0.23 replica set 3 node, Linux 2 vCPU / 7,8 GB RAM).

Toàn bộ môi trường chạy bằng **Docker**, nên máy demo không cần cài MySQL, MongoDB hay Python.

---

## Cấu trúc thư mục

```
topic-4-transaction/
├── docker-compose.yml          2 container: tx-mysql (MySQL 8.4.2) và tx-lab (MongoDB 8.0.23 rs0 + Python)
├── docker/
│   ├── mysql/                  Dockerfile, transaction.cnf (độ bền đầy đủ, error log), tạo user demo
│   └── lab/                    Dockerfile, lab-entrypoint.sh (dựng replica set 3 node trong container)
├── run.py                      Chạy test, xuất results/<thời điểm>/summary.md
├── tests/
│   ├── scenario_a.py           A1–A4: Atomicity và xử lý lỗi (1 phiên)
│   ├── scenario_b.py           B1–B5: Isolation và tranh chấp (2 phiên xen kẽ)
│   └── scenario_c.py           C1–C3: Durability (kill -9) và hiệu năng
├── lib/
│   ├── app_mysql.py            placeOrder / withTransaction chép theo order.service.ts, config/db.ts
│   ├── mongo_model.py          16 bảng -> 8 collection; placeOrder, deliverOrder cho MongoDB
│   ├── mysql_kit.py, mongo_kit.py   Phiên A/B có in timeline, nạp lại dữ liệu chuẩn
│   ├── framework.py            @case, check(), ghi log
│   └── config.py               Cấu hình qua biến môi trường
├── setup/
│   ├── mysql_schema.sql        DROP + schema.sql + indexes.sql nguyên văn từ repo ứng dụng (16 bảng)
│   ├── mysql_data.sql          Bộ dữ liệu thu gọn (3 khách, 5 biến thể, 3 địa điểm, đơn #1 589 triệu)
│   ├── mysql_procedures.sql    sp_place_order, sp_deliver_order
│   ├── luxury_furniture.dbml   EERD
│   └── start_mongo_replset.sh, my.cnf.example   Chỉ dùng khi chạy không qua Docker
└── results/2026-11-09_18-15-06/    Lần chạy dùng cho báo cáo (summary.md, logs/, *.csv)
```

## Môi trường Docker

| Container | Nội dung | Cổng trên máy | Tài khoản |
|---|---|---|---|
| `tx-mysql` | MySQL 8.4.2, REPEATABLE READ, `innodb_flush_log_at_trx_commit = 1`, `sync_binlog = 1`, binlog bật | `127.0.0.1:3306` | `root` / `root`, `demo` / `demo123` |
| `tx-lab` | MongoDB 8.0.23, replica set `rs0` gồm 3 node (27017 là PRIMARY ưu tiên), Python 3 + PyMySQL + PyMongo | `127.0.0.1:27017–27019` | không cần đăng nhập |

Như trong báo cáo, MongoDB cố ý chạy **replica set 3 node trên cùng một máy**, vì multi-document transaction
không chạy trên server đơn lẻ, và `w: "majority"` chỉ thực sự chờ nhân bản khi có node khác.
Bộ test chạy bên trong `tx-lab`. Thư mục repo được mount vào `/app`, nên kết quả ghi thẳng ra `results/` trên máy.

---

## 1. Khởi động

Cần cài **Docker Desktop** (Windows / macOS) hoặc Docker Engine + Docker Compose v2 (Linux), dành trống khoảng 3 GB RAM.

```bash
git clone <link-repo>
cd topic-4-transaction
docker compose up -d --build      # lần đầu tải image và build khoảng 3–5 phút
docker compose ps                 # chờ cả tx-mysql và tx-lab hiện (healthy)
```

Lệnh giống nhau trên PowerShell, CMD và bash.

## 2. Chạy test

Mọi lệnh đều có dạng `docker compose exec lab python run.py ...`

| Lệnh | Chạy gì | Thời gian ước tính |
|---|---|---|
| `docker compose exec lab python run.py --list` | Liệt kê 24 test | |
| `docker compose exec lab python run.py A B` | Kịch bản A và B (16 test, nhanh, nên chạy khi demo) | ~1 phút |
| `docker compose exec lab python run.py --quick` | A, B và C2/C3 cỡ nhỏ (200 đơn, 4 luồng × 50, đo 1 lần); bỏ qua C1 | ~2 phút |
| `docker compose exec lab python run.py` | A, B, C2, C3 đầy đủ như báo cáo (đo 5 lần); bỏ qua C1 | ~6–10 phút |
| `docker compose exec lab python run.py --allow-crash` | Toàn bộ 24 test, giống lần chạy dùng cho báo cáo | ~7–12 phút |
| `docker compose exec lab python run.py B4` | Một tình huống trên cả hai hệ | |
| `docker compose exec lab python run.py B4 --dbms mysql` | Một tình huống, chỉ MySQL (`--dbms mongodb`: chỉ MongoDB) | |

Mỗi test tự xóa và nạp lại dữ liệu chuẩn trước khi chạy, nên có thể chạy theo thứ tự bất kỳ, bao nhiêu lần cũng được.

### Chạy từng test

Cột "Kết quả mong đợi" là kết quả đã ghi trong báo cáo. PASS nghĩa là hệ quản trị hành xử đúng như lý thuyết dự đoán, kể cả khi dự đoán là *có* bất thường.

| Mã | Tình huống | Lệnh | Kết quả mong đợi | Trong báo cáo |
|---|---|---|---|---|
| **A1** | Đặt 2 bàn Venice khi Showroom Q1 chỉ còn 1 | `python run.py A1` | MySQL: lỗi 3819 (CHECK) → ROLLBACK, không còn đơn; đơn kế tiếp nhận id 3 (AUTO_INCREMENT không trả lại); `placeOrder` báo OUT_OF_STOCK và lượt giữ sofa được hoàn tác. MongoDB: validator 121 → abort; không dùng transaction thì có "đơn ma" | Bảng 15, 42 |
| **A2** | Lỗi giữa giao dịch nhưng code vẫn COMMIT | `python run.py A2` | MySQL: chỉ câu lệnh lỗi bị hủy, COMMIT lưu đơn ma 580 triệu; `withTransaction` / EXIT HANDLER không lưu gì. MongoDB: server hủy cả transaction, lỗi 251 | Bảng 15, 42 |
| **A3** | Đổi kho xuất cho một dòng hàng | `python run.py A3` | MySQL: `ROLLBACK TO SAVEPOINT`, đơn lưu sofa ở Q1 + 2 bàn ở Kho Bình Dương. MongoDB: không có savepoint, lỗi 121 hủy cả lượt giữ sofa; cập nhật có điều kiện thì làm được | Bảng 42 |
| **A4** | Tạo bảng / index giữa giao dịch | `python run.py A4` | MySQL: CREATE TABLE ngầm COMMIT, giá vẫn thành 528 / 682 triệu. MongoDB: createIndex bị từ chối (263), giá giữ 480 / 620 triệu | Bảng 42 |
| **B1** | Dirty read | `python run.py B1` | MySQL READ UNCOMMITTED: 0 rồi 1; READ COMMITTED: 1 và 1. MongoDB: luôn 1 | Bảng 43 |
| **B2** | Non-repeatable read, phantom | `python run.py B2` | MySQL READ COMMITTED: giá 480 → 520 triệu, 3/13 → 4/14; REPEATABLE READ không đổi; `FOR SHARE` thấy 4/14. MongoDB: không đổi trong snapshot | Bảng 43 |
| **B3** | Lost update: hai khách cùng đặt sofa Lawson 240 | `python run.py B3` | MySQL: đọc rồi ghi → 1 (mất lượt); `FOR UPDATE`: B chờ ~1,5 s → 2; version: VERSION_CONFLICT rồi thử lại → 2; cập nhật có điều kiện → 2. MongoDB: WriteConflict 112, thử lại → 2 | Bảng 16, 43 |
| **B4** | Write skew: hai yêu cầu lập lịch thanh toán cho đơn #1 | `python run.py B4` | MySQL: không transaction / REPEATABLE READ → 2 khoản final, tổng 883,5 triệu (sai); SERIALIZABLE → deadlock 1213; khóa dòng `orders` bằng `FOR UPDATE` → B chờ ~1,5 s rồi bị từ chối (đúng). MongoDB: payments tách collection → sai; nhúng trong đơn → WriteConflict 112 (đúng) | Bảng 16, 43 |
| **B5** | Deadlock, timeout, giới hạn thời gian | `python run.py B5` | MySQL: deadlock 1213 hủy cả transaction; sắp xếp theo `variant_id` → không deadlock; timeout 1205 sau 3 s chỉ hủy câu lệnh. MongoDB: WriteConflict ngay, không chờ; lệnh ngoài transaction chờ ~1,5 s; quá hạn → 251 | Bảng 43 |
| **C1** | kill -9 server giữa giao dịch | `python run.py C1 --allow-crash` | Giao dịch Bàn giao đã commit còn nguyên (An 420 → 1 009 triệu); đơn dở dang của Chi bị hủy. MySQL: log có pha redo và undo. MongoDB: bầu PRIMARY mới (≤ 20 s, báo cáo đo 10,5 s), node bị kill tự khôi phục | Bảng 44 |
| **C2** | Thông lượng Đặt hàng tuần tự (1 000 đơn × 5 lần) | `python run.py C2` | H1: flush=2 nhanh hơn flush=1; H2: stored procedure nhanh hơn câu lệnh từ ứng dụng; H3: w:1 nhanh hơn w:majority; H4: với w:majority, có transaction nhanh hơn không có | Bảng 45, Hình 8 |
| **C3** | 8 luồng × 100 đơn cùng mua sofa, tồn đúng 800 | `python run.py C3` | Luôn đúng 800 đơn, đơn thứ 801 bị từ chối. MySQL: cập nhật có điều kiện không cần thử lại; version + thử lại đủ 800 đơn; version không thử lại chỉ được khoảng 100/800. MongoDB: thử lại do WriteConflict | Bảng 46 |

> **C1 kill -9 server.** Với MySQL, test gọi `docker kill --signal=KILL tx-mysql` rồi `docker start tx-mysql`,
> qua `/var/run/docker.sock` được mount vào `tx-lab` (Docker Desktop có sẵn). Với MongoDB, test kill tiến trình
> mongod PRIMARY bên trong `tx-lab` rồi khởi động lại node đó. Vì vậy C1 chỉ chạy khi có thêm `--allow-crash`.

> **Số liệu C2/C3.** Chạy trên Docker Desktop (Windows / macOS) thì số đơn/s sẽ khác báo cáo, vì lần đo trong
> báo cáo chạy trực tiếp trên Linux 2 vCPU. PASS / FAIL của C2, C3 không dựa vào số tuyệt đối mà dựa vào tính đúng
> (đủ 800 đơn, không bán vượt) và tỉ lệ giữa các cấu hình (H1–H4). Số trong báo cáo lấy từ `results/2026-11-09_18-15-06/`.

## 3. Đọc kết quả

Mỗi lần chạy tạo `results/<thời điểm>/`, đồng thời chép một bản sang `results/latest/`:

| File | Nội dung |
|---|---|
| `summary.md` | Bảng tổng hợp PASS / FAIL, chi tiết từng đại lượng: quan sát, kỳ vọng, khớp |
| `logs/<test>.log` | Timeline từng lệnh của phiên A / B, ví dụ `B4-MY.log` |
| `C2-*_raw.csv`, `C2-*_summary.csv`, `C3-*_raw.csv` | Số đo từng lần, trung vị, min–max |
| `environment.json`, `results.json` | Phiên bản, cấu hình DBMS, toàn bộ số đo |

Cách đọc log:

```
[t= 0.76s] A | UPDATE inventory SET ... (đang chờ...)        lệnh của phiên A
[t= 2.27s] A | => 1 row(s) affected (sau khi chờ 1.50s)       kết quả, kèm thời gian chờ khóa
[KHỚP ] FOR UPDATE dòng orders: B chờ (s): quan sát = 1.51 | kỳ vọng ≥ 1,4
```

## 4. Demo bằng tay (khi thuyết trình)

Mở shell vào hai hệ (mở 2 cửa sổ terminal nếu muốn đóng vai phiên A và phiên B):

```bash
# MySQL (đăng nhập root, database luxury_furniture)
docker compose exec lab mysql luxury_furniture

# MongoDB (kết nối cả replica set)
docker compose exec lab mongosh "mongodb://127.0.0.1:27017,127.0.0.1:27018,127.0.0.1:27019/luxury_furniture?replicaSet=rs0"
```

Nạp lại dữ liệu chuẩn trước khi demo:

```bash
docker compose exec lab sh -c "cat setup/mysql_schema.sql setup/mysql_data.sql setup/mysql_procedures.sql | mysql"
docker compose exec lab python -c "from lib import mongo_kit as m; m.reset()"
```

Kết nối từ công cụ đồ họa trên máy:

- MySQL Workbench / DBeaver: `127.0.0.1:3306`, user `root` / `root` (hoặc `demo` / `demo123`).
- MongoDB Compass: `mongodb://127.0.0.1:27017,127.0.0.1:27018,127.0.0.1:27019/?replicaSet=rs0`

## 5. Dừng và dọn

```bash
docker compose stop          # tạm dừng, giữ nguyên dữ liệu
docker compose down          # xóa container (MongoDB dựng lại từ đầu ở lần up sau)
docker compose down -v       # xóa luôn volume dữ liệu MySQL
```

---

## Sự cố thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| `port is already allocated` ở 3306 (máy có MySQL cài sẵn) | Tắt MySQL trên máy (Windows: `net stop MySQL80`), hoặc tạo file `.env` chứa `MYSQL_HOST_PORT=3307`. Cổng này chỉ dùng khi kết nối từ máy host; bộ test chạy trong container nên không bị ảnh hưởng |
| Cổng 27017 bận | Tắt MongoDB trên máy (Windows: `net stop MongoDB`) |
| `tx-lab` báo `bad interpreter` hoặc lỗi `DELIMITER` | Git đã đổi file sang CRLF. Repo có `.gitattributes` để giữ LF; nếu đã clone từ trước: `git config --global core.autocrlf input` rồi clone lại |
| Không tải được image `mongo:8.0.23` hoặc `mysql:8.4.2` | Tạo file `.env` chứa `MONGO_VERSION=8.0` hoặc `MYSQL_VERSION=8.4` (bản vá mới nhất cùng dòng), rồi `docker compose up -d --build` |
| C1-MySQL lỗi `Cannot connect to the Docker daemon` | `tx-lab` chưa thấy `/var/run/docker.sock`. Các test khác vẫn chạy bình thường; bỏ C1 bằng cách không thêm `--allow-crash` |
| Container bị dừng hoặc chạy rất chậm | Docker Desktop → Settings → Resources: cấp tối thiểu 4 GB RAM |
| Xem log của server | `docker compose logs lab`, `docker compose exec lab tail -n 50 /var/log/mysql/error.log` |

## Chạy không dùng Docker

Trên Linux / macOS, nếu đã có MySQL 8.4 và MongoDB 8.0 cài trên máy:

1. Dựng replica set: `bash setup/start_mongo_replset.sh`
2. Chạy mysqld với cấu hình như `setup/my.cnf.example`, rồi tạo user: `CREATE USER 'demo'@'%' IDENTIFIED BY 'demo123'; GRANT ALL ON luxury_furniture.* TO 'demo'@'%';`
3. `pip install -r requirements.txt`, chép `env.sh.example` thành `env.sh`, sửa đường dẫn, `source env.sh`
4. `python run.py --allow-crash`

## Bộ test được viết như thế nào

- **Lược đồ của ứng dụng, giữ nguyên văn:** `setup/mysql_schema.sql` gồm `schema.sql` và `indexes.sql` của repo
  ứng dụng. Ràng buộc tồn kho dùng đúng tên của app là `chk_inventory_reserved_le_on_hand`. Bên MongoDB, 16 bảng
  được ánh xạ thành 8 collection (`orders` nhúng `items[]` và `payments[]`), mỗi collection có validator.
- **Giao dịch giữ đúng thứ tự câu lệnh của backend:** `placeOrder` (order.service.ts): sắp xếp dòng hàng theo
  `variant_id`, khóa hàng limited bằng `FOR UPDATE`, cọc 50% + quyết toán 50%. Bàn giao `updateOrderStatus` và
  `createPaymentSchedule` (sales.service.ts) chạy trong `withTransaction` (config/db.ts).
- **C3 so sánh ba cách giữ tồn kho trên MySQL:** `cond`: cập nhật có điều kiện `(qty_on_hand - qty_reserved) >= ?`,
  cơ chế ứng dụng đang dùng theo báo cáo; `version_retry`: optimistic theo `version`, có thử lại; `version_app`:
  optimistic theo `version`, không thử lại, giữ làm biến thể đối chứng.
- **Bốn nguyên tắc để kết quả lặp lại được:** nạp lại dữ liệu chuẩn trước mỗi test; ghi giả thuyết trước khi chạy;
  so tự động từng đại lượng với dự đoán; cố định thứ tự lệnh của hai phiên (bước chờ khóa chạy ở luồng nền, nghỉ
  cố định 1–1,5 s). C2, C3 chạy nóng 50 đơn, đo 5 lần, xoay vòng thứ tự cấu hình, báo cáo trung vị và min–max.

### Thay đổi so với bản đã chạy cho báo cáo

Logic test và dữ liệu giữ nguyên. Các thay đổi chỉ phục vụ việc chạy bằng Docker:

- Thêm `docker-compose.yml`, thư mục `docker/` và README này.
- `lib/config.py`: thêm biến `MONGO_BIND_IP` (mặc định `127.0.0.1`, giống trước), dùng khi C1 khởi động lại node
  MongoDB. Docker đặt thành `0.0.0.0` để Compass trên máy host vẫn kết nối được sau C1.
- `requirements.txt`: thêm `cryptography`. PyMySQL cần gói này để đăng nhập `caching_sha2_password` (mặc định
  của MySQL 8.4) qua TCP.
- `env.sh.example`, `setup/my.cnf.example`: thay đường dẫn của máy đo bằng ví dụ dùng được.

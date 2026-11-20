-- Sinh tự động: DROP + schema.sql + indexes.sql nguyên văn từ repo auren-dbms-application (database/).
DROP DATABASE IF EXISTS luxury_furniture;
-- ============================================================
-- Luxury Furniture E-commerce - schema.sql
-- DBMS   : MySQL 8.0.16+ (cần để CHECK constraint có hiệu lực)
-- Nguồn  : ERD.md (16 bảng, 6 nhóm A-F)
-- Phạm vi: bảng, kiểu dữ liệu, PK, UNIQUE, FK, CHECK.
--          Các index phụ (secondary index) nằm ở indexes.sql
--          để có thể đo hiệu năng trước/sau khi tạo index.
-- Lưu ý  : InnoDB tự tạo index ẩn cho cột FK. Xem ghi chú trong indexes.sql.
-- ============================================================

CREATE DATABASE IF NOT EXISTS luxury_furniture
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE luxury_furniture;

SET NAMES utf8mb4;

-- ------------------------------------------------------------
-- Xoá bảng cũ (theo thứ tự ngược phụ thuộc) để chạy lại được nhiều lần
-- ------------------------------------------------------------
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS reviews;
DROP TABLE IF EXISTS payments;
DROP TABLE IF EXISTS edition_units;
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS inventory;
DROP TABLE IF EXISTS locations;
DROP TABLE IF EXISTS variant_materials;
DROP TABLE IF EXISTS product_variants;
DROP TABLE IF EXISTS materials;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS categories;
DROP TABLE IF EXISTS brands;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS membership_tiers;
DROP TABLE IF EXISTS users;
SET FOREIGN_KEY_CHECKS = 1;

-- ============================================================
-- GROUP A - USERS
-- ============================================================

CREATE TABLE users (
  id             INT UNSIGNED NOT NULL AUTO_INCREMENT,
  email          VARCHAR(150) NOT NULL,
  password_hash  VARCHAR(255) NOT NULL,
  full_name      VARCHAR(120) NOT NULL,
  role           ENUM('admin','sales','customer') NOT NULL DEFAULT 'customer',
  created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB COMMENT='Tài khoản đăng nhập. role = sales dùng làm nhân viên phụ trách đơn';

CREATE TABLE membership_tiers (
  id            INT UNSIGNED NOT NULL AUTO_INCREMENT,
  name          VARCHAR(30)  NOT NULL COMMENT 'Silver / Gold / Black',
  min_spent     DECIMAL(15,2) NOT NULL DEFAULT 0 COMMENT 'Ngưỡng chi tiêu để đạt hạng',
  discount_pct  DECIMAL(5,2)  NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  UNIQUE KEY uq_tiers_name (name),
  CONSTRAINT chk_tiers_min_spent CHECK (min_spent >= 0),
  CONSTRAINT chk_tiers_discount  CHECK (discount_pct BETWEEN 0 AND 100)
) ENGINE=InnoDB;

CREATE TABLE customers (
  id           INT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id      INT UNSIGNED NOT NULL COMMENT '1:1 với users',
  tier_id      INT UNSIGNED NOT NULL,
  phone        VARCHAR(20),
  address      VARCHAR(255),
  city         VARCHAR(80),
  total_spent  DECIMAL(15,2) NOT NULL DEFAULT 0,
  created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_customers_user (user_id),
  CONSTRAINT fk_customers_user FOREIGN KEY (user_id) REFERENCES users (id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_customers_tier FOREIGN KEY (tier_id) REFERENCES membership_tiers (id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT chk_customers_spent CHECK (total_spent >= 0)
) ENGINE=InnoDB;

-- ============================================================
-- GROUP B - CATALOG
-- ============================================================

CREATE TABLE brands (
  id            INT UNSIGNED NOT NULL AUTO_INCREMENT,
  name          VARCHAR(100) NOT NULL,
  country       VARCHAR(60),
  founded_year  SMALLINT,
  PRIMARY KEY (id),
  UNIQUE KEY uq_brands_name (name)
) ENGINE=InnoDB;

CREATE TABLE categories (
  id         INT UNSIGNED NOT NULL AUTO_INCREMENT,
  parent_id  INT UNSIGNED NULL COMMENT 'Tự tham chiếu: Phòng khách > Sofa > Sofa góc',
  name       VARCHAR(100) NOT NULL,
  slug       VARCHAR(120) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_categories_slug (slug),
  CONSTRAINT fk_categories_parent FOREIGN KEY (parent_id) REFERENCES categories (id)
    ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE products (
  id                INT UNSIGNED NOT NULL AUTO_INCREMENT,
  brand_id          INT UNSIGNED NOT NULL,
  category_id       INT UNSIGNED NOT NULL,
  name              VARCHAR(200) NOT NULL,
  description       TEXT,
  collection_name   VARCHAR(120),
  designer_name     VARCHAR(120),
  is_limited        BOOLEAN NOT NULL DEFAULT FALSE,
  is_made_to_order  BOOLEAN NOT NULL DEFAULT FALSE,
  created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_products_brand    FOREIGN KEY (brand_id)    REFERENCES brands (id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_products_category FOREIGN KEY (category_id) REFERENCES categories (id)
    ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB COMMENT='Sản phẩm gốc. Giá và kích thước nằm ở product_variants';

CREATE TABLE materials (
  id      INT UNSIGNED NOT NULL AUTO_INCREMENT,
  name    VARCHAR(100) NOT NULL,
  type    ENUM('wood','leather','stone','metal','fabric','glass') NOT NULL,
  origin  VARCHAR(80),
  PRIMARY KEY (id),
  UNIQUE KEY uq_materials_name (name)
) ENGINE=InnoDB;

CREATE TABLE product_variants (
  id             INT UNSIGNED NOT NULL AUTO_INCREMENT,
  product_id     INT UNSIGNED NOT NULL,
  sku            VARCHAR(60)  NOT NULL,
  size           VARCHAR(60)  COMMENT 'Ví dụ: 240x100x85 cm',
  finish         VARCHAR(60)  COMMENT 'Màu hoàn thiện',
  price          DECIMAL(15,2) NOT NULL,
  lead_time_days INT NOT NULL DEFAULT 0 COMMENT 'Thời gian sản xuất (made-to-order)',
  status         ENUM('active','discontinued') NOT NULL DEFAULT 'active',
  PRIMARY KEY (id),
  UNIQUE KEY uq_variants_sku (sku),
  CONSTRAINT fk_variants_product FOREIGN KEY (product_id) REFERENCES products (id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT chk_variants_price CHECK (price >= 0),
  CONSTRAINT chk_variants_lead  CHECK (lead_time_days >= 0)
) ENGINE=InnoDB;

CREATE TABLE variant_materials (
  variant_id    INT UNSIGNED NOT NULL,
  material_id   INT UNSIGNED NOT NULL,
  portion       DECIMAL(5,2) COMMENT '% chất liệu trong biến thể',
  finish_note   VARCHAR(120),
  PRIMARY KEY (variant_id, material_id),
  CONSTRAINT fk_vm_variant  FOREIGN KEY (variant_id)  REFERENCES product_variants (id)
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT fk_vm_material FOREIGN KEY (material_id) REFERENCES materials (id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT chk_vm_portion CHECK (portion IS NULL OR portion BETWEEN 0 AND 100)
) ENGINE=InnoDB COMMENT='Bảng nối N:M giữa product_variants và materials';

-- ============================================================
-- GROUP C - INVENTORY
-- ============================================================

CREATE TABLE locations (
  id    INT UNSIGNED NOT NULL AUTO_INCREMENT,
  name  VARCHAR(120) NOT NULL,
  type  ENUM('showroom','warehouse') NOT NULL,
  city  VARCHAR(80),
  PRIMARY KEY (id)
) ENGINE=InnoDB;

CREATE TABLE inventory (
  variant_id    INT UNSIGNED NOT NULL,
  location_id   INT UNSIGNED NOT NULL,
  qty_on_hand   INT NOT NULL DEFAULT 0,
  qty_reserved  INT NOT NULL DEFAULT 0,
  version       INT NOT NULL DEFAULT 0 COMMENT 'Optimistic locking',
  PRIMARY KEY (variant_id, location_id),
  CONSTRAINT fk_inventory_variant  FOREIGN KEY (variant_id)  REFERENCES product_variants (id)
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT fk_inventory_location FOREIGN KEY (location_id) REFERENCES locations (id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT chk_inventory_on_hand  CHECK (qty_on_hand >= 0),
  CONSTRAINT chk_inventory_reserved CHECK (qty_reserved >= 0),
  CONSTRAINT chk_inventory_reserved_le_on_hand CHECK (qty_reserved <= qty_on_hand)
) ENGINE=InnoDB COMMENT='Bảng nối N:M variants x locations, mang số lượng tồn';

-- ============================================================
-- GROUP D - SALES
-- (orders, order_items đặt trước edition_units vì edition_units tham chiếu order_items)
-- ============================================================

CREATE TABLE orders (
  id               INT UNSIGNED NOT NULL AUTO_INCREMENT,
  customer_id      INT UNSIGNED NOT NULL,
  sales_user_id    INT UNSIGNED NULL COMMENT 'Nhân viên sales phụ trách',
  order_date       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  status           ENUM('pending','confirmed','in_production','shipped','delivered','cancelled')
                   NOT NULL DEFAULT 'pending',
  subtotal         DECIMAL(15,2) NOT NULL DEFAULT 0,
  discount         DECIMAL(15,2) NOT NULL DEFAULT 0,
  total            DECIMAL(15,2) NOT NULL DEFAULT 0,
  shipping_address VARCHAR(255) NOT NULL COMMENT 'Snapshot địa chỉ lúc đặt',
  delivery_date    DATE,
  PRIMARY KEY (id),
  CONSTRAINT fk_orders_customer FOREIGN KEY (customer_id)   REFERENCES customers (id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_orders_sales    FOREIGN KEY (sales_user_id) REFERENCES users (id)
    ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT chk_orders_amounts CHECK (subtotal >= 0 AND discount >= 0 AND total >= 0)
) ENGINE=InnoDB;

CREATE TABLE order_items (
  id            INT UNSIGNED NOT NULL AUTO_INCREMENT,
  order_id      INT UNSIGNED NOT NULL,
  variant_id    INT UNSIGNED NOT NULL,
  location_id   INT UNSIGNED NOT NULL COMMENT 'Kho/showroom xuất hàng',
  quantity      INT NOT NULL DEFAULT 1,
  unit_price    DECIMAL(15,2) NOT NULL COMMENT 'Giá chốt tại thời điểm bán',
  customization JSON COMMENT 'Yêu cầu tuỳ chỉnh: chất liệu, màu, kích thước',
  PRIMARY KEY (id),
  CONSTRAINT fk_oi_order    FOREIGN KEY (order_id)    REFERENCES orders (id)
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT fk_oi_variant  FOREIGN KEY (variant_id)  REFERENCES product_variants (id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_oi_location FOREIGN KEY (location_id) REFERENCES locations (id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT chk_oi_quantity   CHECK (quantity > 0),
  CONSTRAINT chk_oi_unit_price CHECK (unit_price >= 0)
) ENGINE=InnoDB;

-- ============================================================
-- GROUP C (tiếp) - EDITION UNITS
-- ============================================================

CREATE TABLE edition_units (
  id             INT UNSIGNED NOT NULL AUTO_INCREMENT,
  variant_id     INT UNSIGNED NOT NULL,
  order_item_id  INT UNSIGNED NULL COMMENT 'NULL khi chưa bán',
  serial_no      VARCHAR(40) NOT NULL COMMENT 'Ví dụ: 07/50',
  status         ENUM('available','reserved','sold') NOT NULL DEFAULT 'available',
  PRIMARY KEY (id),
  UNIQUE KEY uq_edition_order_item (order_item_id),
  UNIQUE KEY uq_edition_serial (serial_no),
  CONSTRAINT fk_edition_variant    FOREIGN KEY (variant_id)    REFERENCES product_variants (id)
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT fk_edition_order_item FOREIGN KEY (order_item_id) REFERENCES order_items (id)
    ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB COMMENT='Từng chiếc limited edition, điểm demo Concurrency';

-- ============================================================
-- GROUP E - PAYMENT
-- ============================================================

CREATE TABLE payments (
  id        INT UNSIGNED NOT NULL AUTO_INCREMENT,
  order_id  INT UNSIGNED NOT NULL,
  type      ENUM('deposit','installment','final') NOT NULL,
  amount    DECIMAL(15,2) NOT NULL,
  due_date  DATE,
  paid_at   DATETIME NULL,
  method    VARCHAR(40) COMMENT 'Chuyển khoản / thẻ / tiền mặt',
  status    ENUM('pending','paid','overdue','refunded') NOT NULL DEFAULT 'pending',
  PRIMARY KEY (id),
  CONSTRAINT fk_payments_order FOREIGN KEY (order_id) REFERENCES orders (id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT chk_payments_amount CHECK (amount > 0)
) ENGINE=InnoDB COMMENT='Gộp đặt cọc, trả góp, thanh toán cuối vào một bảng';

-- ============================================================
-- GROUP F - ENGAGEMENT
-- ============================================================

CREATE TABLE reviews (
  id             INT UNSIGNED NOT NULL AUTO_INCREMENT,
  customer_id    INT UNSIGNED NOT NULL,
  product_id     INT UNSIGNED NOT NULL,
  order_item_id  INT UNSIGNED NOT NULL COMMENT 'Xác thực đã mua',
  rating         TINYINT NOT NULL COMMENT '1-5',
  comment        TEXT,
  created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_reviews_customer_item (customer_id, order_item_id),
  CONSTRAINT fk_reviews_customer   FOREIGN KEY (customer_id)   REFERENCES customers (id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_reviews_product    FOREIGN KEY (product_id)    REFERENCES products (id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_reviews_order_item FOREIGN KEY (order_item_id) REFERENCES order_items (id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT chk_reviews_rating CHECK (rating BETWEEN 1 AND 5)
) ENGINE=InnoDB;

-- ============================================================
-- Hết schema. Chạy tiếp (sau khi nạp dữ liệu): indexes.sql
-- ============================================================
-- ============================================================
-- Luxury Furniture E-commerce - indexes.sql
-- Chạy SAU schema.sql (và nên chạy sau khi nạp dữ liệu lớn
-- để việc tạo index nhanh hơn).
--
-- Cấu trúc file:
--   1. Index theo ERD.md
--   2. Index bổ sung (ngoài ERD, phục vụ truy vấn của Sales)
--   3. Index tuỳ chọn (FULLTEXT) - mặc định tắt
--   4. Kịch bản demo Indexing: EXPLAIN trước/sau
--   5. Gỡ index để quay về trạng thái "trước"
--
-- GHI CHÚ VỀ INDEX NGẦM CỦA FOREIGN KEY
--   InnoDB tự tạo index cho cột FK nếu chưa có index phù hợp.
--   Khi tạo index composite có cột FK đứng đầu (vd. orders(customer_id, order_date)),
--   MySQL tự bỏ index ngầm và dùng index mới. Do đó các index trên cột FK
--   thuần tuý (customers.tier_id, categories.parent_id, order_items.order_id,
--   order_items.variant_id) đã có sẵn từ schema.sql; lệnh bên dưới vẫn giữ
--   để khớp ERD và đặt tên rõ ràng.
-- ============================================================

USE luxury_furniture;

-- ============================================================
-- 1. INDEX THEO ERD
-- ============================================================

-- customers
CREATE INDEX idx_customers_city        ON customers (city);
CREATE INDEX idx_customers_tier        ON customers (tier_id);

-- categories
CREATE INDEX idx_categories_parent     ON categories (parent_id);

-- products
CREATE INDEX idx_products_category_brand ON products (category_id, brand_id);
CREATE INDEX idx_products_name           ON products (name);

-- product_variants
CREATE INDEX idx_variants_product_price  ON product_variants (product_id, price);

-- edition_units
CREATE INDEX idx_edition_variant_status  ON edition_units (variant_id, status);

-- orders
CREATE INDEX idx_orders_customer_date    ON orders (customer_id, order_date);
CREATE INDEX idx_orders_status_total     ON orders (status, total);
CREATE INDEX idx_orders_date             ON orders (order_date);

-- order_items
CREATE INDEX idx_oi_order                ON order_items (order_id);
CREATE INDEX idx_oi_variant              ON order_items (variant_id);

-- payments
CREATE INDEX idx_payments_order_type     ON payments (order_id, type);
CREATE INDEX idx_payments_status_due     ON payments (status, due_date);

-- reviews
CREATE INDEX idx_reviews_product_rating  ON reviews (product_id, rating);

-- Đã có từ schema.sql (UNIQUE), không tạo lại:
--   users(email), membership_tiers(name), customers(user_id), brands(name),
--   categories(slug), materials(name), product_variants(sku),
--   edition_units(order_item_id), edition_units(serial_no),
--   reviews(customer_id, order_item_id)
--   PK composite: variant_materials(variant_id, material_id), inventory(variant_id, location_id)

-- ============================================================
-- 2. INDEX BỔ SUNG (NGOÀI ERD)
-- ============================================================

-- Hàng đợi đơn và đơn của từng Sales (FR11, FR13):
--   WHERE sales_user_id = ? AND status = ?
CREATE INDEX idx_orders_sales_status     ON orders (sales_user_id, status);

-- Tìm kho theo biến thể khi xuất hàng / tra tồn theo kho (FR4, FR12):
-- PK (variant_id, location_id) đã phủ truy vấn theo variant.
-- Truy vấn theo location_id có index FK ngầm, không cần thêm.

-- ============================================================
-- 3. INDEX TUỲ CHỌN - FULLTEXT (mặc định tắt)
--    Lý do: idx_products_name (B-Tree) chỉ hỗ trợ LIKE 'sofa%'.
--    LIKE '%sofa%' (FR3) phải quét toàn bảng. FULLTEXT là phương án
--    cải thiện, dùng để minh hoạ giới hạn của B-Tree trong báo cáo.
--    Bỏ dấu chú thích để bật.
-- ============================================================

-- ALTER TABLE products ADD FULLTEXT INDEX ftx_products_name (name) WITH PARSER ngram;
-- SELECT id, name FROM products WHERE MATCH(name) AGAINST ('sofa' IN NATURAL LANGUAGE MODE);

-- ============================================================
-- 4. KỊCH BẢN DEMO INDEXING (EXPLAIN)
--    Cách làm: chạy khối 5 (gỡ index) -> chạy các EXPLAIN -> ghi kết quả ->
--    chạy lại khối 1-2 -> chạy lại các EXPLAIN -> so sánh.
--    Cột cần ghi lại: type, key, rows, filtered, Extra.
--    Dùng EXPLAIN ANALYZE (MySQL 8.0.18+) để có thời gian thực.
-- ============================================================

-- Q1 (FR15 - báo cáo): đơn theo trạng thái và tổng tiền, dùng idx_orders_status_total
-- EXPLAIN ANALYZE
-- SELECT id, total FROM orders WHERE status = 'delivered' AND total > 200000000;

-- Q2 (FR8): lịch sử đơn của một khách, dùng idx_orders_customer_date
-- EXPLAIN ANALYZE
-- SELECT id, order_date, status, total FROM orders
--  WHERE customer_id = 123 ORDER BY order_date DESC;

-- Q3 (FR3): lọc biến thể theo sản phẩm và khoảng giá, dùng idx_variants_product_price
-- EXPLAIN ANALYZE
-- SELECT id, sku, price FROM product_variants
--  WHERE product_id = 50 AND price BETWEEN 50000000 AND 300000000;

-- Q4 (FR13): công nợ quá hạn, dùng idx_payments_status_due
-- EXPLAIN ANALYZE
-- SELECT id, order_id, amount FROM payments
--  WHERE status = 'pending' AND due_date < CURDATE();

-- Q5 (FR15 - báo cáo): doanh thu theo tháng, dùng idx_orders_date
-- EXPLAIN ANALYZE
-- SELECT DATE_FORMAT(order_date,'%Y-%m') AS m, COUNT(*), SUM(total)
--   FROM orders WHERE order_date >= '2026-01-01' AND order_date < '2027-01-01'
--  GROUP BY m;

-- Q6 (FR3): so sánh LIKE tiền tố và LIKE chứa (giới hạn của B-Tree)
-- EXPLAIN SELECT id FROM products WHERE name LIKE 'Sofa%';    -- dùng được idx_products_name
-- EXPLAIN SELECT id FROM products WHERE name LIKE '%sofa%';   -- quét toàn bảng

-- Q7 (FR10 - chống trùng đánh giá): kiểm tra UNIQUE (customer_id, order_item_id)
-- EXPLAIN SELECT id FROM reviews WHERE customer_id = 1 AND order_item_id = 99;

-- Kiểm tra index hiện có
-- SHOW INDEX FROM orders;
-- SELECT TABLE_NAME, INDEX_NAME, GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS cols
--   FROM information_schema.STATISTICS
--  WHERE TABLE_SCHEMA = 'luxury_furniture'
--  GROUP BY TABLE_NAME, INDEX_NAME ORDER BY TABLE_NAME, INDEX_NAME;

-- ============================================================
-- 5. GỠ INDEX ĐỂ QUAY VỀ TRẠNG THÁI "TRƯỚC" (dùng khi demo)
--    Chỉ gỡ các index không phục vụ FK hoặc UNIQUE.
--    Index trên cột FK sẽ được InnoDB thay bằng index ngầm.
--    Bỏ dấu chú thích để chạy.
-- ============================================================

-- DROP INDEX idx_orders_status_total    ON orders;
-- DROP INDEX idx_orders_date            ON orders;
-- DROP INDEX idx_orders_sales_status    ON orders;
-- DROP INDEX idx_orders_customer_date   ON orders;
-- DROP INDEX idx_variants_product_price ON product_variants;
-- DROP INDEX idx_payments_status_due    ON payments;
-- DROP INDEX idx_payments_order_type    ON payments;
-- DROP INDEX idx_products_name          ON products;
-- DROP INDEX idx_products_category_brand ON products;
-- DROP INDEX idx_reviews_product_rating ON reviews;
-- DROP INDEX idx_edition_variant_status ON edition_units;
-- DROP INDEX idx_customers_city         ON customers;

-- Không thể DROP INDEX, thực hiện ALTER TABLE để các index invisible với query optimizer
ALTER TABLE orders           ALTER INDEX idx_orders_status_total     INVISIBLE;
ALTER TABLE orders           ALTER INDEX idx_orders_date             INVISIBLE;
ALTER TABLE orders           ALTER INDEX idx_orders_sales_status     INVISIBLE;
ALTER TABLE orders           ALTER INDEX idx_orders_customer_date    INVISIBLE;
ALTER TABLE product_variants ALTER INDEX idx_variants_product_price  INVISIBLE;
ALTER TABLE payments         ALTER INDEX idx_payments_status_due     INVISIBLE;
ALTER TABLE payments         ALTER INDEX idx_payments_order_type     INVISIBLE;
ALTER TABLE products         ALTER INDEX idx_products_name           INVISIBLE;
ALTER TABLE products         ALTER INDEX idx_products_category_brand INVISIBLE;
ALTER TABLE reviews          ALTER INDEX idx_reviews_product_rating  INVISIBLE;
ALTER TABLE edition_units    ALTER INDEX idx_edition_variant_status  INVISIBLE;
ALTER TABLE customers        ALTER INDEX idx_customers_city          INVISIBLE;

ALTER TABLE orders           ALTER INDEX idx_orders_status_total     VISIBLE;
ALTER TABLE orders           ALTER INDEX idx_orders_date             VISIBLE;
ALTER TABLE orders           ALTER INDEX idx_orders_sales_status     VISIBLE;
ALTER TABLE orders           ALTER INDEX idx_orders_customer_date    VISIBLE;
ALTER TABLE product_variants ALTER INDEX idx_variants_product_price  VISIBLE;
ALTER TABLE payments         ALTER INDEX idx_payments_status_due     VISIBLE;
ALTER TABLE payments         ALTER INDEX idx_payments_order_type     VISIBLE;
ALTER TABLE products         ALTER INDEX idx_products_name           VISIBLE;
ALTER TABLE products         ALTER INDEX idx_products_category_brand VISIBLE;
ALTER TABLE reviews          ALTER INDEX idx_reviews_product_rating  VISIBLE;
ALTER TABLE edition_units    ALTER INDEX idx_edition_variant_status  VISIBLE;
ALTER TABLE customers        ALTER INDEX idx_customers_city          VISIBLE;
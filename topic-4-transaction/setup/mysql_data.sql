-- =====================================================================
-- Dữ liệu mẫu cho bộ test Transaction (chạy sau mysql_schema.sql).
-- Bậc hạng thành viên lấy đúng theo seed của ứng dụng (Silver 0% / Gold 5% / Black 10%).
-- Dữ liệu cố ý nhỏ để mỗi tình huống tranh chấp tái hiện được và kiểm tra được bằng tay.
-- =====================================================================
USE luxury_furniture;

INSERT INTO membership_tiers (id, name, min_spent, discount_pct) VALUES
  (1, 'Silver', 0, 0),
  (2, 'Gold',   150000000, 5),
  (3, 'Black',  500000000, 10);

INSERT INTO users (id, email, password_hash, full_name, role) VALUES
  (1, 'admin@luxe.vn', 'x', 'Quản trị viên',  'admin'),
  (2, 'lan@luxe.vn',   'x', 'Nguyễn Thị Lan', 'sales'),
  (3, 'minh@luxe.vn',  'x', 'Đỗ Quang Minh',  'sales'),
  (4, 'an@mail.vn',    'x', 'Trần Văn An',    'customer'),
  (5, 'binh@mail.vn',  'x', 'Lê Thị Bình',    'customer'),
  (6, 'chi@mail.vn',   'x', 'Phạm Minh Chi',  'customer');

INSERT INTO customers (id, user_id, tier_id, phone, address, city, total_spent) VALUES
  (1, 4, 2, '0901000001', '12 Nguyễn Huệ, Quận 1',  'Hồ Chí Minh', 420000000),  -- Gold
  (2, 5, 1, '0901000002', '5 Tràng Tiền',           'Hà Nội',       60000000),  -- Silver
  (3, 6, 1, '0901000003', '88 Võ Văn Tần, Quận 3',  'Hồ Chí Minh',          0); -- Silver

INSERT INTO brands (id, name, country, founded_year) VALUES
  (1, 'Minotti', 'Italy', 1948), (2, 'Poltrona Frau', 'Italy', 1912), (3, 'Baxter', 'Italy', 1990);

INSERT INTO categories (id, parent_id, name, slug) VALUES
  (1, NULL, 'Phòng khách', 'phong-khach'), (2, 1, 'Sofa', 'sofa'), (3, 1, 'Ghế bành', 'ghe-banh'),
  (4, 1, 'Bàn trà', 'ban-tra'), (5, NULL, 'Phòng ăn', 'phong-an'), (6, 5, 'Bàn ăn', 'ban-an');

INSERT INTO products (id, brand_id, category_id, name, collection_name, designer_name, is_limited, is_made_to_order) VALUES
  (1, 1, 2, 'Sofa Lawson',                'Lawson',    'Rodolfo Dordoni',    FALSE, FALSE),
  (2, 2, 3, 'Ghế Archibald Gran Comfort', 'Archibald', 'Jean-Marie Massaud', TRUE,  FALSE),
  (3, 3, 4, 'Bàn trà Marmo',              'Marmo',     'Paola Navone',       FALSE, TRUE),
  (4, 1, 6, 'Bàn ăn Venice',              'Venice',    'Rodolfo Dordoni',    FALSE, FALSE);

INSERT INTO materials (id, name, type, origin) VALUES
  (1, 'Da Nappa', 'leather', 'Italy'), (2, 'Gỗ óc chó', 'wood', 'USA'),
  (3, 'Đá Calacatta', 'stone', 'Italy'), (4, 'Đồng thau', 'metal', 'Italy');

INSERT INTO product_variants (id, product_id, sku, size, finish, price, lead_time_days) VALUES
  (101, 1, 'LAWSON-240-GRY', '240x100x85 cm', 'Xám tro',   480000000,  0),
  (102, 1, 'LAWSON-300-BEI', '300x105x85 cm', 'Be cát',    620000000,  0),
  (201, 2, 'ARCHI-LTD-CGN',  '90x95x100 cm',  'Cognac',    950000000,  0),
  (301, 3, 'MARMO-120-CAL',  '120x60x35 cm',  'Calacatta', 380000000, 60),
  (401, 4, 'VENICE-220-WAL', '220x100x75 cm', 'Óc chó',    290000000,  0);

INSERT INTO variant_materials (variant_id, material_id, portion, finish_note) VALUES
  (101, 1, 80, 'Da Nappa xám'), (101, 2, 20, 'Chân gỗ'),
  (201, 1, 90, 'Da Cognac khâu tay'), (201, 4, 10, 'Chân đồng'),
  (301, 3, 85, NULL), (301, 4, 15, NULL), (401, 2, 100, 'Óc chó nguyên tấm');

INSERT INTO locations (id, name, type, city) VALUES
  (1, 'Showroom Quận 1',    'showroom',  'Hồ Chí Minh'),
  (2, 'Showroom Hoàn Kiếm', 'showroom',  'Hà Nội'),
  (3, 'Kho Bình Dương',     'warehouse', 'Bình Dương');

INSERT INTO inventory (variant_id, location_id, qty_on_hand, qty_reserved) VALUES
  (101, 1, 2, 0), (101, 3, 6, 0),
  (102, 1, 1, 0), (102, 3, 3, 1),   -- 1 chiếc đang giữ cho đơn #1
  (201, 1, 2, 0),
  (401, 1, 1, 0), (401, 3, 4, 0);   -- bàn ăn Venice: Showroom Q1 chỉ còn 1

-- Ghế Archibald phiên bản giới hạn 50 chiếc; còn 2 chiếc chưa bán
INSERT INTO edition_units (id, variant_id, serial_no, status) VALUES
  (7, 201, '07/50', 'available'),
  (8, 201, '08/50', 'available');

-- Đơn #1 của An: sofa Lawson 300 từ Kho Bình Dương, sales Lan đã nhận, đã trả cọc 50%.
-- Dùng cho B4 (lập lịch thanh toán) và C1 (giao dịch Bàn giao).
INSERT INTO orders (id, customer_id, sales_user_id, status, subtotal, discount, total, shipping_address) VALUES
  (1, 1, 2, 'confirmed', 620000000, 31000000, 589000000, '12 Nguyễn Huệ, Quận 1');
INSERT INTO order_items (id, order_id, variant_id, location_id, quantity, unit_price) VALUES
  (1, 1, 102, 3, 1, 620000000);
INSERT INTO payments (id, order_id, type, amount, due_date, paid_at, method, status) VALUES
  (1, 1, 'deposit', 294500000, CURDATE(), NOW(), 'Chuyển khoản', 'paid');

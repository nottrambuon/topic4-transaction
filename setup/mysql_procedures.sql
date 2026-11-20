-- =====================================================================
-- Stored procedure tương đương hai giao dịch của ứng dụng (dùng cho A2 và C2).
-- sp_place_order  ~ order.service.ts placeOrder (FR5), một dòng hàng
-- sp_deliver_order ~ sales.service.ts updateOrderStatus -> 'delivered' (FR11)
-- Xử lý lỗi: EXIT HANDLER -> ROLLBACK rồi RESIGNAL (ứng dụng vẫn nhận được mã lỗi gốc).
-- =====================================================================
USE luxury_furniture;

DELIMITER //

DROP PROCEDURE IF EXISTS sp_place_order //
CREATE PROCEDURE sp_place_order(IN p_customer INT UNSIGNED, IN p_variant INT UNSIGNED,
                                IN p_location INT UNSIGNED, IN p_qty INT, IN p_address VARCHAR(255),
                                OUT p_order_id INT UNSIGNED)
BEGIN
  DECLARE v_price, v_subtotal, v_discount, v_total, v_deposit DECIMAL(15,2);
  DECLARE v_disc_pct DECIMAL(5,2);
  DECLARE v_on_hand, v_reserved, v_version INT;
  DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;

  START TRANSACTION;
  SELECT t.discount_pct INTO v_disc_pct
    FROM customers c JOIN membership_tiers t ON t.id = c.tier_id WHERE c.id = p_customer;
  SELECT price INTO v_price FROM product_variants WHERE id = p_variant AND status = 'active';
  IF v_price IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'VARIANT_NOT_FOUND';
  END IF;

  -- Giữ hàng bằng optimistic locking qua cột version (giống inventory.repository.ts)
  SELECT qty_on_hand, qty_reserved, version INTO v_on_hand, v_reserved, v_version
    FROM inventory WHERE variant_id = p_variant AND location_id = p_location;
  IF v_on_hand IS NULL OR v_on_hand - v_reserved < p_qty THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'OUT_OF_STOCK';
  END IF;
  UPDATE inventory SET qty_reserved = qty_reserved + p_qty, version = version + 1
   WHERE variant_id = p_variant AND location_id = p_location
     AND version = v_version AND (qty_on_hand - qty_reserved) >= p_qty;
  IF ROW_COUNT() = 0 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'VERSION_CONFLICT';
  END IF;

  SET v_subtotal = v_price * p_qty;
  SET v_discount = ROUND(v_subtotal * v_disc_pct / 100);
  SET v_total    = v_subtotal - v_discount;
  SET v_deposit  = ROUND(v_total * 0.5);

  INSERT INTO orders (customer_id, subtotal, discount, total, shipping_address)
  VALUES (p_customer, v_subtotal, v_discount, v_total, p_address);
  SET p_order_id = LAST_INSERT_ID();
  INSERT INTO order_items (order_id, variant_id, location_id, quantity, unit_price)
  VALUES (p_order_id, p_variant, p_location, p_qty, v_price);
  INSERT INTO payments (order_id, type, amount, due_date, status) VALUES
    (p_order_id, 'deposit', v_deposit,           CURDATE(),                     'pending'),
    (p_order_id, 'final',   v_total - v_deposit, CURDATE() + INTERVAL 30 DAY,   'pending');
  COMMIT;
END //

DROP PROCEDURE IF EXISTS sp_deliver_order //
CREATE PROCEDURE sp_deliver_order(IN p_order INT UNSIGNED, IN p_sales INT UNSIGNED)
BEGIN
  DECLARE v_customer INT UNSIGNED;
  DECLARE v_total DECIMAL(15,2);
  DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;

  START TRANSACTION;
  SELECT customer_id, total INTO v_customer, v_total FROM orders WHERE id = p_order;
  UPDATE orders SET status = 'delivered' WHERE id = p_order AND sales_user_id = p_sales;
  UPDATE inventory i JOIN order_items oi ON oi.variant_id = i.variant_id AND oi.location_id = i.location_id
     SET i.qty_on_hand = GREATEST(0, i.qty_on_hand - oi.quantity),
         i.qty_reserved = GREATEST(0, i.qty_reserved - oi.quantity),
         i.version = i.version + 1
   WHERE oi.order_id = p_order;
  UPDATE edition_units eu JOIN order_items oi ON eu.order_item_id = oi.id
     SET eu.status = 'sold' WHERE oi.order_id = p_order;
  UPDATE customers SET total_spent = total_spent + v_total WHERE id = v_customer;
  COMMIT;
END //

DELIMITER ;

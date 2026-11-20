-- Chạy một lần khi khởi tạo volume dữ liệu MySQL.
CREATE USER IF NOT EXISTS 'demo'@'%' IDENTIFIED BY 'demo123';
GRANT ALL PRIVILEGES ON luxury_furniture.* TO 'demo'@'%';
FLUSH PRIVILEGES;

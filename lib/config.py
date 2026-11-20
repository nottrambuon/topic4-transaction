"""Cấu hình môi trường. Mọi giá trị đều đổi được bằng biến môi trường (xem README, mục "Cấu hình")."""
import os
import shlex

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETUP_DIR = os.path.join(ROOT, "setup")
RESULTS_DIR = os.getenv("RESULTS_DIR", os.path.join(ROOT, "results"))

DB = "luxury_furniture"

# --- MySQL -------------------------------------------------------------------
# Kết nối của "ứng dụng" (các phiên A, B, luồng benchmark)
MYSQL = dict(host=os.getenv("MYSQL_HOST", "127.0.0.1"), port=int(os.getenv("MYSQL_PORT", "3306")),
             user=os.getenv("MYSQL_USER", "demo"), password=os.getenv("MYSQL_PASSWORD", "demo123"))
# Lệnh client quản trị: dùng để nạp lại schema, đổi biến GLOBAL, đọc SHOW ENGINE INNODB STATUS
MYSQL_CLI = shlex.split(os.getenv("MYSQL_CLI", "mysql -uroot"))
# Chỉ dùng cho C1 (crash test)
MYSQL_KILL_CMD = os.getenv("MYSQL_KILL_CMD", "kill -9 $(pidof mysqld)")
MYSQL_START_CMD = os.getenv("MYSQL_START_CMD", "service mysql start")
MYSQL_ERROR_LOG = os.getenv("MYSQL_ERROR_LOG", "/var/log/mysql/error.log")
# Tài khoản quản trị qua unix socket (để đổi biến GLOBAL, đọc trạng thái). Bỏ trống = dùng MYSQL_CLI.
MYSQL_ADMIN_SOCKET = os.getenv("MYSQL_ADMIN_SOCKET", "")

# --- MongoDB -----------------------------------------------------------------
MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017,127.0.0.1:27018,127.0.0.1:27019/?replicaSet=rs0")
# Chỉ dùng cho C1 (kill PRIMARY rồi khởi động lại node đó)
MONGOD_BIN = os.getenv("MONGOD_BIN", "mongod")
MONGO_DATA = os.getenv("MONGO_DATA", os.path.join(ROOT, "data"))
MONGO_BASE_PORT = int(os.getenv("MONGO_BASE_PORT", "27017"))
# Địa chỉ lắng nghe khi C1 khởi động lại node bị kill (Docker: 0.0.0.0 để máy host vẫn kết nối được)
MONGO_BIND_IP = os.getenv("MONGO_BIND_IP", "127.0.0.1")

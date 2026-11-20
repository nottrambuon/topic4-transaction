#!/bin/bash
# Khởi động replica set rs0 gồm 3 node mongod trong container (cổng 27017-27019), giống
# setup/start_mongo_replset.sh, rồi chờ lệnh (docker compose exec lab python run.py ...).
set -euo pipefail

DATA="${MONGO_DATA:-/data/rs}"
BIND="${MONGO_BIND_IP:-0.0.0.0}"
PORTS=(27017 27018 27019)

# Client mysql (MYSQL_CLI=mysql) đọc kết nối quản trị từ file này
cat > /root/.my.cnf <<EOF
[client]
host=${MYSQL_HOST:-mysql}
port=${MYSQL_PORT:-3306}
user=root
password=${MYSQL_ROOT_PASSWORD:-root}
default-character-set=utf8mb4
EOF
chmod 600 /root/.my.cnf

shutdown() {
  echo "Đang tắt replica set..."
  for i in 0 1 2; do mongod --dbpath "$DATA/rs$i" --shutdown >/dev/null 2>&1 || true; done
  exit 0
}
trap shutdown TERM INT

for i in 0 1 2; do
  mkdir -p "$DATA/rs$i"
  # Đã chạy sẵn (container được khởi động lại bằng exec)? thì bỏ qua
  if pgrep -f "mongod .*--port ${PORTS[$i]}" >/dev/null; then continue; fi
  mongod --replSet rs0 --port "${PORTS[$i]}" --dbpath "$DATA/rs$i" --bind_ip "$BIND" \
    --fork --logpath "$DATA/rs$i.log" --logappend >/dev/null
done

for _ in $(seq 1 60); do
  mongosh --quiet --port 27017 --eval 'db.runCommand({ping: 1}).ok' >/dev/null 2>&1 && break
  sleep 1
done

mongosh --quiet --port 27017 --eval '
try { rs.status(); print("Replica set rs0 đã được khởi tạo trước đó."); }
catch (e) {
  rs.initiate({ _id: "rs0", members: [
    { _id: 0, host: "127.0.0.1:27017", priority: 2 },
    { _id: 1, host: "127.0.0.1:27018" },
    { _id: 2, host: "127.0.0.1:27019" } ] });
  print("Đã khởi tạo replica set rs0.");
}'

for _ in $(seq 1 90); do
  if mongosh --quiet --port 27017 --eval 'quit(db.hello().isWritablePrimary ? 0 : 1)' >/dev/null 2>&1; then
    echo "MongoDB replica set rs0 sẵn sàng (PRIMARY 127.0.0.1:27017)."
    break
  fi
  sleep 1
done

"$@" &
wait $!

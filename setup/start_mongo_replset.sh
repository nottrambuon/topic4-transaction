#!/usr/bin/env bash
# Dựng replica set rs0 gồm 3 node mongod trên cùng một máy (Linux / macOS).
# Transaction của MongoDB không chạy trên server đơn lẻ (standalone), nên bắt buộc có replica set.
#   bash setup/start_mongo_replset.sh         # khởi động 3 node, dữ liệu trong $MONGO_DATA (mặc định ./data)
#   bash setup/start_mongo_replset.sh stop    # tắt 3 node
set -euo pipefail
MONGOD_BIN="${MONGOD_BIN:-mongod}"
DATA="${MONGO_DATA:-$(cd "$(dirname "$0")/.." && pwd)/data}"
PORTS=(27017 27018 27019)
if [[ "${1:-}" == "stop" ]]; then
  for i in 0 1 2; do "$MONGOD_BIN" --dbpath "$DATA/rs$i" --shutdown >/dev/null 2>&1 || true; done
  echo "Đã tắt replica set."; exit 0
fi
for i in 0 1 2; do
  mkdir -p "$DATA/rs$i"
  "$MONGOD_BIN" --replSet rs0 --port "${PORTS[$i]}" --dbpath "$DATA/rs$i" --bind_ip 127.0.0.1 \
    --fork --logpath "$DATA/rs$i.log" --logappend >/dev/null
done
sleep 3
mongosh --quiet --port 27017 --eval '
try { rs.status(); print("Replica set đã được khởi tạo trước đó."); }
catch (e) {
  rs.initiate({ _id: "rs0", members: [
    { _id: 0, host: "127.0.0.1:27017", priority: 2 },
    { _id: 1, host: "127.0.0.1:27018" },
    { _id: 2, host: "127.0.0.1:27019" } ] });
  print("Đã khởi tạo replica set rs0.");
}'

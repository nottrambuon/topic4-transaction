#!/bin/bash
# Bảo đảm thư mục error log (volume mysql-log) thuộc user mysql, rồi chạy entrypoint gốc của image.
set -e
mkdir -p /var/log/mysql
chown -R mysql:mysql /var/log/mysql
exec docker-entrypoint.sh "$@"

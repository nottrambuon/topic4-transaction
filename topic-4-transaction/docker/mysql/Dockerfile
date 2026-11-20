ARG MYSQL_VERSION=8.4.2
FROM mysql:${MYSQL_VERSION}

# Cấu hình giống lần đo trong báo cáo + error log ra file để C1 đọc nhật ký redo/undo
COPY docker/mysql/transaction.cnf /etc/mysql/conf.d/transaction.cnf
# Tài khoản ứng dụng demo / demo123 (các phiên A, B và luồng benchmark dùng tài khoản này)
COPY docker/mysql/01-demo-user.sql /docker-entrypoint-initdb.d/01-demo-user.sql
COPY docker/mysql/entrypoint-wrapper.sh /usr/local/bin/entrypoint-wrapper.sh

RUN sed -i 's/\r$//' /usr/local/bin/entrypoint-wrapper.sh /etc/mysql/conf.d/transaction.cnf \
 && chmod 755 /usr/local/bin/entrypoint-wrapper.sh \
 && chmod 644 /etc/mysql/conf.d/transaction.cnf \
 && mkdir -p /var/log/mysql && chown mysql:mysql /var/log/mysql

ENTRYPOINT ["entrypoint-wrapper.sh"]
CMD ["mysqld"]

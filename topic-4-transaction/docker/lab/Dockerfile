ARG MONGO_VERSION=8.0.23

# Docker CLI: chỉ dùng cho C1-MySQL (docker kill / docker start tx-mysql qua /var/run/docker.sock)
FROM docker:27-cli AS dockercli

FROM mongo:${MONGO_VERSION}

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONIOENCODING=utf-8 \
    LANG=C.UTF-8

# python3 chạy bộ test, mysql-client để nạp lại schema (MYSQL_CLI), procps cho pgrep (C1-MongoDB)
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv mysql-client procps ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker

COPY requirements.txt /tmp/requirements.txt
RUN python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt
ENV PATH=/opt/venv/bin:$PATH

COPY docker/lab/lab-entrypoint.sh /usr/local/bin/lab-entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/lab-entrypoint.sh && chmod 755 /usr/local/bin/lab-entrypoint.sh

WORKDIR /app
ENTRYPOINT ["lab-entrypoint.sh"]
CMD ["sleep", "infinity"]

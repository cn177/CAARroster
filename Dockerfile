FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ARA_DATA_DIR=/data \
    TZ=Asia/Shanghai

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x /app/docker-entrypoint.sh && mkdir -p /data

VOLUME ["/data"]
EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
# SQLite 用单进程 + 多线程最省心：没有跨进程锁竞争，300 人规模的读写绰绰有余。
CMD ["gunicorn", "-w", "1", "-k", "gthread", "--threads", "8", \
     "-b", "0.0.0.0:8000", "--access-logfile", "-", "--error-logfile", "-", "app:app"]

#!/bin/sh
# 容器启动脚本：先建表，再按环境变量确保有一个管理账号，最后交给 gunicorn。
set -e

python app.py --init-db

if [ -n "$ARA_ADMIN_PASSWORD" ]; then
  python app.py --create-admin "${ARA_ADMIN_USER:-admin}" "$ARA_ADMIN_PASSWORD"
elif ! python app.py --check-admin; then
  echo ""
  echo "============================================================"
  echo "  还没有任何管理账号，服务启动了也没人能登录。"
  echo "  在宿主机上执行这一条建账号："
  echo ""
  echo "    docker compose exec app python app.py --create-admin admin 你的强密码"
  echo ""
  echo "  或者删掉 docker-compose.yml 里 ARA_ADMIN_PASSWORD 前面的 # 填上密码，"
  echo "  再 docker compose up -d 重启一次。"
  echo "============================================================"
  echo ""
fi

exec "$@"

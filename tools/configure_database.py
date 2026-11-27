"""Create new isolated databases interactively; never overwrite existing credentials."""

from getpass import getpass
from pathlib import Path
import secrets

import psycopg
from psycopg import sql


def main():
    root = Path(__file__).resolve().parents[1]
    destination = root / ".env"
    if destination.exists():
        raise SystemExit(".env已存在，拒绝覆盖。请自行审查现有配置。")
    host = input("PostgreSQL主机 [127.0.0.1]：").strip() or "127.0.0.1"
    port = int(input("端口 [5432]：").strip() or "5432")
    admin = input("初始化管理员 [postgres]：").strip() or "postgres"
    password = getpass("数据库管理员密码（不回显）：")
    application_password = secrets.token_urlsafe(30)
    with psycopg.connect(host=host, port=port, user=admin, password=password,
                         dbname="postgres", autocommit=True) as conn:
        existing_role = conn.execute("SELECT 1 FROM pg_roles WHERE rolname='campus_app'").fetchone()
        existing_db = conn.execute("SELECT 1 FROM pg_database WHERE datname IN "
                                   "('campus_market','campus_market_test')").fetchone()
        if existing_role or existing_db:
            raise SystemExit("目标角色或数据库已存在，未覆盖；请检查是否已配置本项目。")
        conn.execute(sql.SQL("CREATE ROLE campus_app LOGIN PASSWORD {}").format(sql.Literal(application_password)))
        for name in ("campus_market", "campus_market_test"):
            conn.execute(sql.SQL("CREATE DATABASE {} OWNER campus_app").format(sql.Identifier(name)))
    prefix = f"postgresql+psycopg://campus_app:{application_password}@{host}:{port}/"
    settings = (f"DATABASE_URL={prefix}campus_market\nTEST_DATABASE_URL={prefix}campus_market_test\n"
                f"APP_SECRET={secrets.token_urlsafe(48)}\nASSET_DIR=var/images\nCOOKIE_SECURE=false\n")
    with destination.open("x", encoding="utf-8") as stream:
        stream.write(settings)
    print("已创建独立开发/测试数据库并写入.env；凭据未打印。接下来执行 campus-market init。")


if __name__ == "__main__":
    main()

"""Reproducible local entry points for initialization, demo data, and web startup."""

import argparse
from getpass import getpass
import json
from pathlib import Path
import subprocess

from alembic import command
from alembic.config import Config
from sqlalchemy import select

from campus_market.auth import AuthService
from campus_market.config import Settings
from campus_market.db import Database
from campus_market.models import User
from campus_market.seed import seed_demo


def migrate():
    """Run forward-only, versioned migrations from the project directory."""
    path = Path.cwd() / "alembic.ini"
    if not path.is_file():
        raise SystemExit("请在包含alembic.ini的项目根目录运行初始化")
    command.upgrade(Config(str(path)), "head")
    print("数据库迁移已完成；已有业务数据保持不变。")


def create_admin(database):
    """Administrators are created through trusted console input, never public HTTP."""
    username = input("管理员用户名：").strip().lower()
    with database.sessions() as session:
        existing = session.scalar(select(User).where(User.username == username))
        if existing:
            print("账号已存在，未修改其密码或角色。")
            return
    password = getpass("管理员密码（8～64字符，不回显）：")
    if password != getpass("再次输入密码："):
        raise SystemExit("两次密码不一致，未创建账号。")
    user = AuthService(database).register(username, password, role="ADMIN")
    print(f"已创建管理员：{user['username']}")


def postgres_action(action: str):
    """Start/stop only the dedicated cluster, without changing Windows services."""
    binary = Path("D:/PostgreSQL/17/bin/pg_ctl.exe")
    cluster = Path("D:/PostgreSQL/data/campus-market")
    if not binary.is_file() or not (cluster / "PG_VERSION").is_file():
        raise SystemExit("本机未找到计划中的PostgreSQL目录，请参照README准备数据库")
    arguments = [str(binary), "-D", str(cluster), "-w"]
    if action == "start":
        status = subprocess.run([str(binary), "-D", str(cluster), "status"],
                                capture_output=True, check=False)
        if status.returncode == 0:
            print("PostgreSQL已在运行。")
            return
        arguments += ["-l", str(cluster / "server.log"), "start"]
    else:
        arguments += ["-m", "fast", "stop"]
    subprocess.run(arguments, check=True)


def main():
    """CLI is installed as campus-market by editable and wheel installations."""
    parser = argparse.ArgumentParser(description="校园二手交易系统开发与运行工具")
    parser.add_argument("action", choices=("init", "admin", "seed", "serve", "db-start", "db-stop"))
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.action.startswith("db-"):
        postgres_action(args.action[3:])
        return
    settings = Settings.from_env()
    if args.action == "init":
        migrate()
        return
    if args.action == "serve":
        import uvicorn  # pylint: disable=import-outside-toplevel
        uvicorn.run("campus_market.web:create_app", factory=True, host="127.0.0.1", port=args.port)
        return
    database = Database(settings)
    try:
        if args.action == "admin":
            create_admin(database)
        elif args.action == "seed":
            print(json.dumps(seed_demo(database, settings), ensure_ascii=False, default=str, indent=2))
    finally:
        database.close()


if __name__ == "__main__":
    main()

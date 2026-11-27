"""Build, install, and start the wheel outside the source checkout's import path."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx

from campus_market.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def main():
    settings = Settings.from_env()
    subprocess.run(["uv", "build"], cwd=ROOT, check=True)
    environment = ROOT / "var" / "wheel-check"
    if not environment.exists():
        subprocess.run(["uv", "venv", str(environment), "--python", sys.executable], check=True)
    interpreter = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    wheel = ROOT / "dist" / "campus_market-1.0.0-py3-none-any.whl"
    requirements = ROOT / "var" / "runtime-requirements.txt"
    subprocess.run(["uv", "export", "--frozen", "--no-dev", "--no-emit-project", "--no-hashes",
                    "--output-file", str(requirements)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["uv", "pip", "install", "--reinstall-package", "campus-market",
                    "--python", str(interpreter), "-r", str(requirements), str(wheel)], check=True)
    work = environment / "run"
    work.mkdir(exist_ok=True)
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", 8002)) != 0
    env = {**os.environ, "DATABASE_URL": settings.database_url, "APP_SECRET": settings.secret,
           "ASSET_DIR": str(settings.asset_dir), "PYTHONUTF8": "1"}
    log = (ROOT / "artifacts" / "wheel-server.log").open("w", encoding="utf-8")
    process = subprocess.Popen([str(interpreter), "-m", "uvicorn", "campus_market.web:create_app",
        "--factory", "--port", "8002"], cwd=work, env=env, stdout=log, stderr=log,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            assert process.poll() is None, "Installed wheel server exited; inspect wheel-server.log"
            try:
                if httpx.get("http://127.0.0.1:8002/health", timeout=1).status_code == 200:
                    break
            except httpx.TransportError:
                pass
            time.sleep(0.1)
        checks = []
        for path in ("/health", "/market", "/static/app.css", "/static/app.js", "/api/products"):
            response = httpx.get("http://127.0.0.1:8002" + path, timeout=5)
            checks.append({"path": path, "status": response.status_code, "bytes": len(response.content)})
            assert response.status_code == 200
        result = {"passed": True, "wheel": wheel.name, "isolated_installation": True,
                  "checks": checks, "note": "服务从独立wheel虚拟环境启动，工作目录不含源码。"}
        (ROOT / "artifacts" / "wheel-results.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        import signal
        process.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGINT)
        process.wait(timeout=20)
        log.close()


if __name__ == "__main__":
    main()

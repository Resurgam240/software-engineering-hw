"""Package an explicit allowlist; secrets, environments, databases and caches never enter ZIP."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT.parent


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def copy_tree(source, destination):
    for path in source.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=LAB / "实验报告LaTeX工作区/report/main.pdf")
    parser.add_argument("--name", required=True, help="课程要求的提交目录名，仅通过本地命令提供")
    parser.add_argument("--uml-directory", type=Path, required=True, help="最终UML目录")
    args = parser.parse_args()
    name = args.name
    if not name or Path(name).name != name or any(char in name for char in '/\\:') or name in ('.', '..'):
        raise ValueError("Submission name must be a single directory name")
    destination = LAB / name
    destination.mkdir(exist_ok=True)
    known = {"实验报告.pdf", "UML", "code"}
    unexpected = {item.name for item in destination.iterdir()} - known
    if unexpected:
        raise RuntimeError(f"Existing destination contains unknown files: {unexpected}")
    # Refresh only our generated output tree; paths are fixed inside the named submission directory.
    for folder in ("code", "UML"):
        target = destination / folder
        assert target.resolve().parent == destination.resolve() and target.name in ("code", "UML")
        if target.exists():
            shutil.rmtree(target)
        target.mkdir()
    code = destination / "code"
    for filename in ("pyproject.toml", "uv.lock", ".env.example", ".gitignore", "alembic.ini", "README.md"):
        shutil.copy2(ROOT / filename, code / filename)
    for folder in ("src", "migrations", "tests", "tools"):
        copy_tree(ROOT / folder, code / folder)
    for path in (ROOT / "artifacts").iterdir():
        if path.suffix in (".json", ".xml") or path.name == "pylint.txt":
            target = code / "artifacts" / path.name
            target.parent.mkdir(exist_ok=True)
            shutil.copy2(path, target)
    copy_tree(ROOT / "artifacts/screenshots", code / "artifacts/screenshots")
    source_uml = args.uml_directory.resolve()
    for diagram in ("UML类图", "UML组件图", "UML用例图", "UML时序图"):
        for extension in (".png", ".puml"):
            source = source_uml / (diagram + extension)
            assert source.is_file()
            shutil.copy2(source, destination / "UML" / source.name)
    assert args.report.read_bytes().startswith(b"%PDF-")
    shutil.copy2(args.report, destination / "实验报告.pdf")
    files = sorted(path for path in destination.rglob("*") if path.is_file())
    local_secrets = []
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("APP_SECRET="):
            local_secrets.append(line.partition("=")[2].encode())
        if line.startswith("DATABASE_URL="):
            from sqlalchemy.engine import make_url
            local_secrets.append(make_url(line.partition("=")[2]).password.encode())
    for path in files:
        assert path.name not in (".env", "postgres-admin.local")
        assert not any(part in (".venv", ".git", "var", "__pycache__") for part in path.relative_to(destination).parts)
        content = path.read_bytes()
        assert all(secret not in content for secret in local_secrets), f"Local secret in {path}"
    archive = LAB / (name + ".zip")
    with ZipFile(archive, "w", ZIP_DEFLATED) as output:
        for path in files:
            output.write(path, path.relative_to(LAB).as_posix())
    with ZipFile(archive) as output:
        assert output.testzip() is None
        assert all(entry.startswith(name + "/") for entry in output.namelist())
        for path in files:
            assert output.read(path.relative_to(LAB).as_posix()) == path.read_bytes()
    result = {"name": name, "files": len(files), "zip_bytes": archive.stat().st_size,
              "sha256": digest(archive), "report_sha256": digest(destination / "实验报告.pdf"),
              "uml_pairs": 4, "secrets_excluded": True, "zip_crc_and_bytes_verified": True,
              "status": "待本人重写报告、审阅代码及上传GitHub；不是已完成所有人工要求的最终提交"}
    (LAB / "交付校验.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

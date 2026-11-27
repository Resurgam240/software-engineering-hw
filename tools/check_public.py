"""Check tracked files and reachable history before publishing a repository.

Optional private terms are loaded from a local file outside the public repository.
Findings report file locations and categories, never the matched private values.
"""

import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PATH_PATTERN = re.compile(rb"(?:[A-Z]:[/\\](?:Users|[^\r\n]*?[/\\]lab3)|file:///[A-Z]:/)", re.I)
HOST_PATTERN = re.compile(rb'hostname="[^"]+"')


def git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=ROOT)


def forbidden_path(name):
    parts = Path(name).parts
    return (name.startswith("docs/") or any(part in (".venv", "var", "__pycache__") for part in parts)
            or Path(name).name == ".env"
            or (name.startswith("artifacts/") and name.endswith((".txt", ".log"))
                and name != "artifacts/pylint.txt"))


def inspect_content(content, location, terms, findings):
    if PATH_PATTERN.search(content):
        findings.append({"location": location, "category": "local_absolute_path"})
    if HOST_PATTERN.search(content):
        findings.append({"location": location, "category": "machine_hostname"})
    if any(term in content for term in terms):
        findings.append({"location": location, "category": "private_term"})


def inspect_history(terms, findings):
    names = {}
    for line in git("rev-list", "--objects", "--all").splitlines():
        oid, _, name = line.partition(b" ")
        names[oid] = name.decode("utf-8", errors="replace")
    process = subprocess.Popen(["git", "cat-file", "--batch"], cwd=ROOT,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    output, _ = process.communicate(b"\n".join(names) + b"\n")
    position = 0
    while position < len(output):
        end = output.index(b"\n", position)
        oid, kind, size = output[position:end].split()
        size = int(size)
        content = output[end + 1:end + 1 + size]
        position = end + 2 + size
        if kind == b"blob":
            name = names[oid]
            location = "history:" + oid[:10].decode() + ":" + name
            if forbidden_path(name):
                findings.append({"location": location, "category": "excluded_path"})
            inspect_content(content, location, terms, findings)
        elif kind == b"commit":
            inspect_content(content, "commit:" + oid[:10].decode(), terms, findings)
    if process.returncode:
        raise RuntimeError("Could not inspect Git history")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-terms", type=Path, help="Local UTF-8 file: one forbidden private value per line")
    parser.add_argument("--history", action="store_true", help="Also inspect every reachable Git object")
    args = parser.parse_args()
    terms = []
    if args.private_terms:
        terms = [line.encode() for line in args.private_terms.read_text(encoding="utf-8").splitlines() if line]
    findings = []
    count = 0
    for raw in git("ls-files", "-z").split(b"\0"):
        if not raw:
            continue
        name = raw.decode("utf-8")
        path = ROOT / name
        if not path.is_file():
            continue
        count += 1
        if forbidden_path(name):
            findings.append({"location": name, "category": "excluded_path"})
        inspect_content(path.read_bytes(), name, terms, findings)
    if args.history:
        inspect_history(terms, findings)
    print(json.dumps({"passed": not findings, "tracked_files": count,
                      "history_checked": args.history, "findings": findings}, ensure_ascii=False, indent=2))
    raise SystemExit(bool(findings))


if __name__ == "__main__":
    main()

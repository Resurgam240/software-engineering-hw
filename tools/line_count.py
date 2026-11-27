"""Count production Python lines excluding blanks, comments, and docstrings."""

import ast
import io
import json
from pathlib import Path
import tokenize

ROOT = Path(__file__).resolve().parents[1]


def count_file(path):
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    docstrings = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                docstrings.update(range(first.lineno, first.end_lineno + 1))
    code_lines = set()
    excluded = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.ENCODING,
                tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER}
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type not in excluded:
            code_lines.update(range(token.start[0], token.end[0] + 1))
    effective = [number for number in code_lines if number not in docstrings and lines[number - 1].strip()]
    return {"file": path.relative_to(ROOT).as_posix(), "physical": len(lines), "effective": len(effective)}


def main():
    files = [count_file(path) for path in sorted((ROOT / "src/campus_market").rglob("*.py"))]
    result = {"method": "token-bearing physical Python lines, excluding blanks, comments and docstrings",
              "scope": "src/campus_market/*.py only; no tests, migrations, tools, HTML/CSS/JS, dependencies",
              "files": files, "physical": sum(item["physical"] for item in files),
              "effective": sum(item["effective"] for item in files)}
    result["over_1500"] = result["effective"] > 1500
    (ROOT / "artifacts" / "line-count.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    assert result["over_1500"], "Production Python code does not exceed the course threshold"


if __name__ == "__main__":
    main()

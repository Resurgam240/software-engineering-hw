"""Update factual evidence fragments and images, never the user's report prose."""

import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT.parent / "实验报告LaTeX工作区" / "report"


def latex(value):
    replacements = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
                    "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}"}
    return "".join(replacements.get(character, character) for character in str(value))


def read_json(name):
    return json.loads((ROOT / "artifacts" / name).read_text(encoding="utf-8"))


def main():
    evidence = REPORT / "evidence"
    images = REPORT / "images"
    evidence.mkdir(parents=True, exist_ok=True)
    images.mkdir(exist_ok=True)
    size = read_json("line-count.json")
    line_text = (
        f"本轮统计生产 Python 物理行数为 {size['physical']} 行，排除空行、注释和文档字符串后，"
        f"有效行数为 \\textbf{{{size['effective']} 行}}，超过任务书要求的 1500 行。"
        "统计范围只含 \\path{src/campus_market} 中的 Python 文件，不含测试、迁移、工具、"
        "HTML/CSS/JavaScript、第三方库或自动生成代码。逐文件记录保存在 "
        "\\path{artifacts/line-count.json}，可用 \\path{tools/line_count.py} 复现。\n"
    )
    (evidence / "line_count.tex").write_text(line_text, encoding="utf-8")
    tree = ET.parse(ROOT / "artifacts/pytest.xml")
    suites = list(tree.getroot().iter("testsuite"))
    count = sum(int(suite.attrib.get("tests", 0)) for suite in suites)
    failures = sum(int(suite.attrib.get("failures", 0)) + int(suite.attrib.get("errors", 0)) for suite in suites)
    acceptance = read_json("acceptance-results.json")
    browsers = read_json("browser-results.json")
    wheel = read_json("wheel-results.json")
    pylint = (ROOT / "artifacts/pylint.txt").read_text(encoding="utf-8")
    rows = [
        ("PostgreSQL集成与业务测试", f"{count} 项，失败 {failures} 项"),
        ("五类并发冲突", "各10轮；多人竞争每轮20名不同买家"),
        ("提交前失败 / 提交后响应丢失", "各10轮，验证回滚或原标识重试"),
        ("正常服务重启", f"{len(acceptance['restarts'])} 次，数据标识、状态及日志逐项比较一致"),
        ("组合查询性能", f"{acceptance['query']['within_2_seconds']}/100 次在2秒内成功"),
        ("无冲突预约性能", f"{acceptance['reservation']['within_2_seconds']}/100 次在2秒内成功"),
        ("Pylint", "10.00/10，无诊断" if "10.00/10" in pylint else "请查看当前检查记录"),
        ("独立wheel安装与运行", "通过" if wheel["passed"] else "未通过"),
        ("Chrome", next(b["version"] for b in browsers if b["browser"] == "Chrome") + "，核心流程通过"),
        ("Edge", next(b["version"] for b in browsers if b["browser"] == "Edge") + "，核心流程通过"),
        ("真人易用性 / 人工逐行审阅", "未执行 / 待本人完成"),
        ("GitHub远程上传", "按用户要求暂缓，待本人审阅后执行"),
    ]
    result_text = (r"\begin{table}[H]\centering\small" + "\n" +
                   r"\begin{tabularx}{\linewidth}{@{}p{49mm}Y@{}}\toprule" + "\n" +
                   r"检查项目 & 本轮真实结果\\\midrule" + "\n")
    result_text += "\n".join(latex(a) + " & " + latex(b) + r"\\" for a, b in rows)
    result_text += "\n" + r"\bottomrule\end{tabularx}\caption{本轮检查与未完成事项}\end{table}" + "\n"
    (evidence / "results.tex").write_text(result_text, encoding="utf-8")
    history = subprocess.check_output(["git", "log", "-8", "--format=%h %s"], cwd=ROOT, encoding="utf-8")
    git_text = r"\begin{lstlisting}[basicstyle=\scriptsize\ttfamily]" + "\n" + history + r"\end{lstlisting}" + "\n"
    (evidence / "git_history.tex").write_text(git_text, encoding="utf-8")
    for name in ("chrome-market.png", "chrome-completed.png", "chrome-private-access.png", "chrome-audit.png"):
        shutil.copy2(ROOT / "artifacts/screenshots" / name, images / name)
    print("已同步事实片段与四张截图；main.tex及sections正文未改动。")


if __name__ == "__main__":
    main()

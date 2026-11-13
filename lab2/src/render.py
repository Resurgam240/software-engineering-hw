"""Render the four final PlantUML diagrams and seven diagrams.net UI pages.

Run from any directory. Uses only Python's standard library; requires Java and
the official tools documented in ../tools/README.md. No network calls are made.
"""
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
UI_SOURCE = ROOT / 'src/ui'


def run(command):
    result = subprocess.run(
        [str(value) for value in command], capture_output=True,
        encoding='utf-8', errors='replace', timeout=120,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
    )
    if result.returncode:
        raise RuntimeError(f'Export failed ({result.returncode}):\n{result.stdout}\n{result.stderr}')


def render_uml(output, jar, java):
    sources = sorted((ROOT / 'UML').glob('*.puml'))
    if len(sources) != 4:
        raise ValueError('UML must contain exactly four final .puml sources.')
    if not jar.is_file():
        raise FileNotFoundError(f'PlantUML not found: {jar}; see tools/README.md')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='lab2-uml-') as temporary:
        for source in sources:
            run([java, '-Dfile.encoding=UTF-8', '-jar', jar, '-failfast2', '-charset',
                 'UTF-8', '-tpng', '-o', temporary, source])
            rendered = Path(temporary) / source.with_suffix('.png').name
            if not rendered.is_file():
                raise RuntimeError(f'PlantUML produced no image for {source.name}')
            shutil.copy2(rendered, output / rendered.name)
            print(f'UML: {rendered.name}', flush=True)


def render_ui(output, drawio):
    if not drawio.is_file():
        raise FileNotFoundError(f'diagrams.net not found: {drawio}; see tools/README.md')
    pages = json.loads((UI_SOURCE / 'manifest.json').read_text(encoding='utf-8'))
    if [page['name'] for page in pages] != [f'界面{i}' for i in range(1, 8)]:
        raise ValueError('UI manifest must name exactly 界面1 through 界面7 in order.')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='lab2-ui-') as temporary:
        for index, page in enumerate(pages, 1):
            rendered = Path(temporary) / (page['name'] + '.png')
            run([drawio, '--export', '--disable-update', '--format', 'png', '--theme',
                 'light', '--scale', '2', '--border', '0', '--page-index', index,
                 '--output', rendered, UI_SOURCE / '校园二手交易系统.drawio'])
            if not rendered.is_file():
                raise RuntimeError(f'diagrams.net produced no image for {page["name"]}')
            shutil.copy2(rendered, output / rendered.name)
            print(f'UI: {rendered.name}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind', choices=['all', 'uml', 'ui'], default='all')
    parser.add_argument('--output', type=Path, default=ROOT,
                        help='Output root containing UML/ and UI界面/ (default: lab2).')
    parser.add_argument('--plantuml', type=Path, default=ROOT / 'tools/plantuml.jar')
    parser.add_argument('--drawio', type=Path, default=ROOT / 'tools/drawio/draw.io.exe')
    parser.add_argument('--java', default='java')
    args = parser.parse_args()
    output = args.output.resolve()
    if args.kind in ('all', 'uml'):
        render_uml(output / 'UML', args.plantuml.resolve(), args.java)
    if args.kind in ('all', 'ui'):
        render_ui(output / 'UI界面', args.drawio.resolve())

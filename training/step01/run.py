"""Sketch Viewer のエントリーポイント。

    py run.py ../../samples/basic     Page の一覧をコンソールへ出力
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# src/ 以下のパッケージを import できるようにする
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from sketch_viewer import SketchError, load_document  # noqa: E402


def dump(path: str) -> int:
    """Page の一覧をコンソールへ出力する。戻り値は終了コード。"""
    try:
        document = load_document(path)
    except SketchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    for page in document.pages:
        print(f"Page: {page.name}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Sketch Viewer")
    parser.add_argument("path", help=".sketch ファイルまたは展開済みディレクトリ")
    args = parser.parse_args()
    return dump(args.path)


if __name__ == "__main__":
    sys.exit(main())

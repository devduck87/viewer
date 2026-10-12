"""Sketch Viewer のエントリーポイント。

    py run.py                         GUI を起動
    py run.py example.sketch          ファイルを開いた状態で GUI を起動
    py run.py samples/basic --dump    GUI を使わず Layer 階層をコンソールへ出力
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from sketch_viewer import SketchError, format_tree, load_document  # noqa: E402


def dump(path: str) -> int:
    try:
        document = load_document(path)
    except SketchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(format_tree(document))
    for warning in document.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    unsupported = document.unsupported_layer_counts()
    if unsupported:
        detail = ", ".join(f"{t} x{n}" for t, n in sorted(unsupported.items()))
        print(f"\n未対応 Layer: {detail}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Sketch Viewer")
    parser.add_argument("path", nargs="?", help=".sketch ファイルまたは展開済みディレクトリ")
    parser.add_argument("--dump", action="store_true", help="Layer 階層をコンソールへ出力する")
    args = parser.parse_args()

    if args.dump:
        if not args.path:
            parser.error("--dump にはパスの指定が必要です")
        return dump(args.path)

    from sketch_viewer.gui import main as gui_main

    gui_main(args.path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

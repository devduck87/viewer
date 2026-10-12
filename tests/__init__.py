import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = ROOT / "samples" / "basic"
# Sketch 公式 sketch-reference-files (展開済み)
REFERENCE_DIR = ROOT / "samples" / "reference" / "expanded"

sys.path.insert(0, str(ROOT / "src"))


def make_sketch_zip(source_dir: Path, dest: Path) -> Path:
    """展開済み Sketch ディレクトリを .sketch (ZIP) にまとめる。"""
    with zipfile.ZipFile(dest, "w") as zf:
        for file in source_dir.rglob("*"):
            if file.is_file():
                zf.write(file, file.relative_to(source_dir).as_posix())
    return dest

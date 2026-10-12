"""Sketch データへのアクセスを担当する Reader。

Parser / Renderer は ZIP やファイルシステムを直接操作せず、
SketchReader のインターフェースだけを利用する。
"""

from __future__ import annotations

import json
import zipfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .errors import (
    InvalidJSONError,
    InvalidSketchFileError,
    MissingEntryError,
    SketchFileNotFoundError,
)


class SketchReader(ABC):
    """Sketch 内部ファイルへのアクセス方法を抽象化する基底クラス。

    内部パスは常に ``pages/XXXX.json`` のような "/" 区切りの相対パスで指定する。
    """

    def __init__(self, source: Path) -> None:
        self.source = source

    @abstractmethod
    def exists(self, name: str) -> bool:
        """内部ファイルが存在するかを返す。"""

    @abstractmethod
    def read_bytes(self, name: str) -> bytes:
        """内部ファイルをバイト列で返す。存在しなければ MissingEntryError。"""

    def read_json(self, name: str) -> Any:
        """内部ファイルを JSON として読み込む。"""
        data = self.read_bytes(name)
        try:
            return json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidJSONError(f"{name}: JSON として読み込めません ({exc})") from exc

    def read_image(self, name: str) -> bytes:
        """images/ 以下などの画像データを返す。"""
        return self.read_bytes(name)

    def close(self) -> None:
        """保持しているリソースを解放する。"""

    def __enter__(self) -> SketchReader:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


class ZipSketchReader(SketchReader):
    """``.sketch`` (ZIP アーカイブ) から読み込む Reader。"""

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        try:
            self._zip = zipfile.ZipFile(path)
        except (zipfile.BadZipFile, OSError) as exc:
            raise InvalidSketchFileError(f"{path}: ZIP として読み込めません ({exc})") from exc
        self._names = set(self._zip.namelist())

    def exists(self, name: str) -> bool:
        return name in self._names

    def read_bytes(self, name: str) -> bytes:
        if name not in self._names:
            raise MissingEntryError(f"{self.source}: {name} が存在しません")
        return self._zip.read(name)

    def close(self) -> None:
        self._zip.close()


class DirectorySketchReader(SketchReader):
    """展開済み Sketch データ (ディレクトリ) から読み込む Reader。開発・テスト用。"""

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self._root = path.resolve()

    def _resolve(self, name: str) -> Path | None:
        target = (self._root / name).resolve()
        # ルート外 ("../" など) へのアクセスは存在しないものとして扱う
        if not target.is_relative_to(self._root):
            return None
        return target

    def exists(self, name: str) -> bool:
        target = self._resolve(name)
        return target is not None and target.is_file()

    def read_bytes(self, name: str) -> bytes:
        target = self._resolve(name)
        if target is None or not target.is_file():
            raise MissingEntryError(f"{self.source}: {name} が存在しません")
        return target.read_bytes()


def open_reader(path: str | Path) -> SketchReader:
    """パスの種類に応じて適切な Reader を返す。

    ディレクトリなら DirectorySketchReader、それ以外は ZipSketchReader。
    """
    path = Path(path)
    if not path.exists():
        raise SketchFileNotFoundError(f"{path}: ファイルが存在しません")
    if path.is_dir():
        return DirectorySketchReader(path)
    return ZipSketchReader(path)

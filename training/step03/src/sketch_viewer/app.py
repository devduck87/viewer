"""Sketch Viewer のメインウィンドウ。

画面構成:
    左     Layer Tree
    右     Canvas (Step 4 で描画結果を表示する)
    下部   ステータスバー

各部品 (LayerTree など) は互いを直接参照せず、
このクラスがイベントを受け取って部品どうしをつなぐ。
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .errors import SketchError
from .layer_tree import LayerTree
from .model import SketchDocument, SketchLayer, SketchPage
from .parser import load_document

APP_TITLE = "Sketch Viewer"
CANVAS_BACKGROUND = "#c8c8c8"


class SketchViewerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.document: SketchDocument | None = None
        self.current_page: SketchPage | None = None
        self.selected_layer: SketchLayer | None = None

        root.title(APP_TITLE)
        root.geometry("1200x760")
        self._build_menu()
        self._bind_shortcuts()
        self._build_status_bar()
        self._build_panes()

    # ---- 画面の構築 ---------------------------------------------------------

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Open...", accelerator="Ctrl+O", command=self._on_open)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.destroy)
        menubar.add_cascade(label="File", menu=file_menu)

        self.root.config(menu=menubar)

    def _bind_shortcuts(self) -> None:
        self.root.bind_all("<Control-o>", lambda _e: self._on_open())

    def _build_status_bar(self) -> None:
        self.status = tk.StringVar(value="File > Open... で .sketch ファイルを開いてください")
        ttk.Label(self.root, textvariable=self.status, anchor="w", padding=(6, 2)).pack(
            side=tk.BOTTOM, fill=tk.X,
        )

    def _build_panes(self) -> None:
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        self.layer_tree = LayerTree(paned, on_select=self._on_tree_select)
        paned.add(self.layer_tree, weight=1)

        paned.add(self._build_canvas(paned), weight=4)

    def _build_canvas(self, parent: tk.Misc) -> ttk.Frame:
        frame = ttk.Frame(parent)
        self.canvas = tk.Canvas(frame, background=CANVAS_BACKGROUND, highlightthickness=0)
        xscroll = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        yscroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=xscroll.set, yscrollcommand=yscroll.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return frame

    # ---- ファイルを開く -----------------------------------------------------

    def _on_open(self) -> None:
        path = filedialog.askopenfilename(
            title="Sketch ファイルを開く",
            filetypes=[("Sketch files", "*.sketch"), ("All files", "*.*")],
        )
        if path:
            self.open_path(path)

    def open_path(self, path: str | Path) -> None:
        try:
            document = load_document(path)
        except SketchError as exc:
            messagebox.showerror(APP_TITLE, f"ファイルを開けませんでした。\n\n{exc}")
            return

        self.document = document
        self.current_page = document.pages[0] if document.pages else None
        self.selected_layer = None
        self.root.title(f"{Path(path).name} - {APP_TITLE}")
        self.layer_tree.load(document)
        self._update_status()

    # ---- 選択 ---------------------------------------------------------------

    def _on_tree_select(self, page: SketchPage, layer: SketchLayer | None) -> None:
        self.current_page = page
        self.selected_layer = layer
        # 描画は Step 4 で実装する。ここでは選択した項目をステータスバーに表示する
        selected = f"{layer.type}: {layer.name}" if layer is not None else "(Page)"
        self.status.set(f"選択: {page.name} / {selected}")

    # ---- ステータスバー -----------------------------------------------------

    def _update_status(self) -> None:
        if self.document is None:
            return
        parts = [f"{len(self.document.pages)} pages"]
        unsupported = self.document.unsupported_layer_counts()
        if unsupported:
            detail = ", ".join(f"{t} x{n}" for t, n in sorted(unsupported.items()))
            parts.append(f"未対応 Layer: {detail}")
        if self.document.warnings:
            parts.append(f"警告 {len(self.document.warnings)} 件")
        self.status.set("  |  ".join(parts))


def main(path: str | Path | None = None) -> None:
    root = tk.Tk()
    app = SketchViewerApp(root)
    if path is not None:
        root.after_idle(app.open_path, path)
    root.mainloop()

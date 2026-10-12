"""Tkinter による GUI。

左ペインに Page / Layer 階層 (ttk.Treeview)、右ペインに描画結果 (tk.Canvas) を表示する。
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .errors import SketchError
from .model import SketchDocument, SketchLayer, SketchPage
from .parser import load_document
from .renderer import CanvasRenderer

APP_TITLE = "Sketch Viewer"


class SketchViewerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.document: SketchDocument | None = None
        self.current_page: SketchPage | None = None
        # Treeview の item id -> (Page, Layer または None)
        self._tree_items: dict[str, tuple[SketchPage, SketchLayer | None]] = {}

        root.title(APP_TITLE)
        root.geometry("1100x700")
        self._build_menu()
        self._build_body()

    # ---- 画面構築 -------------------------------------------------------

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Open...", accelerator="Ctrl+O", command=self._on_open)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.destroy)
        menubar.add_cascade(label="File", menu=file_menu)
        self.root.config(menu=menubar)
        self.root.bind_all("<Control-o>", lambda _e: self._on_open())

    def _build_body(self) -> None:
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # 左ペイン: Layer Tree
        tree_frame = ttk.Frame(paned)
        self.tree = ttk.Treeview(tree_frame, columns=("type",), selectmode="browse")
        self.tree.heading("#0", text="Name")
        self.tree.heading("type", text="Type")
        self.tree.column("#0", width=200)
        self.tree.column("type", width=90, stretch=False)
        tree_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        paned.add(tree_frame, weight=1)

        # 右ペイン: Canvas
        canvas_frame = ttk.Frame(paned)
        self.canvas = tk.Canvas(canvas_frame, background="#c8c8c8", highlightthickness=0)
        xscroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        yscroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=xscroll.set, yscrollcommand=yscroll.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)
        self.canvas.bind("<MouseWheel>", self._on_mouse_wheel)
        self.canvas.bind("<Shift-MouseWheel>", self._on_shift_mouse_wheel)
        paned.add(canvas_frame, weight=4)

        self.renderer = CanvasRenderer(self.canvas)

        self.status = tk.StringVar(value="File > Open... で .sketch ファイルを開いてください")
        ttk.Label(self.root, textvariable=self.status, anchor="w", padding=(6, 2)).pack(
            side=tk.BOTTOM, fill=tk.X,
        )

    # ---- ファイル操作 ---------------------------------------------------

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
        self.root.title(f"{Path(path).name} - {APP_TITLE}")
        self._populate_tree(document)
        if document.pages:
            self._show_page(document.pages[0])
        else:
            self.current_page = None
            self.canvas.delete("all")
        self._update_status()

    # ---- Layer Tree -----------------------------------------------------

    def _populate_tree(self, document: SketchDocument) -> None:
        self.tree.delete(*self.tree.get_children())
        self._tree_items.clear()
        for page in document.pages:
            page_item = self.tree.insert("", tk.END, text=page.name, values=("page",), open=True)
            self._tree_items[page_item] = (page, None)
            for layer in page.layers:
                self._insert_layer(page_item, page, layer)

    def _insert_layer(self, parent: str, page: SketchPage, layer: SketchLayer) -> None:
        text = layer.name if layer.visible else f"{layer.name} (hidden)"
        item = self.tree.insert(parent, tk.END, text=text, values=(layer.type,))
        self._tree_items[item] = (page, layer)
        for child in layer.children:
            self._insert_layer(item, page, child)

    def _on_tree_select(self, _event: object) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        page, layer = self._tree_items[selection[0]]
        if page is not self.current_page:
            self._show_page(page)
        self.renderer.highlight(layer)

    # ---- 描画 -----------------------------------------------------------

    def _show_page(self, page: SketchPage) -> None:
        self.current_page = page
        self.renderer.render(page)
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)

    def _on_mouse_wheel(self, event: tk.Event) -> None:
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def _on_shift_mouse_wheel(self, event: tk.Event) -> None:
        self.canvas.xview_scroll(-1 if event.delta > 0 else 1, "units")

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

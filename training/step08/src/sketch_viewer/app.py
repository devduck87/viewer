"""Sketch Viewer のメインウィンドウ。

画面構成:
    上部   ツールバー (表示する画面の切り替え・表示倍率)
    左     検索欄 / Layer Tree / プロパティ
    右     Canvas (描画結果)
    下部   ステータスバー

各部品 (LayerTree / PropertiesPanel / CanvasRenderer) は互いを直接参照せず、
このクラスがイベントを受け取って部品どうしをつなぐ。
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .errors import SketchError
from .geometry import bounding_frame
from .layer_tree import LayerTree
from .model import SketchDocument, SketchLayer, SketchPage
from .parser import load_document
from .properties import PropertiesPanel
from .renderer import CanvasRenderer
from .zoom import ZOOM_LEVELS, clamp_zoom, fit_zoom, format_zoom, next_zoom_level

APP_TITLE = "Sketch Viewer"
VIEW_ALL = "(全体)"
CANVAS_BACKGROUND = "#c8c8c8"
# 検索欄に入力してから絞り込むまでの待ち時間 (ミリ秒)
SEARCH_DELAY_MS = 200


class SketchViewerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.document: SketchDocument | None = None
        self.current_page: SketchPage | None = None
        self.view_root: SketchLayer | None = None  # 単独で表示している画面 (None なら Page 全体)
        self.selected_layer: SketchLayer | None = None
        self.zoom = 1.0
        # id(layer) -> Page 直下の祖先 Layer (その Layer が所属する画面)
        self._root_of: dict[int, SketchLayer] = {}
        # 「表示」の選択肢に対応する画面 (先頭の None は全体)
        self._view_choices: list[SketchLayer | None] = [None]
        self._search_job: str | None = None  # 検索の実行待ち (root.after の id)

        root.title(APP_TITLE)
        root.geometry("1200x760")
        self._build_menu()
        self._bind_shortcuts()
        self._build_toolbar()
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

        view_menu = tk.Menu(menubar, tearoff=False)
        view_menu.add_command(label="拡大", accelerator="Ctrl++", command=self._zoom_in)
        view_menu.add_command(label="縮小", accelerator="Ctrl+-", command=self._zoom_out)
        view_menu.add_command(label="100%", accelerator="Ctrl+0", command=self._zoom_reset)
        view_menu.add_command(label="全体を表示", accelerator="Ctrl+9", command=self._zoom_to_fit)
        menubar.add_cascade(label="View", menu=view_menu)

        self.root.config(menu=menubar)

    def _bind_shortcuts(self) -> None:
        self.root.bind_all("<Control-o>", lambda _e: self._on_open())
        self.root.bind_all("<Control-f>", lambda _e: self._focus_search())
        # "+" はキーボード配列によって Shift の有無やキー名が異なるため、複数登録する
        for key in ("plus", "equal", "semicolon", "KP_Add"):
            self.root.bind_all(f"<Control-{key}>", lambda _e: self._zoom_in())
        for key in ("minus", "KP_Subtract"):
            self.root.bind_all(f"<Control-{key}>", lambda _e: self._zoom_out())
        self.root.bind_all("<Control-0>", lambda _e: self._zoom_reset())
        self.root.bind_all("<Control-9>", lambda _e: self._zoom_to_fit())

    def _build_toolbar(self) -> None:
        toolbar = ttk.Frame(self.root, padding=(6, 4))
        toolbar.pack(side=tk.TOP, fill=tk.X)

        # 表示する画面の切り替え
        ttk.Label(toolbar, text="表示:").pack(side=tk.LEFT)
        self.view_combo = ttk.Combobox(toolbar, state="readonly", width=40, values=(VIEW_ALL,))
        self.view_combo.current(0)
        self.view_combo.pack(side=tk.LEFT, padx=(4, 0))
        self.view_combo.bind("<<ComboboxSelected>>", self._on_view_selected)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        # 表示倍率
        ttk.Label(toolbar, text="倍率:").pack(side=tk.LEFT)
        ttk.Button(toolbar, text="−", width=3, command=self._zoom_out).pack(side=tk.LEFT, padx=(4, 0))
        self.zoom_combo = ttk.Combobox(
            toolbar, state="readonly", width=6, values=[format_zoom(z) for z in ZOOM_LEVELS],
        )
        self.zoom_combo.set(format_zoom(self.zoom))
        self.zoom_combo.pack(side=tk.LEFT, padx=2)
        self.zoom_combo.bind("<<ComboboxSelected>>", self._on_zoom_selected)
        ttk.Button(toolbar, text="+", width=3, command=self._zoom_in).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="100%", width=6, command=self._zoom_reset).pack(
            side=tk.LEFT, padx=(4, 0),
        )
        ttk.Button(toolbar, text="全体を表示", command=self._zoom_to_fit).pack(side=tk.LEFT, padx=(4, 0))

    def _build_status_bar(self) -> None:
        self.status = tk.StringVar(value="File > Open... で .sketch ファイルを開いてください")
        ttk.Label(self.root, textvariable=self.status, anchor="w", padding=(6, 2)).pack(
            side=tk.BOTTOM, fill=tk.X,
        )

    def _build_panes(self) -> None:
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(paned)
        self._build_search_bar(left)
        self.properties = PropertiesPanel(left)
        self.properties.pack(side=tk.BOTTOM, fill=tk.X, pady=(4, 0))
        self.layer_tree = LayerTree(
            left,
            on_select=self._on_tree_select,
            on_activate=self._on_tree_activate,
            on_visibility_changed=self._on_visibility_changed,
        )
        self.layer_tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        paned.add(left, weight=1)

        paned.add(self._build_canvas(paned), weight=4)

    def _build_search_bar(self, parent: ttk.Frame) -> None:
        frame = ttk.Frame(parent, padding=(0, 0, 0, 4))
        frame.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(frame, text="検索:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_search_changed)
        self.search_entry = ttk.Entry(frame, textvariable=self.search_var)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        self.search_entry.bind("<Return>", lambda _e: self._goto_match(1))
        self.search_entry.bind("<Shift-Return>", lambda _e: self._goto_match(-1))
        self.search_entry.bind("<Escape>", lambda _e: self.search_var.set(""))
        self.search_count = tk.StringVar()
        ttk.Label(frame, textvariable=self.search_count, width=9, anchor="e").pack(side=tk.LEFT)

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

        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<MouseWheel>", self._on_mouse_wheel)
        self.canvas.bind("<Shift-MouseWheel>", self._on_shift_mouse_wheel)
        self.canvas.bind("<Control-MouseWheel>", self._on_ctrl_mouse_wheel)
        # 中ボタンのドラッグで表示位置を動かす
        self.canvas.bind("<ButtonPress-2>", lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind("<B2-Motion>", lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1))

        self.renderer = CanvasRenderer(self.canvas)
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
        self.selected_layer = None
        self._root_of = {
            id(layer): top
            for page in document.pages for top in page.layers for layer, _ in top.walk()
        }
        self.root.title(f"{Path(path).name} - {APP_TITLE}")
        self.layer_tree.load(document)
        self.search_count.set(self.layer_tree.match_summary())
        if document.pages:
            self._show_page(document.pages[0])
        else:
            self.current_page = None
            self.view_root = None
            self._update_view_combo()
            self.canvas.delete("all")
        self.properties.show(None, None)
        self._update_status()

    # ---- 選択 ---------------------------------------------------------------

    def _on_tree_select(self, page: SketchPage, layer: SketchLayer | None) -> None:
        self.selected_layer = layer
        if layer is None:
            # Page の項目を選んだら、その Page を表示する
            if page is not self.current_page:
                self._show_page(page)
            self.renderer.highlight(None)
            self.properties.show(page, None)
            return

        root = self._root_of[id(layer)]
        showing_other_artboard = self.view_root is not None and self.view_root is not root
        if page is not self.current_page or showing_other_artboard:
            # 1 画面だけを表示しているときは、選択した Layer の画面へ切り替える
            single_view = self.view_root is not None
            self._show_page(page, root if single_view and root.is_artboard else None)
        self.renderer.highlight(layer)
        self._scroll_to(layer)
        self.properties.show(page, layer)

    def _on_tree_activate(self, page: SketchPage, layer: SketchLayer | None) -> None:
        # 画面をダブルクリックしたら、その画面だけを表示する
        if layer is not None and layer.is_artboard and any(layer is top for top in page.layers):
            self._show_page(page, layer)

    def _on_canvas_click(self, event: tk.Event) -> None:
        if self.current_page is None:
            return
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        layer = self.renderer.layer_at(x, y)
        if self.layer_tree.select_layer(layer):
            return  # 以降は Tree の選択イベント (_on_tree_select) で処理する
        # 検索で Tree から除外されている Layer、または何もない場所をクリックした
        self.layer_tree.clear_selection()
        self.selected_layer = layer
        self.renderer.highlight(layer)
        self.properties.show(self.current_page, layer)

    # ---- 表示 / 非表示 ------------------------------------------------------

    def _on_visibility_changed(self, page: SketchPage) -> None:
        if page is self.current_page:
            self._render(keep_scroll=True)

    # ---- 検索 ---------------------------------------------------------------

    def _focus_search(self) -> None:
        self.search_entry.focus_set()
        self.search_entry.select_range(0, tk.END)

    def _on_search_changed(self, *_args: object) -> None:
        # 1 文字入力するたびに Tree を作り直すと重いため、入力が止まってから絞り込む
        if self._search_job is not None:
            self.root.after_cancel(self._search_job)
        self._search_job = self.root.after(SEARCH_DELAY_MS, self._apply_search)

    def _apply_search(self) -> None:
        self._search_job = None
        self.layer_tree.set_query(self.search_var.get().strip())
        self.layer_tree.select_layer(self.selected_layer)
        self.search_count.set(self.layer_tree.match_summary())

    def _goto_match(self, step: int) -> None:
        if self._search_job is not None:
            # 入力直後に Enter を押した場合は、先に絞り込む
            self.root.after_cancel(self._search_job)
            self._apply_search()
        self.layer_tree.goto_match(step)
        self.search_count.set(self.layer_tree.match_summary())

    # ---- 描画 ---------------------------------------------------------------

    def _show_page(self, page: SketchPage, view_root: SketchLayer | None = None) -> None:
        """Page を表示する。view_root を指定すると、その画面だけを表示する。"""
        self.current_page = page
        self.view_root = view_root
        self._update_view_combo()
        self._render()

    def _render(self, keep_scroll: bool = False) -> None:
        """現在の Page を描き直す。keep_scroll が False ならスクロール位置を左上に戻す。"""
        if self.current_page is None:
            return
        xview, yview = self.canvas.xview()[0], self.canvas.yview()[0]
        roots = [self.view_root] if self.view_root is not None else None
        self.renderer.render(self.current_page, roots, self.layer_tree.is_visible, self.zoom)
        self.renderer.highlight(self.selected_layer)
        self.canvas.xview_moveto(xview if keep_scroll else 0)
        self.canvas.yview_moveto(yview if keep_scroll else 0)

    def _scroll_to(self, layer: SketchLayer) -> None:
        """Layer が表示範囲の外にあれば、中央に来るようスクロールする。"""
        outline = self.renderer.outline_of(layer)
        region = self.canvas.cget("scrollregion").split()
        if not outline or len(region) != 4:
            return
        frame = bounding_frame(outline)
        total_width, total_height = float(region[2]), float(region[3])
        view_width, view_height = self.canvas.winfo_width(), self.canvas.winfo_height()
        left, top = self.canvas.canvasx(0), self.canvas.canvasy(0)
        if not (left <= frame.x and frame.right <= left + view_width) and total_width > 0:
            self.canvas.xview_moveto((frame.x + frame.width / 2 - view_width / 2) / total_width)
        if not (top <= frame.y and frame.bottom <= top + view_height) and total_height > 0:
            self.canvas.yview_moveto((frame.y + frame.height / 2 - view_height / 2) / total_height)

    def _update_view_combo(self) -> None:
        """「表示」の選択肢を現在の Page の画面一覧にし、表示中の画面を選ぶ。"""
        artboards = self.current_page.artboards() if self.current_page else []
        self._view_choices = [None, *artboards]
        self.view_combo.configure(values=[VIEW_ALL, *(f"{a.name}  [{a.type}]" for a in artboards)])
        index = next(i for i, choice in enumerate(self._view_choices) if choice is self.view_root)
        self.view_combo.current(index)

    def _on_view_selected(self, _event: tk.Event) -> None:
        self.view_root = self._view_choices[self.view_combo.current()]
        self._render()
        if self.selected_layer is not None:
            self._scroll_to(self.selected_layer)

    # ---- 拡大・縮小・スクロール -------------------------------------------------

    def _zoom_in(self) -> None:
        self._set_zoom(next_zoom_level(self.zoom, 1))

    def _zoom_out(self) -> None:
        self._set_zoom(next_zoom_level(self.zoom, -1))

    def _zoom_reset(self) -> None:
        self._set_zoom(1.0)

    def _on_zoom_selected(self, _event: tk.Event) -> None:
        self._set_zoom(ZOOM_LEVELS[self.zoom_combo.current()])

    def _set_zoom(self, zoom: float, anchor: tuple[float, float] | None = None) -> None:
        """表示倍率を変える。anchor (Canvas ウィジェット上の位置) の下にある点は動かさない。

        anchor を省略すると表示領域の中央を基準にする。
        """
        zoom = clamp_zoom(zoom)
        if self.current_page is None or zoom == self.zoom:
            self.zoom = zoom
            self.zoom_combo.set(format_zoom(zoom))
            return
        if anchor is None:
            anchor = (self.canvas.winfo_width() / 2, self.canvas.winfo_height() / 2)
        ax, ay = anchor
        # anchor の下にある点の、倍率変更後の Canvas 座標を求める (余白の大きさは変わらない)
        margin, ratio = self.renderer.margin, zoom / self.zoom
        x = margin + (self.canvas.canvasx(ax) - margin) * ratio
        y = margin + (self.canvas.canvasy(ay) - margin) * ratio

        self.zoom = zoom
        self.zoom_combo.set(format_zoom(zoom))
        self._render(keep_scroll=True)
        # その点が再び anchor の位置に来るようスクロールする
        _, _, total_width, total_height = (float(v) for v in self.canvas.cget("scrollregion").split())
        self.canvas.xview_moveto((x - ax) / total_width)
        self.canvas.yview_moveto((y - ay) / total_height)

    def _zoom_to_fit(self) -> None:
        if self.current_page is None:
            return
        margin = self.renderer.margin * 2
        self.zoom = fit_zoom(
            self.renderer.bounds.width, self.renderer.bounds.height,
            self.canvas.winfo_width() - margin, self.canvas.winfo_height() - margin,
        )
        self.zoom_combo.set(format_zoom(self.zoom))
        self._render()

    def _on_ctrl_mouse_wheel(self, event: tk.Event) -> None:
        zoom = next_zoom_level(self.zoom, 1 if event.delta > 0 else -1)
        self._set_zoom(zoom, anchor=(event.x, event.y))

    def _on_mouse_wheel(self, event: tk.Event) -> None:
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def _on_shift_mouse_wheel(self, event: tk.Event) -> None:
        self.canvas.xview_scroll(-1 if event.delta > 0 else 1, "units")

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

"""Tkinter による GUI。

上部に表示する画面の切り替え、左ペインに検索欄・Page / Layer 階層 (ttk.Treeview)・選択 Layer のプロパティ、
右ペインに描画結果 (tk.Canvas) を表示する。
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .errors import SketchError
from .geometry import bounding_frame
from .model import Color, SketchDocument, SketchLayer, SketchPage, TextLayer
from .parser import load_document
from .renderer import CanvasRenderer, placement_of

APP_TITLE = "Sketch Viewer"
VIEW_ALL = "(全体)"
# 検索欄の入力から絞り込みまでの待ち時間 (ミリ秒)
_SEARCH_DELAY_MS = 200
# 拡大・縮小で切り替える表示倍率
ZOOM_LEVELS = (0.1, 0.25, 0.33, 0.5, 0.67, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0)

# プロパティ欄の行 (表示名, [(キー, 値の前に付ける見出し), ...])
_INFO_ROWS = (
    ("名前", [("name", "")]),
    ("種類", [("type", "")]),
    ("画面", [("artboard", "")]),
    ("位置", [("x", "X"), ("y", "Y")]),
    ("サイズ", [("width", "W"), ("height", "H")]),
    ("回転", [("rotation", "")]),
    ("塗り", [("fill", "")]),
    ("線", [("border", "")]),
    ("文字色", [("text_color", "")]),
    ("フォント", [("font", "")]),
)
_COLOR_FIELDS = ("fill", "border", "text_color")


def format_number(value: float) -> str:
    """座標などを小数第 2 位までの短い文字列にする (例: 12.0 -> "12"、-0.001 -> "0")。"""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def next_zoom_level(current: float, step: int) -> float:
    """current から step の向き (正: 拡大、負: 縮小) にある次の表示倍率を返す。"""
    if step > 0:
        return next((z for z in ZOOM_LEVELS if z > current * 1.001), ZOOM_LEVELS[-1])
    return next((z for z in reversed(ZOOM_LEVELS) if z < current * 0.999), ZOOM_LEVELS[0])


def fit_zoom(content_width: float, content_height: float, view_width: float,
             view_height: float) -> float:
    """内容全体が表示領域に収まる倍率 (ZOOM_LEVELS の範囲内)。内容が空なら 1.0。"""
    ratios = [view / content for view, content in
              ((view_width, content_width), (view_height, content_height)) if content > 0]
    if not ratios:
        return 1.0
    return max(ZOOM_LEVELS[0], min(ZOOM_LEVELS[-1], min(ratios)))


def format_zoom(zoom: float) -> str:
    return f"{round(zoom * 100)}%"


def format_color(color: Color) -> str:
    """``#RRGGBB`` 形式にする。半透明なら不透明度を添える。"""
    text = color.to_hex().upper()
    if color.alpha < 1:
        text += f"  ({round(max(0.0, color.alpha) * 100)}%)"
    return text


class SketchViewerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.document: SketchDocument | None = None
        self.current_page: SketchPage | None = None
        # 単独で表示している画面 (None なら Page 全体を表示)
        self.view_root: SketchLayer | None = None
        self.selected_layer: SketchLayer | None = None
        self.zoom = 1.0
        # Treeview の item id -> (Page, Layer または None)
        self._tree_items: dict[str, tuple[SketchPage, SketchLayer | None]] = {}
        # id(layer) -> Treeview の item id (検索で絞り込まれた Layer は含まない)
        self._layer_items: dict[int, str] = {}
        # id(layer) -> Page 直下の祖先 Layer
        self._root_of: dict[int, SketchLayer] = {}
        # Layer Tree でチェックを外した Layer (id(layer))
        self._hidden: set[int] = set()
        # 表示切替のドロップダウンの選択肢 (None は全体)
        self._view_choices: list[SketchLayer | None] = [None]
        # 検索に一致した Treeview の item id (Tree の並び順)
        self._matches: list[str] = []
        self._match_set: set[str] = set()
        self._match_index = -1
        self._search_job: str | None = None

        root.title(APP_TITLE)
        root.geometry("1200x760")
        self._checkbox_on = _checkbox_image(root, checked=True)
        self._checkbox_off = _checkbox_image(root, checked=False)
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
        view_menu = tk.Menu(menubar, tearoff=False)
        view_menu.add_command(label="拡大", accelerator="Ctrl++", command=lambda: self._zoom_step(1))
        view_menu.add_command(label="縮小", accelerator="Ctrl+-", command=lambda: self._zoom_step(-1))
        view_menu.add_command(label="100%", accelerator="Ctrl+0", command=lambda: self._set_zoom(1.0))
        view_menu.add_command(label="全体を表示", accelerator="Ctrl+9", command=self._zoom_to_fit)
        menubar.add_cascade(label="View", menu=view_menu)
        self.root.config(menu=menubar)
        self.root.bind_all("<Control-o>", lambda _e: self._on_open())
        self.root.bind_all("<Control-f>", lambda _e: self._focus_search())
        # "+" は配列により Shift の有無やキー名が異なるため複数登録する
        for key in ("plus", "equal", "semicolon", "KP_Add"):
            self.root.bind_all(f"<Control-{key}>", lambda _e: self._zoom_step(1))
        for key in ("minus", "KP_Subtract"):
            self.root.bind_all(f"<Control-{key}>", lambda _e: self._zoom_step(-1))
        self.root.bind_all("<Control-0>", lambda _e: self._set_zoom(1.0))
        self.root.bind_all("<Control-9>", lambda _e: self._zoom_to_fit())

    def _build_body(self) -> None:
        # 上部: 表示する画面の切り替え
        toolbar = ttk.Frame(self.root, padding=(6, 4))
        toolbar.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(toolbar, text="表示:").pack(side=tk.LEFT)
        self.view_combo = ttk.Combobox(toolbar, state="readonly", width=40, values=(VIEW_ALL,))
        self.view_combo.current(0)
        self.view_combo.pack(side=tk.LEFT, padx=(4, 0))
        self.view_combo.bind("<<ComboboxSelected>>", self._on_view_selected)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Label(toolbar, text="倍率:").pack(side=tk.LEFT)
        ttk.Button(toolbar, text="−", width=3, command=lambda: self._zoom_step(-1)).pack(
            side=tk.LEFT, padx=(4, 0),
        )
        self.zoom_combo = ttk.Combobox(
            toolbar, state="readonly", width=6, values=[format_zoom(z) for z in ZOOM_LEVELS],
        )
        self.zoom_combo.set(format_zoom(self.zoom))
        self.zoom_combo.pack(side=tk.LEFT, padx=2)
        self.zoom_combo.bind(
            "<<ComboboxSelected>>", lambda _e: self._set_zoom(ZOOM_LEVELS[self.zoom_combo.current()]),
        )
        ttk.Button(toolbar, text="+", width=3, command=lambda: self._zoom_step(1)).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="100%", width=6, command=lambda: self._set_zoom(1.0)).pack(
            side=tk.LEFT, padx=(4, 0),
        )
        ttk.Button(toolbar, text="全体を表示", command=self._zoom_to_fit).pack(side=tk.LEFT, padx=(4, 0))

        self.status = tk.StringVar(value="File > Open... で .sketch ファイルを開いてください")
        ttk.Label(self.root, textvariable=self.status, anchor="w", padding=(6, 2)).pack(
            side=tk.BOTTOM, fill=tk.X,
        )

        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(paned)
        self._build_search(left)
        self._build_info(left)
        self._build_tree(left)
        paned.add(left, weight=1)

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
        self.canvas.bind("<Control-MouseWheel>", self._on_ctrl_mouse_wheel)
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        # 中ボタンのドラッグで表示位置を動かす
        self.canvas.bind("<ButtonPress-2>", lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind("<B2-Motion>", lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1))
        paned.add(canvas_frame, weight=4)

        self.renderer = CanvasRenderer(self.canvas)

    def _build_search(self, parent: ttk.Frame) -> None:
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

    def _build_tree(self, parent: ttk.Frame) -> None:
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.tree = ttk.Treeview(tree_frame, columns=("type",), selectmode="browse")
        self.tree.heading("#0", text="Name")
        self.tree.heading("type", text="Type")
        self.tree.column("#0", width=220)
        self.tree.column("type", width=90, stretch=False)
        self.tree.tag_configure("dimmed", foreground="#9e9e9e")
        self.tree.tag_configure("match", background="#fff3b0")
        tree_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<Double-1>", self._on_tree_double_click)
        self.tree.bind("<space>", self._on_tree_space)

    def _build_info(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="プロパティ", padding=(6, 4))
        frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(4, 0))
        frame.columnconfigure(2, weight=1)
        self._info_vars: dict[str, tk.StringVar] = {}
        self._swatches: dict[str, tk.Label] = {}
        for row, (label, fields) in enumerate(_INFO_ROWS):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, 6))
            values = ttk.Frame(frame)
            values.grid(row=row, column=2, sticky="ew", pady=1)
            for key, caption in fields:
                if key in _COLOR_FIELDS:
                    swatch = tk.Label(frame, width=2, relief="solid", borderwidth=1)
                    swatch.grid(row=row, column=1, sticky="w", padx=(0, 4))
                    swatch.grid_remove()
                    self._swatches[key] = swatch
                if caption:
                    ttk.Label(values, text=caption).pack(side=tk.LEFT, padx=(0, 2))
                var = tk.StringVar()
                # 読み取り専用の Entry にして値をコピーできるようにする
                ttk.Entry(values, textvariable=var, state="readonly", width=8).pack(
                    side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4 if caption else 0),
                )
                self._info_vars[key] = var

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
        self.selected_layer = None
        self._root_of = {
            id(layer): top
            for page in document.pages for top in page.layers for layer, _ in top.walk()
        }
        # Sketch 上で非表示の Layer は、チェックを外した状態から始める
        self._hidden = {
            id(layer) for page in document.pages for layer, _ in page.walk() if not layer.visible
        }
        self.root.title(f"{Path(path).name} - {APP_TITLE}")
        self._populate_tree()
        if document.pages:
            self._show_page(document.pages[0])
        else:
            self.current_page = None
            self.view_root = None
            self._update_view_combo()
            self.canvas.delete("all")
        self._update_info(None, None)
        self._update_status()

    # ---- Layer Tree -----------------------------------------------------

    def _populate_tree(self) -> None:
        """Layer Tree を作り直す。検索語があれば一致する Layer とその祖先だけを表示する。"""
        self.tree.delete(*self.tree.get_children())
        self._tree_items.clear()
        self._layer_items.clear()
        self._matches = []
        self._match_set = set()
        self._match_index = -1
        if self.document is None:
            return
        query = self.search_var.get().strip()
        for page in self.document.pages:
            page_item = self.tree.insert("", tk.END, text=page.name, values=("page",), open=True)
            self._tree_items[page_item] = (page, None)
            for layer in page.layers:
                self._insert_layer(page_item, page, layer, query, parent_hidden=False)
            if query and not self.tree.get_children(page_item):
                self.tree.delete(page_item)
                del self._tree_items[page_item]

        item = self._layer_items.get(id(self.selected_layer))
        if item is not None:
            self.tree.selection_set(item)
            self.tree.see(item)

    def _insert_layer(self, parent: str, page: SketchPage, layer: SketchLayer, query: str,
                      parent_hidden: bool) -> bool:
        """Layer とその子孫を Tree に追加する。検索で除外されたら False を返す。"""
        text = layer.name if layer.visible else f"{layer.name} (hidden)"
        item = self.tree.insert(parent, tk.END, text=text, values=(layer.type,))
        self._tree_items[item] = (page, layer)
        self._layer_items[id(layer)] = item
        matched = layer.matches(query)
        if matched:
            self._matches.append(item)
            self._match_set.add(item)
        self._apply_item_state(item, parent_hidden, recursive=False)

        hidden = parent_hidden or id(layer) in self._hidden
        has_match = False
        for child in layer.children:
            has_match |= self._insert_layer(item, page, child, query, hidden)
        if query and not matched and not has_match:
            self.tree.delete(item)
            del self._tree_items[item]
            del self._layer_items[id(layer)]
            return False
        if query and has_match:
            self.tree.item(item, open=True)
        return True

    def _apply_item_state(self, item: str, parent_hidden: bool, recursive: bool = True) -> None:
        """チェックボックスの画像と文字色 (祖先ごと非表示なら灰色) を更新する。"""
        _, layer = self._tree_items[item]
        if layer is None:
            return
        checked = id(layer) not in self._hidden
        tags = []
        if parent_hidden or not checked:
            tags.append("dimmed")
        if item in self._match_set:
            tags.append("match")
        self.tree.item(item, image=self._checkbox_on if checked else self._checkbox_off, tags=tags)
        if recursive:
            for child in self.tree.get_children(item):
                self._apply_item_state(child, parent_hidden or not checked)

    def _ancestor_hidden(self, item: str) -> bool:
        parent = self.tree.parent(item)
        while parent:
            _, layer = self._tree_items[parent]
            if layer is not None and id(layer) in self._hidden:
                return True
            parent = self.tree.parent(parent)
        return False

    def _toggle_visibility(self, item: str) -> None:
        page, layer = self._tree_items[item]
        if layer is None:
            return
        self._hidden ^= {id(layer)}
        self._apply_item_state(item, self._ancestor_hidden(item))
        if page is self.current_page:
            self._render(keep_scroll=True)

    def _on_tree_click(self, event: tk.Event) -> str | None:
        # チェックボックス (item の画像) のクリックは表示の切り替えとし、選択は変えない
        item = self.tree.identify_row(event.y)
        if item and "image" in self.tree.identify_element(event.x, event.y):
            self._toggle_visibility(item)
            return "break"
        return None

    def _on_tree_space(self, _event: tk.Event) -> str:
        for item in self.tree.selection():
            self._toggle_visibility(item)
        return "break"

    def _on_tree_double_click(self, event: tk.Event) -> None:
        # 画面をダブルクリックするとその画面だけを表示する
        item = self.tree.identify_row(event.y)
        if not item or "image" in self.tree.identify_element(event.x, event.y):
            return
        page, layer = self._tree_items[item]
        if layer is not None and layer.is_artboard and layer in page.layers:
            self._show_page(page, layer)

    def _on_tree_select(self, _event: object) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        page, layer = self._tree_items[selection[0]]
        self._select(page, layer)

    def _select(self, page: SketchPage, layer: SketchLayer | None) -> None:
        self.selected_layer = layer
        if layer is None:
            if page is not self.current_page:
                self._show_page(page)
            self.renderer.highlight(None)
            self._update_info(page, None)
            return

        root = self._root_of[id(layer)]
        if page is not self.current_page or (self.view_root is not None and self.view_root is not root):
            # 1 画面だけを表示しているときは、選択した Layer の画面へ切り替える
            single = self.view_root is not None
            self._show_page(page, root if single and root.is_artboard else None)
        self.renderer.highlight(layer)
        self._scroll_to(layer)
        self._update_info(page, layer)

    # ---- 検索 -----------------------------------------------------------

    def _focus_search(self) -> None:
        self.search_entry.focus_set()
        self.search_entry.select_range(0, tk.END)

    def _on_search_changed(self, *_args: object) -> None:
        if self._search_job is not None:
            self.root.after_cancel(self._search_job)
        self._search_job = self.root.after(_SEARCH_DELAY_MS, self._apply_search)

    def _apply_search(self) -> None:
        self._search_job = None
        self._populate_tree()
        self._update_search_count()

    def _goto_match(self, step: int) -> None:
        if self._search_job is not None:
            # 入力直後に Enter を押した場合は先に絞り込む
            self.root.after_cancel(self._search_job)
            self._apply_search()
        if not self._matches:
            return
        self._match_index = (self._match_index + step) % len(self._matches)
        item = self._matches[self._match_index]
        self.tree.selection_set(item)
        self.tree.see(item)
        self._update_search_count()

    def _update_search_count(self) -> None:
        if not self.search_var.get().strip():
            self.search_count.set("")
        elif self._match_index >= 0:
            self.search_count.set(f"{self._match_index + 1}/{len(self._matches)} 件")
        else:
            self.search_count.set(f"{len(self._matches)} 件")

    # ---- 描画 -----------------------------------------------------------

    def _show_page(self, page: SketchPage, view_root: SketchLayer | None = None) -> None:
        self.current_page = page
        self.view_root = view_root
        self._update_view_combo()
        self._render()

    def _render(self, keep_scroll: bool = False) -> None:
        if self.current_page is None:
            return
        xview, yview = self.canvas.xview()[0], self.canvas.yview()[0]
        roots = [self.view_root] if self.view_root is not None else None
        self.renderer.render(self.current_page, roots, self._is_visible, self.zoom)
        self.renderer.highlight(self.selected_layer)
        self.canvas.xview_moveto(xview if keep_scroll else 0)
        self.canvas.yview_moveto(yview if keep_scroll else 0)

    def _is_visible(self, layer: SketchLayer) -> bool:
        return id(layer) not in self._hidden

    def _update_view_combo(self) -> None:
        artboards = self.current_page.artboards() if self.current_page else []
        self._view_choices = [None, *artboards]
        self.view_combo.configure(values=[VIEW_ALL, *(f"{a.name}  [{a.type}]" for a in artboards)])
        index = next(i for i, c in enumerate(self._view_choices) if c is self.view_root)
        self.view_combo.current(index)

    def _on_view_selected(self, _event: object) -> None:
        self.view_root = self._view_choices[self.view_combo.current()]
        self._render()
        if self.selected_layer is not None:
            self._scroll_to(self.selected_layer)

    def _on_canvas_click(self, event: tk.Event) -> None:
        if self.current_page is None:
            return
        layer = self.renderer.layer_at(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        item = self._layer_items.get(id(layer)) if layer is not None else None
        if item is not None:
            self.tree.selection_set(item)
            self.tree.see(item)
            return
        # 検索で Tree から除外されている Layer、または何もない場所
        self.tree.selection_remove(*self.tree.selection())
        self.selected_layer = layer
        self.renderer.highlight(layer)
        self._update_info(self.current_page, layer)

    def _scroll_to(self, layer: SketchLayer) -> None:
        """選択した Layer が表示範囲の外にあれば、中央に来るようスクロールする。"""
        outline = self.renderer.outline_of(layer)
        region = self.canvas.cget("scrollregion").split()
        if not outline or len(region) != 4:
            return
        frame = bounding_frame(outline)
        total_w, total_h = float(region[2]), float(region[3])
        view_w, view_h = self.canvas.winfo_width(), self.canvas.winfo_height()
        left, top = self.canvas.canvasx(0), self.canvas.canvasy(0)
        if not (left <= frame.x and frame.right <= left + view_w) and total_w > 0:
            self.canvas.xview_moveto((frame.x + frame.width / 2 - view_w / 2) / total_w)
        if not (top <= frame.y and frame.bottom <= top + view_h) and total_h > 0:
            self.canvas.yview_moveto((frame.y + frame.height / 2 - view_h / 2) / total_h)

    # ---- 拡大・縮小 -------------------------------------------------------

    def _zoom_step(self, step: int, anchor: tuple[float, float] | None = None) -> None:
        self._set_zoom(next_zoom_level(self.zoom, step), anchor)

    def _set_zoom(self, zoom: float, anchor: tuple[float, float] | None = None) -> None:
        """表示倍率を変える。anchor (Canvas ウィジェット上の位置) の下にある点を動かさない。"""
        zoom = max(ZOOM_LEVELS[0], min(ZOOM_LEVELS[-1], zoom))
        if self.current_page is None or zoom == self.zoom:
            self.zoom = zoom
            self.zoom_combo.set(format_zoom(zoom))
            return
        if anchor is None:
            anchor = (self.canvas.winfo_width() / 2, self.canvas.winfo_height() / 2)
        ax, ay = anchor
        # anchor の下の点の、拡大・縮小後の Canvas 座標
        margin, ratio = self.renderer.margin, zoom / self.zoom
        x = margin + (self.canvas.canvasx(ax) - margin) * ratio
        y = margin + (self.canvas.canvasy(ay) - margin) * ratio
        self.zoom = zoom
        self.zoom_combo.set(format_zoom(zoom))
        self._render(keep_scroll=True)
        _, _, total_w, total_h = (float(v) for v in self.canvas.cget("scrollregion").split())
        self.canvas.xview_moveto((x - ax) / total_w)
        self.canvas.yview_moveto((y - ay) / total_h)

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
        self._zoom_step(1 if event.delta > 0 else -1, (event.x, event.y))

    def _on_mouse_wheel(self, event: tk.Event) -> None:
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def _on_shift_mouse_wheel(self, event: tk.Event) -> None:
        self.canvas.xview_scroll(-1 if event.delta > 0 else 1, "units")

    # ---- プロパティ / ステータス ------------------------------------------

    def _update_info(self, page: SketchPage | None, layer: SketchLayer | None) -> None:
        values = dict.fromkeys(self._info_vars, "")
        colors: dict[str, Color | None] = dict.fromkeys(_COLOR_FIELDS)
        placement = placement_of(page, layer) if page is not None and layer is not None else None
        if layer is not None:
            values["name"] = layer.name
            values["type"] = layer.type
        if placement is not None:
            # 座標は所属する画面の左上を原点とする (画面外の Layer は Page 座標)
            values["artboard"] = placement.artboard.name if placement.artboard else "(なし: Page 座標)"
            frame = placement.frame
            values["x"], values["y"] = format_number(frame.x), format_number(frame.y)
            values["width"], values["height"] = format_number(frame.width), format_number(frame.height)
            values["rotation"] = f"{format_number(placement.rotation)}°"
            style = placement.style
            colors["fill"] = style.fill
            if style.border is not None:
                colors["border"] = style.border.color
            if style.opacity < 1:
                values["type"] += f"  (opacity {round(style.opacity * 100)}%)"
        if isinstance(layer, TextLayer):
            colors["text_color"] = layer.color
            values["font"] = f"{layer.font_name}  {format_number(layer.font_size)}"

        for key, color in colors.items():
            swatch = self._swatches[key]
            if color is None:
                values[key] = "なし" if placement is not None and key != "text_color" else ""
                swatch.grid_remove()
                continue
            values[key] = format_color(color)
            swatch.configure(background=color.to_hex())
            swatch.grid()
        if colors["border"] is not None and placement is not None and placement.style.border:
            values["border"] += f"  太さ {format_number(placement.style.border.thickness)}"

        for key, value in values.items():
            self._info_vars[key].set(value)

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


def _checkbox_image(master: tk.Misc, checked: bool, size: int = 13) -> tk.PhotoImage:
    """Treeview の item に表示するチェックボックスの画像。"""
    image = tk.PhotoImage(master=master, width=size, height=size)
    image.put("#ffffff", to=(0, 0, size, size))
    border = "#6b6b6b"
    for box in ((0, 0, size, 1), (0, size - 1, size, size), (0, 0, 1, size), (size - 1, 0, size, size)):
        image.put(border, to=box)
    if checked:
        for x, y in ((3, 6), (4, 7), (5, 8), (6, 7), (7, 6), (8, 5), (9, 4)):
            image.put("#1565c0", to=(x, y, x + 1, y + 2))
    return image


def main(path: str | Path | None = None) -> None:
    root = tk.Tk()
    app = SketchViewerApp(root)
    if path is not None:
        root.after_idle(app.open_path, path)
    root.mainloop()

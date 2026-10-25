"""Page / Layer の階層を表示する Layer Tree (ttk.Treeview)。

項目の選択・ダブルクリックは、コンストラクタで受け取った関数 (コールバック) で通知する。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from .model import SketchDocument, SketchLayer, SketchPage

# 選択などの通知を受け取る関数。layer が None なら Page 自体を選んだことを表す
LayerCallback = Callable[[SketchPage, SketchLayer | None], None]


class LayerTree(ttk.Frame):
    def __init__(self, parent: tk.Misc, on_select: LayerCallback,
                 on_activate: LayerCallback) -> None:
        super().__init__(parent)
        self._on_select = on_select  # 項目を選択したとき
        self._on_activate = on_activate  # 項目をダブルクリックしたとき

        self.document: SketchDocument | None = None
        # Treeview の item id -> (Page, Layer)。Page の項目の Layer は None
        self._items: dict[str, tuple[SketchPage, SketchLayer | None]] = {}
        # id(layer) -> Treeview の item id
        self._item_of_layer: dict[int, str] = {}
        self._build()

    def _build(self) -> None:
        self.tree = ttk.Treeview(self, columns=("type",), selectmode="browse")
        self.tree.heading("#0", text="Name")
        self.tree.heading("type", text="Type")
        self.tree.column("#0", width=220)
        self.tree.column("type", width=90, stretch=False)
        scroll = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self._handle_select)
        self.tree.bind("<Double-1>", self._handle_double_click)

    # ---- 公開メソッド -------------------------------------------------------

    def load(self, document: SketchDocument) -> None:
        """Document の階層を表示する。"""
        self.document = document
        self._rebuild()

    def select_layer(self, layer: SketchLayer | None) -> bool:
        """Layer の項目を選択して見える位置までスクロールする。項目がなければ False。"""
        item = self._item_of_layer.get(id(layer)) if layer is not None else None
        if item is None:
            return False
        self.tree.selection_set(item)
        self.tree.see(item)
        return True

    def clear_selection(self) -> None:
        self.tree.selection_remove(*self.tree.selection())

    # ---- Tree の構築 -------------------------------------------------------

    def _rebuild(self) -> None:
        """Tree を作り直す。"""
        self.tree.delete(*self.tree.get_children())
        self._items.clear()
        self._item_of_layer.clear()
        if self.document is None:
            return
        for page in self.document.pages:
            page_item = self.tree.insert("", tk.END, text=page.name, values=("page",), open=True)
            self._items[page_item] = (page, None)
            for layer in page.layers:
                self._insert_layer(page_item, page, layer)

    def _insert_layer(self, parent: str, page: SketchPage, layer: SketchLayer) -> None:
        """Layer とその子孫を Tree に追加する。"""
        text = layer.name if layer.visible else f"{layer.name} (hidden)"
        item = self.tree.insert(parent, tk.END, text=text, values=(layer.type,))
        self._items[item] = (page, layer)
        self._item_of_layer[id(layer)] = item
        for child in layer.children:
            self._insert_layer(item, page, child)

    # ---- イベント処理 -------------------------------------------------------

    def _handle_select(self, _event: tk.Event) -> None:
        selection = self.tree.selection()
        if selection:
            self._on_select(*self._items[selection[0]])

    def _handle_double_click(self, event: tk.Event) -> None:
        item = self.tree.identify_row(event.y)
        if item:
            self._on_activate(*self._items[item])

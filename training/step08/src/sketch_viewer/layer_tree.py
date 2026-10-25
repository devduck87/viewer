"""Page / Layer の階層を表示する Layer Tree (ttk.Treeview)。

- 項目の選択・ダブルクリックは、コンストラクタで受け取った関数 (コールバック) で通知する
- 項目の先頭のチェックボックスで Layer の表示 / 非表示を切り替える
- 検索語を指定すると、一致する Layer とその祖先だけに絞り込む
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from .model import SketchDocument, SketchLayer, SketchPage

# 選択などの通知を受け取る関数。layer が None なら Page 自体を選んだことを表す
LayerCallback = Callable[[SketchPage, SketchLayer | None], None]

DIMMED_COLOR = "#9e9e9e"  # 祖先ごと非表示の Layer の文字色
MATCH_BACKGROUND = "#fff3b0"  # 検索に一致した項目の背景色


class LayerTree(ttk.Frame):
    def __init__(self, parent: tk.Misc, on_select: LayerCallback,
                 on_activate: LayerCallback, on_visibility_changed: Callable[[SketchPage], None]
                 ) -> None:
        super().__init__(parent)
        self._on_select = on_select  # 項目を選択したとき
        self._on_activate = on_activate  # 項目をダブルクリックしたとき
        self._on_visibility_changed = on_visibility_changed  # チェックを切り替えたとき

        self.document: SketchDocument | None = None
        # Treeview の item id -> (Page, Layer)。Page の項目の Layer は None
        self._items: dict[str, tuple[SketchPage, SketchLayer | None]] = {}
        # id(layer) -> Treeview の item id (検索で絞り込まれた Layer は含まない)
        self._item_of_layer: dict[int, str] = {}
        # チェックを外した Layer (id(layer))
        self._hidden: set[int] = set()
        # 検索
        self._query = ""
        self._matches: list[str] = []  # 一致した item id (Tree の並び順)
        self._match_set: set[str] = set()
        self._match_index = -1  # Enter で選んだ一致の位置 (-1 は未選択)

        self._checkbox_on = _checkbox_image(self, checked=True)
        self._checkbox_off = _checkbox_image(self, checked=False)
        self._build()

    def _build(self) -> None:
        self.tree = ttk.Treeview(self, columns=("type",), selectmode="browse")
        self.tree.heading("#0", text="Name")
        self.tree.heading("type", text="Type")
        self.tree.column("#0", width=220)
        self.tree.column("type", width=90, stretch=False)
        self.tree.tag_configure("dimmed", foreground=DIMMED_COLOR)
        self.tree.tag_configure("match", background=MATCH_BACKGROUND)
        scroll = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self._handle_select)
        self.tree.bind("<Button-1>", self._handle_click)
        self.tree.bind("<Double-1>", self._handle_double_click)
        self.tree.bind("<space>", self._handle_space)

    # ---- 公開メソッド -------------------------------------------------------

    def load(self, document: SketchDocument) -> None:
        """Document の階層を表示する。Sketch 上で非表示の Layer はチェックを外した状態で始める。"""
        self.document = document
        self._hidden = {
            id(layer) for page in document.pages for layer, _ in page.walk() if not layer.visible
        }
        self._rebuild()

    def is_visible(self, layer: SketchLayer) -> bool:
        """Layer のチェックが入っているか (Renderer に渡して描画対象を絞り込む)。"""
        return id(layer) not in self._hidden

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

    def set_query(self, query: str) -> None:
        """検索語を設定し、一致する Layer とその祖先だけを表示する。空なら絞り込みを解除する。"""
        self._query = query
        self._rebuild()

    def goto_match(self, step: int) -> None:
        """step の向き (1: 次、-1: 前) にある検索の一致を選択する。"""
        if not self._matches:
            return
        self._match_index = (self._match_index + step) % len(self._matches)
        item = self._matches[self._match_index]
        self.tree.selection_set(item)
        self.tree.see(item)

    def match_summary(self) -> str:
        """検索の一致件数の表示 (例: "2/5 件")。検索していなければ空文字。"""
        if not self._query:
            return ""
        if self._match_index >= 0:
            return f"{self._match_index + 1}/{len(self._matches)} 件"
        return f"{len(self._matches)} 件"

    # ---- Tree の構築 -------------------------------------------------------

    def _rebuild(self) -> None:
        """Tree を作り直す。検索語があれば、一致する Layer とその祖先だけを表示する。"""
        self.tree.delete(*self.tree.get_children())
        self._items.clear()
        self._item_of_layer.clear()
        self._matches = []
        self._match_set = set()
        self._match_index = -1
        if self.document is None:
            return
        for page in self.document.pages:
            page_item = self.tree.insert("", tk.END, text=page.name, values=("page",), open=True)
            self._items[page_item] = (page, None)
            for layer in page.layers:
                self._insert_layer(page_item, page, layer, parent_hidden=False)
            if self._query and not self.tree.get_children(page_item):
                self._remove_item(page_item)

    def _insert_layer(self, parent: str, page: SketchPage, layer: SketchLayer,
                      parent_hidden: bool) -> bool:
        """Layer とその子孫を Tree に追加する。検索で除外したら False を返す。"""
        text = layer.name if layer.visible else f"{layer.name} (hidden)"
        item = self.tree.insert(parent, tk.END, text=text, values=(layer.type,))
        self._items[item] = (page, layer)
        self._item_of_layer[id(layer)] = item
        matched = layer.matches(self._query)
        if matched:
            self._matches.append(item)
            self._match_set.add(item)
        self._update_item_look(item, parent_hidden, recursive=False)

        hidden = parent_hidden or id(layer) in self._hidden
        has_matching_child = False
        for child in layer.children:
            has_matching_child |= self._insert_layer(item, page, child, hidden)

        if self._query and not matched and not has_matching_child:
            self._remove_item(item)
            return False
        if self._query and has_matching_child:
            self.tree.item(item, open=True)
        return True

    def _remove_item(self, item: str) -> None:
        _, layer = self._items.pop(item)
        if layer is not None:
            del self._item_of_layer[id(layer)]
        self.tree.delete(item)

    # ---- 表示 / 非表示 ------------------------------------------------------

    def _update_item_look(self, item: str, parent_hidden: bool, recursive: bool = True) -> None:
        """チェックボックスの画像と文字色 (祖先ごと非表示なら灰色) を更新する。"""
        _, layer = self._items[item]
        if layer is None:
            return
        checked = self.is_visible(layer)
        tags = []
        if parent_hidden or not checked:
            tags.append("dimmed")
        if item in self._match_set:
            tags.append("match")
        self.tree.item(item, image=self._checkbox_on if checked else self._checkbox_off, tags=tags)
        if recursive:
            for child in self.tree.get_children(item):
                self._update_item_look(child, parent_hidden or not checked)

    def _is_ancestor_hidden(self, item: str) -> bool:
        parent = self.tree.parent(item)
        while parent:
            _, layer = self._items[parent]
            if layer is not None and not self.is_visible(layer):
                return True
            parent = self.tree.parent(parent)
        return False

    def _toggle_visibility(self, item: str) -> None:
        page, layer = self._items[item]
        if layer is None:
            return
        self._hidden ^= {id(layer)}
        self._update_item_look(item, self._is_ancestor_hidden(item))
        self._on_visibility_changed(page)

    # ---- イベント処理 -------------------------------------------------------

    def _is_on_checkbox(self, event: tk.Event) -> bool:
        return "image" in self.tree.identify_element(event.x, event.y)

    def _handle_select(self, _event: tk.Event) -> None:
        selection = self.tree.selection()
        if selection:
            self._on_select(*self._items[selection[0]])

    def _handle_click(self, event: tk.Event) -> str | None:
        # チェックボックスのクリックは表示の切り替えとし、選択は変えない
        item = self.tree.identify_row(event.y)
        if item and self._is_on_checkbox(event):
            self._toggle_visibility(item)
            return "break"
        return None

    def _handle_space(self, _event: tk.Event) -> str:
        for item in self.tree.selection():
            self._toggle_visibility(item)
        return "break"

    def _handle_double_click(self, event: tk.Event) -> None:
        item = self.tree.identify_row(event.y)
        if item and not self._is_on_checkbox(event):
            self._on_activate(*self._items[item])


def _checkbox_image(master: tk.Misc, checked: bool, size: int = 13) -> tk.PhotoImage:
    """Treeview の項目に表示するチェックボックスの画像を描く。"""
    image = tk.PhotoImage(master=master, width=size, height=size)
    image.put("#ffffff", to=(0, 0, size, size))
    # 枠線 (上・下・左・右)
    for box in ((0, 0, size, 1), (0, size - 1, size, size), (0, 0, 1, size), (size - 1, 0, size, size)):
        image.put("#6b6b6b", to=box)
    if checked:
        # チェックマーク
        for x, y in ((3, 6), (4, 7), (5, 8), (6, 7), (7, 6), (8, 5), (9, 4)):
            image.put("#1565c0", to=(x, y, x + 1, y + 2))
    return image

"""Interactive matplotlib UI helpers (pickers and dialogs)."""
from __future__ import annotations

import gc
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

import matplotlib.pyplot as plt
from matplotlib.patheffects import withStroke as _mpl_stroke
from matplotlib.widgets import Button, TextBox

from pyrockimagelab.common.io_paths import (
    DEFAULT_HR_PHOTO_RANGES,
    DISPLAY_LONG_SIDE,
    THUMB_SELECT_LONG_SIDE,
    load_any_image,
    release_working_memory,
)


class QuadPicker:
    """Interactive 4-point picker with auto-sorted corners (TL, TR, BR, BL)."""

    LABELS = ("TL", "TR", "BR", "BL")
    SNAP_PX = 14
    ACTION_CONFIRM = "confirm"
    ACTION_SKIP = "skip"
    ACTION_QUIT = "quit"
    ACTION_CANCEL = "cancel"
    ACTION_REDO = "redo"
    ACTION_RESTITCH = "restitch"
    ACTION_SKIP_PHOTO = "skip_photo"

    @staticmethod
    def _sort_quad(pts):
        pts = sorted(pts, key=lambda p: p[1])
        top2 = sorted(pts[:2], key=lambda p: p[0])
        bot2 = sorted(pts[2:], key=lambda p: p[0])
        return [top2[0], top2[1], bot2[1], bot2[0]]

    def __init__(
        self,
        img_rgb,
        initial_quad=None,
        title="",
        figsize=(12, 8),
        max_display=DISPLAY_LONG_SIDE,
        metadata_fields=None,
        on_field_change=None,
        segment_actions=False,
        redo_action=False,
        restitch_action=False,
        skip_photo_action=False,
        highlight_keys=None,
    ):
        self._highlight_keys = set(highlight_keys or [])
        h, w = img_rgb.shape[:2]
        self.scale = min(1.0, max_display / max(h, w))
        disp_w = max(1, int(round(w * self.scale)))
        disp_h = max(1, int(round(h * self.scale)))
        if self.scale < 1.0:
            self.display_img = cv2.resize(img_rgb, (disp_w, disp_h), interpolation=cv2.INTER_AREA)
        else:
            self.display_img = img_rgb.copy()

        self.pts = []
        if initial_quad is not None:
            for x, y in initial_quad:
                self.pts.append([float(x) * self.scale, float(y) * self.scale])
            if len(self.pts) == 4:
                self.pts = self._sort_quad(self.pts)

        self.drag_idx = None
        self.result = None
        self.segment_action = None
        self._finalized = False
        self._segment_actions = segment_actions
        self._redo_action = redo_action
        self._restitch_action = restitch_action
        self._skip_photo_action = skip_photo_action
        self.metadata_fields = metadata_fields or []
        self.metadata = {}
        self._textboxes = []
        self._textbox_focused = False
        self._on_field_change = on_field_change
        self._updating = False

        n_fields = len(self.metadata_fields)
        has_side = n_fields > 0 or segment_actions or redo_action or restitch_action or skip_photo_action
        side_w = 0.22 if has_side else 0.0

        self.fig = plt.figure(figsize=figsize)
        img_left = side_w + 0.02 if has_side else 0.05
        self.ax = self.fig.add_axes([img_left, 0.05, 0.97 - img_left, 0.88])
        self.ax.imshow(self.display_img)
        help_parts = ["L-click: add/drag | R-click: remove | r: reset",
                       "Enter: confirm | Esc: cancel"]
        if segment_actions:
            help_parts.append("s=skip | q=quit")
        if redo_action:
            help_parts.append("d=redo crops")
        if restitch_action:
            help_parts.append("t=restitch")
        if skip_photo_action:
            help_parts.append("x=skip photo")
        self.ax.set_title(f"{title}\n[{' | '.join(help_parts)}]")
        self.ax.set_axis_off()

        panel_x = 0.01
        panel_w = side_w - 0.02
        cursor_y = 0.92

        for field in self.metadata_fields:
            cursor_y -= 0.05
            ax_tb = self.fig.add_axes([panel_x, cursor_y, panel_w, 0.035])
            default_val = str(field.get("default", ""))
            tb = TextBox(ax_tb, f"{field['label']}: ", initial=default_val)
            tb.label.set_fontsize(8)
            if field["key"] in self._highlight_keys:
                tb.label.set_color("red")
                tb.label.set_fontweight("bold")
            self.metadata[field["key"]] = default_val
            tb.on_text_change(lambda text, k=field["key"]: self._handle_field_change(k, text))
            self._textboxes.append(tb)

        cursor_y -= 0.02
        self._buttons = []

        if segment_actions:
            cursor_y -= 0.045
            ax_skip = self.fig.add_axes([panel_x, cursor_y, panel_w * 0.48, 0.035])
            ax_quit = self.fig.add_axes([panel_x + panel_w * 0.52, cursor_y, panel_w * 0.48, 0.035])
            btn_skip = Button(ax_skip, "Skip seg")
            btn_quit = Button(ax_quit, "Quit")
            btn_skip.on_clicked(lambda _e: self._skip_segment())
            btn_quit.on_clicked(lambda _e: self._quit_batch())
            self._buttons.extend([btn_skip, btn_quit])

        if redo_action:
            cursor_y -= 0.045
            ax_redo = self.fig.add_axes([panel_x, cursor_y, panel_w, 0.035])
            btn_redo = Button(ax_redo, "Redo crops")
            btn_redo.on_clicked(lambda _e: self._redo_crops())
            self._buttons.append(btn_redo)

        if restitch_action:
            cursor_y -= 0.045
            ax_restitch = self.fig.add_axes([panel_x, cursor_y, panel_w, 0.035])
            btn_restitch = Button(ax_restitch, "Restitch")
            btn_restitch.on_clicked(lambda _e: self._restitch())
            self._buttons.append(btn_restitch)

        if skip_photo_action:
            cursor_y -= 0.045
            ax_skipph = self.fig.add_axes([panel_x, cursor_y, panel_w, 0.035])
            btn_skipph = Button(ax_skipph, "Skip Photo")
            btn_skipph.on_clicked(lambda _e: self._skip_photo())
            self._buttons.append(btn_skipph)

        (self.poly_line,) = self.ax.plot([], [], color="yellow", lw=0.75)
        self.scatter = self.ax.scatter([], [], s=25, facecolor="yellow", edgecolor="black", zorder=10)
        self.label_artists = []

        self.cids = [
            self.fig.canvas.mpl_connect("button_press_event", self._on_press),
            self.fig.canvas.mpl_connect("motion_notify_event", self._on_motion),
            self.fig.canvas.mpl_connect("button_release_event", self._on_release),
            self.fig.canvas.mpl_connect("key_press_event", self._on_key),
            self.fig.canvas.mpl_connect("close_event", self._on_close),
        ]
        self._redraw()

    def _redraw(self):
        if self.pts:
            ordered = self._sort_quad(self.pts) if len(self.pts) == 4 else self.pts
            xs = [p[0] for p in ordered]
            ys = [p[1] for p in ordered]
            self.scatter.set_offsets(np.column_stack([xs, ys]))
            self.poly_line.set_data(xs + xs[:1], ys + ys[:1])
        else:
            self.scatter.set_offsets(np.empty((0, 2)))
            self.poly_line.set_data([], [])
        for a in self.label_artists:
            a.remove()
        self.label_artists = []
        if len(self.pts) == 4:
            ordered = self._sort_quad(self.pts)
            for i, (x, y) in enumerate(ordered):
                self.label_artists.append(
                    self.ax.annotate(
                        self.LABELS[i],
                        (x, y),
                        xytext=(10, 10),
                        textcoords="offset points",
                        color="yellow",
                        fontsize=13,
                        fontweight="bold",
                    )
                )
        else:
            for i, (x, y) in enumerate(self.pts):
                self.label_artists.append(
                    self.ax.annotate(
                        str(i + 1),
                        (x, y),
                        xytext=(10, 10),
                        textcoords="offset points",
                        color="yellow",
                        fontsize=13,
                        fontweight="bold",
                    )
                )
        self.fig.canvas.draw_idle()

    def _find_near(self, x, y):
        for i, (px, py) in enumerate(self.pts):
            if (px - x) ** 2 + (py - y) ** 2 < self.SNAP_PX ** 2:
                return i
        return None

    def _handle_field_change(self, key, text):
        if self._updating:
            return
        self.metadata[key] = text
        if self._on_field_change:
            self._updating = True
            updates = self._on_field_change(key, text, dict(self.metadata))
            if updates:
                for ukey, uval in updates.items():
                    for f, tb in zip(self.metadata_fields, self._textboxes):
                        if f["key"] == ukey:
                            tb.set_val(uval)
                            self.metadata[ukey] = uval
                            break
            self._updating = False

    def _on_press(self, event):
        if self._textboxes:
            self._textbox_focused = any(event.inaxes == tb.ax for tb in self._textboxes)
        if event.inaxes is not self.ax or event.xdata is None:
            return
        x, y = event.xdata, event.ydata
        if event.button == 1:
            i = self._find_near(x, y)
            if i is not None:
                self.drag_idx = i
            elif len(self.pts) < 4:
                self.pts.append([x, y])
                self._redraw()
        elif event.button == 3:
            i = self._find_near(x, y)
            if i is not None:
                self.pts.pop(i)
                self._redraw()

    def _on_motion(self, event):
        if self.drag_idx is None or event.inaxes is not self.ax or event.xdata is None:
            return
        self.pts[self.drag_idx] = [event.xdata, event.ydata]
        self._redraw()

    def _on_release(self, event):
        self.drag_idx = None

    def _on_key(self, event):
        if self._textbox_focused:
            return
        if event.key == "enter":
            self._confirm()
        elif event.key == "r":
            self.pts = []
            self._redraw()
        elif event.key == "escape":
            self.segment_action = self.ACTION_CANCEL
            self.result = None
            self._finalized = True
            plt.close(self.fig)
        elif self._segment_actions and event.key == "s":
            self._skip_segment()
        elif self._segment_actions and event.key == "q":
            self._quit_batch()
        elif self._redo_action and event.key == "d":
            self._redo_crops()
        elif self._restitch_action and event.key == "t":
            self._restitch()
        elif self._skip_photo_action and event.key == "x":
            self._skip_photo()

    def _skip_photo(self):
        self.segment_action = self.ACTION_SKIP_PHOTO
        self.result = None
        self._finalized = True
        plt.close(self.fig)

    def _skip_segment(self):
        self.segment_action = self.ACTION_SKIP
        self.result = None
        self._finalized = True
        plt.close(self.fig)

    def _quit_batch(self):
        self.segment_action = self.ACTION_QUIT
        self.result = None
        self._finalized = True
        plt.close(self.fig)

    def _redo_crops(self):
        self.segment_action = self.ACTION_REDO
        self.result = None
        self._finalized = True
        plt.close(self.fig)

    def _restitch(self):
        for field, tb in zip(self.metadata_fields, self._textboxes):
            self.metadata[field["key"]] = tb.text
        self.segment_action = self.ACTION_RESTITCH
        self.result = None
        self._finalized = True
        plt.close(self.fig)

    def _on_close(self, event):
        if not self._finalized and len(self.pts) == 4:
            ordered = self._sort_quad(self.pts)
            self.result = [(p[0] / self.scale, p[1] / self.scale) for p in ordered]
            for field, tb in zip(self.metadata_fields, self._textboxes):
                self.metadata[field["key"]] = tb.text
            self.segment_action = self.ACTION_CONFIRM
            self._finalized = True

    def _confirm(self):
        if len(self.pts) != 4:
            print(f"[picker] Need 4 corners, currently have {len(self.pts)}.")
            return
        ordered = self._sort_quad(self.pts)
        self.result = [(p[0] / self.scale, p[1] / self.scale) for p in ordered]
        for field, tb in zip(self.metadata_fields, self._textboxes):
            self.metadata[field["key"]] = tb.text
        self.segment_action = self.ACTION_CONFIRM
        self._finalized = True
        plt.close(self.fig)

    def run(self):
        try:
            plt.show(block=True)
            return self.result
        finally:
            for cid in getattr(self, "cids", []):
                try:
                    self.fig.canvas.mpl_disconnect(cid)
                except Exception:
                    pass
            if getattr(self, "fig", None) is not None:
                plt.close(self.fig)
            self.display_img = None
            self._buttons = []
            self._textboxes = []
            self.cids = []
            release_working_memory(quiet=True)

class _DialogResult:
    PROCESS = "process"
    SKIP = "skip"
    QUIT = "quit"
    CANCEL = "cancel"
    OK = "ok"


def confirm_folder(uwi, folder_path, idx, total):
    """Yes / Skip / Quit dialog using matplotlib. Returns _DialogResult."""
    result = {"action": _DialogResult.QUIT}

    fig = plt.figure(figsize=(5, 2.8))
    fig.canvas.manager.set_window_title("Core Photo — Folder")
    fig.text(
        0.5, 0.72,
        f"Process this folder?\n\n"
        f"UWI: {uwi}\n"
        f"Folder: {folder_path.name}\n"
        f"[{idx} / {total}]",
        ha="center", va="center", fontsize=11, family="monospace",
    )

    def _make_cb(action):
        def _cb(_event=None):
            result["action"] = action
            plt.close(fig)
        return _cb

    ax_yes = fig.add_axes([0.12, 0.08, 0.22, 0.12])
    ax_skip = fig.add_axes([0.40, 0.08, 0.22, 0.12])
    ax_quit = fig.add_axes([0.68, 0.08, 0.22, 0.12])
    btn_yes = Button(ax_yes, "Process")
    btn_skip = Button(ax_skip, "Skip")
    btn_quit = Button(ax_quit, "Quit")
    btn_yes.on_clicked(_make_cb(_DialogResult.PROCESS))
    btn_skip.on_clicked(_make_cb(_DialogResult.SKIP))
    btn_quit.on_clicked(_make_cb(_DialogResult.QUIT))

    def _on_key(e):
        if e.key == "enter":
            _make_cb(_DialogResult.PROCESS)()
        elif e.key == "escape":
            _make_cb(_DialogResult.QUIT)()

    fig.canvas.mpl_connect("key_press_event", _on_key)

    plt.show(block=True)
    del btn_yes, btn_skip, btn_quit
    plt.close(fig)
    return result["action"]


def _thumbnail_pil(path, max_long_side=THUMB_SELECT_LONG_SIDE):
    """Load image and return a small PIL thumbnail for UI display."""
    img = load_any_image(path)
    h, w = img.shape[:2]
    s = min(1.0, max_long_side / max(h, w))
    if s < 1.0:
        thumb = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    else:
        thumb = img
    return Image.fromarray(thumb)


def pick_box_photo(image_paths, default_path=None):
    """Matplotlib-based box-photo selector with thumbnail grid.

    Uses matplotlib instead of tkinter to avoid the macOS issue where a
    tkinter window persists behind the matplotlib corner picker.
    """
    if not image_paths:
        return None
    if len(image_paths) == 1:
        return image_paths[0]

    default_idx = 0
    if default_path is not None:
        for i, p in enumerate(image_paths):
            if p == default_path or p.name == Path(default_path).name:
                default_idx = i
                break

    n = len(image_paths)
    cols = min(4, max(2, n))
    rows = (n + cols - 1) // cols

    thumbs = []
    for p in image_paths:
        img = load_any_image(p)
        h, w = img.shape[:2]
        s = min(1.0, 200 / max(h, w))
        if s < 1.0:
            img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
        thumbs.append(img)

    state = {"selected": default_idx, "confirmed": False}

    fig, axes = plt.subplots(rows, cols, figsize=(3.2 * cols, 3.5 * rows))
    fig.canvas.manager.set_window_title("Select box photo")
    if rows == 1 and cols == 1:
        axes = np.array([[axes]])
    elif rows == 1:
        axes = axes[np.newaxis, :]
    elif cols == 1:
        axes = axes[:, np.newaxis]

    ax_list = []
    for i in range(rows * cols):
        r, c = divmod(i, cols)
        ax = axes[r, c]
        if i < n:
            ax.imshow(thumbs[i])
            ax.set_title(f"[{i}] {image_paths[i].name}", fontsize=8)
            ax.set_xticks([])
            ax.set_yticks([])
            ax_list.append(ax)
        else:
            ax.set_visible(False)

    def _highlight(idx):
        for j, a in enumerate(ax_list):
            lw = 4 if j == idx else 0.5
            color = "#2196F3" if j == idx else "gray"
            for spine in a.spines.values():
                spine.set_linewidth(lw)
                spine.set_edgecolor(color)
        fig.canvas.draw_idle()

    _highlight(state["selected"])

    fig.suptitle(
        "Click a thumbnail to select the box photo\n"
        "Enter = confirm  |  Esc = cancel",
        fontsize=11,
    )
    fig.subplots_adjust(hspace=0.45, wspace=0.25, top=0.90)

    def _on_click(event):
        for i, ax in enumerate(ax_list):
            if event.inaxes is ax:
                state["selected"] = i
                _highlight(i)
                return

    def _on_key(event):
        if event.key == "enter":
            state["confirmed"] = True
            plt.close(fig)
        elif event.key == "escape":
            state["selected"] = None
            plt.close(fig)

    fig.canvas.mpl_connect("button_press_event", _on_click)
    fig.canvas.mpl_connect("key_press_event", _on_key)
    plt.show(block=True)

    del thumbs
    plt.close(fig)
    gc.collect()

    idx = state["selected"]
    if idx is not None and state["confirmed"]:
        return image_paths[idx]
    if idx is not None and not state["confirmed"]:
        return image_paths[idx]
    return None


def assign_hr_photos(
    photo_paths,
    n_segments,
    prev_assignments=None,
    default_ranges=None,
):
    """Matplotlib thumbnail picker for photo-to-segment assignment.

    Click a segment button to select the active segment, then click photos
    to toggle them.  Color-coded borders show assignments.
    Returns {seg_num: [indices]} or None if cancelled.
    """
    photo_paths = [Path(p) for p in photo_paths]
    photo_names = [p.name for p in photo_paths]
    prev_assignments = prev_assignments or {}
    default_ranges = default_ranges or DEFAULT_HR_PHOTO_RANGES
    n_photos = len(photo_paths)
    if n_photos == 0:
        return {}

    has_saved = any(prev_assignments.get(f"seg{s}") for s in range(1, n_segments + 1))
    can_apply_defaults = (not has_saved) and n_photos >= 19

    seg_colors = ["#E53935", "#43A047", "#1E88E5", "#FB8C00", "#8E24AA",
                   "#00ACC1", "#6D4C41", "#546E7A"]

    print(f"  Loading {n_photos} thumbnails for photo assignment...")
    thumbs = []
    for p in photo_paths:
        img = load_any_image(p)
        h, w = img.shape[:2]
        s = min(1.0, 120 / max(h, w))
        if s < 1.0:
            img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
        thumbs.append(img)

    orders = {}
    for seg_num in range(1, n_segments + 1):
        prev = prev_assignments.get(f"seg{seg_num}", [])
        if not prev and can_apply_defaults and seg_num in default_ranges:
            lo, hi = default_ranges[seg_num]
            prev = list(range(lo, hi))
        orders[seg_num] = [i for i in prev if 0 <= i < n_photos]

    state = {"active_seg": 1, "confirmed": False}

    cols = min(6, max(3, n_photos))
    rows = (n_photos + cols - 1) // cols
    btn_height_ratio = 0.8
    fig_h = 2.2 * rows + btn_height_ratio + 0.6
    fig = plt.figure(figsize=(2.4 * cols, fig_h))
    fig.canvas.manager.set_window_title("Assign photos to segments")

    btn_zone = btn_height_ratio / fig_h
    grid_top = 1.0 - 0.06
    grid_bottom = btn_zone + 0.04
    gs = fig.add_gridspec(rows, cols, left=0.03, right=0.97,
                          top=grid_top, bottom=grid_bottom,
                          hspace=0.55, wspace=0.25)

    ax_list = []
    for i in range(rows * cols):
        r, c = divmod(i, cols)
        ax = fig.add_subplot(gs[r, c])
        if i < n_photos:
            ax.imshow(thumbs[i])
            ax.set_title(f"[{i}] {photo_names[i]}", fontsize=7)
            ax.set_xticks([])
            ax.set_yticks([])
            ax_list.append(ax)
        else:
            ax.set_visible(False)

    order_labels = []

    def _update_borders():
        for a in order_labels:
            a.remove()
        order_labels.clear()

        for i, ax in enumerate(ax_list):
            seg_for_photo = None
            pos_in_seg = None
            for sn in range(1, n_segments + 1):
                if i in orders[sn]:
                    seg_for_photo = sn
                    pos_in_seg = orders[sn].index(i) + 1
                    break
            if seg_for_photo is not None:
                color = seg_colors[(seg_for_photo - 1) % len(seg_colors)]
                lw = 4
                txt = ax.text(
                    0.5, 0.5, str(pos_in_seg),
                    transform=ax.transAxes, ha="center", va="center",
                    fontsize=22, fontweight="bold", color="white",
                    path_effects=[_mpl_stroke(linewidth=3, foreground=color)],
                )
                order_labels.append(txt)
            else:
                color = "#CCCCCC"
                lw = 0.5
            for spine in ax.spines.values():
                spine.set_linewidth(lw)
                spine.set_edgecolor(color)
        fig.canvas.draw_idle()

    _update_borders()

    def _update_title():
        seg = state["active_seg"]
        color = seg_colors[(seg - 1) % len(seg_colors)]
        counts = ", ".join(f"S{s}:{len(orders[s])}" for s in range(1, n_segments + 1))
        fig.suptitle(
            f"Active: Segment {seg}  ({counts})\n"
            "Click photo to toggle  |  1-9 = switch segment  |  Enter = OK  |  Esc = cancel",
            fontsize=10, color=color,
        )
        fig.canvas.draw_idle()

    _update_title()

    seg_buttons = []
    for sn in range(1, n_segments + 1):
        x = 0.05 + (sn - 1) * 0.18
        ax_btn = fig.add_axes([x, 0.01, 0.16, btn_zone * 0.55])
        color = seg_colors[(sn - 1) % len(seg_colors)]
        btn = Button(ax_btn, f"Seg {sn}", color=color, hovercolor=color)
        btn.label.set_color("white")
        btn.label.set_fontweight("bold")

        def _switch(_, s=sn):
            state["active_seg"] = s
            _update_title()

        btn.on_clicked(_switch)
        seg_buttons.append(btn)

    ax_ok = fig.add_axes([0.72, 0.01, 0.12, btn_zone * 0.55])
    ax_cancel = fig.add_axes([0.86, 0.01, 0.12, btn_zone * 0.55])
    btn_ok = Button(ax_ok, "OK")
    btn_cancel = Button(ax_cancel, "Cancel")

    result = {"assignments": None}

    def _on_ok(_event=None):
        result["assignments"] = {s: list(orders[s]) for s in range(1, n_segments + 1)}
        state["confirmed"] = True
        plt.close(fig)

    def _on_cancel(_event=None):
        plt.close(fig)

    btn_ok.on_clicked(_on_ok)
    btn_cancel.on_clicked(_on_cancel)

    def _on_photo_click(event):
        for i, ax in enumerate(ax_list):
            if event.inaxes is ax:
                seg = state["active_seg"]
                if i in orders[seg]:
                    orders[seg].remove(i)
                else:
                    for other in range(1, n_segments + 1):
                        if other != seg and i in orders[other]:
                            orders[other].remove(i)
                    orders[seg].append(i)
                _update_borders()
                _update_title()
                return

    def _on_key(event):
        if event.key == "enter":
            _on_ok()
        elif event.key == "escape":
            _on_cancel()
        elif event.key.isdigit() and 1 <= int(event.key) <= n_segments:
            state["active_seg"] = int(event.key)
            _update_title()

    fig.canvas.mpl_connect("button_press_event", _on_photo_click)
    fig.canvas.mpl_connect("key_press_event", _on_key)
    plt.show(block=True)

    del thumbs, seg_buttons, btn_ok, btn_cancel
    plt.close(fig)
    gc.collect()

    return result["assignments"]

def show_progress_and_ask(summary, mode, run_lr=True, run_hr=True):
    """Matplotlib popup with progress counts and Resume/Restart/Quit buttons.

    Returns 'resume', 'restart_all', 'redo_last', or 'quit'.
    """
    if run_lr and run_hr:
        detail_text = (
            f"  LR + HR complete:     {summary['n_both_done']}\n"
            f"  LR done, HR pending:  {summary['n_lr_only']}\n"
            f"  HR done, LR pending:  {summary['n_hr_only']}\n"
            f"  Not started:          {summary['n_not_started']}"
        )
    elif run_lr and not run_hr:
        detail_text = (
            f"  LR complete:  {summary['n_done']}\n"
            f"  LR pending:   {summary['n_pending']}"
        )
    else:  # run_hr only
        detail_text = (
            f"  HR complete:  {summary['n_done']}\n"
            f"  HR pending:   {summary['n_pending']}"
        )

    text = (
        f"Progress for {summary['n_total']} folder(s)  (mode: {mode}):\n\n"
        f"{detail_text}\n\n"
        "Resume             — skip completed, process remaining\n"
        "Restart All        — reprocess everything (picks preserved)\n"
        "Redo Last In-Progress — redo the folder where you stopped"
    )

    result = {"action": "quit"}

    fig = plt.figure(figsize=(8.5, 3.8))
    fig.canvas.manager.set_window_title("Core Photo — Progress")
    fig.text(0.5, 0.58, text, ha="center", va="center", fontsize=10, family="monospace")

    def _make_cb(action):
        def _cb(_event=None):
            result["action"] = action
            plt.close(fig)
        return _cb

    ax_resume = fig.add_axes([0.03, 0.06, 0.18, 0.12])
    ax_restart_all = fig.add_axes([0.24, 0.06, 0.18, 0.12])
    ax_redo_last = fig.add_axes([0.45, 0.06, 0.30, 0.12])
    ax_quit = fig.add_axes([0.78, 0.06, 0.18, 0.12])
    btn_resume = Button(ax_resume, "Resume")
    btn_restart_all = Button(ax_restart_all, "Restart All")
    btn_redo_last = Button(ax_redo_last, "Redo Last In-Progress")
    btn_quit = Button(ax_quit, "Quit")
    btn_resume.on_clicked(_make_cb("resume"))
    btn_restart_all.on_clicked(_make_cb("restart_all"))
    btn_redo_last.on_clicked(_make_cb("redo_last"))
    btn_quit.on_clicked(_make_cb("quit"))

    plt.show(block=True)
    del btn_resume, btn_restart_all, btn_redo_last, btn_quit
    plt.close(fig)

    return result["action"]

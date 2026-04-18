#!/usr/bin/env python3
"""
King Legacy Fish Macro - Linux/Xorg Port
Original by AsphaltCake
Ported to Linux/Xorg

Dependencies:
    pip install mss numpy pillow keyboard python-xlib
    sudo apt install python3-tk  # or: sudo dnf install python3-tkinter

Note: keyboard module needs either:
    - sudo to run, OR
    - add your user to the 'input' group: sudo usermod -aG input $USER
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
from PIL import ImageGrab, ImageDraw, ImageTk
import json
import os
import sys
import mss
import numpy as np
import webbrowser
import requests
from datetime import datetime

# Linux mouse control via Xlib
try:
    from Xlib import X, display as Xdisplay
    from Xlib.ext.xtest import fake_input
    XLIB_AVAILABLE = True
except ImportError:
    XLIB_AVAILABLE = False
    print("Warning: python-xlib not installed. Mouse control won't work.")
    print("Install with: pip install python-xlib")

try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False
    print("Warning: keyboard module not installed. Hotkeys won't work.")
    print("Install with: pip install keyboard")

try:
    import pyautogui
except ImportError:
    pyautogui = None


# ── Xlib mouse helpers (replaces win32api.mouse_event) ──────────────────────

_xdisplay = None

def _get_xdisplay():
    global _xdisplay
    if _xdisplay is None and XLIB_AVAILABLE:
        _xdisplay = Xdisplay.Display()
    return _xdisplay

def mouse_down():
    """Simulate left mouse button press via Xlib."""
    if not XLIB_AVAILABLE:
        return
    d = _get_xdisplay()
    fake_input(d, X.ButtonPress, 1)
    d.sync()

def mouse_up():
    """Simulate left mouse button release via Xlib."""
    if not XLIB_AVAILABLE:
        return
    d = _get_xdisplay()
    fake_input(d, X.ButtonRelease, 1)
    d.sync()


# ── Settings path ────────────────────────────────────────────────────────────

def get_settings_path():
    if getattr(sys, 'frozen', False):
        app_dir = os.path.dirname(sys.executable)
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(app_dir, 'KingLegacySettings.txt')


# ── SingleBoxSelector ────────────────────────────────────────────────────────

class SingleBoxSelector:
    """Fullscreen overlay for selecting a single box area."""

    def __init__(self, parent, screenshot, initial_area, box_name, callback):
        self.callback = callback
        self.screenshot = screenshot
        self.box_name = box_name

        self.window = tk.Toplevel(parent)
        self.window.attributes('-fullscreen', True)
        self.window.attributes('-topmost', True)
        self.window.configure(cursor='cross')

        self.screen_width = self.window.winfo_screenwidth()
        self.screen_height = self.window.winfo_screenheight()

        self.canvas = tk.Canvas(
            self.window,
            width=self.screen_width,
            height=self.screen_height,
            highlightthickness=0
        )
        self.canvas.pack()

        self.photo = ImageTk.PhotoImage(screenshot)
        self.canvas.create_image(0, 0, image=self.photo, anchor='nw')

        self.x1 = initial_area['x']
        self.y1 = initial_area['y']
        self.x2 = self.x1 + initial_area['width']
        self.y2 = self.y1 + initial_area['height']

        self.dragging = False
        self.drag_corner = None
        self.resize_threshold = 10

        self.rect = self.canvas.create_rectangle(
            self.x1, self.y1, self.x2, self.y2,
            outline='#2196F3', width=3,
            fill='#2196F3', stipple='gray50'
        )

        label_x = self.x1 + (self.x2 - self.x1) // 2
        self.label = self.canvas.create_text(
            label_x, self.y1 - 20,
            text=box_name,
            font=('Arial', 14, 'bold'),
            fill='#2196F3'
        )

        self.handles = []
        self.create_handles()

        instructions = 'Drag corners to resize | Drag box to move | Press ENTER to save | ESC to cancel'
        self.canvas.create_text(
            self.screen_width // 2, 30,
            text=instructions,
            font=('Arial', 12, 'bold'),
            fill='white',
            tags='instructions'
        )

        self.canvas.bind('<Button-1>', self.on_mouse_down)
        self.canvas.bind('<B1-Motion>', self.on_mouse_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_mouse_up)
        self.canvas.bind('<Motion>', self.on_mouse_move)
        self.window.bind('<Return>', lambda e: self.save_and_close())
        self.window.bind('<Escape>', lambda e: self.cancel())

    def create_handles(self):
        handle_size = 12
        for handle in self.handles:
            self.canvas.delete(handle)
        self.handles.clear()

        corners = [
            (self.x1, self.y1),
            (self.x2, self.y1),
            (self.x1, self.y2),
            (self.x2, self.y2),
        ]
        for x, y in corners:
            handle = self.canvas.create_rectangle(
                x - handle_size, y - handle_size,
                x + handle_size, y + handle_size,
                fill='', outline='#2196F3', width=2
            )
            self.handles.append(handle)
            corner_marker = self.canvas.create_rectangle(
                x - 3, y - 3, x + 3, y + 3,
                fill='red', outline='white', width=1
            )
            self.handles.append(corner_marker)
            line1 = self.canvas.create_line(
                x - handle_size, y, x + handle_size, y,
                fill='yellow', width=1
            )
            line2 = self.canvas.create_line(
                x, y - handle_size, x, y + handle_size,
                fill='yellow', width=1
            )
            self.handles.append(line1)
            self.handles.append(line2)

    def get_corner_at_position(self, x, y):
        corners = {
            'nw': (self.x1, self.y1),
            'ne': (self.x2, self.y1),
            'sw': (self.x1, self.y2),
            'se': (self.x2, self.y2),
        }
        for corner, (cx, cy) in corners.items():
            if abs(x - cx) < self.resize_threshold and abs(y - cy) < self.resize_threshold:
                return corner
        return None

    def is_inside_box(self, x, y):
        return self.x1 < x < self.x2 and self.y1 < y < self.y2

    def on_mouse_down(self, event):
        self.drag_start_x = event.x
        self.drag_start_y = event.y
        corner = self.get_corner_at_position(event.x, event.y)
        if corner:
            self.dragging = True
            self.drag_corner = corner
            return
        if self.is_inside_box(event.x, event.y):
            self.dragging = True
            self.drag_corner = 'move'

    def on_mouse_drag(self, event):
        if not self.dragging:
            return
        dx = event.x - self.drag_start_x
        dy = event.y - self.drag_start_y
        if self.drag_corner == 'move':
            self.x1 += dx; self.y1 += dy
            self.x2 += dx; self.y2 += dy
        elif self.drag_corner == 'nw':
            self.x1, self.y1 = event.x, event.y
        elif self.drag_corner == 'ne':
            self.x2, self.y1 = event.x, event.y
        elif self.drag_corner == 'sw':
            self.x1, self.y2 = event.x, event.y
        elif self.drag_corner == 'se':
            self.x2, self.y2 = event.x, event.y
        if self.x1 > self.x2:
            self.x1, self.x2 = self.x2, self.x1
        if self.y1 > self.y2:
            self.y1, self.y2 = self.y2, self.y1
        self.update_box()
        self.drag_start_x = event.x
        self.drag_start_y = event.y

    def on_mouse_up(self, event):
        self.dragging = False
        self.drag_corner = None

    def on_mouse_move(self, event):
        corner = self.get_corner_at_position(event.x, event.y)
        if corner:
            cursors = {
                'nw': 'top_left_corner',
                'ne': 'top_right_corner',
                'sw': 'bottom_left_corner',
                'se': 'bottom_right_corner',
            }
            self.window.configure(cursor=cursors.get(corner, 'cross'))
            return
        if self.is_inside_box(event.x, event.y):
            self.window.configure(cursor='fleur')
        else:
            self.window.configure(cursor='cross')

    def update_box(self):
        self.canvas.coords(self.rect, self.x1, self.y1, self.x2, self.y2)
        label_x = self.x1 + (self.x2 - self.x1) // 2
        self.canvas.coords(self.label, label_x, self.y1 - 20)
        self.create_handles()

    def save_and_close(self):
        coords = {
            'x': int(self.x1),
            'y': int(self.y1),
            'width': int(self.x2 - self.x1),
            'height': int(self.y2 - self.y1),
        }
        if self.callback:
            self.callback(coords)
        self.window.destroy()

    def cancel(self):
        self.window.destroy()


# ── MacroGUI ─────────────────────────────────────────────────────────────────

class MacroGUI:

    def __init__(self, root):
        self.root = root
        self.root.title('King Legacy Fish Macro (Linux)')
        self.root.geometry('420x420')
        self.root.resizable(False, False)
        self.root.attributes('-topmost', True)

        self.is_running = False
        self.change_area_enabled = False
        self.area_selector = None
        self.main_loop_thread = None

        self.settings_file = get_settings_path()

        self.hotkeys = {
            'start_stop': 'f1',
            'change_area': 'f2',
            'exit': 'f3',
        }

        self.default_resolution = (2560, 1440)
        self.default_fish_box = {'x': 820, 'y': 992, 'width': 921, 'height': 39}
        self.fish_box = self.default_fish_box.copy()

        # ── Webhook & stats ──────────────────────────────────────────────────
        self.webhook_url = "https://discord.com/api/webhooks/1492728016747626666/8KcekuqC4KN_0uRKJOobqfdiQubipONo3eQt8xvfKB9tUjTnhwc-PMt15kWG9F_rhrRm"
        self.webhook_enabled = False
        self.webhook_interval = 30          # minutes between periodic stats
        self.fish_common = 0
        self.fish_uncommon = 0
        self.fish_rare = 0
        self.fish_legendary = 0
        self.devil_fruits = 0
        self.session_start_time = None
        self.last_webhook_time = 0
        # ─────────────────────────────────────────────────────────────────────

        self.load_settings()

        self.rebinding_key = None
        self.rebind_hook = None

        self.setup_gui()
        self.setup_hotkeys()

    def setup_gui(self):
        main_frame = ttk.Frame(self.root, padding='20')
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        header = ttk.Label(main_frame, text='Hotkeys', font=('Arial', 12, 'bold'))
        header.grid(row=0, column=0, columnspan=3, pady=(0, 15))

        ttk.Label(main_frame, text='Start/Stop:', width=15).grid(
            row=1, column=0, sticky=tk.W, pady=5)
        self.start_stop_label = ttk.Label(
            main_frame,
            text=self.hotkeys['start_stop'].upper(),
            font=('Arial', 10, 'bold'), width=10,
            relief=tk.SUNKEN, anchor=tk.CENTER
        )
        self.start_stop_label.grid(row=1, column=1, padx=5)
        self.start_stop_btn = ttk.Button(
            main_frame, text='Rebind', width=8,
            command=lambda: self.start_rebind('start_stop')
        )
        self.start_stop_btn.grid(row=1, column=2, padx=5)

        ttk.Label(main_frame, text='Change Area:', width=15).grid(
            row=2, column=0, sticky=tk.W, pady=5)
        self.change_area_label = ttk.Label(
            main_frame,
            text=self.hotkeys['change_area'].upper(),
            font=('Arial', 10, 'bold'), width=10,
            relief=tk.SUNKEN, anchor=tk.CENTER
        )
        self.change_area_label.grid(row=2, column=1, padx=5)
        self.change_area_btn = ttk.Button(
            main_frame, text='Rebind', width=8,
            command=lambda: self.start_rebind('change_area')
        )
        self.change_area_btn.grid(row=2, column=2, padx=5)

        ttk.Label(main_frame, text='Exit:', width=15).grid(
            row=3, column=0, sticky=tk.W, pady=5)
        self.exit_label = ttk.Label(
            main_frame,
            text=self.hotkeys['exit'].upper(),
            font=('Arial', 10, 'bold'), width=10,
            relief=tk.SUNKEN, anchor=tk.CENTER
        )
        self.exit_label.grid(row=3, column=1, padx=5)
        self.exit_btn = ttk.Button(
            main_frame, text='Rebind', width=8,
            command=lambda: self.start_rebind('exit')
        )
        self.exit_btn.grid(row=3, column=2, padx=5)

        self.status_label = ttk.Label(
            main_frame, text='Status: Stopped', foreground='red'
        )
        self.status_label.grid(row=4, column=0, columnspan=3, pady=(20, 0))

        # ── Webhook section ──────────────────────────────────────────────────
        sep = ttk.Separator(main_frame, orient='horizontal')
        sep.grid(row=5, column=0, columnspan=3, sticky='ew', pady=(15, 8))

        webhook_header = ttk.Label(main_frame, text='🔔 Discord Webhook',
                                   font=('Arial', 10, 'bold'))
        webhook_header.grid(row=6, column=0, columnspan=3, sticky=tk.W, pady=(0, 5))

        # Enable checkbox
        self.webhook_enabled_var = tk.BooleanVar(value=self.webhook_enabled)
        webhook_check = ttk.Checkbutton(main_frame,
                                        text='Enable Webhook Notifications',
                                        variable=self.webhook_enabled_var,
                                        command=self.toggle_webhook)
        webhook_check.grid(row=7, column=0, columnspan=3, sticky=tk.W)

        # URL entry
        ttk.Label(main_frame, text='Webhook URL:').grid(
            row=8, column=0, sticky=tk.W, pady=(6, 0))
        self.webhook_url_var = tk.StringVar(value=self.webhook_url)
        webhook_entry = ttk.Entry(main_frame, textvariable=self.webhook_url_var, width=38)
        webhook_entry.grid(row=9, column=0, columnspan=3, sticky='ew', pady=(2, 6))
        webhook_entry.bind('<FocusOut>', lambda e: self.update_webhook_url())

        # Interval + test button on the same row
        interval_frame = ttk.Frame(main_frame)
        interval_frame.grid(row=10, column=0, columnspan=3, sticky='ew')

        ttk.Label(interval_frame, text='Stats interval (min):').pack(side=tk.LEFT)
        self.webhook_interval_var = tk.IntVar(value=self.webhook_interval)
        interval_spin = ttk.Spinbox(interval_frame, from_=1, to=120, increment=1,
                                    textvariable=self.webhook_interval_var, width=5)
        interval_spin.pack(side=tk.LEFT, padx=(4, 12))
        interval_spin.bind('<Return>', lambda e: self.update_webhook_interval())
        interval_spin.bind('<FocusOut>', lambda e: self.update_webhook_interval())

        test_btn = ttk.Button(interval_frame, text='🧪 Test Webhook',
                              command=self.test_webhook)
        test_btn.pack(side=tk.LEFT)
        # ─────────────────────────────────────────────────────────────────────

    def setup_hotkeys(self):
        if not KEYBOARD_AVAILABLE:
            print("Hotkeys unavailable - keyboard module not installed or missing permissions.")
            print("Try running with sudo, or: sudo usermod -aG input $USER (then re-login)")
            return
        try:
            keyboard.unhook_all()
            keyboard.add_hotkey(self.hotkeys['start_stop'], self.toggle_start_stop)
            keyboard.add_hotkey(self.hotkeys['change_area'], self.toggle_change_area)
            keyboard.add_hotkey(self.hotkeys['exit'], self.exit_program)
        except Exception as e:
            print(f"Could not set up hotkeys: {e}")

    def start_rebind(self, key_name):
        if self.rebinding_key:
            return
        self.rebinding_key = key_name
        label_map = {
            'start_stop': self.start_stop_label,
            'change_area': self.change_area_label,
            'exit': self.exit_label,
        }
        label_map[key_name].config(text='Press key...', foreground='blue')
        for btn in [self.start_stop_btn, self.change_area_btn, self.exit_btn]:
            btn.config(state=tk.DISABLED)
        if KEYBOARD_AVAILABLE:
            try:
                self.rebind_hook = keyboard.on_press(self.on_rebind_key_press, suppress=True)
            except Exception as e:
                print(f"Rebind error: {e}")
                self.rebinding_key = None

    def on_rebind_key_press(self, event):
        if not self.rebinding_key:
            return
        new_key = event.name
        self.hotkeys[self.rebinding_key] = new_key
        label_map = {
            'start_stop': self.start_stop_label,
            'change_area': self.change_area_label,
            'exit': self.exit_label,
        }
        label_map[self.rebinding_key].config(text=new_key.upper(), foreground='black')
        for btn in [self.start_stop_btn, self.change_area_btn, self.exit_btn]:
            btn.config(state=tk.NORMAL)
        if self.rebind_hook and KEYBOARD_AVAILABLE:
            try:
                keyboard.unhook(self.rebind_hook)
            except Exception:
                pass
        self.rebind_hook = None
        self.rebinding_key = None
        self.setup_hotkeys()

    def toggle_start_stop(self):
        self.is_running = not self.is_running
        if self.is_running:
            self.session_start_time = time.time()
            self.last_webhook_time = time.time()
            self.fish_common = 0
            self.fish_uncommon = 0
            self.fish_rare = 0
            self.fish_legendary = 0
            self.devil_fruits = 0
            self.status_label.config(text='Status: Running', foreground='green')
            self.main_loop_thread = threading.Thread(target=self.main_loop, daemon=True)
            self.main_loop_thread.start()
        else:
            self.status_label.config(text='Status: Stopped', foreground='red')
            # Send final stats + stopped alert
            threading.Thread(target=self._send_stopped_report, daemon=True).start()

    def _send_stopped_report(self):
        """Send final stats then a 'Macro Stopped' embed, matching Image 1."""
        self.send_webhook_stats()
        if not self.webhook_enabled or not self.webhook_url:
            return
        try:
            embed = {
                'title': '🔴 Fishing Macro Stopped',
                'description': 'Session ended.',
                'color': 0xef4444,
                'timestamp': datetime.utcnow().isoformat(),
                'footer': {'text': 'King Legacy Fish Macro - Linux'}
            }
            requests.post(self.webhook_url, json={'embeds': [embed]}, timeout=5)
        except Exception as e:
            print(f'❌ Webhook stopped-alert error: {e}')

    def toggle_change_area(self):
        self.change_area_enabled = not self.change_area_enabled
        if self.change_area_enabled:
            print('Change Area: ON - Opening area selector...')
            self.open_area_selector()
        else:
            print('Change Area: OFF - Saving and closing area selector...')
            if self.area_selector and self.area_selector.window.winfo_exists():
                coords = {
                    'x': int(self.area_selector.x1),
                    'y': int(self.area_selector.y1),
                    'width': int(self.area_selector.x2 - self.area_selector.x1),
                    'height': int(self.area_selector.y2 - self.area_selector.y1),
                }
                self.fish_box = coords
                self.save_settings()
                print(f"Fish Box saved: x={coords['x']}, y={coords['y']}, width={coords['width']}, height={coords['height']}")
                self.area_selector.window.destroy()
                self.area_selector = None

    def is_white_with_tolerance(self, r, g, b, tolerance=3):
        return abs(r - 255) <= tolerance and abs(g - 255) <= tolerance and abs(b - 255) <= tolerance

    def main_loop(self):
        print('Main loop started')
        offset = None
        calibrated = False
        mouse_is_down = False
        last_line_found_time = None
        fishing_state = 'idle'

        def cast_rod():
            nonlocal mouse_is_down
            print('Casting rod...')
            # Make sure mouse is released before casting
            if mouse_is_down:
                mouse_up()
                mouse_is_down = False
                time.sleep(0.1)
            mouse_down()
            time.sleep(0.5)
            mouse_up()
            # Wait for the cast animation before scanning
            time.sleep(2.0)
            print('Rod cast!')

        cast_rod()
        fishing_state = 'waiting_for_line'
        last_line_found_time = time.time()

        with mss.mss() as sct:
            while self.is_running:
                monitor = {
                    'left': self.fish_box['x'],
                    'top': self.fish_box['y'],
                    'width': self.fish_box['width'],
                    'height': self.fish_box['height'],
                }
                screenshot = sct.grab(monitor)
                img = np.array(screenshot)

                # Find white line (fishing indicator)
                line_x = None
                found_line = False
                for y in range(img.shape[0]):
                    for x in range(img.shape[1]):
                        r, g, b = img[y, x, 0], img[y, x, 1], img[y, x, 2]
                        if r == 255 and g == 255 and b == 255:
                            line_x = self.fish_box['x'] + x
                            found_line = True
                            break
                    if found_line:
                        break

                if not found_line:
                    # Release mouse if it was held
                    if mouse_is_down:
                        mouse_up()
                        mouse_is_down = False

                    if fishing_state == 'waiting_for_line':
                        elapsed = time.time() - last_line_found_time
                        if elapsed > 20:
                            print(f'No line detected for {elapsed:.1f}s - recasting...')
                            calibrated = False
                            offset = None
                            cast_rod()
                            fishing_state = 'waiting_for_line'
                            last_line_found_time = time.time()
                    elif fishing_state == 'tracking':
                        print('Line disappeared - fish caught! Waiting 1.5s...')
                        self.fish_common += 1   # King Legacy has no rarity detection; counts as Common
                        # Send periodic stats if interval elapsed
                        if (self.webhook_enabled and self.webhook_url and
                                time.time() - self.last_webhook_time >= self.webhook_interval * 60):
                            threading.Thread(target=self.send_webhook_stats, daemon=True).start()
                        time.sleep(1.5)
                        print('Recasting...')
                        calibrated = False
                        offset = None
                        cast_rod()
                        fishing_state = 'waiting_for_line'
                        last_line_found_time = time.time()
                    continue

                if fishing_state == 'waiting_for_line':
                    print('Line detected! Starting to track...')
                    fishing_state = 'tracking'

                last_line_found_time = time.time()

                # Find bar (right edge)
                bottom_y = img.shape[0] - 1
                right_bar_pos = None
                found_bar = False
                for x in range(img.shape[1] - 1, -1, -1):
                    r, g, b = int(img[bottom_y, x, 0]), int(img[bottom_y, x, 1]), int(img[bottom_y, x, 2])
                    if self.is_white_with_tolerance(r, g, b):
                        right_bar_pos = x
                        found_bar = True
                        break

                # Calibrate bar offset
                if found_bar and not calibrated:
                    print('Calibrating bar offset...')
                    left_bar_pos = None
                    for x in range(img.shape[1]):
                        r, g, b = int(img[bottom_y, x, 0]), int(img[bottom_y, x, 1]), int(img[bottom_y, x, 2])
                        if self.is_white_with_tolerance(r, g, b):
                            left_bar_pos = x
                            break
                    if left_bar_pos is not None and right_bar_pos is not None:
                        width = right_bar_pos - left_bar_pos
                        offset = width // 2
                        calibrated = True
                        print(f'Calibrated - Left: {left_bar_pos}, Right: {right_bar_pos}, Width: {width}, Offset: {offset}')

                bar_x = None
                if found_bar and calibrated:
                    right_bar_absolute = self.fish_box['x'] + right_bar_pos
                    bar_x = right_bar_absolute - offset
                elif found_bar and not calibrated:
                    bar_x = None

                # Mouse control logic
                if found_bar and calibrated and bar_x is not None and line_x is not None:
                    if bar_x < line_x:
                        if not mouse_is_down:
                            mouse_down()
                            mouse_is_down = True
                    elif bar_x >= line_x:
                        if mouse_is_down:
                            mouse_up()
                            mouse_is_down = False
                else:
                    if mouse_is_down:
                        mouse_up()
                        mouse_is_down = False

                line_str = str(line_x) if found_line else 'Not found'
                bar_str = str(bar_x) if (found_bar and calibrated and bar_x is not None) else 'Not found'
                print(f'Line: {line_str} | Bar: {bar_str}')

        if mouse_is_down:
            mouse_up()
        print('Main loop stopped')

    def open_area_selector(self):
        if self.area_selector:
            return
        screenshot = ImageGrab.grab()
        self.area_selector = SingleBoxSelector(
            self.root, screenshot, self.fish_box,
            'Fish Box', self.on_area_selected
        )

    def close_area_selector(self):
        if self.area_selector and self.area_selector.window.winfo_exists():
            self.area_selector.window.destroy()
        self.area_selector = None
        self.change_area_enabled = False

    def on_area_selected(self, coords):
        self.fish_box = coords
        self.area_selector = None
        self.change_area_enabled = False
        self.save_settings()
        print(f"Fish Box saved: x={coords['x']}, y={coords['y']}, width={coords['width']}, height={coords['height']}")

    def load_settings(self):
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    data = json.load(f)
                self.hotkeys = data.get('hotkeys', self.hotkeys)
                self.fish_box = data.get('fish_box', self.fish_box)
                self.webhook_url = data.get('webhook_url', self.webhook_url)
                self.webhook_enabled = data.get('webhook_enabled', self.webhook_enabled)
                self.webhook_interval = data.get('webhook_interval', self.webhook_interval)
                print(f'Settings loaded from {self.settings_file}')
            except Exception as e:
                print(f'Error loading settings: {e}')
        else:
            print('First launch detected - scaling default fish box to current resolution...')
            self.scale_fish_box_to_resolution()
            self.save_settings()

    def scale_fish_box_to_resolution(self):
        # We can't call winfo before mainloop in some cases, use Xlib if available
        try:
            if XLIB_AVAILABLE:
                d = _get_xdisplay()
                screen = d.screen()
                screen_width = screen.width_in_pixels
                screen_height = screen.height_in_pixels
            else:
                screen_width = self.root.winfo_screenwidth()
                screen_height = self.root.winfo_screenheight()
        except Exception:
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()

        default_width, default_height = self.default_resolution
        scale_x = screen_width / default_width
        scale_y = screen_height / default_height
        self.fish_box = {
            'x': int(self.default_fish_box['x'] * scale_x),
            'y': int(self.default_fish_box['y'] * scale_y),
            'width': int(self.default_fish_box['width'] * scale_x),
            'height': int(self.default_fish_box['height'] * scale_y),
        }
        print(f'Scaled from {default_width}x{default_height} to {screen_width}x{screen_height}')
        print(f"Fish Box: x={self.fish_box['x']}, y={self.fish_box['y']}, width={self.fish_box['width']}, height={self.fish_box['height']}")

    def save_settings(self):
        try:
            data = {
                'hotkeys': self.hotkeys,
                'fish_box': self.fish_box,
                'webhook_url': self.webhook_url,
                'webhook_enabled': self.webhook_enabled,
                'webhook_interval': self.webhook_interval,
            }
            with open(self.settings_file, 'w') as f:
                json.dump(data, f, indent=4)
            print(f'Settings saved to {self.settings_file}')
        except Exception as e:
            print(f'Error saving settings: {e}')

    # ── Webhook methods (ported from ZkMacroGpo MAC VERSION) ─────────────────

    def toggle_webhook(self):
        """Toggle webhook notifications on/off."""
        self.webhook_enabled = self.webhook_enabled_var.get()
        self.save_settings()
        if self.webhook_enabled:
            print('✓ Webhook notifications enabled')
            if not self.webhook_url:
                messagebox.showwarning(
                    'Webhook URL Missing',
                    'Please enter your Discord webhook URL to receive notifications!'
                )
        else:
            print('✓ Webhook notifications disabled')

    def update_webhook_url(self):
        """Save updated webhook URL."""
        self.webhook_url = self.webhook_url_var.get().strip()
        self.save_settings()
        print('✓ Webhook URL updated')

    def update_webhook_interval(self):
        """Save updated stats interval."""
        self.webhook_interval = self.webhook_interval_var.get()
        self.save_settings()
        print(f'✓ Webhook interval: {self.webhook_interval} minutes')

    def test_webhook(self):
        """Send a test message to the configured webhook."""
        self.update_webhook_url()
        if not self.webhook_url:
            messagebox.showerror('Error', 'Please enter a webhook URL first!')
            return
        print('Testing webhook...')
        # Temporarily enable for the test even if checkbox is off
        saved = self.webhook_enabled
        self.webhook_enabled = True
        success = self.send_webhook_notification(
            '🧪 This is a test notification from King Legacy Fish Macro!',
            color=0x10b981
        )
        self.webhook_enabled = saved
        if success:
            messagebox.showinfo('Success', 'Webhook test successful! Check your Discord channel.')
        else:
            messagebox.showerror('Error', 'Webhook test failed. Please check your URL and try again.')

    def send_webhook_notification(self, message, color=0x3b82f6):
        """Send a simple embed message to the Discord webhook."""
        if not self.webhook_enabled or not self.webhook_url:
            return False
        try:
            embed = {
                'title': '🎣 King Legacy Fish Macro',
                'description': message,
                'color': color,
                'timestamp': datetime.utcnow().isoformat(),
                'footer': {'text': 'King Legacy Fish Macro - Linux'}
            }
            data = {'embeds': [embed]}
            response = requests.post(self.webhook_url, json=data, timeout=10)
            if response.status_code == 204:
                print(f'✓ Webhook sent: {message}')
                return True
            else:
                print(f'✗ Webhook failed: {response.status_code}')
                return False
        except Exception as e:
            print(f'✗ Webhook error: {e}')
            return False

    def send_webhook_stats(self):
        """Send fishing stats to Discord — layout matches Image 1."""
        if not self.webhook_enabled or not self.webhook_url:
            return
        try:
            elapsed = time.time() - self.session_start_time if self.session_start_time else 0
            hours = int(elapsed // 3600)
            minutes = int((elapsed % 3600) // 60)

            total_fish = self.fish_common + self.fish_uncommon + self.fish_rare + self.fish_legendary
            fish_per_hour = (total_fish / elapsed * 3600) if elapsed > 0 else 0

            embed = {
                'title': '📊 Fishing Session Stats',
                'color': 3447003,
                'fields': [
                    # Row 1 — single wide field
                    {'name': '⏱️ Session Time',
                     'value': f'{hours}h {minutes}m',
                     'inline': False},
                    # Row 2 — three inline fields
                    {'name': '🐟 Total Fish',  'value': str(total_fish),          'inline': True},
                    {'name': '📈 Fish/Hour',   'value': f'{fish_per_hour:.1f}',   'inline': True},
                    {'name': '⚪ Common',      'value': str(self.fish_common),     'inline': True},
                    # Row 3 — three inline fields
                    {'name': '🟢 Uncommon',   'value': str(self.fish_uncommon),   'inline': True},
                    {'name': '🔵 Rare',        'value': str(self.fish_rare),       'inline': True},
                    {'name': '🌈 Legendary',   'value': str(self.fish_legendary),  'inline': True},
                    # Row 4 — single wide field
                    {'name': '🍎 Devil Fruits', 'value': str(self.devil_fruits),   'inline': False},
                ],
                'timestamp': datetime.utcnow().isoformat(),
                'footer': {'text': 'King Legacy Fish Macro - Linux'}
            }
            payload = {'embeds': [embed]}
            response = requests.post(self.webhook_url, json=payload, timeout=5)
            if response.status_code == 204:
                self.last_webhook_time = time.time()
                print('✅ Stats sent to Discord webhook')
            else:
                print(f'⚠️ Webhook stats failed: {response.status_code}')
        except Exception as e:
            print(f'❌ Webhook error: {e}')

    # ─────────────────────────────────────────────────────────────────────────

    def exit_program(self):
        self.is_running = False
        self.save_settings()
        if KEYBOARD_AVAILABLE:
            try:
                keyboard.unhook_all()
            except Exception:
                pass
        self.root.quit()
        self.root.destroy()


# ── Terms / first launch ─────────────────────────────────────────────────────

def check_first_launch_and_terms():
    settings_file = get_settings_path()
    if os.path.exists(settings_file):
        return True, False

    print('First launch detected - showing Terms of Use...')
    terms_text = (
        '═══════════════════════════════════════════════════════\n'
        '              KING LEGACY FISHING MACRO\n'
        '                    by AsphaltCake\n'
        '          Linux/Xorg Port (community contribution)\n'
        '═══════════════════════════════════════════════════════\n\n'
        'By using this macro, you agree to the following:\n\n'
        '1. USAGE & LIABILITY\n'
        '   • This macro is for King Legacy fishing automation\n'
        '   • Author is NOT responsible for any issues\n'
        '   • No guarantee of functionality\n\n'
        '2. COMPLIANCE\n'
        '   • You are responsible for following game rules\n'
        '   • Use responsibly and at your own discretion\n\n'
        '3. CREDITS\n'
        '   • Original Author: AsphaltCake\n'
        '   • YouTube: https://www.youtube.com/@AsphaltCake\n'
        '   • Linux port: community contribution\n\n'
        'By clicking OK, you accept these terms.\n'
        '═══════════════════════════════════════════════════════\n'
    )
    root = tk.Tk()
    root.withdraw()
    result = messagebox.askokcancel('Terms of Use - King Legacy Fishing Macro', terms_text, icon='info')
    root.destroy()
    if result:
        print('Terms accepted!')
        return True, True
    else:
        print('Terms declined. Exiting...')
        return False, False


# ── Entry point ──────────────────────────────────────────────────────────────

def main():
    if not XLIB_AVAILABLE:
        print("ERROR: python-xlib is required for mouse control on Linux.")
        print("Install it with: pip install python-xlib")
        sys.exit(1)

    terms_accepted, is_first_launch = check_first_launch_and_terms()
    if not terms_accepted:
        sys.exit(0)

    # No auto-subscribe shenanigans in the Linux port.
    # If you enjoy the tool, visit: https://www.youtube.com/@AsphaltCake

    root = tk.Tk()
    app = MacroGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()

import tkinter as tk
from tkinter import ttk
import keyboard
from PIL import ImageGrab, ImageTk, Image
import json
import os
import sys
import ctypes
import threading
import time
import mss
import numpy as np
import cv2
import warnings
try:
    from ultralytics import YOLO
except Exception as e:
    YOLO = None
    print(f"ERROR: Ultralytics not available: {e}")
import pyautogui
import win32api
import win32con

# Remove PyAutoGUI's built-in delay
pyautogui.PAUSE = 0

# Set DPI awareness to handle Windows scaling properly
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except:
    try:
        ctypes.windll.user32.SetProcessDPIAware()  # Fallback for older Windows
    except:
        pass


class TripleAreaSelector:
    """Full-screen overlay for selecting shake, fish, and friend areas simultaneously"""

    def __init__(self, parent, screenshot, shake_area, fish_area, friend_area, callback, close_key="F1"):
        self.callback = callback
        self.screenshot = screenshot
        self.close_key = close_key.lower()  # Store the key that closes this window

        # Create fullscreen window
        self.window = tk.Toplevel(parent)
        self.window.attributes('-fullscreen', True)
        self.window.attributes('-topmost', True)
        self.window.configure(cursor='cross')

        # Get screen dimensions (physical pixels due to DPI awareness)
        self.screen_width = screenshot.width
        self.screen_height = screenshot.height
        
        # Force window to match screenshot dimensions exactly
        self.window.geometry(f"{self.screen_width}x{self.screen_height}+0+0")

        # Create canvas
        self.canvas = tk.Canvas(self.window, width=self.screen_width, height=self.screen_height, highlightthickness=0)
        self.canvas.pack()
        
        # Display screenshot
        self.photo = ImageTk.PhotoImage(screenshot)
        self.canvas.create_image(0, 0, image=self.photo, anchor='nw')

        # Initialize box coordinates
        self.shake_x1, self.shake_y1 = shake_area["x"], shake_area["y"]
        self.shake_x2, self.shake_y2 = self.shake_x1 + shake_area["width"], self.shake_y1 + shake_area["height"]
        
        self.fish_x1, self.fish_y1 = fish_area["x"], fish_area["y"]
        self.fish_x2, self.fish_y2 = self.fish_x1 + fish_area["width"], self.fish_y1 + fish_area["height"]
        
        self.friend_x1, self.friend_y1 = friend_area["x"], friend_area["y"]
        self.friend_x2, self.friend_y2 = self.friend_x1 + friend_area["width"], self.friend_y1 + friend_area["height"]

        # Drawing state
        self.dragging = False
        self.active_box = None
        self.drag_corner = None
        self.resize_threshold = 10

        # Create Shake Box (Red)
        self.shake_rect = self.canvas.create_rectangle(
            self.shake_x1, self.shake_y1, self.shake_x2, self.shake_y2,
            outline='#f44336', width=2, fill='#f44336', stipple='gray50'
        )
        shake_label_x = self.shake_x1 + (self.shake_x2 - self.shake_x1) // 2
        self.shake_label = self.canvas.create_text(
            shake_label_x, self.shake_y1 - 20, text="Shake Area",
            font=("Arial", 12, "bold"), fill='#f44336'
        )

        # Create Fish Box (Blue)
        self.fish_rect = self.canvas.create_rectangle(
            self.fish_x1, self.fish_y1, self.fish_x2, self.fish_y2,
            outline='#2196F3', width=2, fill='#2196F3', stipple='gray50'
        )
        fish_label_x = self.fish_x1 + (self.fish_x2 - self.fish_x1) // 2
        self.fish_label = self.canvas.create_text(
            fish_label_x, self.fish_y1 - 20, text="Fish Area",
            font=("Arial", 12, "bold"), fill='#2196F3'
        )

        # Create Friend Box (Green)
        self.friend_rect = self.canvas.create_rectangle(
            self.friend_x1, self.friend_y1, self.friend_x2, self.friend_y2,
            outline='#4CAF50', width=2, fill='#4CAF50', stipple='gray50'
        )
        friend_label_x = self.friend_x1 + (self.friend_x2 - self.friend_x1) // 2
        self.friend_label = self.canvas.create_text(
            friend_label_x, self.friend_y1 - 20, text="Friend Area",
            font=("Arial", 12, "bold"), fill='#4CAF50'
        )

        # Corner handles
        self.fish_handles = []
        self.shake_handles = []
        self.friend_handles = []
        self.create_all_handles()
        
        self.current_cursor = 'cross'

        # Bind events
        self.canvas.bind('<Button-1>', self.on_mouse_down)
        self.canvas.bind('<B1-Motion>', self.on_mouse_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_mouse_up)
        self.canvas.bind('<Motion>', self.on_mouse_move)
        
        # Close on Escape or the configured close key - bind to window for focus
        self.window.bind('<Escape>', lambda e: self.save_and_close())
        # Bind the actual key (convert to tkinter format)
        close_key_tk = f'<{self.close_key.upper()}>'
        self.window.bind(close_key_tk, lambda e: self.save_and_close())
        self.window.bind(f'<KeyPress-{self.close_key.upper()}>', lambda e: self.save_and_close())
        
        # Ensure window has focus
        self.window.focus_force()
        self.window.grab_set()

    def create_all_handles(self):
        """Create corner handles for all boxes"""
        self.create_handles_for_box('fish')
        self.create_handles_for_box('shake')
        self.create_handles_for_box('friend')

    def create_handles_for_box(self, box_type):
        """Create corner handles for a specific box"""
        handle_size = 12
        corner_marker_size = 3

        if box_type == 'fish':
            x1, y1, x2, y2 = self.fish_x1, self.fish_y1, self.fish_x2, self.fish_y2
            color = '#2196F3'
            handles_list = self.fish_handles
        elif box_type == 'shake':
            x1, y1, x2, y2 = self.shake_x1, self.shake_y1, self.shake_x2, self.shake_y2
            color = '#f44336'
            handles_list = self.shake_handles
        else:  # friend
            x1, y1, x2, y2 = self.friend_x1, self.friend_y1, self.friend_x2, self.friend_y2
            color = '#4CAF50'
            handles_list = self.friend_handles

        for handle in handles_list:
            self.canvas.delete(handle)
        handles_list.clear()

        corners = [(x1, y1, 'nw'), (x2, y1, 'ne'), (x1, y2, 'sw'), (x2, y2, 'se')]

        for x, y, corner in corners:
            # Outer handle
            handle = self.canvas.create_rectangle(
                x - handle_size, y - handle_size,
                x + handle_size, y + handle_size,
                fill='', outline=color, width=2
            )
            handles_list.append(handle)

            # Corner marker
            corner_marker = self.canvas.create_rectangle(
                x - corner_marker_size, y - corner_marker_size,
                x + corner_marker_size, y + corner_marker_size,
                fill='red', outline='white', width=1
            )
            handles_list.append(corner_marker)

            # Crosshair
            line1 = self.canvas.create_line(x - handle_size, y, x + handle_size, y, fill='yellow', width=1)
            line2 = self.canvas.create_line(x, y - handle_size, x, y + handle_size, fill='yellow', width=1)
            handles_list.append(line1)
            handles_list.append(line2)

    def get_corner_at_position(self, x, y, box_type):
        """Determine which corner is near the cursor"""
        if box_type == 'fish':
            x1, y1, x2, y2 = self.fish_x1, self.fish_y1, self.fish_x2, self.fish_y2
        elif box_type == 'shake':
            x1, y1, x2, y2 = self.shake_x1, self.shake_y1, self.shake_x2, self.shake_y2
        else:  # friend
            x1, y1, x2, y2 = self.friend_x1, self.friend_y1, self.friend_x2, self.friend_y2

        corners = {'nw': (x1, y1), 'ne': (x2, y1), 'sw': (x1, y2), 'se': (x2, y2)}
        
        for corner, (cx, cy) in corners.items():
            if abs(x - cx) < self.resize_threshold and abs(y - cy) < self.resize_threshold:
                return corner
        return None

    def is_inside_box(self, x, y, box_type):
        """Check if point is inside a specific box"""
        if box_type == 'fish':
            return self.fish_x1 < x < self.fish_x2 and self.fish_y1 < y < self.fish_y2
        elif box_type == 'shake':
            return self.shake_x1 < x < self.shake_x2 and self.shake_y1 < y < self.shake_y2
        else:  # friend
            return self.friend_x1 < x < self.friend_x2 and self.friend_y1 < y < self.friend_y2

    def on_mouse_down(self, event):
        """Handle mouse button press"""
        self.drag_start_x = event.x
        self.drag_start_y = event.y

        for box in ['fish', 'shake', 'friend']:
            corner = self.get_corner_at_position(event.x, event.y, box)
            if corner:
                self.dragging = True
                self.active_box = box
                self.drag_corner = corner
                return

            if self.is_inside_box(event.x, event.y, box):
                self.dragging = True
                self.active_box = box
                self.drag_corner = 'move'
                return

    def on_mouse_drag(self, event):
        """Handle mouse drag"""
        if not self.dragging or not self.active_box:
            return

        dx = event.x - self.drag_start_x
        dy = event.y - self.drag_start_y

        if self.active_box == 'fish':
            if self.drag_corner == 'move':
                self.fish_x1 += dx
                self.fish_y1 += dy
                self.fish_x2 += dx
                self.fish_y2 += dy
            elif self.drag_corner == 'nw':
                self.fish_x1, self.fish_y1 = event.x, event.y
            elif self.drag_corner == 'ne':
                self.fish_x2, self.fish_y1 = event.x, event.y
            elif self.drag_corner == 'sw':
                self.fish_x1, self.fish_y2 = event.x, event.y
            elif self.drag_corner == 'se':
                self.fish_x2, self.fish_y2 = event.x, event.y

            if self.fish_x1 > self.fish_x2:
                self.fish_x1, self.fish_x2 = self.fish_x2, self.fish_x1
            if self.fish_y1 > self.fish_y2:
                self.fish_y1, self.fish_y2 = self.fish_y2, self.fish_y1
                
        elif self.active_box == 'shake':
            if self.drag_corner == 'move':
                self.shake_x1 += dx
                self.shake_y1 += dy
                self.shake_x2 += dx
                self.shake_y2 += dy
            elif self.drag_corner == 'nw':
                self.shake_x1, self.shake_y1 = event.x, event.y
            elif self.drag_corner == 'ne':
                self.shake_x2, self.shake_y1 = event.x, event.y
            elif self.drag_corner == 'sw':
                self.shake_x1, self.shake_y2 = event.x, event.y
            elif self.drag_corner == 'se':
                self.shake_x2, self.shake_y2 = event.x, event.y

            if self.shake_x1 > self.shake_x2:
                self.shake_x1, self.shake_x2 = self.shake_x2, self.shake_x1
            if self.shake_y1 > self.shake_y2:
                self.shake_y1, self.shake_y2 = self.shake_y2, self.shake_y1
                
        else:  # friend
            if self.drag_corner == 'move':
                self.friend_x1 += dx
                self.friend_y1 += dy
                self.friend_x2 += dx
                self.friend_y2 += dy
            elif self.drag_corner == 'nw':
                self.friend_x1, self.friend_y1 = event.x, event.y
            elif self.drag_corner == 'ne':
                self.friend_x2, self.friend_y1 = event.x, event.y
            elif self.drag_corner == 'sw':
                self.friend_x1, self.friend_y2 = event.x, event.y
            elif self.drag_corner == 'se':
                self.friend_x2, self.friend_y2 = event.x, event.y

            if self.friend_x1 > self.friend_x2:
                self.friend_x1, self.friend_x2 = self.friend_x2, self.friend_x1
            if self.friend_y1 > self.friend_y2:
                self.friend_y1, self.friend_y2 = self.friend_y2, self.friend_y1

        self.update_boxes()
        self.drag_start_x = event.x
        self.drag_start_y = event.y

    def on_mouse_up(self, event):
        """Handle mouse button release"""
        self.dragging = False
        self.active_box = None
        self.drag_corner = None

    def on_mouse_move(self, event):
        """Handle mouse movement"""
        fish_corner = self.get_corner_at_position(event.x, event.y, 'fish')
        shake_corner = self.get_corner_at_position(event.x, event.y, 'shake')
        friend_corner = self.get_corner_at_position(event.x, event.y, 'friend')

        new_cursor = 'cross'
        if fish_corner or shake_corner or friend_corner:
            corner = fish_corner or shake_corner or friend_corner
            cursors = {'nw': 'top_left_corner', 'ne': 'top_right_corner',
                      'sw': 'bottom_left_corner', 'se': 'bottom_right_corner'}
            new_cursor = cursors.get(corner, 'cross')
        elif (self.is_inside_box(event.x, event.y, 'fish') or 
              self.is_inside_box(event.x, event.y, 'shake') or
              self.is_inside_box(event.x, event.y, 'friend')):
            new_cursor = 'fleur'
        
        if new_cursor != self.current_cursor:
            self.window.configure(cursor=new_cursor)
            self.current_cursor = new_cursor

    def update_boxes(self):
        """Update all box positions"""
        # Update Shake Box
        self.canvas.coords(self.shake_rect, self.shake_x1, self.shake_y1, self.shake_x2, self.shake_y2)
        shake_label_x = self.shake_x1 + (self.shake_x2 - self.shake_x1) // 2
        self.canvas.coords(self.shake_label, shake_label_x, self.shake_y1 - 20)
        
        # Update Fish Box
        self.canvas.coords(self.fish_rect, self.fish_x1, self.fish_y1, self.fish_x2, self.fish_y2)
        fish_label_x = self.fish_x1 + (self.fish_x2 - self.fish_x1) // 2
        self.canvas.coords(self.fish_label, fish_label_x, self.fish_y1 - 20)
        
        # Update Friend Box
        self.canvas.coords(self.friend_rect, self.friend_x1, self.friend_y1, self.friend_x2, self.friend_y2)
        friend_label_x = self.friend_x1 + (self.friend_x2 - self.friend_x1) // 2
        self.canvas.coords(self.friend_label, friend_label_x, self.friend_y1 - 20)
        
        self.create_all_handles()

    def save_and_close(self):
        """Save settings and close the selector"""
        # Prevent multiple calls
        if hasattr(self, '_closing') and self._closing:
            return
        self._closing = True
        
        shake_area = {
            "x": self.shake_x1,
            "y": self.shake_y1,
            "width": self.shake_x2 - self.shake_x1,
            "height": self.shake_y2 - self.shake_y1
        }
        fish_area = {
            "x": self.fish_x1,
            "y": self.fish_y1,
            "width": self.fish_x2 - self.fish_x1,
            "height": self.fish_y2 - self.fish_y1
        }
        friend_area = {
            "x": self.friend_x1,
            "y": self.friend_y1,
            "width": self.friend_x2 - self.friend_x1,
            "height": self.friend_y2 - self.friend_y1
        }
        
        # Release grab before destroying
        try:
            self.window.grab_release()
        except:
            pass
        
        self.callback(shake_area, fish_area, friend_area)
        self.window.destroy()


class IRUSNeuralGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("IRUS Neural")
        
        # Load settings
        self.settings = self._load_settings()
        
        # Hotkey bindings
        self.start_stop_key = self.settings.get("start_stop_key", "F3")
        self.change_area_key = self.settings.get("change_area_key", "F1")
        self.exit_key = self.settings.get("exit_key", "F3")
        
        # Status
        self.is_running = False
        self.area_selector_active = False
        self.current_selector = None  # Store reference to active selector
        
        # Main loop thread control
        self.stop_event = threading.Event()
        self.loop_thread = None
        
        # YOLO model (lazy loaded)
        self.yolo_model = None
        self.shake_model = None
        
        # Debug overlay
        self.show_debug_overlay = self.settings.get("show_debug_overlay", False)
        self.maelstrom_mode = self.settings.get("maelstrom_mode", False)
        self.maelstrom_y_coord = self.settings.get("maelstrom_y_coord", None)
        self.debug_overlay = None
        self.debug_canvas = None
        self.arrow_ids = {}
        
        # PD Controller parameters removed (Gate 3 tracking-only)
        
        # Create GUI elements
        self.create_widgets()
        self.setup_hotkeys()
        
        # Apply always on top setting
        self.root.attributes('-topmost', self.settings.get("always_on_top", False))
        
        # Auto-resize window to fit content
        self.root.update_idletasks()
        self.root.minsize(self.root.winfo_reqwidth(), self.root.winfo_reqheight())
        
        # Save on close
        self.root.protocol("WM_DELETE_WINDOW", self.exit_app)
        
        # Preload YOLO model in main thread to prevent window flashing during fishing
        # Schedule after the main window is fully displayed
        self.root.after(100, self._preload_yolo_model)
        
    def _get_settings_path(self):
        """Get the path to NeuralSettings.json (works for both .py and .exe)"""
        if getattr(sys, 'frozen', False):
            # Running as compiled exe
            app_dir = os.path.dirname(sys.executable)
        else:
            # Running as script
            app_dir = os.path.dirname(os.path.abspath(__file__))
        
        return os.path.join(app_dir, "NeuralSettings.json")
    
    def _load_settings(self):
        """Load settings from NeuralSettings.json"""
        settings_path = self._get_settings_path()
        
        # Get current screen resolution for scaling defaults
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # Reference resolution (where hardcoded values were measured)
        ref_width = 2560
        ref_height = 1440
        
        # Scale factors
        scale_x = screen_width / ref_width
        scale_y = screen_height / ref_height
        
        # Default settings with auto-scaled areas
        default_settings = {
            "start_stop_key": "F3",
            "change_area_key": "F1",
            "exit_key": "F4",
            # Base areas measured at 2560x1440; will be scaled below
            "shake_area": {
                "x": 412,
                "y": 186,
                "width": 1800,
                "height": 877
            },
            "fish_area": {
                "x": 755,
                "y": 1088,
                "width": 1049,
                "height": 184
            },
            "friend_area": {
                "x": 7,
                "y": 1295,
                "width": 115,
                "height": 120
            },
            "always_on_top": True,
            "auto_minimize": True,
            "selected_model": "None",
            "selected_shake_model": "None",
            "shake_model_confidence": 0.75,
            "shake_timeout": 5.0,
            "duplicate_shake_override": 1.0,
            "show_debug_overlay": True,
            "cast_hold_time": 0.5,
            "post_fish_wait": 2.0,
            "gate1_timeout": 20.0,
            "auto_select_rod": True,
            "rod_slot": 1,
            "equipment_bag_slot": 2,
            "auto_select_rod_delay": 250,
            "model_confidence": 0.75,
            "kp": 0.45,
            "kd": 0.1,
            "bar_ratio": 0.6,
            "speed_alpha": 0.9,
            "damping_forward": 2.3,
            "damping_reverse": 0.7,
            "maelstrom_mode": False,
            "maelstrom_y_coord": 95,
            "maelstrom_color_tolerance": 0,
            "maelstrom_scan_left_margin": 0.2,
            "maelstrom_scan_right_margin": 0.3,
            "maelstrom_left_section": 0.2,
            "maelstrom_right_section": 0.4
        }
        
        # Helper to scale and clamp an area to current screen size
        def _scale_and_clamp(area):
            x = int(round(area["x"] * scale_x))
            y = int(round(area["y"] * scale_y))
            w = int(round(area["width"] * scale_x))
            h = int(round(area["height"] * scale_y))
            # Clamp within screen bounds
            x = max(0, min(x, screen_width - 1))
            y = max(0, min(y, screen_height - 1))
            if x + w > screen_width:
                w = max(1, screen_width - x)
            if y + h > screen_height:
                h = max(1, screen_height - y)
            return {"x": x, "y": y, "width": w, "height": h}

        # Helper to only clamp (no scaling)
        def _clamp(area):
            x, y, w, h = area["x"], area["y"], area["width"], area["height"]
            x = max(0, min(int(round(x)), screen_width - 1))
            y = max(0, min(int(round(y)), screen_height - 1))
            w = max(1, int(round(w)))
            h = max(1, int(round(h)))
            if x + w > screen_width:
                w = max(1, screen_width - x)
            if y + h > screen_height:
                h = max(1, screen_height - y)
            return {"x": x, "y": y, "width": w, "height": h}

        if os.path.exists(settings_path):
            try:
                with open(settings_path, 'r') as f:
                    loaded = json.load(f)
                    default_settings.update(loaded)
                    print(f"Settings loaded from: {settings_path}")
                    # If settings contain original 2560x1440 defaults and current screen differs, scale them
                    base_shake = {"x": 412, "y": 186, "width": 1800, "height": 877}
                    base_fish = {"x": 755, "y": 1088, "width": 1049, "height": 184}
                    base_friend = {"x": 7, "y": 1295, "width": 115, "height": 120}
                    base_maelstrom_y = 95  # Base Y coordinate at 2560x1440
                    screen_differs = (screen_width != ref_width) or (screen_height != ref_height)
                    sa = default_settings.get("shake_area", base_shake)
                    fa = default_settings.get("fish_area", base_fish)
                    ra = default_settings.get("friend_area", base_friend)
                    maelstrom_y = default_settings.get("maelstrom_y_coord")
                    if screen_differs:
                        changed = False
                        if sa == base_shake:
                            default_settings["shake_area"] = _scale_and_clamp(sa)
                            changed = True
                        else:
                            default_settings["shake_area"] = _clamp(sa)
                        if fa == base_fish:
                            default_settings["fish_area"] = _scale_and_clamp(fa)
                            changed = True
                        else:
                            default_settings["fish_area"] = _clamp(fa)
                        if ra == base_friend:
                            default_settings["friend_area"] = _scale_and_clamp(ra)
                            changed = True
                        else:
                            default_settings["friend_area"] = _clamp(ra)
                        # Scale maelstrom_y_coord if it matches the base value
                        if maelstrom_y is not None and maelstrom_y == base_maelstrom_y:
                            default_settings["maelstrom_y_coord"] = int(round(base_maelstrom_y * scale_y))
                            changed = True
                        if changed:
                            print("Detected unscaled defaults; auto-scaled areas to current resolution.")
                            self._save_settings(default_settings)
            except Exception as e:
                print(f"Error loading settings: {e}")
        else:
            # Scale defaults for current resolution before first save
            default_settings["shake_area"] = _scale_and_clamp(default_settings["shake_area"])
            default_settings["fish_area"] = _scale_and_clamp(default_settings["fish_area"])
            default_settings["friend_area"] = _scale_and_clamp(default_settings["friend_area"])
            print(f"Settings file not found. Creating scaled defaults for {screen_width}x{screen_height}")
            self._save_settings(default_settings)
        # Log geometry for debugging
        print(f"Screen: {screen_width}x{screen_height} (ref {ref_width}x{ref_height})")
        print(f"Shake area: {default_settings['shake_area']}")
        print(f"Fish area: {default_settings['fish_area']}")
        print(f"Friend area: {default_settings['friend_area']}")
        
        return default_settings
    
    def _save_settings(self, settings=None):
        """Save settings to NeuralSettings.json"""
        if settings is None:
            settings = self.settings
        
        settings_path = self._get_settings_path()
        
        try:
            with open(settings_path, 'w') as f:
                json.dump(settings, f, indent=4)
            print(f"Settings saved to: {settings_path}")
        except Exception as e:
            print(f"Error saving settings: {e}")
        
    def create_widgets(self):
        # Create notebook (tabbed interface)
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # ========== GENERAL TAB ==========
        general_tab = ttk.Frame(notebook, padding="10")
        notebook.add(general_tab, text="General")
        
        row = 0
        
        # Hotkeys
        ttk.Label(general_tab, text="Hotkeys:", font=("Arial", 9, "bold")).grid(row=row, column=0, columnspan=3, sticky=tk.W, pady=(0, 5))
        row += 1
        
        self.start_stop_btn = ttk.Button(general_tab, text=f"Start/Stop ({self.start_stop_key})", 
                                          command=self.toggle_start_stop, width=20)
        self.start_stop_btn.grid(row=row, column=0, padx=5, pady=2)
        ttk.Button(general_tab, text="Rebind", command=lambda: self.rebind("start_stop"), 
                   width=8).grid(row=row, column=1, pady=2)
        row += 1
        
        self.change_area_btn = ttk.Button(general_tab, text=f"Change Area ({self.change_area_key})", 
                                           command=self.change_area, width=20)
        self.change_area_btn.grid(row=row, column=0, padx=5, pady=2)
        ttk.Button(general_tab, text="Rebind", command=lambda: self.rebind("change_area"), 
                   width=8).grid(row=row, column=1, pady=2)
        row += 1
        
        self.exit_btn = ttk.Button(general_tab, text=f"Exit ({self.exit_key})", 
                                    command=self.exit_app, width=20)
        self.exit_btn.grid(row=row, column=0, padx=5, pady=2)
        ttk.Button(general_tab, text="Rebind", command=lambda: self.rebind("exit"), 
                   width=8).grid(row=row, column=1, pady=2)
        row += 1
        
        # Status
        self.status_label = ttk.Label(general_tab, text="Status: Stopped", 
                                       font=("Arial", 10, "bold"))
        self.status_label.grid(row=row, column=0, columnspan=2, pady=8)
        row += 1
        
        # Always on top
        self.always_on_top_var = tk.BooleanVar(value=self.settings.get("always_on_top", False))
        always_on_top_check = ttk.Checkbutton(general_tab, text="Always on Top", 
                                               variable=self.always_on_top_var,
                                               command=self.toggle_always_on_top)
        always_on_top_check.grid(row=row, column=0, padx=5, pady=2, sticky=tk.W)
        row += 1
        
        # Auto Minimize
        self.auto_minimize_var = tk.BooleanVar(value=self.settings.get("auto_minimize", True))
        auto_minimize_check = ttk.Checkbutton(general_tab, text="Auto Minimize", 
                                              variable=self.auto_minimize_var,
                                              command=self.on_auto_minimize_changed)
        auto_minimize_check.grid(row=row, column=0, padx=5, pady=2, sticky=tk.W)
        
        # ========== CAST TAB ==========
        cast_tab = ttk.Frame(notebook, padding="10")
        notebook.add(cast_tab, text="Cast")
        
        row = 0
        
        ttk.Label(cast_tab, text="Cast Hold (ms):").grid(row=row, column=0, padx=5, sticky=tk.W)
        self.cast_hold_var = tk.StringVar(value=f"{self.settings.get('cast_hold_time', 0.5)*1000:.0f}")
        cast_hold_entry = ttk.Entry(cast_tab, textvariable=self.cast_hold_var, width=10)
        cast_hold_entry.grid(row=row, column=1, padx=5, pady=2, sticky=tk.W)
        cast_hold_entry.bind('<Return>', lambda e: self.on_cast_hold_changed())
        cast_hold_entry.bind('<FocusOut>', lambda e: self.on_cast_hold_changed())
        row += 1
        
        # Auto Select Rod checkbox
        self.auto_select_rod_var = tk.BooleanVar(value=self.settings.get('auto_select_rod', False))
        auto_select_checkbox = ttk.Checkbutton(cast_tab, text="Auto Select Rod", 
                                               variable=self.auto_select_rod_var,
                                               command=self.on_auto_select_rod_changed)
        auto_select_checkbox.grid(row=row, column=0, columnspan=2, padx=5, pady=5, sticky=tk.W)
        row += 1
        
        # Rod slot (visible only when auto_select_rod is checked)
        self.rod_label = ttk.Label(cast_tab, text="Rod:")
        self.rod_label.grid(row=row, column=0, padx=5, sticky=tk.W)
        self.rod_var = tk.StringVar(value=str(self.settings.get('rod_slot', 1)))
        self.rod_dropdown = ttk.Combobox(cast_tab, textvariable=self.rod_var, 
                                         values=[str(i) for i in range(10)], width=8, state='readonly')
        self.rod_dropdown.grid(row=row, column=1, padx=5, pady=2, sticky=tk.W)
        self.rod_dropdown.bind('<<ComboboxSelected>>', lambda e: self.on_rod_slot_changed())
        row += 1
        
        # Equipment Bag slot (visible only when auto_select_rod is checked)
        self.bag_label = ttk.Label(cast_tab, text="Equipment Bag:")
        self.bag_label.grid(row=row, column=0, padx=5, sticky=tk.W)
        self.bag_var = tk.StringVar(value=str(self.settings.get('equipment_bag_slot', 2)))
        self.bag_dropdown = ttk.Combobox(cast_tab, textvariable=self.bag_var, 
                                         values=[str(i) for i in range(10)], width=8, state='readonly')
        self.bag_dropdown.grid(row=row, column=1, padx=5, pady=2, sticky=tk.W)
        self.bag_dropdown.bind('<<ComboboxSelected>>', lambda e: self.on_equipment_bag_slot_changed())
        row += 1
        
        # Delay (visible only when auto_select_rod is checked)
        self.delay_label = ttk.Label(cast_tab, text="Delay (ms):")
        self.delay_label.grid(row=row, column=0, padx=5, sticky=tk.W)
        self.delay_var = tk.StringVar(value=f"{self.settings.get('auto_select_rod_delay', 250)}")
        self.delay_entry = ttk.Entry(cast_tab, textvariable=self.delay_var, width=10)
        self.delay_entry.grid(row=row, column=1, padx=5, pady=2, sticky=tk.W)
        self.delay_entry.bind('<Return>', lambda e: self.on_auto_select_rod_delay_changed())
        self.delay_entry.bind('<FocusOut>', lambda e: self.on_auto_select_rod_delay_changed())
        
        # Update visibility
        self.update_rod_selection_visibility()
        
        # ========== SHAKE TAB ==========
        shake_tab = ttk.Frame(notebook, padding="10")
        notebook.add(shake_tab, text="Shake")
        
        row = 0
        
        # Shake .pt File selector
        ttk.Label(shake_tab, text="Shake .pt File:").grid(row=row, column=0, padx=5, sticky=tk.W)
        self.shake_model_var = tk.StringVar()
        self.shake_model_dropdown = ttk.Combobox(shake_tab, textvariable=self.shake_model_var, 
                                            state="readonly", width=25)
        self.shake_model_dropdown.grid(row=row, column=1, padx=5, pady=2, sticky=tk.W)
        self.shake_model_dropdown.bind('<<ComboboxSelected>>', self.on_shake_model_selected)
        self.refresh_shake_model_list()
        row += 1
        
        # Shake model confidence
        ttk.Label(shake_tab, text="Confidence:").grid(row=row, column=0, padx=5, sticky=tk.W)
        self.shake_confidence_var = tk.StringVar(value=f"{self.settings.get('shake_model_confidence', 0.75):.2f}")
        shake_confidence_entry = ttk.Entry(shake_tab, textvariable=self.shake_confidence_var, width=10)
        shake_confidence_entry.grid(row=row, column=1, padx=5, pady=2, sticky=tk.W)
        shake_confidence_entry.bind('<Return>', lambda e: self.on_shake_confidence_changed())
        shake_confidence_entry.bind('<FocusOut>', lambda e: self.on_shake_confidence_changed())
        ttk.Label(shake_tab, text="(0.05-0.95)", foreground="gray").grid(row=row, column=2, padx=2, sticky=tk.W)
        row += 1
        
        # Shake timeout
        ttk.Label(shake_tab, text="Shake Timeout (s):").grid(row=row, column=0, padx=5, sticky=tk.W)
        self.shake_timeout_var = tk.StringVar(value=f"{self.settings.get('shake_timeout', 5.0):.2f}")
        shake_timeout_entry = ttk.Entry(shake_tab, textvariable=self.shake_timeout_var, width=10)
        shake_timeout_entry.grid(row=row, column=1, padx=5, pady=2, sticky=tk.W)
        shake_timeout_entry.bind('<Return>', lambda e: self.on_shake_timeout_changed())
        shake_timeout_entry.bind('<FocusOut>', lambda e: self.on_shake_timeout_changed())
        ttk.Label(shake_tab, text="Max wait for shake detection", foreground="gray").grid(row=row, column=2, padx=5, sticky=tk.W)
        row += 1
        
        # Duplicate shake override
        ttk.Label(shake_tab, text="Duplicate Override (s):").grid(row=row, column=0, padx=5, sticky=tk.W)
        self.duplicate_shake_override_var = tk.StringVar(value=f"{self.settings.get('duplicate_shake_override', 1.0):.2f}")
        duplicate_override_entry = ttk.Entry(shake_tab, textvariable=self.duplicate_shake_override_var, width=10)
        duplicate_override_entry.grid(row=row, column=1, padx=5, pady=2, sticky=tk.W)
        duplicate_override_entry.bind('<Return>', lambda e: self.on_duplicate_shake_override_changed())
        duplicate_override_entry.bind('<FocusOut>', lambda e: self.on_duplicate_shake_override_changed())
        ttk.Label(shake_tab, text="Override duplicate block after this time", foreground="gray").grid(row=row, column=2, padx=5, sticky=tk.W)
        row += 1
        
        # ========== FISH TAB ==========
        fish_tab = ttk.Frame(notebook, padding="10")
        notebook.add(fish_tab, text="Fish")
        
        row = 0
        
        # Rod .pt File selector
        ttk.Label(fish_tab, text="Rod .pt File:").grid(row=row, column=0, padx=5, sticky=tk.W)
        self.model_var = tk.StringVar()
        self.model_dropdown = ttk.Combobox(fish_tab, textvariable=self.model_var, 
                                            state="readonly", width=25)
        self.model_dropdown.grid(row=row, column=1, padx=5, pady=2, sticky=tk.W)
        self.model_dropdown.bind('<<ComboboxSelected>>', self.on_model_selected)
        self.refresh_model_list()
        row += 1
        
        # Model confidence
        ttk.Label(fish_tab, text="Confidence:").grid(row=row, column=0, padx=5, sticky=tk.W)
        self.confidence_var = tk.StringVar(value=f"{self.settings.get('model_confidence', 0.75):.2f}")
        confidence_entry = ttk.Entry(fish_tab, textvariable=self.confidence_var, width=10)
        confidence_entry.grid(row=row, column=1, padx=5, pady=2, sticky=tk.W)
        confidence_entry.bind('<Return>', lambda e: self.on_confidence_changed())
        confidence_entry.bind('<FocusOut>', lambda e: self.on_confidence_changed())
        ttk.Label(fish_tab, text="(0.05-0.95)", foreground="gray").grid(row=row, column=2, padx=2, sticky=tk.W)
        row += 1
        
        # Maelstrom Mode
        self.maelstrom_mode_var = tk.BooleanVar(value=self.maelstrom_mode)
        maelstrom_check = ttk.Checkbutton(fish_tab, text="Maelstrom Mode", 
                                          variable=self.maelstrom_mode_var,
                                          command=self.toggle_maelstrom_mode)
        maelstrom_check.grid(row=row, column=0, padx=5, pady=2, sticky=tk.W)
        
        # Maelstrom Select Point button
        select_point_btn = ttk.Button(fish_tab, text="Select Point", command=self.select_maelstrom_point)
        select_point_btn.grid(row=row, column=1, padx=5, pady=2, sticky=tk.W)
        
        # Show current Y coordinate if set
        self.maelstrom_y_label = ttk.Label(fish_tab, text=f"Y: {self.maelstrom_y_coord if self.maelstrom_y_coord is not None else 'Not set'}" if self.maelstrom_y_coord is not None else "Y: Not set", foreground="gray")
        self.maelstrom_y_label.grid(row=row, column=2, padx=2, sticky=tk.W)
        row += 1
        
        # Maelstrom Settings Section (in a frame that can be hidden)
        self.maelstrom_settings_frame = ttk.Frame(fish_tab)
        self.maelstrom_settings_frame.grid(row=row, column=0, columnspan=3, sticky=tk.W+tk.E)
        settings_row = 0
        
        ttk.Label(self.maelstrom_settings_frame, text="Maelstrom Rod Settings:", font=("Arial", 9, "bold")).grid(row=settings_row, column=0, columnspan=3, sticky=tk.W, pady=(5, 0))
        settings_row += 1
        
        # maelstrom_color_tolerance
        ttk.Label(self.maelstrom_settings_frame, text="Color Tolerance:", font=("Arial", 9, "bold")).grid(row=settings_row, column=0, padx=5, sticky=tk.W)
        self.maelstrom_color_tol_var = tk.StringVar(value=f"{self.settings.get('maelstrom_color_tolerance', 3)}")
        color_tol_entry = ttk.Entry(self.maelstrom_settings_frame, textvariable=self.maelstrom_color_tol_var, width=10)
        color_tol_entry.grid(row=settings_row, column=1, padx=5, pady=1, sticky=tk.W)
        color_tol_entry.bind('<Return>', lambda e: self.on_maelstrom_color_tol_changed())
        color_tol_entry.bind('<FocusOut>', lambda e: self.on_maelstrom_color_tol_changed())
        ttk.Label(self.maelstrom_settings_frame, text="How much the color can vary (±). Higher = more lenient.", 
                  foreground="gray", font=("Arial", 8)).grid(row=settings_row, column=2, padx=5, sticky=tk.W)
        settings_row += 1
        
        # maelstrom_scan_left_margin
        ttk.Label(self.maelstrom_settings_frame, text="Scan Left Margin:", font=("Arial", 9, "bold")).grid(row=settings_row, column=0, padx=5, sticky=tk.W)
        self.maelstrom_scan_left_margin_var = tk.StringVar(value=f"{self.settings.get('maelstrom_scan_left_margin', 0.2):.2f}")
        scan_left_margin_entry = ttk.Entry(self.maelstrom_settings_frame, textvariable=self.maelstrom_scan_left_margin_var, width=10)
        scan_left_margin_entry.grid(row=settings_row, column=1, padx=5, pady=1, sticky=tk.W)
        scan_left_margin_entry.bind('<Return>', lambda e: self.on_maelstrom_scan_left_margin_changed())
        scan_left_margin_entry.bind('<FocusOut>', lambda e: self.on_maelstrom_scan_left_margin_changed())
        ttk.Label(self.maelstrom_settings_frame, text="How far from left edge to start scan (0-0.5). 0.2 = 20% inward.", 
                  foreground="gray", font=("Arial", 8)).grid(row=settings_row, column=2, padx=5, sticky=tk.W)
        settings_row += 1
        
        # maelstrom_scan_right_margin
        ttk.Label(self.maelstrom_settings_frame, text="Scan Right Margin:", font=("Arial", 9, "bold")).grid(row=settings_row, column=0, padx=5, sticky=tk.W)
        self.maelstrom_scan_right_margin_var = tk.StringVar(value=f"{self.settings.get('maelstrom_scan_right_margin', 0.2):.2f}")
        scan_right_margin_entry = ttk.Entry(self.maelstrom_settings_frame, textvariable=self.maelstrom_scan_right_margin_var, width=10)
        scan_right_margin_entry.grid(row=settings_row, column=1, padx=5, pady=1, sticky=tk.W)
        scan_right_margin_entry.bind('<Return>', lambda e: self.on_maelstrom_scan_right_margin_changed())
        scan_right_margin_entry.bind('<FocusOut>', lambda e: self.on_maelstrom_scan_right_margin_changed())
        ttk.Label(self.maelstrom_settings_frame, text="How far from right edge to end scan (0-0.5). 0.2 = 20% inward.", 
                  foreground="gray", font=("Arial", 8)).grid(row=settings_row, column=2, padx=5, sticky=tk.W)
        settings_row += 1
        
        # maelstrom_left_section
        ttk.Label(self.maelstrom_settings_frame, text="Left Section:", font=("Arial", 9, "bold")).grid(row=settings_row, column=0, padx=5, sticky=tk.W)
        self.maelstrom_left_section_var = tk.StringVar(value=f"{self.settings.get('maelstrom_left_section', 0.1):.2f}")
        left_section_entry = ttk.Entry(self.maelstrom_settings_frame, textvariable=self.maelstrom_left_section_var, width=10)
        left_section_entry.grid(row=settings_row, column=1, padx=5, pady=1, sticky=tk.W)
        left_section_entry.bind('<Return>', lambda e: self.on_maelstrom_left_section_changed())
        left_section_entry.bind('<FocusOut>', lambda e: self.on_maelstrom_left_section_changed())
        ttk.Label(self.maelstrom_settings_frame, text="When icon is in leftmost X% of bar, release to move it right (0-1). 0.1 = 10%.", 
                  foreground="gray", font=("Arial", 8)).grid(row=settings_row, column=2, padx=5, sticky=tk.W)
        settings_row += 1
        
        # maelstrom_right_section
        ttk.Label(self.maelstrom_settings_frame, text="Right Section:", font=("Arial", 9, "bold")).grid(row=settings_row, column=0, padx=5, sticky=tk.W)
        self.maelstrom_right_section_var = tk.StringVar(value=f"{self.settings.get('maelstrom_right_section', 0.5):.2f}")
        right_section_entry = ttk.Entry(self.maelstrom_settings_frame, textvariable=self.maelstrom_right_section_var, width=10)
        right_section_entry.grid(row=settings_row, column=1, padx=5, pady=1, sticky=tk.W)
        right_section_entry.bind('<Return>', lambda e: self.on_maelstrom_right_section_changed())
        right_section_entry.bind('<FocusOut>', lambda e: self.on_maelstrom_right_section_changed())
        ttk.Label(self.maelstrom_settings_frame, text="When icon is past X% of bar, play minigame (0-1). 0.5 = right half.", 
                  foreground="gray", font=("Arial", 8)).grid(row=settings_row, column=2, padx=5, sticky=tk.W)
        settings_row += 1
        
        # Toggle visibility based on maelstrom mode
        if not self.maelstrom_mode:
            self.maelstrom_settings_frame.grid_remove()
        
        row += 1
        
        # Controller Tuning
        ttk.Label(fish_tab, text="Controller Tuning:", font=("Arial", 9, "bold")).grid(row=row, column=0, columnspan=3, sticky=tk.W, pady=(5, 0))
        row += 1
        
        # kp
        ttk.Label(fish_tab, text="kp:", font=("Arial", 9, "bold")).grid(row=row, column=0, padx=5, sticky=tk.W)
        self.kp_var = tk.StringVar(value=f"{self.settings.get('kp', 0.9):.3f}")
        kp_entry = ttk.Entry(fish_tab, textvariable=self.kp_var, width=10)
        kp_entry.grid(row=row, column=1, padx=5, pady=1, sticky=tk.W)
        kp_entry.bind('<Return>', lambda e: self.on_kp_changed())
        kp_entry.bind('<FocusOut>', lambda e: self.on_kp_changed())
        ttk.Label(fish_tab, text="Pull strength. ↑ if bar lags, ↓ if overshoot.", 
                  foreground="gray", font=("Arial", 8)).grid(row=row, column=2, padx=5, sticky=tk.W)
        row += 1
        
        # kd
        ttk.Label(fish_tab, text="kd:", font=("Arial", 9, "bold")).grid(row=row, column=0, padx=5, sticky=tk.W)
        self.kd_var = tk.StringVar(value=f"{self.settings.get('kd', 0.3):.3f}")
        kd_entry = ttk.Entry(fish_tab, textvariable=self.kd_var, width=10)
        kd_entry.grid(row=row, column=1, padx=5, pady=1, sticky=tk.W)
        kd_entry.bind('<Return>', lambda e: self.on_kd_changed())
        kd_entry.bind('<FocusOut>', lambda e: self.on_kd_changed())
        ttk.Label(fish_tab, text="Damping. ↑ to reduce wobble, ↓ if sluggish.", 
                  foreground="gray", font=("Arial", 8)).grid(row=row, column=2, padx=5, sticky=tk.W)
        row += 1
        
        # bar_ratio
        ttk.Label(fish_tab, text="bar_ratio:", font=("Arial", 9, "bold")).grid(row=row, column=0, padx=5, sticky=tk.W)
        self.bar_ratio_var = tk.StringVar(value=f"{self.settings.get('bar_ratio', 0.6):.2f}")
        bar_ratio_entry = ttk.Entry(fish_tab, textvariable=self.bar_ratio_var, width=10)
        bar_ratio_entry.grid(row=row, column=1, padx=5, pady=1, sticky=tk.W)
        bar_ratio_entry.bind('<Return>', lambda e: self.on_bar_ratio_changed())
        bar_ratio_entry.bind('<FocusOut>', lambda e: self.on_bar_ratio_changed())
        ttk.Label(fish_tab, text="Edge trigger point. ↑ for earlier reactions.", 
                  foreground="gray", font=("Arial", 8)).grid(row=row, column=2, padx=5, sticky=tk.W)
        row += 1
        
        # speed_alpha
        ttk.Label(fish_tab, text="speed_alpha:", font=("Arial", 9, "bold")).grid(row=row, column=0, padx=5, sticky=tk.W)
        self.speed_alpha_var = tk.StringVar(value=f"{self.settings.get('speed_alpha', 0.7):.2f}")
        speed_alpha_entry = ttk.Entry(fish_tab, textvariable=self.speed_alpha_var, width=10)
        speed_alpha_entry.grid(row=row, column=1, padx=5, pady=1, sticky=tk.W)
        speed_alpha_entry.bind('<Return>', lambda e: self.on_speed_alpha_changed())
        speed_alpha_entry.bind('<FocusOut>', lambda e: self.on_speed_alpha_changed())
        ttk.Label(fish_tab, text="Speed smoothing. ↑ faster, ↓ less noise.", 
                  foreground="gray", font=("Arial", 8)).grid(row=row, column=2, padx=5, sticky=tk.W)
        row += 1
        
        # damping_forward
        ttk.Label(fish_tab, text="damp_fwd:", font=("Arial", 9, "bold")).grid(row=row, column=0, padx=5, sticky=tk.W)
        self.damp_fwd_var = tk.StringVar(value=f"{self.settings.get('damping_forward', 2.0):.2f}")
        damp_fwd_entry = ttk.Entry(fish_tab, textvariable=self.damp_fwd_var, width=10)
        damp_fwd_entry.grid(row=row, column=1, padx=5, pady=1, sticky=tk.W)
        damp_fwd_entry.bind('<Return>', lambda e: self.on_damping_forward_changed())
        damp_fwd_entry.bind('<FocusOut>', lambda e: self.on_damping_forward_changed())
        ttk.Label(fish_tab, text="Braking when approaching. ↑ if overshoot.", 
                  foreground="gray", font=("Arial", 8)).grid(row=row, column=2, padx=5, sticky=tk.W)
        row += 1
        
        # damping_reverse
        ttk.Label(fish_tab, text="damp_rev:", font=("Arial", 9, "bold")).grid(row=row, column=0, padx=5, sticky=tk.W)
        self.damp_rev_var = tk.StringVar(value=f"{self.settings.get('damping_reverse', 0.5):.2f}")
        damp_rev_entry = ttk.Entry(fish_tab, textvariable=self.damp_rev_var, width=10)
        damp_rev_entry.grid(row=row, column=1, padx=5, pady=1, sticky=tk.W)
        damp_rev_entry.bind('<Return>', lambda e: self.on_damping_reverse_changed())
        damp_rev_entry.bind('<FocusOut>', lambda e: self.on_damping_reverse_changed())
        ttk.Label(fish_tab, text="Damping when chasing. ↓ if too slow to catch.", 
                  foreground="gray", font=("Arial", 8)).grid(row=row, column=2, padx=5, sticky=tk.W)
        row += 1
        
        # Debug overlay
        self.debug_overlay_var = tk.BooleanVar(value=self.show_debug_overlay)
        debug_check = ttk.Checkbutton(fish_tab, text="Show Debug Overlay", 
                                      variable=self.debug_overlay_var,
                                      command=self.toggle_debug_overlay)
        debug_check.grid(row=row, column=0, padx=5, pady=2, sticky=tk.W)
        row += 1
        
        # Post-fish wait time
        ttk.Label(fish_tab, text="Post-Fish Wait (s):").grid(row=row, column=0, padx=5, sticky=tk.W)
        self.post_fish_wait_var = tk.StringVar(value=f"{self.settings.get('post_fish_wait', 2.0):.2f}")
        post_fish_wait_entry = ttk.Entry(fish_tab, textvariable=self.post_fish_wait_var, width=10)
        post_fish_wait_entry.grid(row=row, column=1, padx=5, pady=2, sticky=tk.W)
        post_fish_wait_entry.bind('<Return>', lambda e: self.on_post_fish_wait_changed())
        post_fish_wait_entry.bind('<FocusOut>', lambda e: self.on_post_fish_wait_changed())
        ttk.Label(fish_tab, text="Wait before next cycle", foreground="gray").grid(row=row, column=2, padx=5, sticky=tk.W)
        row += 1
        
        # Gate 1 timeout
        ttk.Label(fish_tab, text="Gate 1 Timeout (s):").grid(row=row, column=0, padx=5, sticky=tk.W)
        self.gate1_timeout_var = tk.StringVar(value=f"{self.settings.get('gate1_timeout', 5.0):.2f}")
        gate1_timeout_entry = ttk.Entry(fish_tab, textvariable=self.gate1_timeout_var, width=10)
        gate1_timeout_entry.grid(row=row, column=1, padx=5, pady=2, sticky=tk.W)
        gate1_timeout_entry.bind('<Return>', lambda e: self.on_gate1_timeout_changed())
        gate1_timeout_entry.bind('<FocusOut>', lambda e: self.on_gate1_timeout_changed())
        ttk.Label(fish_tab, text="Max wait for icon/bar to appear", foreground="gray").grid(row=row, column=2, padx=5, sticky=tk.W)
    def setup_hotkeys(self):
        keyboard.unhook_all()
        keyboard.on_press_key(self.start_stop_key, lambda _: self.toggle_start_stop())
        keyboard.on_press_key(self.change_area_key, lambda _: self.change_area())
        keyboard.on_press_key(self.exit_key, lambda _: self.exit_app())
    
    def toggle_always_on_top(self):
        """Toggle always on top window attribute"""
        is_on_top = self.always_on_top_var.get()
        self.root.attributes('-topmost', is_on_top)
        self.settings["always_on_top"] = is_on_top
        self._save_settings()
        print(f"Always on top: {is_on_top}")
    
    def on_auto_minimize_changed(self):
        """Handle Auto Minimize checkbox change"""
        self.settings["auto_minimize"] = self.auto_minimize_var.get()
        self._save_settings()
        print(f"Auto Minimize: {self.auto_minimize_var.get()}")
    
    def get_pt_models(self):
        """Scan current directory for .pt model files"""
        if getattr(sys, 'frozen', False):
            app_dir = os.path.dirname(sys.executable)
        else:
            app_dir = os.path.dirname(os.path.abspath(__file__))
        
        try:
            pt_files = [f for f in os.listdir(app_dir) if f.endswith('.pt')]
            return sorted(pt_files) if pt_files else []
        except Exception as e:
            print(f"Error scanning for .pt files: {e}")
            return []
    
    def refresh_model_list(self):
        """Refresh the model dropdown list"""
        models = self.get_pt_models()
        
        if not models:
            self.model_dropdown['values'] = ["None"]
            self.model_var.set("None")
        else:
            self.model_dropdown['values'] = models
            # Set to saved model if it exists, otherwise first model
            saved_model = self.settings.get("selected_model", "None")
            if saved_model in models:
                self.model_var.set(saved_model)
            else:
                self.model_var.set(models[0])
                self.settings["selected_model"] = models[0]
                self._save_settings()
    
    def on_model_selected(self, event):
        """Handle model selection change"""
        selected = self.model_var.get()
        self.settings["selected_model"] = selected
        self._save_settings()
        # Unload previous model
        self.yolo_model = None
        print(f"Selected model: {selected}")
    
    def refresh_shake_model_list(self):
        """Refresh the shake model dropdown list"""
        models = self.get_pt_models()
        models_with_none = ["None"] + models
        
        self.shake_model_dropdown['values'] = models_with_none
        # Set to saved model if it exists, otherwise "None"
        saved_model = self.settings.get("selected_shake_model", "None")
        if saved_model in models_with_none:
            self.shake_model_var.set(saved_model)
        else:
            self.shake_model_var.set("None")
            self.settings["selected_shake_model"] = "None"
            self._save_settings()
    
    def on_shake_model_selected(self, event):
        """Handle shake model selection change"""
        selected = self.shake_model_var.get()
        self.settings["selected_shake_model"] = selected
        self._save_settings()
        # Unload previous shake model
        self.shake_model = None
        print(f"Selected shake model: {selected}")
    
    def toggle_debug_overlay(self):
        """Toggle debug overlay on/off"""
        self.show_debug_overlay = self.debug_overlay_var.get()
        self.settings["show_debug_overlay"] = self.show_debug_overlay
        self._save_settings()
        if not self.show_debug_overlay:
            self._cleanup_debug_overlay()
        print(f"DEBUG OVERLAY TOGGLED: {self.show_debug_overlay}")
    
    def toggle_maelstrom_mode(self):
        """Toggle Maelstrom Mode on/off"""
        self.maelstrom_mode = self.maelstrom_mode_var.get()
        self.settings["maelstrom_mode"] = self.maelstrom_mode
        self._save_settings()
        
        # Show/hide maelstrom settings frame
        if self.maelstrom_mode:
            self.maelstrom_settings_frame.grid()
        else:
            self.maelstrom_settings_frame.grid_remove()
        
        print(f"MAELSTROM MODE: {self.maelstrom_mode}")
    
    def select_maelstrom_point(self):
        """Select a point on screen to get Y coordinate for maelstrom detection"""
        print("Click on the maelstrom bar to select Y coordinate...")
        
        # Create fullscreen transparent overlay
        overlay = tk.Toplevel(self.root)
        overlay.attributes('-fullscreen', True)
        overlay.attributes('-topmost', True)
        overlay.attributes('-alpha', 0.3)
        overlay.configure(bg='black', cursor='crosshair')
        
        # Add instruction text
        instruction = tk.Label(overlay, text="Click on the maelstrom bar", 
                              font=('Arial', 20, 'bold'), fg='yellow', bg='black')
        instruction.pack(pady=50)
        
        def on_click(event):
            # Get absolute screen coordinates
            screen_y = event.y_root
            
            # Store Y coordinate relative to fish area
            fish_area = self.settings.get("fish_area")
            if fish_area and fish_area.get("y") is not None and fish_area.get("height") is not None:
                relative_y = screen_y - fish_area['y']
                if 0 <= relative_y < fish_area['height']:
                    self.maelstrom_y_coord = relative_y
                    self.settings["maelstrom_y_coord"] = relative_y
                    self._save_settings()
                    self.maelstrom_y_label.config(text=f"Y: {relative_y}")
                    print(f"Maelstrom Y coordinate set to: {relative_y} (screen Y: {screen_y})")
                else:
                    print(f"Click outside fish area. Please try again.")
            else:
                print("Please set Fish Area first!")
            
            overlay.destroy()
        
        overlay.bind('<Button-1>', on_click)
        overlay.bind('<Escape>', lambda e: overlay.destroy())
    
    def on_confidence_changed(self):
        """Handle confidence entry change"""
        try:
            conf_value = float(self.confidence_var.get())
            if 0.05 <= conf_value <= 0.95:
                self.settings["model_confidence"] = conf_value
                self._save_settings()
                print(f"Model confidence: {conf_value:.2f}")
                self.confidence_var.set(f"{conf_value:.2f}")
            else:
                print(f"⚠️ Confidence must be between 0.05 and 0.95")
                self.confidence_var.set(f"{self.settings.get('model_confidence', 0.75):.2f}")
        except ValueError:
            print(f"⚠️ Invalid confidence value")
            self.confidence_var.set(f"{self.settings.get('model_confidence', 0.75):.2f}")
    
    def on_shake_confidence_changed(self):
        """Handle shake confidence entry change"""
        try:
            conf_value = float(self.shake_confidence_var.get())
            if 0.05 <= conf_value <= 0.95:
                self.settings["shake_model_confidence"] = conf_value
                self._save_settings()
                print(f"Shake model confidence: {conf_value:.2f}")
                self.shake_confidence_var.set(f"{conf_value:.2f}")
            else:
                print(f"⚠️ Shake confidence must be between 0.05 and 0.95")
                self.shake_confidence_var.set(f"{self.settings.get('shake_model_confidence', 0.75):.2f}")
        except ValueError:
            print(f"⚠️ Invalid shake confidence value")
            self.shake_confidence_var.set(f"{self.settings.get('shake_model_confidence', 0.75):.2f}")
    
    def on_shake_timeout_changed(self):
        """Handle shake timeout change"""
        try:
            timeout_value = float(self.shake_timeout_var.get())
            if timeout_value < 0.5 or timeout_value > 60.0:
                print(f"⚠️ Shake timeout must be between 0.5s and 60s")
                timeout_value = float(self.settings.get('shake_timeout', 5.0))
            else:
                self.settings['shake_timeout'] = timeout_value
                self._save_settings()
                print(f"Shake timeout: {timeout_value:.2f}s")
            self.shake_timeout_var.set(f"{timeout_value:.2f}")
        except ValueError:
            print(f"⚠️ Invalid shake timeout value")
            timeout_value = float(self.settings.get('shake_timeout', 5.0))
            self.shake_timeout_var.set(f"{timeout_value:.2f}")
    
    def on_duplicate_shake_override_changed(self):
        """Handle duplicate shake override change"""
        try:
            override_value = float(self.duplicate_shake_override_var.get())
            if override_value < 0.1 or override_value > 10.0:
                print(f"⚠️ Duplicate shake override must be between 0.1s and 10s")
                override_value = float(self.settings.get('duplicate_shake_override', 1.0))
            else:
                self.settings['duplicate_shake_override'] = override_value
                self._save_settings()
                print(f"Duplicate shake override: {override_value:.2f}s")
            self.duplicate_shake_override_var.set(f"{override_value:.2f}")
        except ValueError:
            print(f"⚠️ Invalid duplicate shake override value")
            override_value = float(self.settings.get('duplicate_shake_override', 1.0))
            self.duplicate_shake_override_var.set(f"{override_value:.2f}")
    
    # (Kp/Kd handlers removed)

    # (Removed Gate 3 tuning handlers; Gate 3 is tracking-only and GUI entries were removed)
    
    # ===== Controller parameter handlers =====
    def _set_float_setting(self, key, var, value, lo, hi, fmt):
        try:
            v = float(value)
            if v < lo or v > hi:
                print(f"⚠️ {key} must be between {lo} and {hi}")
                v = float(self.settings.get(key, v))
            self.settings[key] = v
            self._save_settings()
            var.set(fmt.format(v))
            print(f"{key} set to {v}")
        except ValueError:
            print(f"⚠️ Invalid value for {key}")
            v = float(self.settings.get(key))
            var.set(fmt.format(v))

    def on_kp_changed(self):
        self._set_float_setting("kp", self.kp_var, self.kp_var.get(), 0.3, 3.0, "{:.3f}")

    def on_kd_changed(self):
        self._set_float_setting("kd", self.kd_var, self.kd_var.get(), 0.1, 2.0, "{:.3f}")

    def on_bar_ratio_changed(self):
        self._set_float_setting("bar_ratio", self.bar_ratio_var, self.bar_ratio_var.get(), 0.3, 0.9, "{:.2f}")

    def on_speed_alpha_changed(self):
        self._set_float_setting("speed_alpha", self.speed_alpha_var, self.speed_alpha_var.get(), 0.2, 0.95, "{:.2f}")

    def on_damping_forward_changed(self):
        self._set_float_setting("damping_forward", self.damp_fwd_var, self.damp_fwd_var.get(), 0.5, 4.0, "{:.2f}")

    def on_damping_reverse_changed(self):
        self._set_float_setting("damping_reverse", self.damp_rev_var, self.damp_rev_var.get(), 0.1, 3.0, "{:.2f}")
    
    def on_maelstrom_color_tol_changed(self):
        """Handle maelstrom color tolerance change"""
        try:
            tol_value = int(self.maelstrom_color_tol_var.get())
            if tol_value < 0 or tol_value > 50:
                print(f"⚠️ Color tolerance must be between 0 and 50")
                tol_value = int(self.settings.get('maelstrom_color_tolerance', 3))
            else:
                self.settings['maelstrom_color_tolerance'] = tol_value
                self._save_settings()
                print(f"Maelstrom color tolerance: {tol_value}")
            self.maelstrom_color_tol_var.set(f"{tol_value}")
        except ValueError:
            print(f"⚠️ Invalid color tolerance value")
            tol_value = int(self.settings.get('maelstrom_color_tolerance', 3))
            self.maelstrom_color_tol_var.set(f"{tol_value}")
    
    def on_maelstrom_scan_left_margin_changed(self):
        self._set_float_setting("maelstrom_scan_left_margin", self.maelstrom_scan_left_margin_var, self.maelstrom_scan_left_margin_var.get(), 0.0, 0.5, "{:.2f}")
    
    def on_maelstrom_scan_right_margin_changed(self):
        self._set_float_setting("maelstrom_scan_right_margin", self.maelstrom_scan_right_margin_var, self.maelstrom_scan_right_margin_var.get(), 0.0, 0.5, "{:.2f}")
    
    def on_maelstrom_left_section_changed(self):
        self._set_float_setting("maelstrom_left_section", self.maelstrom_left_section_var, self.maelstrom_left_section_var.get(), 0.0, 0.5, "{:.2f}")
    
    def on_maelstrom_right_section_changed(self):
        self._set_float_setting("maelstrom_right_section", self.maelstrom_right_section_var, self.maelstrom_right_section_var.get(), 0.1, 1.0, "{:.2f}")
    
    def on_cast_hold_changed(self):
        """Handle cast hold time change (converts from ms to seconds)"""
        try:
            ms_value = float(self.cast_hold_var.get())
            if ms_value < 50 or ms_value > 5000:
                print(f"⚠️ Cast hold time must be between 50ms and 5000ms")
                ms_value = float(self.settings.get('cast_hold_time', 0.5)) * 1000
            else:
                self.settings['cast_hold_time'] = ms_value / 1000.0
                self._save_settings()
                print(f"Cast hold time: {ms_value:.0f}ms")
            self.cast_hold_var.set(f"{ms_value:.0f}")
        except ValueError:
            print(f"⚠️ Invalid cast hold time value")
            ms_value = float(self.settings.get('cast_hold_time', 0.5)) * 1000
            self.cast_hold_var.set(f"{ms_value:.0f}")
    
    def on_post_fish_wait_changed(self):
        """Handle post-fish wait time change"""
        try:
            wait_value = float(self.post_fish_wait_var.get())
            if wait_value < 0.1 or wait_value > 60.0:
                print(f"⚠️ Post-fish wait must be between 0.1s and 60s")
                wait_value = float(self.settings.get('post_fish_wait', 2.0))
            else:
                self.settings['post_fish_wait'] = wait_value
                self._save_settings()
                print(f"Post-fish wait: {wait_value:.2f}s")
            self.post_fish_wait_var.set(f"{wait_value:.2f}")
        except ValueError:
            print(f"⚠️ Invalid post-fish wait value")
            wait_value = float(self.settings.get('post_fish_wait', 2.0))
            self.post_fish_wait_var.set(f"{wait_value:.2f}")
    
    def on_gate1_timeout_changed(self):
        """Handle Gate 1 timeout change"""
        try:
            timeout_value = float(self.gate1_timeout_var.get())
            if timeout_value < 0.5 or timeout_value > 60.0:
                print(f"⚠️ Gate 1 timeout must be between 0.5s and 60s")
                timeout_value = float(self.settings.get('gate1_timeout', 5.0))
            else:
                self.settings['gate1_timeout'] = timeout_value
                self._save_settings()
                print(f"Gate 1 timeout: {timeout_value:.2f}s")
            self.gate1_timeout_var.set(f"{timeout_value:.2f}")
        except ValueError:
            print(f"⚠️ Invalid Gate 1 timeout value")
            timeout_value = float(self.settings.get('gate1_timeout', 5.0))
            self.gate1_timeout_var.set(f"{timeout_value:.2f}")
    
    def on_auto_select_rod_changed(self):
        """Handle Auto Select Rod checkbox toggle"""
        self.settings['auto_select_rod'] = self.auto_select_rod_var.get()
        self._save_settings()
        self.update_rod_selection_visibility()
        print(f"Auto Select Rod: {self.auto_select_rod_var.get()}")
    
    def on_rod_slot_changed(self):
        """Handle Rod slot dropdown change"""
        try:
            slot_value = int(self.rod_var.get())
            self.settings['rod_slot'] = slot_value
            self._save_settings()
            print(f"Rod slot: {slot_value}")
        except ValueError:
            print(f"⚠️ Invalid rod slot value")
    
    def on_equipment_bag_slot_changed(self):
        """Handle Equipment Bag slot dropdown change"""
        try:
            slot_value = int(self.bag_var.get())
            self.settings['equipment_bag_slot'] = slot_value
            self._save_settings()
            print(f"Equipment Bag slot: {slot_value}")
        except ValueError:
            print(f"⚠️ Invalid equipment bag slot value")
    
    def on_auto_select_rod_delay_changed(self):
        """Handle Auto Select Rod delay change (in milliseconds)"""
        try:
            delay_ms = int(self.delay_var.get())
            if delay_ms < 10 or delay_ms > 10000:
                print(f"⚠️ Auto Select Rod delay must be between 10ms and 10000ms")
                delay_ms = int(self.settings.get('auto_select_rod_delay', 250))
            else:
                self.settings['auto_select_rod_delay'] = delay_ms
                self._save_settings()
                print(f"Auto Select Rod delay: {delay_ms}ms")
            self.delay_var.set(f"{delay_ms}")
        except ValueError:
            print(f"⚠️ Invalid Auto Select Rod delay value")
            delay_ms = int(self.settings.get('auto_select_rod_delay', 250))
            self.delay_var.set(f"{delay_ms}")
    
    def update_rod_selection_visibility(self):
        """Show/hide Rod and Equipment Bag controls based on auto_select_rod checkbox"""
        if self.auto_select_rod_var.get():
            self.rod_label.grid(row=2, column=0, padx=5, sticky=tk.W)
            self.rod_dropdown.grid(row=2, column=1, padx=5, pady=2, sticky=tk.W)
            self.bag_label.grid(row=3, column=0, padx=5, sticky=tk.W)
            self.bag_dropdown.grid(row=3, column=1, padx=5, pady=2, sticky=tk.W)
            self.delay_label.grid(row=4, column=0, padx=5, sticky=tk.W)
            self.delay_entry.grid(row=4, column=1, padx=5, pady=2, sticky=tk.W)
        else:
            self.rod_label.grid_remove()
            self.rod_dropdown.grid_remove()
            self.bag_label.grid_remove()
            self.bag_dropdown.grid_remove()
            self.delay_label.grid_remove()
            self.delay_entry.grid_remove()
    
    def _create_debug_overlay(self):
        """Create transparent overlay window for debugging arrows"""
        if self.debug_overlay is not None:
            return
        
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        self.debug_overlay = tk.Toplevel(self.root)
        self.debug_overlay.attributes('-topmost', True)
        self.debug_overlay.attributes('-transparentcolor', 'black')
        self.debug_overlay.overrideredirect(True)
        self.debug_overlay.geometry(f"{screen_width}x{screen_height}+0+0")
        self.debug_overlay.configure(bg='black')
        
        self.debug_canvas = tk.Canvas(self.debug_overlay, bg='black', highlightthickness=0)
        self.debug_canvas.pack(fill='both', expand=True)
    
    def _cleanup_debug_overlay(self):
        """Clean up and destroy debug overlay"""
        if self.debug_overlay is not None:
            try:
                self.debug_overlay.destroy()
            except:
                pass
            self.debug_overlay = None
            self.debug_canvas = None
            self.arrow_ids = {}
    
    def _draw_arrow_down(self, arrow_id, x, y, color='red'):
        """Draw or update downward pointing arrow at position"""
        if not self.show_debug_overlay or self.debug_canvas is None:
            return None
        
        size = 20
        coords = [x, y+size, x-size//2, y, x+size//2, y]
        
        if arrow_id:
            try:
                self.debug_canvas.coords(arrow_id, *coords)
                return arrow_id
            except:
                return self.debug_canvas.create_polygon(coords, fill=color, outline=color)
        else:
            return self.debug_canvas.create_polygon(coords, fill=color, outline=color)
    
    def _draw_arrow_up(self, arrow_id, x, y, color='red'):
        """Draw or update upward pointing arrow at position"""
        if not self.show_debug_overlay or self.debug_canvas is None:
            return None
        
        size = 20
        coords = [x, y-size, x-size//2, y, x+size//2, y]
        
        if arrow_id:
            try:
                self.debug_canvas.coords(arrow_id, *coords)
                return arrow_id
            except:
                return self.debug_canvas.create_polygon(coords, fill=color, outline=color)
        else:
            return self.debug_canvas.create_polygon(coords, fill=color, outline=color)
    
    def _draw_box(self, x1, y1, x2, y2, color='green', tag='box'):
        """Draw bounding box"""
        if not self.show_debug_overlay or self.debug_canvas is None:
            return None
        
        return self.debug_canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=2, tags=tag)
    
    def _draw_text(self, x, y, text, color='white', tag='text'):
        """Draw text label"""
        if not self.show_debug_overlay or self.debug_canvas is None:
            return None
        
        return self.debug_canvas.create_text(x, y, text=text, fill=color, font=("Arial", 12, "bold"), tags=tag)
    
    def _clear_debug_items(self, tag=None):
        """Clear debug items by tag, or all if no tag specified"""
        if self.debug_canvas is None:
            return
        
        try:
            if tag:
                self.debug_canvas.delete(tag)
            else:
                self.debug_canvas.delete('all')
        except:
            pass
    
    def _send_mouse_down(self):
        """Send mouse down once"""
        try:
            pyautogui.mouseDown()
        except Exception as e:
            error_str = str(e)
            if "Error code from Windows: 0" not in error_str:
                print(f"⚠️ Error in mouseDown: {e}")
    
    def _send_mouse_up(self):
        """Send mouse up once"""
        try:
            pyautogui.mouseUp()
        except Exception as e:
            error_str = str(e)
            if "Error code from Windows: 0" not in error_str:
                print(f"⚠️ Error in mouseUp: {e}")
    
    def _send_key_press(self, key_char):
        """
        Send a keyboard key press using win32api.
        Handles any single character or special key names like 'Enter'.
        """
        try:
            # Handle special key names
            if key_char.lower() == "enter":
                vk_code = win32con.VK_RETURN
                scan_code = 0
            elif len(key_char) == 1:
                # Use VkKeyScan to get the correct virtual key and shift state for any character
                result = win32api.VkKeyScan(key_char)
                if result == -1:
                    print(f"    ⚡ Cannot map key: {key_char}")
                    return
                
                vk_code = result & 0xFF  # Lower byte is the virtual key code
                shift_state = (result >> 8) & 0xFF  # Higher byte contains shift state
                
                # Handle shift state if needed
                need_shift = (shift_state & 1) != 0
                need_ctrl = (shift_state & 2) != 0
                need_alt = (shift_state & 4) != 0
                
                # Press modifier keys if needed
                if need_shift:
                    win32api.keybd_event(win32con.VK_SHIFT, 0, 0, 0)
                if need_ctrl:
                    win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
                if need_alt:
                    win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
                
                # Press the main key
                scan_code = win32api.MapVirtualKey(vk_code, 0)
                win32api.keybd_event(vk_code, scan_code, 0, 0)  # Key down
                win32api.keybd_event(vk_code, scan_code, win32con.KEYEVENTF_KEYUP, 0)  # Key up
                
                # Release modifier keys if needed
                if need_alt:
                    win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
                if need_ctrl:
                    win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
                if need_shift:
                    win32api.keybd_event(win32con.VK_SHIFT, 0, win32con.KEYEVENTF_KEYUP, 0)
                
                return
            else:
                print(f"    ⚡ Unsupported key format: {key_char}")
                return
            
            # For special keys like Enter that don't need VkKeyScan
            scan_code = win32api.MapVirtualKey(vk_code, 0)
            win32api.keybd_event(vk_code, scan_code, 0, 0)  # Key down
            time.sleep(0.01)  # Small delay
            win32api.keybd_event(vk_code, scan_code, win32con.KEYEVENTF_KEYUP, 0)  # Key up
        except Exception as e:
            error_str = str(e)
            # Ignore win32api "success" errors (error code 0)
            if "Error code from Windows: 0" not in error_str:
                print(f"⚠️ Error sending key: {e}")
    
    def cast(self):
        """Cast fishing rod"""
        print("Executing: Cast")
        
        # Focus on Roblox window first
        self._focus_roblox()
        
        # Check if auto select rod is enabled
        if self.settings.get('auto_select_rod', False):
            equipment_bag_slot = str(self.settings.get('equipment_bag_slot', 2))
            rod_slot = str(self.settings.get('rod_slot', 1))
            delay_ms = self.settings.get('auto_select_rod_delay', 250)
            delay_sec = delay_ms / 1000.0
            
            # Press equipment bag slot key
            print(f"Auto Select Rod: Pressing {equipment_bag_slot}")
            self._send_key_press(equipment_bag_slot)
            
            # Wait for delay
            if self.stop_event.wait(delay_sec):
                return
            
            # Press rod slot key
            print(f"Auto Select Rod: Pressing {rod_slot}")
            self._send_key_press(rod_slot)
            
            # Wait for delay
            if self.stop_event.wait(delay_sec):
                return
        
        # Get cast hold time from settings
        cast_hold_time = self.settings.get('cast_hold_time', 0.5)
        
        # Hold left click
        print(f"Cast: Holding left click for {cast_hold_time*1000:.0f}ms")
        self._send_mouse_down()
        
        # Wait for specified hold time
        if self.stop_event.wait(cast_hold_time):
            self._send_mouse_up()
            return
        
        # Release left click
        print("Cast: Released left click")
        self._send_mouse_up()
        print("Cast: Complete")
        
    def shake(self):
        """Shake rod - detect and click on 'Shake' objects using YOLO"""
        print("Executing: Shake")
        
        # Load shake model if not already loaded
        if not self._load_shake_model():
            print("Cannot proceed with shake detection - no model loaded")
            return
        
        shake_area = self.settings.get("shake_area")
        if not shake_area:
            print("ERROR: Shake area not configured")
            return
        
        friend_area = self.settings.get("friend_area")
        if not friend_area:
            print("ERROR: Friend area not configured")
            return
        
        # Prepare MSS monitor regions
        shake_monitor = {
            "left": shake_area["x"],
            "top": shake_area["y"],
            "width": shake_area["width"],
            "height": shake_area["height"]
        }
        
        friend_monitor = {
            "left": friend_area["x"],
            "top": friend_area["y"],
            "width": friend_area["width"],
            "height": friend_area["height"]
        }
        
        # Target color for friend area exit condition: RGB(155, 255, 155) -> BGR(155, 255, 155)
        target_color_bgr = np.array([155, 255, 155], dtype=np.uint8)
        color_tolerance = 10  # Increased tolerance for color matching (handles screen capture variations)
        
        print("Shake: Detecting and clicking shakes until friend area color disappears")
        
        # Track clicked shake positions to avoid duplicates
        clicked_shakes = set()
        last_detected_shakes = set()
        
        # Timeout tracking
        shake_timeout = self.settings.get('shake_timeout', 5.0)
        last_shake_time = time.time()  # Track when we last saw a shake
        
        # Duplicate override tracking
        duplicate_override_time = self.settings.get('duplicate_shake_override', 1.0)
        last_blocked_shake = None  # (x, y) of shake we're trying to click
        blocked_shake_start_time = None  # When we started being blocked from clicking this shake
        
        with mss.mss() as sct:
            loop_count = 0
            while not self.stop_event.is_set():
                loop_count += 1
                
                # Check friend area for exit condition (green color disappearance)
                friend_screenshot = sct.grab(friend_monitor)
                friend_img_np = np.array(friend_screenshot)
                friend_img_bgr = cv2.cvtColor(friend_img_np, cv2.COLOR_BGRA2BGR)  # Explicit BGRA -> BGR conversion
                
                # Debug: Print first pixel color and save snapshot on first loop
                if loop_count == 1:
                    sample_pixel = friend_img_bgr[friend_img_bgr.shape[0]//2, friend_img_bgr.shape[1]//2]
                    print(f"DEBUG: Friend area sample pixel (BGR): {sample_pixel}, Target: {target_color_bgr}")
                    
                    # Check if exact color exists anywhere in the image
                    exact_match = np.all(friend_img_bgr == target_color_bgr, axis=2)
                    exact_count = np.sum(exact_match)
                    print(f"DEBUG: Exact color [155, 255, 155] pixel count: {exact_count}")
                    
                    # Print channel ranges
                    print(f"DEBUG: B channel range: {friend_img_bgr[:,:,0].min()} - {friend_img_bgr[:,:,0].max()}")
                    print(f"DEBUG: G channel range: {friend_img_bgr[:,:,1].min()} - {friend_img_bgr[:,:,1].max()}")
                    print(f"DEBUG: R channel range: {friend_img_bgr[:,:,2].min()} - {friend_img_bgr[:,:,2].max()}")
                    
                    # Find colors close to target (within 5 of each channel)
                    close_mask = (np.abs(friend_img_bgr[:,:,0] - 155) <= 5) & \
                                 (np.abs(friend_img_bgr[:,:,1] - 255) <= 5) & \
                                 (np.abs(friend_img_bgr[:,:,2] - 155) <= 5)
                    close_count = np.sum(close_mask)
                    print(f"DEBUG: Pixels within ±5 of target: {close_count}")
                    
                    # Show some sample colors from the image
                    print(f"DEBUG: Image shape: {friend_img_bgr.shape}")
                    print(f"DEBUG: First 5 pixels: {friend_img_bgr[0, :5]}")
                
                # Use cv2.inRange with tolerance for more reliable color matching
                # Convert to int16 to prevent overflow, then clip and convert back
                lower_bound = np.clip(target_color_bgr.astype(np.int16) - color_tolerance, 0, 255).astype(np.uint8)
                upper_bound = np.clip(target_color_bgr.astype(np.int16) + color_tolerance, 0, 255).astype(np.uint8)
                
                if loop_count == 1:
                    print(f"DEBUG: lower_bound: {lower_bound}, upper_bound: {upper_bound}")
                
                mask = cv2.inRange(friend_img_bgr, lower_bound, upper_bound)
                matching_pixels = cv2.countNonZero(mask)
                
                if loop_count == 1:
                    print(f"DEBUG: cv2.inRange result: {matching_pixels} pixels")
                    # Manually check what cv2.inRange should find
                    manual_check = np.all((friend_img_bgr >= lower_bound) & (friend_img_bgr <= upper_bound), axis=2)
                    manual_count = np.sum(manual_check)
                    print(f"DEBUG: Manual range check: {manual_count} pixels")
                
                color_exists = matching_pixels > 0  # Even 1 pixel means color is present
                
                if not color_exists:
                    print(f"✓ Shake: Friend area color disappeared (0 pixels) after {loop_count} checks - exiting")
                    break
                
                # Check timeout (only if color still exists)
                elapsed_since_shake = time.time() - last_shake_time
                if elapsed_since_shake > shake_timeout:
                    print(f"⏱️ Shake timeout ({shake_timeout}s) - no shakes detected - restarting cycle")
                    return "timeout"
                
                # Detect shakes in shake_area
                shake_screenshot = sct.grab(shake_monitor)
                shake_img_np = np.array(shake_screenshot)
                shake_img_bgr = shake_img_np[:, :, :3]  # BGRA -> BGR
                
                conf_threshold = self.settings.get("shake_model_confidence", 0.75)
                results = self.shake_model.predict(shake_img_bgr, conf=conf_threshold, verbose=False)
                
                current_shakes = set()
                shake_found_this_loop = False
                current_time = time.time()
                
                if len(results) > 0 and len(results[0].boxes) > 0:
                    for box in results[0].boxes:
                        cls_id = int(box.cls[0])
                        class_name = results[0].names[cls_id]
                        
                        if class_name.lower() == "icon":
                            shake_found_this_loop = True
                            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                            center_x = int((x1 + x2) / 2)
                            center_y = int((y1 + y2) / 2)
                            
                            # Check if this position is too close to any already-clicked shake
                            click_tolerance = 30  # pixels - don't click within 30px of previous clicks
                            too_close_to_clicked = False
                            closest_clicked_id = None
                            for clicked_id in clicked_shakes:
                                clicked_x, clicked_y = clicked_id
                                distance = ((center_x - clicked_x)**2 + (center_y - clicked_y)**2)**0.5
                                if distance < click_tolerance:
                                    too_close_to_clicked = True
                                    closest_clicked_id = clicked_id
                                    break
                            
                            # Check if we should override the duplicate block
                            should_override = False
                            if too_close_to_clicked:
                                # Track how long we've been blocked on this same shake
                                current_blocked_shake = (center_x, center_y)
                                
                                if last_blocked_shake is None or last_blocked_shake != current_blocked_shake:
                                    # New shake being blocked, start timer
                                    last_blocked_shake = current_blocked_shake
                                    blocked_shake_start_time = current_time
                                else:
                                    # Same shake still being blocked, check if we should override
                                    time_blocked = current_time - blocked_shake_start_time
                                    if time_blocked >= duplicate_override_time:
                                        should_override = True
                                        print(f"[SHAKE] Override: Clicking duplicate after {time_blocked:.2f}s blocked")
                                        # Remove the old click from memory so we can click this position
                                        if closest_clicked_id:
                                            clicked_shakes.discard(closest_clicked_id)
                            
                            if too_close_to_clicked and not should_override:
                                continue  # Skip this shake, too close to one we already clicked
                            
                            # Use actual position as unique identifier
                            shake_id = (center_x, center_y)
                            current_shakes.add(shake_id)
                            
                            # Click this shake
                            # Convert to absolute screen coordinates
                            screen_x = shake_area["x"] + center_x
                            screen_y = shake_area["y"] + center_y
                            
                            print(f"[SHAKE] Clicking shake at ({screen_x}, {screen_y})")
                            
                            # Anti-Roblox click technique from comet reference
                            # 1. Move cursor to position
                            ctypes.windll.user32.SetCursorPos(screen_x, screen_y)
                            
                            # 2. Move cursor down by 1 pixel relatively to register with Roblox
                            ctypes.windll.user32.mouse_event(0x0001, 0, 1, 0, 0)  # MOUSEEVENTF_MOVE
                            
                            # 3. Perform click
                            ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTDOWN
                            ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTUP
                            
                            clicked_shakes.add(shake_id)
                            
                            # Reset blocked shake timer since we successfully clicked something
                            last_blocked_shake = None
                            blocked_shake_start_time = None
                
                # Reset timeout if we found any shake
                if shake_found_this_loop:
                    last_shake_time = time.time()
                
                # Remove disappeared shakes from clicked set only if new shakes appeared elsewhere
                disappeared_shakes = last_detected_shakes - current_shakes
                new_shakes = current_shakes - last_detected_shakes
                if new_shakes and disappeared_shakes:
                    for shake_id in disappeared_shakes:
                        clicked_shakes.discard(shake_id)
                
                last_detected_shakes = current_shakes
                
                # Small delay (1ms)
                if self.stop_event.wait(0.001):
                    break
                
                # Print status every 20 loops (~1 second)
                if loop_count % 20 == 0:
                    shake_count = len(current_shakes)
                    time_left = shake_timeout - elapsed_since_shake
                    print(f"[SHAKE] Loop {loop_count} | Shakes: {shake_count} | Clicked: {len(clicked_shakes)} | Timeout: {time_left:.1f}s | Green pixels: {matching_pixels}")
        
        if self.stop_event.is_set():
            print("Shake interrupted")
        
        print("Shake: Complete")
        
    def _focus_roblox(self):
        """Focus on Roblox window"""
        try:
            import pygetwindow as gw
            # Find Roblox window
            roblox_windows = gw.getWindowsWithTitle('Roblox')
            if roblox_windows:
                roblox_window = roblox_windows[0]
                roblox_window.activate()
                print("✓ Roblox window focused")
            else:
                print("⚠️ Roblox window not found - proceeding anyway")
        except ImportError:
            # Fallback: use ctypes to focus window by title
            try:
                import ctypes
                hwnd = ctypes.windll.user32.FindWindowW(None, "Roblox")
                if hwnd:
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                    print("✓ Roblox window focused")
                else:
                    print("⚠️ Roblox window not found - proceeding anyway")
            except Exception as e:
                print(f"⚠️ Could not focus Roblox window: {e}")
    
    def _preload_yolo_model(self):
        """Preload YOLO model at startup in main thread to prevent window flashing"""
        try:
            if self.yolo_model is None:
                model_name = self.settings.get("selected_model", "None")
                if model_name != "None" and model_name:
                    # Get model path
                    if getattr(sys, 'frozen', False):
                        app_dir = os.path.dirname(sys.executable)
                    else:
                        app_dir = os.path.dirname(os.path.abspath(__file__))
                    
                    model_path = os.path.join(app_dir, model_name)
                    
                    if os.path.exists(model_path):
                        print(f"Preloading YOLO model: {model_name}...")
                        import warnings
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore")
                            self.yolo_model = YOLO(model_path, verbose=False)
                        print(f"✓ YOLO model preloaded successfully")
        except Exception as e:
            print(f"Warning: Could not preload YOLO model: {e}")
    
    def _load_yolo_model(self):
        """Lazy load YOLO model when needed"""
        if self.yolo_model is None:
            if YOLO is None:
                print("ERROR: Ultralytics YOLO not installed. Install with: pip install ultralytics")
                return False
            model_name = self.settings.get("selected_model", "None")
            
            if model_name == "None" or not model_name:
                print("ERROR: No model selected!")
                return False
            
            # Get model path
            if getattr(sys, 'frozen', False):
                app_dir = os.path.dirname(sys.executable)
            else:
                app_dir = os.path.dirname(os.path.abspath(__file__))
            
            model_path = os.path.join(app_dir, model_name)
            
            if not os.path.exists(model_path):
                print(f"ERROR: Model file not found: {model_path}")
                return False
            
            try:
                print(f"Loading YOLO model: {model_name}...")
                # Update GUI to keep it responsive during load
                self.root.update()
                # Suppress YOLO warnings and verbose output during load
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    self.yolo_model = YOLO(model_path, verbose=False)
                print(f"✓ Model loaded successfully")
            except Exception as e:
                print(f"ERROR loading model: {e}")
                return False
        
        return True
    
    def _load_shake_model(self):
        """Lazy load shake YOLO model when needed"""
        if self.shake_model is None:
            if YOLO is None:
                print("ERROR: Ultralytics YOLO not installed. Install with: pip install ultralytics")
                return False
            model_name = self.settings.get("selected_shake_model", "None")
            
            if model_name == "None" or not model_name:
                print("ERROR: No shake model selected!")
                return False
            
            # Get model path
            if getattr(sys, 'frozen', False):
                app_dir = os.path.dirname(sys.executable)
            else:
                app_dir = os.path.dirname(os.path.abspath(__file__))
            
            model_path = os.path.join(app_dir, model_name)
            
            if not os.path.exists(model_path):
                print(f"ERROR: Shake model file not found: {model_path}")
                return False
            
            try:
                print(f"Loading shake YOLO model: {model_name}...")
                self.root.update()
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    self.shake_model = YOLO(model_path, verbose=False)
                print(f"✓ Shake model loaded successfully")
            except Exception as e:
                print(f"ERROR loading shake model: {e}")
                return False
        
        return True
    
    def fish(self):
        """Detect fish icon and bar using YOLO in three stages"""
        print("Executing: Fish")
        
        # Create debug overlay if enabled
        if self.show_debug_overlay:
            self._create_debug_overlay()
        
        # Load model if not already loaded
        if not self._load_yolo_model():
            print("Cannot proceed with fish detection - no model loaded")
            return None
        
        fish_area = self.settings.get("fish_area")
        if not fish_area:
            print("ERROR: Fish area not configured")
            return None
        
        # Prepare MSS monitor region
        monitor = {
            "left": fish_area["x"],
            "top": fish_area["y"],
            "width": fish_area["width"],
            "height": fish_area["height"]
        }
        
        # Create MSS instance (thread-safe)
        with mss.mss() as sct:
            # ========== GATE 1: Wait for icon to appear ==========
            print("🚪 GATE 1: Waiting for icon to appear...")
            
            initial_icon_x = None
            initial_bar_x = None
            found_icon = False
            gate1_timeout = self.settings.get('gate1_timeout', 5.0)
            gate1_start_time = time.time()
            
            while not self.stop_event.is_set() and not found_icon:
                # Check timeout
                elapsed_time = time.time() - gate1_start_time
                if elapsed_time > gate1_timeout:
                    print(f"⏱️ Gate 1 timeout ({gate1_timeout}s) - exiting fish detection")
                    self._cleanup_debug_overlay()
                    return None
                screenshot = sct.grab(monitor)
                img_np = np.array(screenshot)
                img_bgr = img_np[:, :, :3]  # Keep BGR format (BGRA -> BGR)
                
                conf_threshold = self.settings.get("model_confidence", 0.75)
                results = self.yolo_model.predict(img_bgr, conf=conf_threshold, verbose=False)
                
                if len(results) > 0 and len(results[0].boxes) > 0:
                    for box in results[0].boxes:
                        cls_id = int(box.cls[0])
                        class_name = results[0].names[cls_id]
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        
                        if class_name.lower() == "icon":
                            initial_icon_x = int((x1 + x2) / 2)
                            found_icon = True
                            print(f"✓ Found icon at X: {initial_icon_x}px")
                            break
                        
                        elif class_name.lower() == "bar":
                            bar_left = int(x1)
                            bar_right = int(x2)
                            initial_bar_x = (bar_left + bar_right) // 2
                
                if not found_icon:
                    self.stop_event.wait(0.001)
            
            if self.stop_event.is_set():
                print("Gate 1 interrupted")
                self._cleanup_debug_overlay()
                return None
            
            # ========== GATE 2: Alternate hold/release until movement detected ==========
            print("🚪 GATE 2: Alternating hold/release until movement (5px threshold)...")
            
            movement_threshold = 5  # pixels
            alternate_state = False  # Start with release
            scan_count = 0
            movement_detected = False
        
            while not self.stop_event.is_set() and not movement_detected:
                    screenshot = sct.grab(monitor)
                    img_np = np.array(screenshot)
                    img_bgr = img_np[:, :, :3]  # Keep BGR format (BGRA -> BGR)
                    
                    conf_threshold = self.settings.get("model_confidence", 0.75)
                    results = self.yolo_model.predict(img_bgr, conf=conf_threshold, verbose=False)
                    
                    icon_center_x = None
                    bar_center_x = None
                    bar_left = None
                    bar_right = None
                    still_exists = False
                    
                    if len(results) > 0 and len(results[0].boxes) > 0:
                        for box in results[0].boxes:
                            cls_id = int(box.cls[0])
                            class_name = results[0].names[cls_id]
                            
                            if class_name.lower() in ["icon", "bar"]:
                                still_exists = True
                                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                                
                                if class_name.lower() == "icon":
                                    icon_center_x = int((x1 + x2) / 2)
                                elif class_name.lower() == "bar":
                                    bar_left = int(x1)
                                    bar_right = int(x2)
                                    bar_center_x = (bar_left + bar_right) // 2
                    
                    # Draw debug arrows
                    if self.show_debug_overlay and still_exists:
                        if icon_center_x is not None:
                            arrow_x = fish_area["x"] + icon_center_x
                            arrow_y = fish_area["y"] - 30
                            self.arrow_ids['icon_arrow'] = self._draw_arrow_down(
                                self.arrow_ids.get('icon_arrow'), arrow_x, arrow_y, 'cyan'
                            )
                        if bar_left is not None and bar_right is not None:
                            arrow_y = fish_area["y"] + fish_area["height"] + 30
                            self.arrow_ids['bar_left_arrow'] = self._draw_arrow_up(
                                self.arrow_ids.get('bar_left_arrow'), fish_area["x"] + bar_left, arrow_y, 'yellow'
                            )
                            self.arrow_ids['bar_right_arrow'] = self._draw_arrow_up(
                                self.arrow_ids.get('bar_right_arrow'), fish_area["x"] + bar_right, arrow_y, 'yellow'
                            )
                    
                    # Check if minigame ended - both icon AND bar must be gone
                    if icon_center_x is None and bar_center_x is None:
                        print("✓ Icon AND bar disappeared - minigame complete")
                        self._send_mouse_up()
                        break
                    
                    # Check for movement
                    if initial_icon_x is not None and icon_center_x is not None:
                        if abs(icon_center_x - initial_icon_x) >= movement_threshold:
                            movement_detected = True
                            print(f"✓ Icon moved {abs(icon_center_x - initial_icon_x)}px - entering Gate 3")
                    
                    if initial_bar_x is not None and bar_center_x is not None:
                        if abs(bar_center_x - initial_bar_x) >= movement_threshold:
                            movement_detected = True
                            print(f"✓ Bar moved {abs(bar_center_x - initial_bar_x)}px - entering Gate 3")
                    
                    # Alternate hold/release every scan
                    if not movement_detected:
                        scan_count += 1
                        alternate_state = not alternate_state
                        
                        if alternate_state:
                            self._send_mouse_down()
                        else:
                            self._send_mouse_up()
                        
                        print(f"[GATE2] Scan {scan_count} | {'HOLD' if alternate_state else 'REL '} | Icon: {icon_center_x if icon_center_x else 'N/A'}px | Bar: {bar_center_x if bar_center_x else 'N/A'}px")
            
            if self.stop_event.is_set():
                print("Gate 2 interrupted")
                self._send_mouse_up()
                self._cleanup_debug_overlay()
                return None
            
            if not still_exists:
                self._cleanup_debug_overlay()
                return None
            
            # ========== GATE 3: Tracking only (no control) ==========
            print("🚪 GATE 3: Tracking icon and bar (no control)...")
            
            # Clear Gate 2 bar arrow (middle arrow) to avoid confusion with Gate 3's left/right arrows
            if 'bar_arrow' in self.arrow_ids and self.debug_canvas is not None:
                try:
                    self.debug_canvas.delete(self.arrow_ids['bar_arrow'])
                    del self.arrow_ids['bar_arrow']
                except:
                    pass
            
            # Ensure mouse is released; Gate 3 does not control
            self._send_mouse_up()

            # ---- Comet-style Controller Parameters (from settings) ----
            kp = float(self.settings.get("kp", 0.9))
            kd = float(self.settings.get("kd", 0.3))
            pd_clamp = 1.0            # clamp for PD output (kept internal)
            bar_ratio = float(self.settings.get("bar_ratio", 0.6))
            speed_alpha = float(self.settings.get("speed_alpha", 0.7))
            damping_forward = float(self.settings.get("damping_forward", 2.0))
            damping_reverse = float(self.settings.get("damping_reverse", 0.5))

            # Hold state to avoid spamming mouseDown while already holding
            hold_state = False

            # Passive tracking state (optional: velocities for debug)
            prev_time = None
            prev_bar_center = None
            bar_velocity = 0.0

            # Comet controller memory
            initial_target_gap = None
            last_target_left_x = None
            last_target_right_x = None
            last_left_bar_x = None
            last_right_bar_x = None
            last_error = None
            last_target_x = None
            
            while not self.stop_event.is_set():
                loop_start = time.time()
                
                screenshot = sct.grab(monitor)
                img_np = np.array(screenshot)
                img_bgr = img_np[:, :, :3]  # Keep BGR format (BGRA -> BGR)
                
                conf_threshold = self.settings.get("model_confidence", 0.75)
                results = self.yolo_model.predict(img_bgr, conf=conf_threshold, verbose=False)
                
                icon_center_x = None
                bar_center_x = None
                bar_left_x = None
                bar_right_x = None
                still_exists = False
                
                if len(results) > 0 and len(results[0].boxes) > 0:
                    for box in results[0].boxes:
                        cls_id = int(box.cls[0])
                        class_name = results[0].names[cls_id]
                        
                        if class_name.lower() in ["icon", "bar"]:
                            still_exists = True
                            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                            
                            if class_name.lower() == "icon":
                                icon_center_x = int((x1 + x2) / 2)
                            elif class_name.lower() == "bar":
                                bar_left_x = int(x1)
                                bar_right_x = int(x2)
                                bar_center_x = (bar_left_x + bar_right_x) // 2
                
                # Draw debug arrows
                if self.show_debug_overlay and still_exists:
                    if icon_center_x is not None:
                        arrow_x = fish_area["x"] + icon_center_x
                        arrow_y = fish_area["y"] - 30
                        self.arrow_ids['icon_arrow'] = self._draw_arrow_down(
                            self.arrow_ids.get('icon_arrow'), arrow_x, arrow_y, 'cyan'
                        )
                    if bar_left_x is not None and bar_right_x is not None:
                        arrow_y = fish_area["y"] + fish_area["height"] + 30
                        self.arrow_ids['bar_left_arrow'] = self._draw_arrow_up(
                            self.arrow_ids.get('bar_left_arrow'), fish_area["x"] + bar_left_x, arrow_y, 'yellow'
                        )
                        self.arrow_ids['bar_right_arrow'] = self._draw_arrow_up(
                            self.arrow_ids.get('bar_right_arrow'), fish_area["x"] + bar_right_x, arrow_y, 'yellow'
                        )
                
                # Check if minigame ended - both icon AND bar must be gone
                if icon_center_x is None and bar_center_x is None:
                    print("✓ Icon AND bar disappeared - minigame complete")
                    self._send_mouse_up()
                    break
                
                # Comet-style controller: stability + edge + PD
                if icon_center_x is not None and bar_center_x is not None:
                    current_time = time.time()

                    # Smoothed bar velocity (pixels/sec) for PD control
                    if prev_time is not None and prev_bar_center is not None:
                        dt = current_time - prev_time
                        if dt > 0:
                            raw_bar_velocity = (bar_center_x - prev_bar_center) / dt
                            # velocity smoothing using speed_alpha
                            bar_velocity = speed_alpha * raw_bar_velocity + (1 - speed_alpha) * bar_velocity

                    prev_time = current_time
                    prev_bar_center = bar_center_x

                    error = icon_center_x - bar_center_x
                    elapsed = current_time - loop_start
                    width = fish_area["width"]

                    # Compute left/right target (approximate from center; gap memory helps when available)
                    target_middle_x = icon_center_x
                    # Use detected bar edges directly
                    left_bar_x = bar_left_x if bar_left_x is not None else (bar_center_x - 1)
                    right_bar_x = bar_right_x if bar_right_x is not None else (bar_center_x + 1)
                    bar_middle_x = (left_bar_x + right_bar_x) / 2.0

                    # Initialize target gap on first valid frame
                    if initial_target_gap is None and bar_left_x is not None and bar_right_x is not None:
                        initial_target_gap = abs(right_bar_x - left_bar_x)
                        last_target_left_x = target_middle_x - initial_target_gap / 2.0
                        last_target_right_x = target_middle_x + initial_target_gap / 2.0
                        last_left_bar_x = left_bar_x
                        last_right_bar_x = right_bar_x

                    # Edge detection using bar_ratio
                    current_bar_width = abs(right_bar_x - left_bar_x)
                    edge_threshold = current_bar_width * bar_ratio if current_bar_width > 0 else width * 0.5 * bar_ratio
                    target_at_left_edge = target_middle_x < edge_threshold
                    target_at_right_edge = target_middle_x > (width - edge_threshold)
                    target_at_edge = target_at_left_edge or target_at_right_edge

                    # Comet logic
                    if target_at_edge:
                        if target_at_left_edge:
                            should_hold = False
                        elif target_at_right_edge:
                            should_hold = True
                    else:
                        # PD control with asymmetric damping
                        # P term
                        p_term = kp * error
                        # D term (bar velocity already computed; use asymmetric damping)
                        error_magnitude_decreasing = (last_error is not None) and (abs(error) < abs(last_error))
                        bar_moving_toward_target = (bar_velocity > 0 and error > 0) or (bar_velocity < 0 and error < 0)
                        if error_magnitude_decreasing and bar_moving_toward_target:
                            damping_multiplier = damping_forward
                        else:
                            damping_multiplier = damping_reverse
                        d_term = -kd * damping_multiplier * bar_velocity

                        control_signal = max(-pd_clamp, min(pd_clamp, p_term + d_term))
                        should_hold = control_signal > 0

                        # Update PD memory
                        last_error = error
                        last_target_x = target_middle_x
                        last_left_bar_x = left_bar_x
                        last_right_bar_x = right_bar_x

                    # Execute mouse control only on state change
                    desired_hold = should_hold
                    if desired_hold != hold_state:
                        if desired_hold:
                            self._send_mouse_down()
                            action = "HOLD"
                        else:
                            self._send_mouse_up()
                            action = "REL "
                        hold_state = desired_hold
                    else:
                        action = "HOLD" if hold_state else "REL "

                    # Print status
                    print(
                        f"[GATE3 COMET {elapsed:.3f}s] {action} | Bar: {bar_center_x:4d}px | Icon: {icon_center_x:4d}px | "
                        f"Err: {error:+5.1f}px | BarVel: {bar_velocity:+6.1f} | P: {kp*error:+6.2f} | D: {-kd*bar_velocity:+6.2f}"
                    )
                # If one is missing, just continue without mouse actions
            
            if self.stop_event.is_set():
                print("Gate 3 interrupted")
                self._send_mouse_up()
                self._cleanup_debug_overlay()
                return None
        
        # Clean up overlay
        self._cleanup_debug_overlay()
        return None
    
    def maelstrom_fish(self):
        """Maelstrom mode fish - Gate 1 + Gate 3 with maelstrom-only logic"""
        print("Executing: Maelstrom Fish")
        
        # Create debug overlay if enabled
        if self.show_debug_overlay:
            self._create_debug_overlay()
        
        # Load model if not already loaded
        if not self._load_yolo_model():
            print("Cannot proceed with fish detection - no model loaded")
            return None
        
        fish_area = self.settings.get("fish_area")
        if not fish_area:
            print("ERROR: Fish area not configured")
            return None
        
        # Prepare MSS monitor region
        monitor = {
            "left": fish_area["x"],
            "top": fish_area["y"],
            "width": fish_area["width"],
            "height": fish_area["height"]
        }
        
        # Create MSS instance (thread-safe)
        with mss.mss() as sct:
            # ========== GATE 1: Wait for icon to appear ==========
            print("🚪 GATE 1: Waiting for icon to appear...")
            
            initial_icon_x = None
            found_icon = False
            gate1_timeout = self.settings.get('gate1_timeout', 5.0)
            gate1_start_time = time.time()
            
            while not self.stop_event.is_set() and not found_icon:
                # Check timeout
                elapsed_time = time.time() - gate1_start_time
                if elapsed_time > gate1_timeout:
                    print(f"⏱️ Gate 1 timeout ({gate1_timeout}s) - exiting fish detection")
                    self._cleanup_debug_overlay()
                    return None
                
                screenshot = sct.grab(monitor)
                img_np = np.array(screenshot)
                img_bgr = img_np[:, :, :3]  # Keep BGR format (BGRA -> BGR)
                
                conf_threshold = self.settings.get("model_confidence", 0.75)
                results = self.yolo_model.predict(img_bgr, conf=conf_threshold, verbose=False)
                
                if len(results) > 0 and len(results[0].boxes) > 0:
                    for box in results[0].boxes:
                        cls_id = int(box.cls[0])
                        class_name = results[0].names[cls_id]
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        
                        if class_name.lower() == "icon":
                            initial_icon_x = int((x1 + x2) / 2)
                            found_icon = True
                            print(f"✓ Found icon at X: {initial_icon_x}px")
                            break
                
                if not found_icon:
                    self.stop_event.wait(0.001)
            
            if self.stop_event.is_set():
                print("Gate 1 interrupted")
                self._cleanup_debug_overlay()
                return None
            
            # ========== GATE 3: Maelstrom control logic ==========
            print("🚪 GATE 3: Maelstrom minigame control...")
            
            # Ensure mouse is released at start
            self._send_mouse_up()
            hold_state = False
            
            # Maelstrom parameters from settings
            bar_ratio = float(self.settings.get("bar_ratio", 0.6))
            speed_alpha = float(self.settings.get("speed_alpha", 0.7))
            maelstrom_color_tolerance = int(self.settings.get("maelstrom_color_tolerance", 3))
            maelstrom_scan_left_margin = float(self.settings.get("maelstrom_scan_left_margin", 0.2))
            maelstrom_scan_right_margin = float(self.settings.get("maelstrom_scan_right_margin", 0.2))
            maelstrom_left_section = float(self.settings.get("maelstrom_left_section", 0.1))
            maelstrom_right_section = float(self.settings.get("maelstrom_right_section", 0.5))
            
            # Note: maelstrom_gap_threshold and maelstrom_separation_speed removed - no longer used after simplification
            
            # Maelstrom tracking variables - fresh for this fish
            maelstrom_target_colors = [
                np.array([130, 80, 74], dtype=np.uint8),
                np.array([135, 86, 79], dtype=np.uint8),
                np.array([135, 86, 80], dtype=np.uint8),
                np.array([135, 85, 79], dtype=np.uint8),
                np.array([135, 85, 78], dtype=np.uint8),
                np.array([135, 84, 78], dtype=np.uint8),
                np.array([135, 84, 77], dtype=np.uint8),
                np.array([135, 83, 77], dtype=np.uint8),
            ]
            maelstrom_prev_left_x = None
            maelstrom_prev_right_x = None
            maelstrom_prev_time = None
            maelstrom_approach_rate = 0.0
            maelstrom_state = "minigame"  # State machine: "minigame" or "release"
            colors_were_missing = False  # Track if colors were lost - must detect again before holding
            
            # Comet fallback parameters
            kp = float(self.settings.get("kp", 0.9))
            kd = float(self.settings.get("kd", 0.3))
            damping_forward = float(self.settings.get("damping_forward", 2.0))
            damping_reverse = float(self.settings.get("damping_reverse", 0.5))
            prev_time = None
            prev_bar_center = None
            bar_velocity = 0.0
            last_error = None
            
            while not self.stop_event.is_set():
                loop_start = time.time()
                
                screenshot = sct.grab(monitor)
                img_np = np.array(screenshot)
                img_bgr = img_np[:, :, :3]
                
                conf_threshold = self.settings.get("model_confidence", 0.75)
                results = self.yolo_model.predict(img_bgr, conf=conf_threshold, verbose=False)
                
                icon_center_x = None
                bar_center_x = None
                bar_left_x = None
                bar_right_x = None
                bar_top_y = None
                still_exists = False
                
                if len(results) > 0 and len(results[0].boxes) > 0:
                    for box in results[0].boxes:
                        cls_id = int(box.cls[0])
                        class_name = results[0].names[cls_id]
                        
                        if class_name.lower() in ["icon", "bar"]:
                            still_exists = True
                            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                            
                            if class_name.lower() == "icon":
                                icon_center_x = int((x1 + x2) / 2)
                                print(f"[DEBUG] YOLO detected icon at X={icon_center_x}")
                            elif class_name.lower() == "bar":
                                bar_left_x = int(x1)
                                bar_right_x = int(x2)
                                bar_center_x = (bar_left_x + bar_right_x) // 2
                                bar_top_y = int(y1)
                                print(f"[DEBUG] YOLO detected bar: left={bar_left_x}, right={bar_right_x}, center={bar_center_x}")
                else:
                    print(f"[DEBUG] YOLO detected NO boxes (results length: {len(results) if len(results) > 0 else 0})")
                
                # Show what we ended up with after detection
                if icon_center_x is None or bar_center_x is None:
                    print(f"[DEBUG] Detection incomplete - icon={'DETECTED' if icon_center_x is not None else 'MISSING'}, bar={'DETECTED' if bar_center_x is not None else 'MISSING'}")
                
                # Draw debug arrows
                if self.show_debug_overlay and still_exists:
                    if icon_center_x is not None:
                        arrow_x = fish_area["x"] + icon_center_x
                        arrow_y = fish_area["y"] - 30
                        self.arrow_ids['icon_arrow'] = self._draw_arrow_down(
                            self.arrow_ids.get('icon_arrow'), arrow_x, arrow_y, 'cyan'
                        )
                    if bar_left_x is not None and bar_right_x is not None:
                        arrow_y = fish_area["y"] + fish_area["height"] + 30
                        self.arrow_ids['bar_left_arrow'] = self._draw_arrow_up(
                            self.arrow_ids.get('bar_left_arrow'), fish_area["x"] + bar_left_x, arrow_y, 'yellow'
                        )
                        self.arrow_ids['bar_right_arrow'] = self._draw_arrow_up(
                            self.arrow_ids.get('bar_right_arrow'), fish_area["x"] + bar_right_x, arrow_y, 'yellow'
                        )
                        
                        # Draw maelstrom scan area arrows
                        try:
                            bar_width = bar_right_x - bar_left_x
                            scan_left = int(bar_left_x + (bar_width * maelstrom_scan_left_margin))
                            scan_right = int(bar_right_x - (bar_width * maelstrom_scan_right_margin))
                            arrow_y = fish_area["y"] - 30
                            self.arrow_ids['maelstrom_left_arrow'] = self._draw_arrow_down(
                                self.arrow_ids.get('maelstrom_left_arrow'), 
                                fish_area["x"] + scan_left, arrow_y, 'magenta'
                            )
                            self.arrow_ids['maelstrom_right_arrow'] = self._draw_arrow_down(
                                self.arrow_ids.get('maelstrom_right_arrow'), 
                                fish_area["x"] + scan_right, arrow_y, 'magenta'
                            )
                            print(f"[DEBUG] Arrows updated: L={fish_area['x'] + scan_left}, R={fish_area['x'] + scan_right}")
                        except Exception as e:
                            print(f"[DEBUG] Arrow drawing error: {e}")
                
                # Check if minigame ended - both icon AND bar must be gone
                if icon_center_x is None and bar_center_x is None:
                    print("✓ Icon AND bar disappeared - minigame complete")
                    self._send_mouse_up()
                    break
                
                # Main maelstrom logic
                if icon_center_x is not None and bar_center_x is not None and bar_left_x is not None and bar_right_x is not None:
                    print(f"[DEBUG] Main logic block entered - icon={icon_center_x}, bar_center={bar_center_x}")
                    current_time = time.time()
                    
                    # Calculate bar velocity for comet fallback
                    if prev_time is not None and prev_bar_center is not None:
                        dt = current_time - prev_time
                        if dt > 0:
                            raw_bar_velocity = (bar_center_x - prev_bar_center) / dt
                            bar_velocity = speed_alpha * raw_bar_velocity + (1 - speed_alpha) * bar_velocity
                    
                    prev_time = current_time
                    prev_bar_center = bar_center_x
                    
                    # Edge detection
                    current_bar_width = abs(bar_right_x - bar_left_x)
                    width = fish_area["width"]
                    edge_threshold = current_bar_width * bar_ratio if current_bar_width > 0 else width * 0.5 * bar_ratio
                    target_at_left_edge = icon_center_x < edge_threshold
                    target_at_right_edge = icon_center_x > (width - edge_threshold)
                    
                    # Try maelstrom color detection first
                    maelstrom_triggered = False
                    should_hold = False
                    
                    # Define color scan area based on YOLO bar detection
                    if bar_left_x is not None and bar_right_x is not None and bar_top_y is not None:
                        bar_width = bar_right_x - bar_left_x
                        
                        # Scan area boundaries (using separate left/right margins)
                        scan_left = int(bar_left_x + (bar_width * maelstrom_scan_left_margin))
                        scan_right = int(bar_right_x - (bar_width * maelstrom_scan_right_margin))
                        scan_bottom = bar_top_y  # Top of bar (from YOLO detection)
                        scan_top = self.maelstrom_y_coord if self.maelstrom_y_coord is not None else 0
                        
                        # Ensure valid bounds
                        if scan_top < scan_bottom and scan_left < scan_right:
                            # Crop the image to scan area
                            scan_region = img_bgr[scan_top:scan_bottom, scan_left:scan_right]
                            
                            # Scan for target colors in cropped region
                            mask = None
                            for target_color in maelstrom_target_colors:
                                lower_bound = np.clip(target_color.astype(np.int16) - maelstrom_color_tolerance, 0, 255).astype(np.uint8)
                                upper_bound = np.clip(target_color.astype(np.int16) + maelstrom_color_tolerance, 0, 255).astype(np.uint8)
                                color_mask = cv2.inRange(scan_region, lower_bound, upper_bound)
                                mask = color_mask if mask is None else cv2.bitwise_or(mask, color_mask)
                            
                            # Find leftmost and rightmost pixels in cropped region
                            coords = np.column_stack(np.where(mask > 0))
                            coords_found = len(coords) > 0
                            if coords_found:
                                x_coords = coords[:, 1]
                                # Convert back to full image coordinates
                                leftmost_x = int(np.min(x_coords)) + scan_left
                                rightmost_x = int(np.max(x_coords)) + scan_left
                                print(f"[DEBUG] Colors FOUND: {len(coords)} pixels, leftmost={leftmost_x}, rightmost={rightmost_x}")
                            else:
                                coords_found = False
                                print(f"[DEBUG] Colors NOT FOUND in scan region")
                        else:
                            coords_found = False
                            print(f"[DEBUG] Invalid scan bounds - scan skipped")
                    else:
                        coords_found = False
                        print(f"[DEBUG] Bar position incomplete - color scan skipped")
                    
                    if coords_found:
                        gap = rightmost_x - leftmost_x
                        
                        # Colors detected - clear the missing flag
                        colors_were_missing = False
                        
                        # Calculate approach rate
                        if maelstrom_prev_left_x is not None and maelstrom_prev_right_x is not None and maelstrom_prev_time is not None:
                            dt = current_time - maelstrom_prev_time
                            if dt > 0:
                                left_velocity = (leftmost_x - maelstrom_prev_left_x) / dt
                                right_velocity = (rightmost_x - maelstrom_prev_right_x) / dt
                                raw_approach_rate = left_velocity - right_velocity
                                maelstrom_approach_rate = speed_alpha * raw_approach_rate + (1 - speed_alpha) * maelstrom_approach_rate
                        
                        # Check icon position relative to bar (split into 3 sections using settings)
                        bar_width = bar_right_x - bar_left_x
                        left_threshold = bar_left_x + (bar_width * maelstrom_left_section)
                        right_threshold = bar_left_x + (bar_width * maelstrom_right_section)
                        
                        in_left_section = icon_center_x < left_threshold
                        in_middle_section = left_threshold <= icon_center_x <= right_threshold
                        in_right_section = icon_center_x > right_threshold
                        
                        print(f"[DEBUG] Icon sections: left={in_left_section}, middle={in_middle_section}, right={in_right_section}, at_right_edge={target_at_right_edge}")
                        print(f"[DEBUG] Current state: {maelstrom_state}")
                        
                        maelstrom_triggered = True
                        
                        # State machine: Right edge vs middle zone
                        if target_at_right_edge:
                            # Icon at right edge of screen - spam minigame
                            maelstrom_state = "minigame"
                            # Simple logic: hold if colors present AND not waiting for redetection
                            should_hold = not colors_were_missing
                            if should_hold:
                                print(f"[MAELSTROM] RIGHT EDGE - Colors detected - HOLD")
                            else:
                                print(f"[MAELSTROM] RIGHT EDGE - Waiting for color redetection - RELEASE")
                        
                        else:
                            # Middle zone - state machine based on bar sections
                            if in_left_section:
                                # Left section: Enter "moving_to_right" state - release until we reach right section
                                # OVERRIDE: Always release in left section to prevent overshoot
                                maelstrom_state = "moving_to_right"
                                should_hold = False
                                print(f"[MAELSTROM] LEFT SECTION - Moving to right - RELEASE")
                            
                            elif in_right_section:
                                # Right section: Always play minigame
                                maelstrom_state = "minigame"
                                # Simple logic: hold if colors present AND not waiting for redetection
                                should_hold = not colors_were_missing
                                if should_hold:
                                    print(f"[MAELSTROM] RIGHT SECTION - Colors detected - HOLD")
                                else:
                                    print(f"[MAELSTROM] RIGHT SECTION - Waiting for color redetection - RELEASE")
                            
                            else:  # in_middle_section
                                # Middle section: Depends on state
                                if maelstrom_state == "moving_to_right":
                                    # Coming from left - keep releasing until we reach right section
                                    should_hold = False
                                    print(f"[MAELSTROM] MIDDLE SECTION - Moving to right - RELEASE")
                                else:
                                    # Already in minigame state - play the minigame
                                    maelstrom_state = "minigame"
                                    # Simple logic: hold if colors present AND not waiting for redetection
                                    should_hold = not colors_were_missing
                                    if should_hold:
                                        print(f"[MAELSTROM] MIDDLE SECTION - Colors detected - HOLD")
                                    else:
                                        print(f"[MAELSTROM] MIDDLE SECTION - Waiting for color redetection - RELEASE")
                        
                        # Update tracking
                        maelstrom_prev_left_x = leftmost_x
                        maelstrom_prev_right_x = rightmost_x
                        maelstrom_prev_time = current_time
                    
                    else:
                        # Colors not detected - release and set flag
                        colors_were_missing = True
                        # But first check if we need to override based on icon position
                        if bar_left_x is not None and bar_right_x is not None and icon_center_x is not None:
                            bar_width = bar_right_x - bar_left_x
                            left_threshold = bar_left_x + (bar_width * maelstrom_left_section)
                            in_left_section = icon_center_x < left_threshold
                            
                            if in_left_section:
                                # Override: force release if in left section
                                maelstrom_state = "moving_to_right"
                                print(f"[MAELSTROM] LEFT SECTION (no colors) - Moving to right - RELEASE")
                            else:
                                print(f"[MAELSTROM] No colors detected - RELEASE")
                        else:
                            print(f"[MAELSTROM] No colors detected - RELEASE")
                        
                        should_hold = False
                        maelstrom_triggered = True
                    
                    # Fallback to comet if colors not detected
                    if not maelstrom_triggered:
                        if bar_left_x is None or bar_right_x is None:
                            print("[MAELSTROM] No bar detected")
                        elif not (scan_top < scan_bottom and scan_left < scan_right):
                            print(f"[MAELSTROM] Invalid scan bounds - Top: {scan_top}, Bottom: {scan_bottom}, Left: {scan_left}, Right: {scan_right}")
                        else:
                            print("[MAELSTROM] No colors detected in scan region - Using comet fallback")
                        
                        error = icon_center_x - bar_center_x
                        
                        if target_at_left_edge:
                            should_hold = False
                        elif target_at_right_edge:
                            should_hold = True
                        else:
                            # PD control
                            p_term = kp * error
                            error_magnitude_decreasing = (last_error is not None) and (abs(error) < abs(last_error))
                            bar_moving_toward_target = (bar_velocity > 0 and error > 0) or (bar_velocity < 0 and error < 0)
                            if error_magnitude_decreasing and bar_moving_toward_target:
                                damping_multiplier = damping_forward
                            else:
                                damping_multiplier = damping_reverse
                            d_term = -kd * damping_multiplier * bar_velocity
                            control_signal = max(-1.0, min(1.0, p_term + d_term))
                            should_hold = control_signal > 0
                            last_error = error
                    
                    # Execute mouse control
                    if should_hold != hold_state:
                        if should_hold:
                            print(f"[DEBUG] Mouse DOWN")
                            self._send_mouse_down()
                        else:
                            print(f"[DEBUG] Mouse UP")
                            self._send_mouse_up()
                        hold_state = should_hold
                else:
                    print(f"[DEBUG] Main logic SKIPPED - icon={icon_center_x}, bar_center={bar_center_x}, bar_left={bar_left_x}, bar_right={bar_right_x}")
            
            if self.stop_event.is_set():
                print("Maelstrom fish interrupted")
                self._send_mouse_up()
                self._cleanup_debug_overlay()
                return None
        
        # Clean up
        self._cleanup_debug_overlay()
        return None
    
    def main_loop(self):
        """Main automation loop - can be stopped instantly"""
        print("Main loop started")
        
        while not self.stop_event.is_set():
            try:
                # 1. Cast
                if self.stop_event.is_set():
                    break
                self.cast()
                
                # 2. Shake
                if self.stop_event.is_set():
                    break
                shake_result = self.shake()
                
                # If shake timed out, restart the cycle (skip fish)
                if shake_result == "timeout":
                    print("Shake timed out - restarting cycle")
                    continue
                
                # 3. Fish
                if self.stop_event.is_set():
                    break
                
                # Use maelstrom fish logic if maelstrom mode is enabled, otherwise use normal comet fish
                if self.maelstrom_mode:
                    self.maelstrom_fish()
                else:
                    self.fish()
                
                # Wait after fish before next cycle
                post_fish_wait = self.settings.get('post_fish_wait', 2.0)
                if self.stop_event.wait(post_fish_wait):
                    break
                
            except Exception as e:
                error_str = str(e)
                # Ignore win32api "success" errors (error code 0)
                if "Error code from Windows: 0" not in error_str:
                    print(f"Error in main loop: {e}")
                    import traceback
                    traceback.print_exc()
                    break
        
        print("Main loop stopped")
        
    def toggle_start_stop(self):
        self.is_running = not self.is_running
        
        if self.is_running:
            # Start the main loop
            self.stop_event.clear()
            self.loop_thread = threading.Thread(target=self.main_loop, daemon=True)
            self.loop_thread.start()
            status = "Running"
            # Minimize the window if auto_minimize is enabled
            if self.settings.get("auto_minimize", True):
                self.root.iconify()
        else:
            # Stop the main loop instantly
            self.stop_event.set()
            if self.loop_thread and self.loop_thread.is_alive():
                self.loop_thread.join(timeout=1.0)  # Wait max 1 second
            status = "Stopped"
            # Restore the window
            self.root.deiconify()
            self.root.lift()
            self.root.focus()
        
        self.status_label.config(text=f"Status: {status}")
        print(f"Toggle Start/Stop - Now {status}")
        
    def change_area(self):
        if self.area_selector_active:
            # Close the current selector if it's open
            if self.current_selector:
                self.current_selector.save_and_close()
            return
        
        self.area_selector_active = True
        print("Change Area triggered - Taking screenshot...")
        
        # Take screenshot
        screenshot = ImageGrab.grab()
        
        # Open area selector
        def on_areas_selected(shake_area, fish_area, friend_area):
            self.settings["shake_area"] = shake_area
            self.settings["fish_area"] = fish_area
            self.settings["friend_area"] = friend_area
            self._save_settings()
            self.status_label.config(text="Status: Areas Saved!")
            print(f"Areas saved: Shake={shake_area}, Fish={fish_area}, Friend={friend_area}")
            self.root.after(2000, lambda: self.status_label.config(
                text=f"Status: {'Running' if self.is_running else 'Stopped'}"))
            # Reset flag after a short delay to prevent immediate re-trigger
            self.root.after(100, lambda: setattr(self, 'area_selector_active', False))
            self.current_selector = None
        
        def on_selector_closed():
            # Ensure flag is reset even if window is closed without saving
            self.area_selector_active = False
            self.current_selector = None
            self.root.focus_force()  # Return focus to main window
        
        selector = TripleAreaSelector(
            self.root,
            screenshot,
            self.settings["shake_area"],
            self.settings["fish_area"],
            self.settings["friend_area"],
            on_areas_selected,
            self.change_area_key  # Pass the current change_area key
        )
        
        # Store reference to current selector
        self.current_selector = selector
        
        # Bind window destruction to reset flag
        selector.window.bind('<Destroy>', lambda e: on_selector_closed())
        
    def exit_app(self):
        print("🛑 EXIT KEY PRESSED - Force closing now...")
        # Try to stop loops and release mouse, then hard-exit
        self.stop_event.set()
        try:
            self._send_mouse_up()
        except:
            pass
        # Immediately terminate the process without further cleanup/saves
        os._exit(0)
        
    def rebind(self, action):
        # Temporarily unhook all hotkeys to prevent interference
        keyboard.unhook_all()
        
        # Update status to show waiting
        action_names = {
            "start_stop": "Start/Stop",
            "change_area": "Change Area",
            "exit": "Exit"
        }
        self.status_label.config(text=f"Press a key for {action_names.get(action, action)}...")
        
        listener_active = [True]
        
        def on_key_press(event):
            if not listener_active[0]:
                return
            
            new_key = event.name.upper()  # Normalize to uppercase
            
            # Check if key is already in use by another action
            existing_keys = {}
            if action != "start_stop":
                existing_keys["Start/Stop"] = self.start_stop_key
            if action != "change_area":
                existing_keys["Change Area"] = self.change_area_key
            if action != "exit":
                existing_keys["Exit"] = self.exit_key
            
            # Check for conflicts
            for existing_action, existing_key in existing_keys.items():
                if new_key == existing_key:
                    self.status_label.config(text=f"Error: {new_key} already used for {existing_action}!")
                    self.root.after(2000, lambda: self.status_label.config(
                        text=f"Press a key for {action_names.get(action, action)}..."))
                    return  # Don't deactivate listener, wait for another key
            
            listener_active[0] = False
            
            # Update the appropriate key binding
            if action == "start_stop":
                self.start_stop_key = new_key
                self.settings["start_stop_key"] = new_key
                self.start_stop_btn.config(text=f"Start/Stop ({new_key})")
            elif action == "change_area":
                self.change_area_key = new_key
                self.settings["change_area_key"] = new_key
                self.change_area_btn.config(text=f"Change Area ({new_key})")
            elif action == "exit":
                self.exit_key = new_key
                self.settings["exit_key"] = new_key
                self.exit_btn.config(text=f"Exit ({new_key})")
            
            # Save settings immediately
            self._save_settings()
            
            # Clean up and restore
            keyboard.unhook_all()
            self.setup_hotkeys()  # Reestablish hotkeys with new binding
            
            # Update status
            self.status_label.config(text=f"{action_names.get(action, action)} rebound to {new_key}")
            self.root.after(2000, lambda: self.status_label.config(
                text=f"Status: {'Running' if self.is_running else 'Stopped'}"))
        
        # Set up keyboard listener
        keyboard.on_press(on_key_press, suppress=False)

if __name__ == "__main__":
    root = tk.Tk()
    app = IRUSNeuralGUI(root)
    root.mainloop()

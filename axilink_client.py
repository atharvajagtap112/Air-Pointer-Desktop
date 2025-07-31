import websocket
import json
import pyautogui
import threading
import tkinter as tk
from tkinter import ttk
import qrcode
from PIL import Image, ImageTk
import random
import time
import socket
import mss
from io import BytesIO
import base64
import os
import sys
import traceback

# Disable PyAutoGUI failsafe for smoother operation
pyautogui.FAILSAFE = False


def get_local_ip():
    """Get local IP address for WebSocket server"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP


ip = get_local_ip()
class RemoteControlClient:
    def __init__(self):
        """Initialize the Axilink Desktop Client"""
        self.SERVER_WS_URL = f"ws://{ip}:8080/ws"
        self.session_code = None
        self.ws = None
        self.is_connected = False
        self.root = None
        self.qr_label = None
        self.status_label = None
        self.code_label = None
        self.qr_generated = False
        self.mode = "control"
        self.screen_thread = None
        self.stop_screen_thread = threading.Event()
        self.debug_label = None
        self.last_frame_time = 0
        self.consecutive_errors = 0
        self.monitor_info = {}  # Store monitor positions and sizes

        # For improved frame skipping
        self.frame_skip = 0
        self.adaptive_frame_skip = True
        self.last_frame_duration = 0

        # HARDCODED: Touch coordinate mapping options based on calibration
        self.flip_x_coordinates = False
        self.flip_y_coordinates = False

        # HARDCODED: Fine-tuning values as specified
        self.scaling_factor_x = 1.16  # X scale = 1.16
        self.scaling_factor_y = 1.0  # Y scale = 1.00
        self.offset_x = 0.0  # X offset = 0.00
        self.offset_y = 0.0  # Y offset = 0.00

        # Create the root window first
        self.root = tk.Tk()
        self.root.withdraw()  # Hide it for now

        # Now we can safely create Tkinter variables
        self.monitor_var = tk.IntVar(value=1)  # Default to first monitor
        self.quality_var = tk.IntVar(value=65)  # Default to 65% quality - lower for better performance
        self.fps_var = tk.IntVar(value=15)  # Default to 15 FPS - higher for smoother experience

        # Advanced settings with better defaults
        self.resize_factor_var = tk.DoubleVar(value=0.5)  # Default resize to 50%
        self.enable_adaptive_quality = tk.BooleanVar(value=True)  # Enable adaptive quality by default

        # Initialization for adaptive quality
        self.target_size_kb = 150  # Target size in KB
        self.min_quality = 40  # Minimum quality level
        self.max_quality = 85  # Maximum quality level
        self.current_quality = 65  # Starting quality

        # Default monitor selection
        self.selected_monitor = 1

        # Get screen dimensions for aspect ratio calculations
        self.screen_width, self.screen_height = pyautogui.size()
        self.screen_aspect_ratio = self.screen_width / self.screen_height

        # Create an in-memory buffer for image processing
        self.img_buffer = BytesIO()

    def generate_session_code(self):
        """Generate a random 4-digit session code"""
        return str(random.randint(1000, 9999))

    def generate_qr_code(self, code):
        """Generate QR code for the session"""
        qr_data = code + f"ws://{ip}:8080/ws"
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        return img

    def test_center_point(self):
        """Move cursor to center of selected monitor to test mapping"""
        try:
            # Map center point (0.5, 0.5) to screen coordinates
            x, y = self.map_touch_coordinates(0.5, 0.5)

            # Move cursor to the mapped center point
            pyautogui.moveTo(x, y)

            # Log the action
            print(f"[INFO] Testing center point: Moving cursor to ({x}, {y})")
            self.update_debug(f"Moved to center: ({x}, {y})")

            # Create a visual indicator that disappears after a moment
            indicator = tk.Toplevel(self.root)
            indicator.attributes('-alpha', 0.7)  # Semi-transparent
            indicator.attributes('-topmost', True)
            indicator.overrideredirect(True)  # No window decorations

            # Position and size the indicator
            size = 30
            indicator.geometry(f"{size}x{size}+{x - size // 2}+{y - size // 2}")

            # Add a colored circle
            canvas = tk.Canvas(indicator, bg='black', highlightthickness=0)
            canvas.pack(fill=tk.BOTH, expand=True)
            canvas.create_oval(2, 2, size - 2, size - 2, fill='red', outline='white', width=2)

            # Automatically close after 1.5 seconds
            indicator.after(1500, indicator.destroy)

        except Exception as e:
            print(f"[ERROR] Test center point failed: {e}")
            traceback.print_exc()

    def setup_gui(self):
        """Set up the Tkinter GUI with scrolling functionality"""
        self.root.deiconify()  # Show the window now
        self.root.title("Axilink Desktop Client")
        self.root.geometry("400x550")  # Slightly larger for advanced settings
        self.root.configure(bg='#2c3e50')
        self.root.attributes('-topmost', False)  # Set to False to avoid interfering with screen mirroring

        # --------- Begin Scrollable Frame Setup ---------
        outer_frame = tk.Frame(self.root, bg='#2c3e50')
        outer_frame.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(outer_frame, bg='#2c3e50', highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg='#2c3e50')

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _on_mousewheel(event):
            if os.name == 'nt':
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            else:
                canvas.yview_scroll(int(-1 * event.delta), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
        canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))
        # --------- End Scrollable Frame Setup ---------

        title_label = tk.Label(scrollable_frame, text="Axilink Desktop Client", font=("Arial", 18, "bold"),
                               bg='#2c3e50', fg='white')
        title_label.pack(pady=15)

        self.code_label = tk.Label(scrollable_frame, text="", font=("Arial", 28, "bold"),
                                   bg='#34495e', fg='#ecf0f1', padx=20, pady=10, relief='raised', bd=2)
        self.code_label.pack(pady=10)

        qr_frame = tk.Frame(scrollable_frame, bg='#2c3e50')
        qr_frame.pack(pady=10)
        self.qr_label = tk.Label(qr_frame, bg='white', relief='raised', bd=2)
        self.qr_label.pack()

        self.status_label = tk.Label(scrollable_frame, text="Initializing...", font=("Arial", 12),
                                     bg='#2c3e50', fg='#95a5a6')
        self.status_label.pack(pady=10)

        # Add monitor selection UI
        self.monitor_frame = tk.Frame(scrollable_frame, bg='#2c3e50')
        self.monitor_frame.pack(pady=5, fill=tk.X, padx=10)

        monitor_label = tk.Label(self.monitor_frame, text="Monitor to mirror:",
                                 font=("Arial", 10), bg='#2c3e50', fg='white')
        monitor_label.pack(pady=(5, 2))

        # This will be populated once we scan monitors
        self.monitor_buttons_frame = tk.Frame(self.monitor_frame, bg='#2c3e50')
        self.monitor_buttons_frame.pack()

        # Add quality selector for mirroring
        quality_frame = tk.Frame(scrollable_frame, bg='#2c3e50')
        quality_frame.pack(pady=5, fill=tk.X, padx=10)

        quality_label = tk.Label(quality_frame, text="Image Quality:",
                                 font=("Arial", 10), bg='#2c3e50', fg='white')
        quality_label.pack(side=tk.LEFT, padx=5)

        quality_scale = tk.Scale(quality_frame, from_=40, to=85,
                                 orient=tk.HORIZONTAL, variable=self.quality_var,
                                 bg='#2c3e50', fg='white', highlightbackground='#2c3e50')
        quality_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Add fps selector for mirroring
        fps_frame = tk.Frame(scrollable_frame, bg='#2c3e50')
        fps_frame.pack(pady=5, fill=tk.X, padx=10)

        fps_label = tk.Label(fps_frame, text="Frame Rate:",
                             font=("Arial", 10), bg='#2c3e50', fg='white')
        fps_label.pack(side=tk.LEFT, padx=5)

        fps_scale = tk.Scale(fps_frame, from_=5, to=25,
                             orient=tk.HORIZONTAL, variable=self.fps_var,
                             bg='#2c3e50', fg='white', highlightbackground='#2c3e50')
        fps_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Add resize factor selector for mirroring
        resize_frame = tk.Frame(scrollable_frame, bg='#2c3e50')
        resize_frame.pack(pady=5, fill=tk.X, padx=10)

        resize_label = tk.Label(resize_frame, text="Resize Factor:",
                                font=("Arial", 10), bg='#2c3e50', fg='white')
        resize_label.pack(side=tk.LEFT, padx=5)

        resize_scale = tk.Scale(resize_frame, from_=0.25, to=0.65, resolution=0.05,
                                orient=tk.HORIZONTAL, variable=self.resize_factor_var,
                                bg='#2c3e50', fg='white', highlightbackground='#2c3e50')
        resize_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Add adaptive quality checkbox
        adapt_frame = tk.Frame(scrollable_frame, bg='#2c3e50')
        adapt_frame.pack(pady=5, fill=tk.X, padx=10)

        adaptive_cb = tk.Checkbutton(adapt_frame, text="Auto-adjust quality for performance",
                                     variable=self.enable_adaptive_quality,
                                     bg='#2c3e50', fg='white', selectcolor='#34495e',
                                     activebackground='#2c3e50', activeforeground='white')
        adaptive_cb.pack(pady=2)

        button_frame = tk.Frame(scrollable_frame, bg='#2c3e50')
        button_frame.pack(pady=10)

        refresh_btn = tk.Button(button_frame, text="🔄 Generate Code", command=self.generate_new_code,
                                bg='#27ae60', fg='white', font=("Arial", 12, "bold"), padx=20, pady=8,
                                relief='flat', cursor='hand2')
        refresh_btn.pack(side=tk.LEFT, padx=5)

        force_btn = tk.Button(button_frame, text="⚠️ Force New", command=self.force_new_code,
                              bg='#e67e22', fg='white', font=("Arial", 10, "bold"), padx=15, pady=8,
                              relief='flat', cursor='hand2')
        force_btn.pack(side=tk.LEFT, padx=5)

        exit_btn = tk.Button(button_frame, text="❌ Exit", command=self.close_application,
                             bg='#e74c3c', fg='white', font=("Arial", 12, "bold"), padx=20, pady=8,
                             relief='flat', cursor='hand2')
        exit_btn.pack(side=tk.LEFT, padx=5)

        instructions = tk.Label(scrollable_frame,
                                text="📱 Scan QR code with your mobile app\n🎮 Control this computer remotely or mirror screen",
                                font=("Arial", 10), bg='#2c3e50', fg='#bdc3c7', justify=tk.CENTER)
        instructions.pack(pady=10)

        info_label = tk.Label(scrollable_frame,
                              text=f"WebSocket: {self.SERVER_WS_URL.replace('ws://', '')}",
                              font=("Arial", 8), bg='#2c3e50', fg='#7f8c8d')
        info_label.pack(pady=5)

        # Add calibration status label
        calib_status = tk.Label(scrollable_frame,
                                text=f"Touch Calibration: X-Scale: 1.16, Y-Scale: 1.00",
                                font=("Arial", 8), bg='#2c3e50', fg='#7f8c8d')
        calib_status.pack(pady=2)

        # Performance monitor label
        self.perf_label = tk.Label(scrollable_frame,
                                   text="Performance: Waiting for data...",
                                   font=("Arial", 8), bg='#2c3e50', fg='#7f8c8d')
        self.perf_label.pack(pady=2)

        # Add debug log frame
        debug_frame = tk.Frame(scrollable_frame, bg='#2c3e50')
        debug_frame.pack(pady=5, fill=tk.X, padx=10)
        self.debug_label = tk.Label(debug_frame, text="Debug: Ready",
                                    font=("Courier", 8), bg='#34495e', fg='#95a5a6',
                                    anchor='w', justify=tk.LEFT)
        self.debug_label.pack(fill=tk.X)

        # Detect and create monitor selection UI
        self.detect_monitors()

        # Start health check timer
        self.root.after(5000, self.check_connection_health)

    def detect_monitors(self):
        """Detect available monitors and create selection UI"""
        try:
            # Create a fresh MSS instance for monitor detection
            with mss.mss() as sct:
                # Clear existing buttons
                for widget in self.monitor_buttons_frame.winfo_children():
                    widget.destroy()

                # Skip monitor 0 (all monitors combined)
                monitor_count = len(sct.monitors) - 1

                if monitor_count < 1:
                    # No monitors detected or error
                    tk.Label(self.monitor_buttons_frame,
                             text="No monitors detected",
                             fg="red",
                             bg='#2c3e50').pack()
                    return

                # Store monitor information for click mapping
                self.monitor_info = {}
                debug_info = f"Detected {monitor_count} monitor(s):"

                for i, m in enumerate(sct.monitors):
                    if i == 0:  # Skip the "all monitors" entry
                        continue

                    # Store monitor details
                    self.monitor_info[i] = {
                        'left': m['left'],
                        'top': m['top'],
                        'width': m['width'],
                        'height': m['height']
                    }

                    debug_info += f" {i}:{m['width']}x{m['height']}"

                self.update_debug(debug_info)

                # Frame for monitor buttons
                button_style = {"bg": "#34495e", "fg": "white",
                                "activebackground": "#2980b9",
                                "activeforeground": "white",
                                "selectcolor": "#2980b9"}

                for i in range(1, monitor_count + 1):
                    monitor = sct.monitors[i]
                    size_text = f"{monitor['width']}x{monitor['height']}"
                    # Important: Using a lambda with default argument to capture the current value of i
                    btn = tk.Radiobutton(
                        self.monitor_buttons_frame,
                        text=f"Screen {i}: {size_text}",
                        variable=self.monitor_var,
                        value=i,
                        command=lambda idx=i: self.select_monitor(idx),
                        **button_style
                    )
                    btn.pack(pady=2)

                # Set the default monitor
                self.monitor_var.set(1)
                self.select_monitor(1)

        except Exception as e:
            error_msg = f"Error detecting monitors: {str(e)[:100]}"
            self.update_debug(error_msg)
            print(f"[ERROR] Detecting monitors: {e}")

    def select_monitor(self, idx):
        """Handle monitor selection"""
        print(f"[INFO] Selected monitor {idx}")
        self.selected_monitor = idx  # Store the index directly

        # Update click mapping factors for this monitor
        try:
            # Create a fresh MSS instance for thread safety
            with mss.mss() as sct:
                monitor = sct.monitors[idx]
                # Update offset for the selected monitor
                self.offset_x = monitor['left']
                self.offset_y = monitor['top']

                # Update monitor aspect ratio
                self.monitor_aspect_ratio = monitor['width'] / monitor['height']

                self.update_debug(
                    f"Selected monitor {idx}: {monitor['width']}x{monitor['height']} at ({monitor['left']},{monitor['top']})")
        except Exception as e:
            print(f"[ERROR] Failed to get monitor details: {e}")
            self.update_debug(f"Error: {str(e)[:40]}")

        # If we're currently mirroring, restart with new monitor
        if self.mode == "mirror" and self.screen_thread and self.screen_thread.is_alive():
            self.update_debug("Restarting screen mirroring...")
            self.stop_screen_mirroring()
            time.sleep(0.5)  # Give it time to fully stop
            self.start_screen_mirroring()

    def check_connection_health(self):
        """Periodically check connection health and reconnect if needed"""
        if self.qr_generated and not self.is_connected:
            print("[INFO] Connection health check: Reconnecting websocket")
            self.connect_websocket()

        # Schedule next check
        self.root.after(5000, self.check_connection_health)

    def update_debug(self, text):
        """Update debug label with latest info"""
        if self.debug_label:
            self.debug_label.config(text=f"Debug: {text}")

    def update_display(self, code, qr_img):
        """Update the UI with session code and QR code"""
        self.code_label.config(text=f"Code: {code}")
        qr_img = qr_img.resize((250, 250), Image.LANCZOS)
        qr_photo = ImageTk.PhotoImage(qr_img)
        self.qr_label.config(image=qr_photo)
        self.qr_label.image = qr_photo

    def generate_new_code(self):
        """Generate a new session code and QR code"""
        if self.qr_generated:
            self.status_label.config(text="⚠️ QR Code already generated! Use existing code.", fg='#f39c12')
            return
        self.session_code = self.generate_session_code()
        qr_img = self.generate_qr_code(self.session_code)
        self.update_display(self.session_code, qr_img)
        self.status_label.config(text="✅ QR Code Ready - Waiting for connection...", fg='#f39c12')
        self.qr_generated = True
        self.connect_websocket()

    def force_new_code(self):
        """Force generation of a new session code"""
        import tkinter.messagebox as messagebox
        response = messagebox.askyesno(
            "Force New Code", "This will disconnect current sessions and generate a new code.\n\nAre you sure?")
        if not response:
            return

        if self.ws:
            try:
                self.ws.close()
            except:
                pass
            self.is_connected = False

        self.qr_generated = False
        self.generate_new_code()

    def connect_websocket(self):
        """Connect to the WebSocket server with improved error handling"""
        # Close existing connection if any
        if hasattr(self, 'ws') and self.ws:
            try:
                self.ws.close()
            except:
                pass
            self.ws = None
            time.sleep(0.5)  # Give it time to close properly

        def run_websocket():
            websocket.enableTrace(False)

            try:
                # Add WebSocket options for better performance with large payloads
                self.ws = websocket.WebSocketApp(
                    self.SERVER_WS_URL,
                    on_open=self.on_open,
                    on_message=self.on_message,
                    on_error=self.on_error,
                    on_close=self.on_close
                )

                # Set ping for keep-alive and timeouts
                self.ws.run_forever(
                    ping_interval=30,
                    ping_timeout=10,
                    skip_utf8_validation=True  # Improves performance
                )
            except Exception as e:
                print(f"[ERROR] WebSocket thread error: {e}")
                self.update_debug(f"WS Error: {str(e)[:40]}")
                # Try to reconnect after delay
                time.sleep(3)
                self.root.after(0, self.connect_websocket)

        # Start the websocket in a separate thread
        thread = threading.Thread(target=run_websocket)
        thread.daemon = True
        thread.start()

    def subscribe_to_topics(self, ws):
        """Subscribe to all STOMP topics"""
        try:
            # Connect to STOMP
            ws.send('CONNECT\naccept-version:1.2\n\n\u0000')
            time.sleep(0.2)  # Small delay to ensure CONNECT is processed

            # Subscribe to move topic (mouse/keyboard)
            move_topic = f'/topic/move/{self.session_code}'
            ws.send(f'SUBSCRIBE\nid:0\ndestination:{move_topic}\n\n\u0000')
            print(f"[INFO] Subscribed to {move_topic}")
            time.sleep(0.1)  # Small delay between subscriptions

            # Subscribe to mode topic (mirror/control)
            mode_topic = f'/topic/mode/{self.session_code}'
            ws.send(f'SUBSCRIBE\nid:1\ndestination:{mode_topic}\n\n\u0000')
            print(f"[INFO] Subscribed to {mode_topic}")
            time.sleep(0.1)  # Small delay between subscriptions

            # Subscribe to touch topic (for touches on mirrored screen)
            touch_topic = f'/topic/touch/{self.session_code}'
            ws.send(f'SUBSCRIBE\nid:2\ndestination:{touch_topic}\n\n\u0000')
            print(f"[INFO] Subscribed to {touch_topic}")
            time.sleep(0.1)  # Small delay between subscriptions

            # Subscribe to screen topic (for screen mirroring frames)
            screen_topic = f'/topic/screen/{self.session_code}'
            ws.send(f'SUBSCRIBE\nid:3\ndestination:{screen_topic}\n\n\u0000')
            print(f"[INFO] Subscribed to {screen_topic}")

            # Update UI
            self.root.after(0, lambda: self.status_label.config(
                text="🔗 Subscribed to all topics", fg='#27ae60'))

        except Exception as e:
            print(f"[ERROR] Failed to subscribe to topics: {e}")
            self.update_debug(f"Subscribe error: {str(e)[:40]}")

    def parse_stomp_message(self, message):
        """Parse a STOMP message and extract destination and body with improved JSON handling"""
        try:
            # Convert message to string if it's bytes
            if isinstance(message, bytes):
                message = message.decode('utf-8')

            if not message.startswith("MESSAGE"):
                return None, None

            # Find headers and body more reliably
            null_terminator_pos = message.rfind("\u0000")
            if null_terminator_pos > 0:
                message = message[:null_terminator_pos]

            # Find header/body separator (empty line)
            parts = message.split("\n\n", 1)
            if len(parts) != 2:
                return None, None

            headers, body = parts

            # Extract destination
            destination = None
            for line in headers.split("\n"):
                if line.startswith("destination:"):
                    destination = line.split(":", 1)[1].strip()
                    break

            # Print raw message body for touch events to debug
            if destination and "touch" in destination:
                print(f"[DEBUG] Raw STOMP body for touch event: {body}")

            return destination, body
        except Exception as e:
            print(f"[ERROR] Failed to parse STOMP message: {e}")
            traceback.print_exc()
            return None, None

    def map_touch_coordinates(self, x_percent, y_percent):
        """
        Map touch coordinates using hardcoded optimized calibration values
        """
        try:
            # Print raw input
            print(f"[DEBUG] Raw touch input: ({x_percent:.4f}, {y_percent:.4f})")

            # Apply coordinate flipping if needed
            if self.flip_x_coordinates:
                x_percent = 1.0 - x_percent
            if self.flip_y_coordinates:
                y_percent = 1.0 - y_percent

            # Apply hardcoded calibration values
            # X scale = 1.16, Y scale = 1.00, X offset = 0.00, Y offset = 0.00
            x_percent = ((x_percent - 0.5) * self.scaling_factor_x) + 0.5 + self.offset_x
            y_percent = ((y_percent - 0.5) * self.scaling_factor_y) + 0.5 + self.offset_y

            # Ensure values stay in valid range
            x_percent = max(0.0, min(1.0, x_percent))
            y_percent = max(0.0, min(1.0, y_percent))

            # Get monitor information
            mon_info = self.monitor_info.get(self.selected_monitor)
            if not mon_info:
                # Fallback to full screen coordinates if monitor info not available
                screen_width, screen_height = pyautogui.size()
                x = int(screen_width * x_percent)
                y = int(screen_height * y_percent)
            else:
                # Map directly to monitor coordinates
                mon_left = mon_info['left']
                mon_top = mon_info['top']
                mon_width = mon_info['width']
                mon_height = mon_info['height']

                # Direct mapping to full monitor area
                x = int(mon_left + (mon_width * x_percent))
                y = int(mon_top + (mon_height * y_percent))

            print(f"[DEBUG] Mapped to monitor {self.selected_monitor}: ({int(x)}, {int(y)})")
            return int(x), int(y)

        except Exception as e:
            print(f"[ERROR] Coordinate mapping error: {e}")
            traceback.print_exc()
            # Return center of screen as fallback
            screen_width, screen_height = pyautogui.size()
            return screen_width // 2, screen_height // 2

    def handle_touch_event(self, x_percent, y_percent, click_type):
        """Process a touch event with improved handling"""
        try:
            # Print incoming coordinates
            print(f"[INFO] Processing touch: {click_type} at ({x_percent:.4f}, {y_percent:.4f})")

            # If accuracy test is active, use test handler
            if hasattr(self, 'accuracy_test_active') and self.accuracy_test_active and hasattr(self,
                                                                                               'test_touch_handler'):
                self.test_touch_handler(x_percent, y_percent)
                return True

            # Map coordinates to screen
            x, y = self.map_touch_coordinates(x_percent, y_percent)

            # Move cursor to mapped position
            pyautogui.moveTo(x, y)

            # Perform click action
            if click_type == "left_click":
                pyautogui.click()
            elif click_type == "right_click":
                pyautogui.click(button='right')
            elif click_type == "double_click":
                pyautogui.doubleClick()

            self.status_label.config(
                text=f"👆 Touch: ({int(x_percent * 100)}%, {int(y_percent * 100)}%) → ({x}, {y})",
                fg='#e67e22')

            return True
        except Exception as e:
            print(f"[ERROR] Touch handling failed: {e}")
            return False

    def on_message(self, ws, message):
        """Handle incoming WebSocket messages"""
        try:
            # Parse the STOMP message
            destination, body = self.parse_stomp_message(message)

            if not destination or not body:
                # Not a valid STOMP message or couldn't parse it
                return

            # Update debug display with the destination
            if "/topic/screen/" not in destination:  # Don't spam debug with screen frames
                self.update_debug(f"Message on {destination}")

            # Parse the JSON body
            try:
                data = json.loads(body)
            except json.JSONDecodeError as e:
                print(f"[ERROR] JSON parse error: {e} for body: {body[:50]}...")
                return

            # TOPIC: Screen mirroring
            if f"/topic/screen/{self.session_code}" in destination:
                # Received a screen frame
                if "image" in data:
                    # Update UI to show we're receiving frames
                    self.status_label.config(text="🖥️ Receiving screen frames", fg="#3498db")
                return

            # TOPIC: Mode selection
            if f"/topic/mode/{self.session_code}" in destination:
                mode_val = data.get("mode")
                print(f"[INFO] Mode change: {mode_val}")

                if mode_val == "mirror":
                    self.mode = "mirror"
                    self.status_label.config(text="🖥️ Mirroring screen to client...", fg="#3498db")
                    self.start_screen_mirroring()
                    return

                elif mode_val == "control":
                    self.mode = "control"
                    self.status_label.config(text="🎮 Remote control mode", fg="#27ae60")
                    self.stop_screen_mirroring()
                    return

            # TOPIC: Touch events
            if f"/topic/touch/{self.session_code}" in destination:
                try:
                    # Get touch coordinates as percentage of screen with better error handling
                    if 'xPercent' in data and 'yPercent' in data:
                        x_percent = float(data['xPercent'])
                        y_percent = float(data['yPercent'])
                        click_type = data.get("clickType", "left_click")

                        # Handle the touch event
                        self.handle_touch_event(x_percent, y_percent, click_type)
                    else:
                        # Try to find other keys that might contain the coordinates
                        keys = list(data.keys())
                        print(f"[WARN] Missing xPercent/yPercent. Available keys: {keys}")

                        # Look for alternate keys
                        x_key = next((k for k in keys if 'x' in k.lower()), None)
                        y_key = next((k for k in keys if 'y' in k.lower()), None)

                        if x_key and y_key:
                            print(f"[INFO] Found alternate keys: {x_key}, {y_key}")
                            x_percent = float(data.get(x_key, 0.5))
                            y_percent = float(data.get(y_key, 0.5))
                            click_type = data.get("clickType", "left_click")

                            # Handle the touch event
                            self.handle_touch_event(x_percent, y_percent, click_type)
                        else:
                            print("[ERROR] Could not find touch coordinates in message")
                            self.update_debug("Touch error: missing coordinates")
                except Exception as e:
                    print(f"[ERROR] Touch handling error: {e}")
                    traceback.print_exc()
                return

            # TOPIC: Mouse/keyboard control
            if f"/topic/move/{self.session_code}" in destination:
                self.status_label.config(text="🔗 Connected - Receiving commands", fg='#27ae60')

                action = data.get("action")
                if action:
                    if action == "left_click":
                        pyautogui.click()
                    elif action == "right_click":
                        pyautogui.click(button='right')
                    elif action == "double_click":
                        pyautogui.doubleClick()
                    elif action == "type":
                        char = data.get("text", "")
                        if char:
                            pyautogui.typewrite(char)
                    elif action == "backspace":
                        pyautogui.press('backspace')
                    elif action == "enter":
                        pyautogui.press('enter')
                    elif action == "scroll":
                        scroll_amount = float(data.get("scroll_dy", 0))
                        if abs(scroll_amount) > 0.01:
                            # Increase scroll speed
                            pyautogui.scroll(int(scroll_amount * 30))
                    return

                # Mouse movement with increased speed
                dx = data.get("dx", 0)
                dy = data.get("dy", 0)
                x, y = pyautogui.position()
                screen_width, screen_height = pyautogui.size()
                # Increase speed by using factor 150 instead of 100
                new_x = min(max(x + dx * 150, 1), screen_width - 2)
                new_y = min(max(y + dy * 150, 1), screen_height - 2)
                pyautogui.moveTo(new_x, new_y)

        except Exception as e:
            error_msg = f"Error in message handler: {str(e)[:40]}"
            print("[ERROR] in on_message:", e)
            self.update_debug(error_msg)

    def start_screen_mirroring(self):
        """Start the screen mirroring thread"""
        if self.screen_thread and self.screen_thread.is_alive():
            self.stop_screen_mirroring()
            time.sleep(0.5)  # Wait a bit for thread to stop

        self.stop_screen_thread.clear()
        self.screen_thread = threading.Thread(target=self.send_screen_frames, daemon=True)
        self.screen_thread.start()

    def stop_screen_mirroring(self):
        """Stop the screen mirroring thread"""
        self.stop_screen_thread.set()
        if self.screen_thread and self.screen_thread.is_alive():
            try:
                self.screen_thread.join(timeout=1.0)  # Wait for thread to finish
            except:
                pass
            print("[INFO] Screen mirroring stopped")
        self.update_debug("Screen mirroring stopped")

    def send_screen_frames(self):
        """High performance screen mirroring function with optimizations for low latency"""
        # Get selected monitor
        monitor_idx = self.selected_monitor
        if isinstance(monitor_idx, tk.IntVar):
            monitor_idx = monitor_idx.get()

        try:
            # Create MSS instance inside the thread that will use it
            with mss.mss() as sct:
                # Validate monitor index
                monitor_count = len(sct.monitors) - 1
                if monitor_idx < 1 or monitor_idx > monitor_count:
                    monitor_idx = 1
                    self.update_debug(f"Invalid monitor {monitor_idx}, using monitor 1")

                # Get the monitor
                monitor = sct.monitors[monitor_idx]

                # Print monitor info for debugging
                print(
                    f"[INFO] Mirroring monitor {monitor_idx}: {monitor['width']}x{monitor['height']} at ({monitor['left']},{monitor['top']})")
                self.update_debug(f"Mirroring: {monitor['width']}x{monitor['height']}")

                # Get quality settings
                try:
                    quality = self.quality_var.get()
                    self.current_quality = quality
                except:
                    quality = 65  # Default quality
                    self.current_quality = quality

                # Get resize factor setting
                try:
                    resize_factor = self.resize_factor_var.get()
                except:
                    resize_factor = 0.5  # Default 50% resize

                # Get frame rate setting
                try:
                    target_fps = self.fps_var.get()
                except:
                    target_fps = 15  # Default FPS

                # Frame interval based on FPS (minimum time between frames)
                frame_interval = 1.0 / target_fps

                # Maximum message size (900KB - safe margin below 1MB STOMP limit)
                max_size = 900000

                # Reset performance tracking
                self.consecutive_errors = 0
                max_consecutive_errors = 5
                frame_count = 0
                fps_timer = time.time()

                # Adaptive quality and frame skipping
                self.frame_skip = 0
                last_sent_time = 0

                # Set initial dimensions based on monitor resolution and resize factor
                width, height = monitor['width'], monitor['height']
                new_width = max(320, int(width * resize_factor))
                new_height = max(240, int(height * resize_factor))

                # Make sure dimensions are even for better encoding
                new_width = new_width - (new_width % 2)
                new_height = new_height - (new_height % 2)

                # Get aspect ratio
                aspect_ratio = width / height

                print("[INFO] Starting optimized screen mirroring thread")
                self.status_label.config(text=f"🖥️ Mirroring screen {monitor_idx}", fg="#3498db")
                self.update_debug(f"Starting: {new_width}x{new_height}, Q:{quality}%")

                # Main loop for screen mirroring
                while not self.stop_screen_thread.is_set():
                    try:
                        frame_start_time = time.time()

                        # Check if websocket is still connected
                        if not self.ws or not self.is_connected:
                            print("[ERROR] WebSocket disconnected during mirroring")
                            self.update_debug("WebSocket disconnected")
                            break

                        # Get elapsed time since last frame
                        elapsed = frame_start_time - last_sent_time

                        # Skip frames if needed to maintain target FPS
                        if elapsed < frame_interval and self.frame_skip > 0:
                            # Wait a bit to avoid CPU spin
                            time.sleep(0.001)
                            continue

                        # Update quality setting from slider if not in adaptive mode
                        if not self.enable_adaptive_quality.get():
                            try:
                                quality = self.quality_var.get()
                                self.current_quality = quality
                            except:
                                pass  # Keep current quality

                        # Update resize factor - this can be adjusted anytime
                        try:
                            resize_factor = self.resize_factor_var.get()
                            # Recalculate dimensions
                            new_width = max(320, int(width * resize_factor))
                            new_height = max(240, int(height * resize_factor))
                            # Make sure dimensions are even
                            new_width = new_width - (new_width % 2)
                            new_height = new_height - (new_height % 2)
                        except:
                            pass  # Keep current dimensions

                        # Capture screen - this is the most time-consuming operation
                        capture_start = time.time()
                        sct_img = sct.grab(monitor)
                        capture_time = time.time() - capture_start

                        # Convert to PIL image - use numpy for speed when available
                        try:
                            # Faster conversion using numpy when available
                            import numpy as np
                            img_array = np.array(sct_img)
                            img = Image.fromarray(img_array)
                        except ImportError:
                            # Fallback to standard conversion
                            img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)

                        # Resize image (use BILINEAR for better speed/quality balance)
                        img = img.resize((new_width, new_height), Image.BILINEAR)

                        # Convert to JPEG using a recycled buffer
                        self.img_buffer.seek(0)
                        self.img_buffer.truncate(0)
                        img.save(self.img_buffer, format="JPEG", quality=self.current_quality, optimize=True)
                        img_size = self.img_buffer.tell()

                        # Adaptive quality management
                        if self.enable_adaptive_quality.get():
                            # Target is around 150KB per frame
                            if img_size > self.target_size_kb * 1.2 * 1024:  # Over 180KB
                                # Reduce quality if we're above min_quality
                                if self.current_quality > self.min_quality:
                                    self.current_quality = max(self.min_quality, self.current_quality - 5)
                            elif img_size < self.target_size_kb * 0.8 * 1024:  # Under 120KB
                                # Increase quality if we're below max_quality
                                if self.current_quality < self.max_quality:
                                    self.current_quality = min(self.max_quality, self.current_quality + 1)

                        # If still too large after quality adjustment, reduce size further
                        if img_size > max_size:
                            # Reduce dimensions by 10%
                            new_width = int(new_width * 0.9)
                            new_height = int(new_height * 0.9)
                            # Make sure dimensions are even
                            new_width = new_width - (new_width % 2)
                            new_height = new_height - (new_height % 2)

                            # Resize and re-encode
                            img = img.resize((new_width, new_height), Image.BILINEAR)
                            self.img_buffer.seek(0)
                            self.img_buffer.truncate(0)
                            img.save(self.img_buffer, format="JPEG", quality=self.current_quality, optimize=True)
                            img_size = self.img_buffer.tell()

                        # Get image bytes from buffer
                        self.img_buffer.seek(0)
                        b64_img = base64.b64encode(self.img_buffer.getvalue()).decode("utf-8")

                        # Prepare message with timestamp for tracking
                        msg = {
                            "image": b64_img,
                            "aspectRatio": aspect_ratio,
                            "timestamp": int(time.time() * 1000)
                        }

                        # Send the message
                        send_start = time.time()
                        if self._send_stomp_message(msg):
                            # Message sent successfully
                            last_sent_time = time.time()
                            send_time = last_sent_time - send_start
                            total_time = last_sent_time - frame_start_time

                            # Update FPS counter
                            frame_count += 1
                            fps_elapsed = last_sent_time - fps_timer

                            if fps_elapsed >= 1.0:
                                current_fps = frame_count / fps_elapsed
                                frame_count = 0
                                fps_timer = last_sent_time

                                # Update performance metrics
                                kb_size = img_size / 1024
                                self.update_debug(
                                    f"Size: {new_width}x{new_height}, {kb_size:.1f}KB, Q:{self.current_quality}%, FPS:{current_fps:.1f}")

                                # Update performance monitor label with more detailed info
                                perf_text = (f"Performance: {current_fps:.1f} FPS, "
                                             f"Frame: {total_time * 1000:.0f}ms, "
                                             f"Capture: {capture_time * 1000:.0f}ms, "
                                             f"Send: {send_time * 1000:.0f}ms, "
                                             f"Size: {kb_size:.1f}KB")
                                self.perf_label.config(text=perf_text)

                                # Adaptive frame skipping based on performance
                                if self.adaptive_frame_skip:
                                    if total_time > frame_interval * 1.2:  # We're struggling to keep up
                                        self.frame_skip = min(2, self.frame_skip + 1)  # Increase frame skip
                                    elif total_time < frame_interval * 0.8 and self.frame_skip > 0:
                                        self.frame_skip = self.frame_skip - 1  # Decrease frame skip

                            # Reset error counter on success
                            self.consecutive_errors = 0
                        else:
                            # Sending failed, break the loop if we've had too many errors
                            self.consecutive_errors += 1
                            if self.consecutive_errors >= max_consecutive_errors:
                                break
                            continue

                        # Maintain frame rate - sleep only if we have time to spare
                        elapsed = time.time() - frame_start_time
                        if elapsed < frame_interval:
                            sleep_time = max(0.001, frame_interval - elapsed)  # Minimum sleep of 1ms
                            time.sleep(sleep_time)

                    except Exception as e:
                        error_message = f"Mirror error: {str(e)[:40]}"
                        print(f"[ERROR] Mirroring: {e}")
                        traceback.print_exc()
                        self.update_debug(error_message)
                        self.consecutive_errors += 1

                        # Short delay on error before retry
                        time.sleep(0.2)

                        if self.consecutive_errors >= max_consecutive_errors:
                            print("[ERROR] Too many errors in screen mirror thread")
                            self.stop_screen_thread.set()

        except Exception as e:
            print(f"[ERROR] Screen mirroring thread fatal error: {e}")
            traceback.print_exc()
            self.update_debug(f"Fatal error: {str(e)[:40]}")

        print("[INFO] Screen mirroring thread stopped")
        self.update_debug("Screen mirroring stopped")

    def _send_stomp_message(self, msg_data):
        """Helper to send a STOMP message and handle errors"""
        try:
            if not self.ws or not self.ws.sock or not self.ws.sock.connected:
                print("[ERROR] WebSocket not connected")
                self.update_debug("WebSocket not connected")
                self.consecutive_errors += 1
                return False

            # Prepare STOMP message
            json_msg = json.dumps(msg_data)
            content_length = len(json_msg)

            stomp_msg = (
                f"SEND\n"
                f"destination:/app/screen/{self.session_code}\n"
                f"content-type:application/json\n"
                f"content-length:{content_length}\n"
                f"\n"
                f"{json_msg}\u0000"
            )

            # Send the message
            self.ws.send(stomp_msg)
            self.last_frame_time = time.time()
            return True

        except Exception as e:
            print(f"[ERROR] Failed to send frame: {e}")
            self.update_debug(f"Send error: {str(e)[:30]}")
            self.consecutive_errors += 1

            # If too many consecutive errors, stop mirroring
            if self.consecutive_errors >= 5:
                print("[ERROR] Too many consecutive errors, stopping mirroring")
                self.status_label.config(
                    text="⚠️ Screen mirroring failed - too many errors", fg='#e74c3c')
                self.stop_screen_thread.set()

                # Try to reconnect in background
                self.root.after(3000, self.connect_websocket)

            return False

    def on_open(self, ws):
        """Handle WebSocket open event"""
        print("[INFO] Connected to WebSocket")
        self.is_connected = True
        self.consecutive_errors = 0
        self.status_label.config(text="🔗 Connected to server", fg='#27ae60')
        threading.Thread(target=self.subscribe_to_topics, args=(ws,)).start()

    def on_error(self, ws, error):
        """Handle WebSocket error"""
        print(f"[ERROR] WebSocket: {error}")
        self.status_label.config(text="❌ Connection error", fg='#e74c3c')

    def on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket close event"""
        print(f"[INFO] WebSocket connection closed: {close_status_code}, {close_msg}")

        # Mark as disconnected
        self.is_connected = False

        # Stop screen mirroring if active
        if self.mode == "mirror":
            self.stop_screen_mirroring()

        # Update UI
        self.status_label.config(text=f"⚠️ Connection closed", fg='#f39c12')

        # Reconnect after a delay, but only if we haven't manually closed it
        if close_status_code not in (1000, None):  # Not a normal closure
            print("[INFO] Attempting to reconnect in 3 seconds...")
            self.update_debug(f"Connection lost: {close_status_code}. Reconnecting...")

            # Schedule reconnect (use root.after to avoid threading issues)
            self.root.after(3000, self.connect_websocket)
        else:
            self.update_debug("Connection closed normally")

    def close_application(self):
        """Handle application close"""
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
        if self.screen_thread and self.screen_thread.is_alive():
            self.stop_screen_mirroring()
        self.root.quit()
        self.root.destroy()
        print("[INFO] Application closed")

        try:
            self.img_buffer.close()
        except:
            pass

    def run(self):
        """Run the application"""
        self.setup_gui()
        self.root.after(500, self.generate_new_code)
        self.root.mainloop()


if __name__ == "__main__":
    try:
        # Print startup information
        print("=" * 60)
        print("Axilink Desktop Client v1.1")
        print("=" * 60)
        print(f"Python: {sys.version}")
        print(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("-" * 60)

        # Check for required packages
        try:
            import qrcode
            from PIL import Image, ImageTk
        except ImportError:
            print("Installing required packages...")
            import subprocess

            subprocess.check_call(['pip', 'install', 'qrcode[pil]', 'Pillow', 'websocket-client', 'mss', 'pyautogui'])
            import qrcode
            from PIL import Image, ImageTk

        print("[INFO] Starting Axilink Desktop Client")
        client = RemoteControlClient()
        client.run()
    except Exception as e:
        print(f"[ERROR] Fatal error: {e}")
        # Create error log
        try:
            with open("axilink_error.log", "a") as f:
                f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Fatal error: {e}\n")
                traceback.print_exc(file=f)
        except:
            pass

        # Show error in message box
        try:
            import tkinter.messagebox as messagebox

            messagebox.showerror("Fatal Error", f"An error occurred: {str(e)}\nCheck axilink_error.log for details.")
        except:
            pass
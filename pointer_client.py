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


def get_local_ip():
    """Get the local IPv4 address (e.g., 192.168.x.x or 10.x.x.x)"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # connect to an unreachable IP — no data is sent
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
        self.SERVER_WS_URL = f"ws://{ip}:8080/ws"
        self.session_code = None
        self.ws = None
        self.is_connected = False
        self.root = None
        self.qr_label = None
        self.status_label = None
        self.code_label = None
        self.qr_generated = False
        
    def generate_session_code(self):
        """Generate a 4-digit session code"""
        return str(random.randint(1000, 9999))
    
    def generate_qr_code(self, code):
        """Generate QR code for the session code"""
        # Simple QR data - just the session code and WebSocket URL
        qr_data = code+f"ws://{ip}:8080/ws"
        
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        # Create QR code image
        img = qr.make_image(fill_color="black", back_color="white")
        
     
        
        return img
    
    def setup_gui(self):
        """Setup the GUI window"""
        self.root = tk.Tk()
        self.root.title("Remote Control Server")
        self.root.geometry("400x550")
        self.root.configure(bg='#2c3e50')
        
        # Make window stay on top
        self.root.attributes('-topmost', True)
        
        # Title
        title_label = tk.Label(
            self.root, 
            text="Remote Control Server", 
            font=("Arial", 18, "bold"),
            bg='#2c3e50',
            fg='white'
        )
        title_label.pack(pady=15)
        
        # Session code display
        self.code_label = tk.Label(
            self.root, 
            text="", 
            font=("Arial", 28, "bold"),
            bg='#34495e',
            fg='#ecf0f1',
            padx=20,
            pady=10,
            relief='raised',
            bd=2
        )
        self.code_label.pack(pady=10)
        
        # QR Code display
        qr_frame = tk.Frame(self.root, bg='#2c3e50')
        qr_frame.pack(pady=10)
        
        self.qr_label = tk.Label(qr_frame, bg='white', relief='raised', bd=2)
        self.qr_label.pack()
        
        # Status display
        self.status_label = tk.Label(
            self.root, 
            text="Initializing...", 
            font=("Arial", 12),
            bg='#2c3e50',
            fg='#95a5a6'
        )
        self.status_label.pack(pady=10)
        
        # Control buttons
        button_frame = tk.Frame(self.root, bg='#2c3e50')
        button_frame.pack(pady=20)
        
        refresh_btn = tk.Button(
            button_frame,
            text="🔄 Generate Code",
            command=self.generate_new_code,
            bg='#27ae60',
            fg='white',
            font=("Arial", 12, "bold"),
            padx=20,
            pady=8,
            relief='flat',
            cursor='hand2'
        )
        refresh_btn.pack(side=tk.LEFT, padx=5)
        
        # Add Force New Code button (for admin use)
        force_btn = tk.Button(
            button_frame,
            text="⚠️ Force New",
            command=self.force_new_code,
            bg='#e67e22',
            fg='white',
            font=("Arial", 10, "bold"),
            padx=15,
            pady=8,
            relief='flat',
            cursor='hand2'
        )
        force_btn.pack(side=tk.LEFT, padx=5)
        
        exit_btn = tk.Button(
            button_frame,
            text="❌ Exit",
            command=self.close_application,
            bg='#e74c3c',
            fg='white',
            font=("Arial", 12, "bold"),
            padx=20,
            pady=8,
            relief='flat',
            cursor='hand2'
        )
        exit_btn.pack(side=tk.LEFT, padx=5)
        
        # Instructions
        instructions = tk.Label(
            self.root,
            text="📱 Scan QR code with your mobile app\n🎮 Control this computer remotely",
            font=("Arial", 10),
            bg='#2c3e50',
            fg='#bdc3c7',
            justify=tk.CENTER
        )
        instructions.pack(pady=10)
        
        # Connection info
        info_label = tk.Label(
            self.root,
            text=f"WebSocket: {self.SERVER_WS_URL.replace('ws://', '')}",
            font=("Arial", 8),
            bg='#2c3e50',
            fg='#7f8c8d'
        )
        info_label.pack(pady=5)
        
    def update_display(self, code, qr_img):
        """Update the display with new code and QR"""
        # Update code display
        self.code_label.config(text=f"Code: {code}")
        
        # Update QR code
        qr_img = qr_img.resize((250, 250), Image.Resampling.LANCZOS)
        qr_photo = ImageTk.PhotoImage(qr_img)
        self.qr_label.config(image=qr_photo)
        self.qr_label.image = qr_photo  # Keep a reference
        
    def generate_new_code(self):
        """Generate new session code - only ONCE unless forced"""
        if self.qr_generated:
            # If QR already generated, just show message - don't generate new one
            self.status_label.config(text="⚠️ QR Code already generated! Use existing code.", fg='#f39c12')
            return
        
        # Generate code only if not generated before
        self.session_code = self.generate_session_code()
        qr_img = self.generate_qr_code(self.session_code)
        self.update_display(self.session_code, qr_img)
        self.status_label.config(text="✅ QR Code Ready - Waiting for connection...", fg='#f39c12')
        
        self.qr_generated = True
        
        # Start WebSocket connection
        self.connect_websocket()
    
    def force_new_code(self):
        """Force generate new code (for admin use)"""
        import tkinter.messagebox as messagebox
        
        response = messagebox.askyesno(
            "Force New Code", 
            "This will disconnect current sessions and generate a new code.\n\nAre you sure?"
        )
        if not response:
            return
        
        if self.ws:
            self.ws.close()
            self.is_connected = False
        
        # Reset and generate new
        self.qr_generated = False
        self.generate_new_code()
    
    def connect_websocket(self):
        """Connect to WebSocket with session code"""
        def run_websocket():
            websocket.enableTrace(False)
            self.ws = websocket.WebSocketApp(
                self.SERVER_WS_URL,
                on_open=self.on_open,
                on_message=self.on_message,
                on_error=self.on_error,
                on_close=self.on_close
            )
            self.ws.run_forever()
        
        thread = threading.Thread(target=run_websocket)
        thread.daemon = True
        thread.start()
    
    def subscribe_to_motion(self, ws):
        """Subscribe to motion topic with session code"""
        ws.send('CONNECT\naccept-version:1.2\n\n\u0000')
        topic = f'/topic/move/{self.session_code}'
        ws.send(f'SUBSCRIBE\nid:0\ndestination:{topic}\n\n\u0000')
        print(f"[INFO] Subscribed to {topic}")
    
    def on_message(self, ws, message):
        """Handle incoming WebSocket messages - YOUR ORIGINAL LOGIC"""
        try:
            expected_topic = f"destination:/topic/move/{self.session_code}"
            if expected_topic in message:
                parts = message.split("\n\n")
                if len(parts) > 1:
                    body = parts[1].strip("\u0000")
                    data = json.loads(body)
                    
                    # Update status on GUI thread
                    self.root.after(0, lambda: self.status_label.config(
                        text="🔗 Connected - Receiving commands", fg='#27ae60'
                    ))

                    action = data.get("action")
                    if action:
                        if action == "left_click":
                            pyautogui.click()
                            # print("[ACTION] Left Click")
                        elif action == "right_click":
                            pyautogui.click(button='right')
                            # print("[ACTION] Right Click")
                        elif action == "double_click":
                            pyautogui.doubleClick()
                            # print("[ACTION] Double Click")
                        elif action == "type":
                            char = data.get("text", "")
                            if char:
                                pyautogui.typewrite(char)
                                # print(f"[ACTION] Typed: {char}")
                        elif action == "backspace":
                            pyautogui.press('backspace')
                            # print("[ACTION] Backspace")
                        elif action == "scroll":
                            scroll_amount = float(data.get("scroll_dy", 0))
                            if abs(scroll_amount) > 0.01:
                                pyautogui.scroll(int(scroll_amount * 20))
                                # print(f"[ACTION] Scroll {scroll_amount}")
                        return

                    # ✅ Otherwise, treat as movement - YOUR ORIGINAL LOGIC
                    dx = data.get("dx", 0)
                    dy = data.get("dy", 0)

                    x, y = pyautogui.position()
                    screen_width, screen_height = pyautogui.size()

                    new_x = min(max(x + dx * 100, 1), screen_width - 2)
                    new_y = min(max(y + dy * 100, 1), screen_height - 2)

                    pyautogui.moveTo(new_x, new_y)

        except Exception as e:
            print("[ERROR]", e)
    
    def on_open(self, ws):
        """Handle WebSocket connection opened"""
        print("[INFO] Connected to WebSocket")
        self.is_connected = True
        self.root.after(0, lambda: self.status_label.config(
            text="🔗 Connected to server", fg='#27ae60'
        ))
        threading.Thread(target=self.subscribe_to_motion, args=(ws,)).start()
    
    def on_error(self, ws, error):
        """Handle WebSocket errors"""
        print(f"[ERROR] WebSocket: {error}")
        self.root.after(0, lambda: self.status_label.config(
            text="❌ Connection error", fg='#e74c3c'
        ))
    
    def on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket connection closed"""
        print("[INFO] WebSocket connection closed")
        self.is_connected = False
        self.root.after(0, lambda: self.status_label.config(
            text="⚠️ Connection closed", fg='#f39c12'
        ))
    
    def close_application(self):
        """Close the application"""
        if self.ws:
            self.ws.close()
        self.root.quit()
        self.root.destroy()
    
    def run(self):
        """Run the application"""
        self.setup_gui()
        
        # Generate initial session after GUI is ready
        self.root.after(500, self.generate_new_code)
        
        # Start GUI
        self.root.mainloop()

if __name__ == "__main__":
    # Install required packages if not available
    try:
        import qrcode
        from PIL import Image, ImageTk
    except ImportError:
        print("Installing required packages...")
        import subprocess
        subprocess.check_call(['pip', 'install', 'qrcode[pil]', 'Pillow'])
        import qrcode
        from PIL import Image, ImageTk
    
    client = RemoteControlClient()
    client.run()
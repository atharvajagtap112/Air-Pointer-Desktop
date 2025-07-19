import subprocess
import socket
import time
import os

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # connect to a dummy address
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def launch():
    ip = get_local_ip()
    print(f"[INFO] Using IP: {ip}")

    # Set IP as env variable for Python GUI to read
    os.environ['SERVER_IP'] = ip

    # Start Spring Boot
    backend_process = subprocess.Popen(
        ['java', '-jar', 'backend.jar'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    # Wait for backend to start
    print("[INFO] Waiting for backend to boot...")
    time.sleep(4)  # You can improve this with a port check

    # Launch the Python GUI
    subprocess.call(['python', 'pointer_client.py'])

    # Clean up
    backend_process.terminate()

if __name__ == "__main__":
    launch()

import os
import subprocess
import time
import sys
import psutil

from config_dialog import get_config_from_dialog, read_config

DIR = os.path.dirname(sys.executable)

# Only prompt on first run, reuse config otherwise
config = get_config_from_dialog()

SERVER = config['server']
PORT = config['port']
BOT_BASE = config['bot_base']

bots = [
    [os.path.join(DIR, "bot_server"), "--server", SERVER, "--port", str(PORT), "--bot-name", f"{BOT_BASE}", "--api-port", "6001"],
    [os.path.join(DIR, "bot_server"), "--server", SERVER, "--port", str(PORT), "--bot-name", f"{BOT_BASE}1", "--api-port", "6002"],
    [os.path.join(DIR, "bot_server"), "--server", SERVER, "--port", str(PORT), "--bot-name", f"{BOT_BASE}2", "--api-port", "6003"]
]

procs = []
for cmd in bots:
    try:
        print(f"Starting bot: {cmd}")
        p = subprocess.Popen(cmd, cwd=DIR)
    except Exception as e:
        print(f"Could not start bot: {cmd}: {e}")
        continue
    procs.append(p)

time.sleep(2)

gui_cmd = [os.path.join(DIR, "gui")]
try:
    print(f"Launching GUI: {gui_cmd}")
    subprocess.call(gui_cmd, cwd=DIR)
except Exception as e:
    print(f"Failed to launch GUI: {e}")

for p in procs:
    try:
        print(f"Terminating bot process PID: {p.pid}")
        p.terminate()
        try:
            p.wait(timeout=3)
        except subprocess.TimeoutExpired:
            print(f"Bot PID {p.pid} did not exit in time. Killing...")
            p.kill()
    except Exception as e:
        print(f"Error terminating bot process: {e}")

print("All bots terminated. Exiting app.")

try:
    for proc in psutil.process_iter(['pid', 'name', 'exe', 'cmdline']):
        if proc.info['name'] and 'bot_server' in proc.info['name']:
            print(f"Forcibly killing leftover bot_server PID={proc.pid}")
            try:
                proc.kill()
            except Exception as e:
                print(f"Could not kill PID={proc.pid}: {e}")
except Exception as e:
    print(f"psutil cleanup failed: {e}")

print("All bots terminated. Exiting app.")

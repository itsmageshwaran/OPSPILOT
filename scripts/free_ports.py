import os
import sys
import subprocess
import argparse
import signal

TARGET_PORTS = [8000, 8080, 5173]

def free_target_ports():
    parser = argparse.ArgumentParser(description="Inspect OpsPilot's standard development ports.")
    parser.add_argument("--force", action="store_true", help="terminate listeners on those ports")
    force = parser.parse_args().force
    listeners = {}

    if sys.platform == "win32":
        try:
            output = subprocess.check_output(["netstat", "-aon"], text=True, errors="ignore")
            for line in output.splitlines():
                for port in TARGET_PORTS:
                    if f":{port} " in line and "LISTENING" in line:
                        parts = line.strip().split()
                        if len(parts) >= 5:
                            listeners.setdefault(port, set()).add(int(parts[-1]))
        except Exception as e:
            print(f"[!] Warning during Windows port scan: {e}")
    else:
        for port in TARGET_PORTS:
            try:
                output = subprocess.check_output(["lsof", "-ti", f":{port}"], text=True, stderr=subprocess.DEVNULL)
                listeners[port] = {int(pid) for pid in output.split()}
            except FileNotFoundError:
                print("[!] lsof is required to inspect ports on this system.")
                return
            except subprocess.CalledProcessError:
                continue

    if not listeners:
        print("[+] Ports 8000, 8080, and 5173 are free.")
        return

    for port, pids in listeners.items():
        for pid in sorted(pids):
            if force:
                try:
                    if sys.platform == "win32":
                        subprocess.run(["taskkill", "/F", "/PID", str(pid)], check=False, capture_output=True)
                    else:
                        os.kill(pid, signal.SIGTERM)
                    print(f"[*] Stopped PID {pid} listening on port {port}.")
                except (OSError, ValueError) as e:
                    print(f"[!] Could not stop PID {pid}: {e}")
            else:
                print(f"[!] Port {port} is in use by PID {pid}; no process was stopped. Use --force to stop it.")

if __name__ == "__main__":
    free_target_ports()

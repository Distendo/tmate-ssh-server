import os
import subprocess
import threading
import signal
from flask import Flask, jsonify

app = Flask(__name__)

TMATE_SOCKET = "/tmp/tmate.sock"
TMATE_READY = threading.Event()
tmate_ssh = None
tmate_web = None
tmate_process = None


def start_tmate():
    global tmate_ssh, tmate_web, tmate_process

    try:
        tmate_process = subprocess.Popen(
            ["tmate", "-S", TMATE_SOCKET, "new-session", "-d"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            ["tmate", "-S", TMATE_SOCKET, "wait", "tmate-ready"],
            check=True, timeout=30,
        )

        ssh_res = subprocess.run(
            ["tmate", "-S", TMATE_SOCKET, "display", "-p", "#{tmate_ssh}"],
            capture_output=True, text=True, timeout=5,
        )
        web_res = subprocess.run(
            ["tmate", "-S", TMATE_SOCKET, "display", "-p", "#{tmate_web}"],
            capture_output=True, text=True, timeout=5,
        )

        tmate_ssh = ssh_res.stdout.strip()
        tmate_web = web_res.stdout.strip()
    except Exception as e:
        app.logger.error(f"tmate error: {e}")

    TMATE_READY.set()


@app.route("/")
def index():
    return jsonify({"status": "alive", "service": "tmate-ssh"})


@app.route("/ssh")
def get_ssh():
    TMATE_READY.wait(timeout=10)
    if tmate_ssh:
        return jsonify({"command": tmate_ssh, "web": tmate_web})
    return jsonify({"error": "tmate not ready"}), 503


@app.route("/health")
def health():
    alive = tmate_process is not None and tmate_process.poll() is None
    return jsonify({"tmate_alive": alive, "connected": tmate_ssh is not None})


def shutdown():
    if tmate_process:
        tmate_process.terminate()
        tmate_process.wait(timeout=5)


signal.signal(signal.SIGTERM, lambda *_: shutdown())

threading.Thread(target=start_tmate, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

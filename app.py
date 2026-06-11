import os
import subprocess
import threading
import signal
import logging
from flask import Flask, jsonify

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

TMATE_READY = threading.Event()
tmate_ssh = None
tmate_web = None
tmate_process = None
tmate_error = None


def start_tmate():
    global tmate_ssh, tmate_web, tmate_process, tmate_error

    try:
        home = os.environ.get("HOME", "/root")
        os.makedirs(f"{home}/.tmate", exist_ok=True)

        app.logger.info("Starting tmate session...")
        tmate_stderr = open("/tmp/tmate_new_session.log", "w")
        tmate_process = subprocess.Popen(
            ["tmate", "new-session", "-d"],
            stdout=subprocess.DEVNULL, stderr=tmate_stderr,
        )

        app.logger.info("Waiting for tmate-ready...")
        result = subprocess.run(
            ["tmate", "wait", "tmate-ready"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            tmate_error = f"tmate wait failed: {result.stderr.strip()}"
            app.logger.error(tmate_error)
            TMATE_READY.set()
            return

        ssh_res = subprocess.run(
            ["tmate", "display", "-p", "#{tmate_ssh}"],
            capture_output=True, text=True, timeout=5,
        )
        web_res = subprocess.run(
            ["tmate", "display", "-p", "#{tmate_web}"],
            capture_output=True, text=True, timeout=5,
        )

        tmate_ssh = ssh_res.stdout.strip()
        tmate_web = web_res.stdout.strip()
        app.logger.info(f"tmate ready: ssh={tmate_ssh}")
    except subprocess.TimeoutExpired:
        tmate_error = "tmate timed out waiting for session"
        app.logger.error(tmate_error)
    except FileNotFoundError:
        tmate_error = "tmate binary not found"
        app.logger.error(tmate_error)
    except Exception as e:
        tmate_error = str(e)
        app.logger.error(f"tmate error: {e}")

    TMATE_READY.set()


@app.route("/")
def index():
    return jsonify({"status": "alive", "service": "tmate-ssh"})


@app.route("/ssh")
def get_ssh():
    TMATE_READY.wait(timeout=30)
    if tmate_ssh:
        return jsonify({"command": tmate_ssh, "web": tmate_web})
    return jsonify({
        "error": "tmate not ready",
        "detail": tmate_error,
        "alive": tmate_process is not None and tmate_process.poll() is None,
    }), 503


@app.route("/health")
def health():
    alive = tmate_process is not None and tmate_process.poll() is None
    return jsonify({
        "tmate_alive": alive,
        "connected": tmate_ssh is not None,
        "error": tmate_error,
    })


def shutdown():
    if tmate_process:
        tmate_process.terminate()
        tmate_process.wait(timeout=5)


signal.signal(signal.SIGTERM, lambda *_: shutdown())

threading.Thread(target=start_tmate, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

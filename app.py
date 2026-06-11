import os
import subprocess
import threading
import logging
from flask import Flask, jsonify

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

TMATE_READY = threading.Event()
tmate_ssh = None
tmate_web = None
tmate_error = None


def start_tmate():
    global tmate_ssh, tmate_web, tmate_error

    try:
        home = os.environ.get("HOME", "/root")
        os.makedirs(f"{home}/.tmate", exist_ok=True)

        app.logger.info("Starting tmate session...")
        ns = subprocess.run(
            ["tmate", "new-session", "-d"],
            capture_output=True, text=True, timeout=30,
        )
        if ns.returncode != 0:
            tmate_error = f"new-session failed (rc={ns.returncode}): {ns.stderr.strip()}"
            app.logger.error(tmate_error)
            TMATE_READY.set()
            return

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
        tmate_error = "tmate timed out"
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
    }), 503


@app.route("/health")
def health():
    return jsonify({
        "connected": tmate_ssh is not None,
        "error": tmate_error,
    })


threading.Thread(target=start_tmate, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

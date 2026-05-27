
import os
import uuid
import time
import threading
import subprocess
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, abort
import imageio_ffmpeg

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

jobs = {}

def set_job(job_id, **kwargs):
    jobs.setdefault(job_id, {})
    jobs[job_id].update(kwargs)

def add_log(job_id, text):
    if not text:
        return
    jobs.setdefault(job_id, {})
    logs = jobs[job_id].setdefault("logs", [])
    logs.append(str(text)[-4000:])
    jobs[job_id]["logs"] = logs[-80:]

def run_streamlink(job_id, url, quality, ts_file):
    # Comando exatamente no formato que você disse que funciona:
    # streamlink --output "arquivo.ts" "url" best
    cmd = [
        "streamlink",
        "--output",
        str(ts_file),
        url,
        quality
    ]

    add_log(job_id, "Rodando comando:")
    add_log(job_id, " ".join(f'"{c}"' if " " in c else c for c in cmd))

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    for line in process.stdout:
        add_log(job_id, line.rstrip())

    process.wait()

    add_log(job_id, f"Streamlink finalizou com código: {process.returncode}")

    if process.returncode != 0:
        raise RuntimeError("Streamlink falhou. Veja o log acima.")

    if not ts_file.exists():
        raise RuntimeError("O Streamlink terminou, mas o arquivo .ts não foi criado.")

    if ts_file.stat().st_size < 1024:
        raise RuntimeError("O arquivo .ts foi criado vazio ou pequeno demais.")

def convert_to_mp4(job_id, ts_file, mp4_file):
    cmd = [
        FFMPEG,
        "-y",
        "-i",
        str(ts_file),
        "-c:v",
        "libx264",
        "-tag:v",
        "avc1",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(mp4_file)
    ]

    add_log(job_id, "Convertendo para MP4 H.264 AVC1:")
    add_log(job_id, " ".join(f'"{c}"' if " " in c else c for c in cmd))

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    for line in process.stdout:
        add_log(job_id, line.rstrip())

    process.wait()

    add_log(job_id, f"FFmpeg finalizou com código: {process.returncode}")

    if process.returncode != 0:
        raise RuntimeError("FFmpeg falhou. Veja o log acima.")

    if not mp4_file.exists():
        raise RuntimeError("O MP4 não foi criado.")

    if mp4_file.stat().st_size < 1024:
        raise RuntimeError("O MP4 foi criado vazio ou pequeno demais.")

def worker(job_id, url, quality, fmt):
    try:
        set_job(job_id, status="running", error=None, file=None, filename=None)
        add_log(job_id, "Iniciando...")

        ts_file = DOWNLOAD_DIR / f"video_{job_id}.ts"
        mp4_file = DOWNLOAD_DIR / f"video_{job_id}.mp4"

        run_streamlink(job_id, url, quality, ts_file)

        if fmt == "mp4":
            convert_to_mp4(job_id, ts_file, mp4_file)
            final_file = mp4_file
            filename = f"video_{job_id}.mp4"
        else:
            final_file = ts_file
            filename = f"video_{job_id}.ts"

        set_job(
            job_id,
            status="done",
            file=str(final_file),
            filename=filename,
            size=final_file.stat().st_size
        )
        add_log(job_id, "Arquivo pronto.")

    except Exception as e:
        set_job(job_id, status="error", error=str(e))
        add_log(job_id, "ERRO: " + str(e))

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/health")
def health():
    return jsonify({
        "ok": True,
        "ffmpeg": FFMPEG,
        "downloads": str(DOWNLOAD_DIR)
    })

@app.route("/start", methods=["POST"])
def start():
    data = request.get_json(force=True)

    url = (data.get("url") or "").strip()
    quality = (data.get("quality") or "best").strip()
    fmt = (data.get("format") or "ts").strip().lower()

    if not url.startswith(("http://", "https://")):
        return jsonify({"ok": False, "error": "URL inválida."}), 400

    if fmt not in ("ts", "mp4"):
        return jsonify({"ok": False, "error": "Formato inválido."}), 400

    job_id = uuid.uuid4().hex[:12]
    jobs[job_id] = {
        "status": "queued",
        "logs": [],
        "url": url,
        "quality": quality,
        "format": fmt,
        "created": time.time()
    }

    thread = threading.Thread(
        target=worker,
        args=(job_id, url, quality, fmt),
        daemon=True
    )
    thread.start()

    return jsonify({"ok": True, "job_id": job_id})

@app.route("/status/<job_id>")
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"ok": False, "error": "Job não encontrado."}), 404

    return jsonify({
        "ok": True,
        "status": job.get("status"),
        "error": job.get("error"),
        "logs": job.get("logs", []),
        "download_url": f"/file/{job_id}" if job.get("status") == "done" else None,
        "filename": job.get("filename"),
        "size": job.get("size")
    })

@app.route("/file/<job_id>")
def file(job_id):
    job = jobs.get(job_id)
    if not job or job.get("status") != "done":
        abort(404)

    path = Path(job["file"])
    if not path.exists():
        abort(404)

    return send_file(
        path,
        as_attachment=True,
        download_name=job.get("filename") or path.name
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)


import os
import uuid
import time
import threading
import subprocess
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, abort

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

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
    jobs[job_id]["logs"] = logs[-120:]

def worker(job_id, url, qualidade):
    try:
        set_job(job_id, status="running", error=None)
        add_log(job_id, "Iniciando download...")

        # Nome RELATIVO, igual ao CMD:
        nome_arquivo = f"nomedo video {job_id}.ts"

        # Executa dentro da pasta downloads, então NÃO aparece /opt/render/... no comando.
        comando = f'streamlink --output "{nome_arquivo}" "{url}" {qualidade}'

        add_log(job_id, "Comando executado:")
        add_log(job_id, comando)

        p = subprocess.Popen(
            comando,
            shell=True,
            cwd=str(DOWNLOAD_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        for linha in p.stdout:
            add_log(job_id, linha.rstrip())

        p.wait()
        add_log(job_id, f"Código final: {p.returncode}")

        arquivo_final = DOWNLOAD_DIR / nome_arquivo

        if p.returncode != 0:
            raise RuntimeError("Streamlink falhou. Veja o log.")

        if not arquivo_final.exists():
            raise RuntimeError("O arquivo .ts não foi criado.")

        if arquivo_final.stat().st_size < 1024:
            raise RuntimeError("O arquivo .ts ficou vazio ou pequeno demais.")

        set_job(
            job_id,
            status="done",
            file=str(arquivo_final),
            filename=nome_arquivo,
            size=arquivo_final.stat().st_size
        )

        add_log(job_id, "Arquivo pronto.")

    except Exception as e:
        set_job(job_id, status="error", error=str(e))
        add_log(job_id, "ERRO: " + str(e))

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/start", methods=["POST"])
def start():
    data = request.get_json(force=True)
    url = (data.get("url") or "").strip()
    qualidade = (data.get("quality") or "best").strip()

    if not url.startswith(("http://", "https://")):
        return jsonify({"ok": False, "error": "URL inválida."}), 400

    if not qualidade:
        qualidade = "best"

    job_id = uuid.uuid4().hex[:8]
    jobs[job_id] = {
        "status": "queued",
        "logs": [],
        "created": time.time()
    }

    t = threading.Thread(target=worker, args=(job_id, url, qualidade), daemon=True)
    t.start()

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

    return send_file(path, as_attachment=True, download_name=job.get("filename") or path.name)

@app.route("/health")
def health():
    return jsonify({"ok": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)

import os
import uuid
import shutil
import subprocess
from pathlib import Path
from flask import Flask, render_template, request, send_file

app = Flask(__name__)

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

@app.route("/")
def index():
    return render_template("index.html")

def baixar_streamlink(url, qualidade, output_file):
    cmd = [
        "streamlink",
        "--output",
        str(output_file),
        url,
        qualidade
    ]

    process = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    print(process.stdout)
    print(process.stderr)

    if process.returncode != 0:
        return False, process.stderr

    return True, None

@app.route("/download", methods=["POST"])
def download():
    url = request.form.get("url", "").strip()
    qualidade = request.form.get("quality", "best")
    formato = request.form.get("format", "ts")

    if not url:
        return render_template("index.html", error="URL inválida.")

    uid = uuid.uuid4().hex[:8]

    ts_file = DOWNLOAD_DIR / f"video_{uid}.ts"

    ok, erro = baixar_streamlink(url, qualidade, ts_file)

    if not ok:
        return render_template("index.html", error=erro)

    final_file = ts_file

    if formato == "mp4":
        mp4_file = DOWNLOAD_DIR / f"video_{uid}.mp4"

        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(ts_file),
            "-c:v",
            "libx264",
            "-tag:v",
            "avc1",
            "-c:a",
            "aac",
            str(mp4_file)
        ]

        ffmpeg = subprocess.run(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        print(ffmpeg.stdout)
        print(ffmpeg.stderr)

        if ffmpeg.returncode != 0:
            return render_template("index.html", error=ffmpeg.stderr)

        final_file = mp4_file

    return send_file(final_file, as_attachment=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

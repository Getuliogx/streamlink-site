import os
import re
import uuid
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, render_template, request, jsonify, send_from_directory
import imageio_ffmpeg
from streamlink import Streamlink

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "static" / "downloads"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024

QUALITY_ORDER = ["best", "720p", "480p", "360p", "worst"]


def safe_name(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9._-]+", "_", text).strip("_")
    return text[:80] or "video"


def guess_name(url: str) -> str:
    host = urlparse(url).netloc.replace("www.", "")
    return safe_name(host or "video")


def get_stream_url(page_url: str, quality: str = "best") -> str:
    session = Streamlink()
    session.set_option("http-timeout", 30)
    streams = session.streams(page_url)
    if not streams:
        raise RuntimeError("Nenhum stream encontrado nessa URL.")

    selected = streams.get(quality)
    if not selected:
        for q in QUALITY_ORDER:
            selected = streams.get(q)
            if selected:
                break
    if not selected:
        selected = next(iter(streams.values()))

    return selected.to_url()


def run_ffmpeg_to_ts(stream_url: str, out_file: Path):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg,
        "-y",
        "-i", stream_url,
        "-c", "copy",
        "-f", "mpegts",
        str(out_file),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=900)


def run_ffmpeg_to_mp4(stream_url: str, out_file: Path):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg,
        "-y",
        "-i", stream_url,
        "-map", "0:v:0?",
        "-map", "0:a:0?",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(out_file),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=900)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/baixar", methods=["POST"])
def baixar():
    data = request.get_json(force=True)
    url = (data.get("url") or "").strip()
    formato = (data.get("formato") or "mp4").lower()
    qualidade = (data.get("qualidade") or "best").strip()

    if not url.startswith(("http://", "https://")):
        return jsonify({"ok": False, "erro": "Informe uma URL válida começando com http:// ou https://"}), 400
    if formato not in {"ts", "mp4"}:
        return jsonify({"ok": False, "erro": "Formato inválido."}), 400

    file_id = uuid.uuid4().hex[:10]
    filename = f"{guess_name(url)}_{file_id}.{formato}"
    out_file = DOWNLOAD_DIR / filename

    try:
        stream_url = get_stream_url(url, qualidade)
        if formato == "ts":
            run_ffmpeg_to_ts(stream_url, out_file)
        else:
            run_ffmpeg_to_mp4(stream_url, out_file)
        return jsonify({
            "ok": True,
            "arquivo": filename,
            "download": f"/download/{filename}",
            "mensagem": "Arquivo gerado com sucesso."
        })
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "erro": "Tempo limite estourou. O Render Free pode não aguentar vídeos longos."}), 500
    except subprocess.CalledProcessError as e:
        erro = e.stderr.decode("utf-8", errors="ignore")[-1200:]
        return jsonify({"ok": False, "erro": "FFmpeg falhou.", "detalhes": erro}), 500
    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)}), 500


@app.route("/download/<path:filename>")
def download(filename):
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)


@app.route("/health")
def health():
    return "ok"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

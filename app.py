
import os
import re
import json
import time
import uuid
import shutil
import logging
import tempfile
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, render_template, request, send_file, jsonify, after_this_request
import imageio_ffmpeg
import requests

app = Flask(__name__)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("streamlink-site")

BASE_DIR = Path(__file__).resolve().parent
TMP_DIR = Path(tempfile.gettempdir()) / "streamlink_site_downloads"
TMP_DIR.mkdir(parents=True, exist_ok=True)

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


def safe_name(name: str, ext: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9._-]+", "_", name or "video").strip("_")
    if not name:
        name = "video"
    if not name.lower().endswith("." + ext):
        name += "." + ext
    return name[:120]


def run_cmd(cmd, timeout=60):
    log.info("CMD: %s", " ".join(map(str, cmd)))
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
    log.info("RET=%s", p.returncode)
    if p.stdout:
        log.info("STDOUT: %s", p.stdout[-4000:])
    if p.stderr:
        log.info("STDERR: %s", p.stderr[-4000:])
    return p


def streamlink_json(url):
    cmd = [
        "python", "-m", "streamlink",
        "--json",
        "--http-header", f"User-Agent={USER_AGENT}",
        url,
    ]
    p = run_cmd(cmd, timeout=90)
    if p.returncode != 0:
        return None, p.stderr or p.stdout
    try:
        return json.loads(p.stdout), None
    except Exception as e:
        return None, f"Streamlink JSON inválido: {e}; saída={p.stdout[:1000]}"


def choose_stream(data, quality):
    streams = data.get("streams", {}) if data else {}
    if not streams:
        return None
    if quality in streams:
        return quality
    if quality == "best":
        for q in ["best", "1080p", "720p", "480p", "360p", "worst"]:
            if q in streams:
                return q
    if "best" in streams:
        return "best"
    return next(iter(streams.keys()))


def download_with_streamlink(url, quality, out_file):
    data, err = streamlink_json(url)
    selected = choose_stream(data, quality)
    if not selected:
        return False, err or "Streamlink não encontrou stream nessa URL."

    cmd = [
        "python", "-m", "streamlink",
        "--force",
        "--http-header", f"User-Agent={USER_AGENT}",
        "-o", str(out_file),
        url,
        selected,
    ]
    p = run_cmd(cmd, timeout=1800)
    if p.returncode != 0 or not out_file.exists() or out_file.stat().st_size < 1024:
        return False, p.stderr or p.stdout or "Streamlink falhou sem detalhes."
    return True, None


def get_direct_url_with_ytdlp(url, quality):
    # Fallback útil para páginas on-demand que Streamlink não entende bem.
    fmt = "best"
    if quality and quality not in ("best", "worst"):
        h = re.sub(r"[^0-9]", "", quality)
        if h:
            fmt = f"best[height<={h}]/best"
    elif quality == "worst":
        fmt = "worst"

    cmd = [
        "python", "-m", "yt_dlp",
        "--no-playlist",
        "--user-agent", USER_AGENT,
        "-f", fmt,
        "-g",
        url,
    ]
    p = run_cmd(cmd, timeout=120)
    if p.returncode != 0:
        return None, p.stderr or p.stdout or "yt-dlp não conseguiu resolver a URL."
    lines = [x.strip() for x in p.stdout.splitlines() if x.strip().startswith(("http://", "https://"))]
    if not lines:
        return None, "yt-dlp não retornou link direto."
    return lines[0], None


def ffmpeg_copy_to_ts(input_url_or_file, out_file):
    cmd = [
        FFMPEG, "-y",
        "-headers", f"User-Agent: {USER_AGENT}\r\n",
        "-i", str(input_url_or_file),
        "-c", "copy",
        "-f", "mpegts",
        str(out_file),
    ]
    p = run_cmd(cmd, timeout=1800)
    if p.returncode != 0 or not out_file.exists() or out_file.stat().st_size < 1024:
        return False, p.stderr or p.stdout or "FFmpeg TS falhou."
    return True, None


def ffmpeg_to_mp4_h264(input_url_or_file, out_file):
    # Gera MP4 compatível H.264/AVC1 + AAC.
    cmd = [
        FFMPEG, "-y",
        "-headers", f"User-Agent: {USER_AGENT}\r\n",
        "-i", str(input_url_or_file),
        "-map", "0:v:0?", "-map", "0:a:0?",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-tag:v", "avc1",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(out_file),
    ]
    p = run_cmd(cmd, timeout=1800)
    if p.returncode != 0 or not out_file.exists() or out_file.stat().st_size < 1024:
        return False, p.stderr or p.stdout or "FFmpeg MP4 falhou."
    return True, None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    return jsonify({
        "ok": True,
        "ffmpeg": FFMPEG,
        "tmp": str(TMP_DIR),
    })


@app.route("/download", methods=["POST"])
def download():
    url = (request.form.get("url") or "").strip()
    fmt = (request.form.get("format") or "mp4").strip().lower()
    quality = (request.form.get("quality") or "best").strip()

    log.info("NOVO DOWNLOAD url=%s format=%s quality=%s", url, fmt, quality)

    if not url.startswith(("http://", "https://")):
        return render_template("index.html", error="URL inválida.", last_url=url)

    if fmt not in ("mp4", "ts"):
        return render_template("index.html", error="Formato inválido.", last_url=url)

    job = uuid.uuid4().hex
    work = TMP_DIR / job
    work.mkdir(parents=True, exist_ok=True)

    parsed = urlparse(url)
    host = parsed.netloc.replace("www.", "")
    final_name = safe_name(host + "_" + job[:8], fmt)
    out_file = work / final_name

    errors = []

    try:
        # 1) Tenta Streamlink para TS bruto
        if fmt == "ts":
            ok, err = download_with_streamlink(url, quality, out_file)
            if not ok:
                errors.append("Streamlink: " + str(err)[-1200:])
                direct, derr = get_direct_url_with_ytdlp(url, quality)
                if not direct:
                    errors.append("yt-dlp: " + str(derr)[-1200:])
                    raise RuntimeError("\n\n".join(errors))
                ok, err = ffmpeg_copy_to_ts(direct, out_file)
                if not ok:
                    errors.append("FFmpeg TS: " + str(err)[-1200:])
                    raise RuntimeError("\n\n".join(errors))

        # 2) MP4 H264 AVC1: tenta resolver por yt-dlp primeiro; se falhar usa Streamlink TS temporário
        else:
            direct, derr = get_direct_url_with_ytdlp(url, quality)
            if direct:
                ok, err = ffmpeg_to_mp4_h264(direct, out_file)
                if not ok:
                    errors.append("FFmpeg direto: " + str(err)[-1200:])
                    # fallback
                    tmp_ts = work / "input.ts"
                    ok2, err2 = download_with_streamlink(url, quality, tmp_ts)
                    if not ok2:
                        errors.append("Streamlink fallback: " + str(err2)[-1200:])
                        raise RuntimeError("\n\n".join(errors))
                    ok3, err3 = ffmpeg_to_mp4_h264(tmp_ts, out_file)
                    if not ok3:
                        errors.append("FFmpeg fallback: " + str(err3)[-1200:])
                        raise RuntimeError("\n\n".join(errors))
            else:
                errors.append("yt-dlp: " + str(derr)[-1200:])
                tmp_ts = work / "input.ts"
                ok, err = download_with_streamlink(url, quality, tmp_ts)
                if not ok:
                    errors.append("Streamlink: " + str(err)[-1200:])
                    raise RuntimeError("\n\n".join(errors))
                ok, err = ffmpeg_to_mp4_h264(tmp_ts, out_file)
                if not ok:
                    errors.append("FFmpeg: " + str(err)[-1200:])
                    raise RuntimeError("\n\n".join(errors))

        log.info("ARQUIVO OK: %s size=%s", out_file, out_file.stat().st_size)

        @after_this_request
        def cleanup(response):
            try:
                shutil.rmtree(work, ignore_errors=True)
            except Exception:
                pass
            return response

        return send_file(out_file, as_attachment=True, download_name=final_name)

    except subprocess.TimeoutExpired:
        log.exception("Timeout")
        shutil.rmtree(work, ignore_errors=True)
        return render_template("index.html", error="Demorou demais e o Render cortou o processo. Tente qualidade menor ou TS.", last_url=url)
    except Exception as e:
        log.exception("Falha no download")
        shutil.rmtree(work, ignore_errors=True)
        msg = str(e)
        if len(msg) > 1800:
            msg = msg[-1800:]
        return render_template("index.html", error=msg, last_url=url)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)

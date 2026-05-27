import os, re, uuid, subprocess, sys, time
from pathlib import Path
from urllib.parse import urlparse, urlencode

from flask import Flask, render_template, request, jsonify, send_from_directory
import imageio_ffmpeg
from streamlink import Streamlink

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / 'static' / 'downloads'
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024

QUALITY_ORDER = ['best', '1080p', '720p', '480p', '360p', 'worst']
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36'

def log(msg):
    print(f'[streamlink-site] {msg}', flush=True)

def safe_name(text: str) -> str:
    return (re.sub(r'[^a-zA-Z0-9._-]+', '_', text).strip('_')[:80] or 'video')

def guess_name(url: str) -> str:
    host = urlparse(url).netloc.replace('www.', '')
    return safe_name(host or 'video')

def pluto_episode_m3u8(page_url: str):
    """Tenta transformar URL Pluto on-demand /episode/<id> em playlist HLS.
    Não quebra DRM: se o conteúdo exigir DRM, o FFmpeg vai falhar e avisar.
    """
    if 'pluto.tv' not in page_url:
        return None
    m = re.search(r'/episode/([a-zA-Z0-9_-]+)', page_url)
    if not m:
        return None
    episode_id = m.group(1)
    params = {
        'advertisingId': '',
        'appName': 'web',
        'appStoreUrl': '',
        'appVersion': '5.0.0',
        'architecture': '',
        'buildVersion': '',
        'deviceDNT': '0',
        'deviceId': str(uuid.uuid4()),
        'deviceLat': '-23.5505',
        'deviceLon': '-46.6333',
        'deviceMake': 'Chrome',
        'deviceModel': 'Chrome',
        'deviceType': 'web',
        'deviceVersion': '124.0.0.0',
        'includeExtendedEvents': 'false',
        'marketingRegion': 'BR',
        'sid': str(uuid.uuid4()),
        'userId': '',
        'serverSideAds': 'true',
    }
    return f'https://service-stitcher.clusters.pluto.tv/stitch/hls/episode/{episode_id}/master.m3u8?' + urlencode(params)

def get_stream_url(page_url: str, quality: str = 'best') -> str:
    # URL HLS direta
    if '.m3u8' in page_url:
        return page_url

    # Pluto on-demand: Streamlink nem sempre detecta a página, então monta o HLS do episódio
    pluto = pluto_episode_m3u8(page_url)
    if pluto:
        log('Pluto on-demand detectado; usando playlist HLS do episódio.')
        return pluto

    session = Streamlink()
    session.set_option('http-timeout', 30)
    session.set_option('http-headers', {'User-Agent': UA, 'Referer': page_url})
    log(f'Procurando streams com Streamlink: {page_url}')
    streams = session.streams(page_url)
    log('Qualidades encontradas: ' + ', '.join(streams.keys()) if streams else 'Nenhuma qualidade encontrada')
    if not streams:
        raise RuntimeError('Nenhum stream encontrado nessa URL. Tente colar uma URL .m3u8 direta ou uma URL suportada pelo Streamlink.')

    selected = streams.get(quality)
    if not selected:
        for q in QUALITY_ORDER:
            selected = streams.get(q)
            if selected:
                break
    if not selected:
        selected = next(iter(streams.values()))
    return selected.to_url()

def run_ffmpeg(stream_url: str, out_file: Path, formato: str, referer: str):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    headers = f'User-Agent: {UA}\r\nReferer: {referer}\r\n'
    cmd = [ffmpeg, '-y', '-hide_banner', '-loglevel', 'error', '-headers', headers, '-i', stream_url]
    if formato == 'ts':
        cmd += ['-c', 'copy', '-f', 'mpegts', str(out_file)]
    else:
        cmd += [
            '-map', '0:v:0?', '-map', '0:a:0?',
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23',
            '-pix_fmt', 'yuv420p', '-tag:v', 'avc1',
            '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', str(out_file)
        ]
    log('Rodando FFmpeg...')
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=900)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-3000:] or 'FFmpeg falhou sem detalhes.')
    if not out_file.exists() or out_file.stat().st_size < 1024:
        raise RuntimeError('Arquivo saiu vazio. A URL pode estar protegida por DRM, bloqueada por região ou sem permissão.')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/baixar', methods=['POST'])
def baixar():
    data = request.get_json(force=True)
    url = (data.get('url') or '').strip()
    formato = (data.get('formato') or 'mp4').lower()
    qualidade = (data.get('qualidade') or 'best').strip()
    if not url.startswith(('http://', 'https://')):
        return jsonify(ok=False, erro='Informe uma URL válida começando com http:// ou https://'), 400
    if formato not in {'ts', 'mp4'}:
        return jsonify(ok=False, erro='Formato inválido.'), 400
    filename = f"{guess_name(url)}_{uuid.uuid4().hex[:10]}.{formato}"
    out_file = DOWNLOAD_DIR / filename
    try:
        log(f'Requisição: formato={formato} qualidade={qualidade} url={url}')
        stream_url = get_stream_url(url, qualidade)
        log(f'Playlist/stream obtido: {stream_url[:180]}')
        run_ffmpeg(stream_url, out_file, formato, url)
        size_mb = round(out_file.stat().st_size / 1024 / 1024, 2)
        log(f'Arquivo pronto: {filename} ({size_mb} MB)')
        return jsonify(ok=True, arquivo=filename, download=f'/download/{filename}', mensagem=f'Arquivo gerado com sucesso ({size_mb} MB).')
    except subprocess.TimeoutExpired:
        log('ERRO: timeout')
        return jsonify(ok=False, erro='Tempo limite estourou. O Render Free pode não aguentar vídeos longos.'), 500
    except Exception as e:
        log('ERRO: ' + str(e))
        return jsonify(ok=False, erro=str(e)), 500

@app.route('/download/<path:filename>')
def download(filename):
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)

@app.route('/health')
def health():
    return 'ok'

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

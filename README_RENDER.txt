# Streamlink Downloader para Render + GitHub

Esta versão NÃO usa Docker e NÃO depende do FFmpeg do sistema.

Ela usa:
- Flask
- Streamlink
- yt-dlp como fallback
- imageio-ffmpeg, que baixa/fornece FFmpeg dentro do ambiente Python

## Render

Crie como:

New + -> Web Service

Configuração:

Runtime:
Python 3

Build Command:
pip install -r requirements.txt

Start Command:
gunicorn app:app --bind 0.0.0.0:$PORT --timeout 1200 --workers 1 --log-level info --access-logfile - --error-logfile -

Depois:
Manual Deploy -> Clear build cache & deploy

## Teste

Abra:
https://SEU-SITE.onrender.com/health

Se aparecer JSON com "ok": true e caminho do ffmpeg, o FFmpeg está funcionando.

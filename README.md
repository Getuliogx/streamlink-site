# Streamlink Downloader - Render + GitHub

Use como **Web Service** no Render.

Build Command:
```bash
pip install -r requirements.txt
```

Start Command:
```bash
gunicorn app:app --bind 0.0.0.0:$PORT --timeout 900 --workers 1 --log-level info --access-logfile - --error-logfile -
```

Correções desta versão:
- logs aparecem no Render;
- aceita URL `.m3u8` direta;
- fallback para Pluto TV on-demand `/episode/<id>`;
- MP4 sai com H.264 e tag AVC1;
- mostra erro real do FFmpeg na tela.

Use apenas com vídeos/streams que você tem direito de baixar.

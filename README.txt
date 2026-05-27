COMO SUBIR NO GITHUB + RENDER

1. Extraia este ZIP.
2. No GitHub, apague os arquivos antigos do repositório.
3. Envie TODOS os arquivos deste ZIP.

No Render:
New + -> Web Service

Use:
Runtime: Python 3

Build Command:
pip install -r requirements.txt

Start Command:
gunicorn app:app --bind 0.0.0.0:$PORT --timeout 1200 --workers 1 --threads 4 --log-level info --access-logfile - --error-logfile -

Depois clique:
Manual Deploy -> Clear build cache & deploy

IMPORTANTE:
Agora o site NÃO faz POST direto para baixar.
Ele inicia um job, mostra o log na tela e depois aparece o botão "Baixar arquivo pronto".

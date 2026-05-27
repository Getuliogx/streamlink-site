VERSÃO COM STREAMLINK MAIS NOVO DIRETO DO GITHUB

No GitHub:
1. Apague os arquivos antigos.
2. Envie todos os arquivos deste ZIP.

No Render:
Build Command:
pip install -r requirements.txt

Start Command:
gunicorn app:app --bind 0.0.0.0:$PORT --timeout 1200 --workers 1 --threads 4 --log-level info --access-logfile - --error-logfile -

Depois:
Manual Deploy -> Clear build cache & deploy

IMPORTANTE:
Se no seu CMD funciona e no Render não, mesmo com Streamlink atualizado, então é bloqueio por região/IP do servidor Render.
Nesse caso Pluto BR só vai baixar em servidor com IP do Brasil, não no Render.

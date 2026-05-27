VERSÃO CORRIGIDA

Agora o comando no log fica sem /opt/render:

streamlink --output "nomedo video XXXXX.ts" "URL" best

O comando é executado dentro da pasta downloads usando cwd.

Render:
Build Command:
pip install -r requirements.txt

Start Command:
gunicorn app:app --bind 0.0.0.0:$PORT --timeout 1200 --workers 1 --threads 4 --log-level info --access-logfile - --error-logfile -

Depois:
Manual Deploy -> Clear build cache & deploy

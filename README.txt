GITHUB:
- Extraia o ZIP
- Crie repositório no GitHub
- Envie TODOS os arquivos

RENDER:
- New +
- Web Service
- Conecte GitHub
- Escolha repositório

BUILD COMMAND:
pip install -r requirements.txt

START COMMAND:
gunicorn app:app --bind 0.0.0.0:$PORT --timeout 1200

Depois:
Manual Deploy -> Clear build cache & deploy

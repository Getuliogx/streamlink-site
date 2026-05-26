# Streamlink Downloader para Render + GitHub

Site Flask para baixar vídeos/streams usando Streamlink e salvar como `.ts` ou `.mp4`.

## Importante
Use apenas com URLs que você tem direito de baixar. O armazenamento do Render Free é temporário: arquivos podem sumir quando o serviço reiniciar.

## Como subir no GitHub

1. Crie um repositório no GitHub.
2. Envie todos estes arquivos para o repositório.
3. No Render, clique em **New +** > **Web Service**.
4. Conecte seu GitHub e escolha o repositório.
5. Use:
   - Runtime: Python
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT --timeout 600`
6. Clique em Deploy.

O arquivo `render.yaml` também permite deploy por Blueprint.

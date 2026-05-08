# Deploy local e container

Este projeto roda em dois modos:

- Local, usando o Python instalado na maquina.
- Container Docker, usando os arquivos `Dockerfile` e `docker-compose.yml`.

## Arquivos sensiveis

O arquivo `auth/config.yaml` nao deve ser gravado dentro da imagem Docker. Ele e montado no container pelo `docker-compose.yml`.

Use `auth/config.example.yaml` apenas como modelo.

## Execucao local

No PowerShell, dentro da pasta do projeto:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python deployment\smoke_test.py
python -m streamlit run app.py --server.port 8502 --server.address 127.0.0.1
```

Acesse:

```text
http://127.0.0.1:8502
```

## Execucao com Docker Compose

1. Confira se existem:

```text
auth/config.yaml
data/Geo.shp
data/Geo.dbf
data/Geo.shx
data/Geo.prj
```

2. Copie o arquivo de exemplo de ambiente, se quiser customizar porta/projeto:

```powershell
Copy-Item .env.example .env
```

3. Suba o container:

```powershell
docker compose up --build
```

Acesse:

```text
http://127.0.0.1:8502
```

## Earth Engine no container

Ha duas formas recomendadas:

1. Definir o projeto em `auth/config.yaml`:

```yaml
earth_engine:
  project: "streamelit"
  service_account_email: ""
  service_account_file: ""
```

2. Usar service account:

```yaml
earth_engine:
  project: "streamelit"
  service_account_email: "conta@projeto.iam.gserviceaccount.com"
  service_account_file: "/app/auth/earth-engine-service-account.json"
```

Coloque o JSON da service account dentro de `auth/` na maquina local. Essa pasta e montada em `/app/auth` no container.

## Variaveis uteis

- `APP_AUTH_CONFIG`: caminho do YAML de autenticacao.
- `CODEBOOK_AUTH_CONFIG`: alternativa ao `APP_AUTH_CONFIG` para execucao no Codebook.
- `APP_GEO_PATH`: caminho do shapefile principal.
- `CODEBOOK_GEO_PATH`: alternativa ao `APP_GEO_PATH` para execucao no Codebook.
- `EE_PROJECT`: projeto Google Cloud/Earth Engine.
- `GOOGLE_APPLICATION_CREDENTIALS` ou `EE_CREDENTIALS_PATH`: JSON da service account.
- `EE_SERVICE_ACCOUNT_EMAIL`: e-mail da service account, se necessario.

## Execucao no Codebook

Para rodar no Codebook, mantenha a mesma estrutura do projeto e configure as
variaveis do ambiente antes de iniciar o Streamlit:

```text
APP_AUTH_CONFIG=/app/auth/config.yaml
APP_GEO_PATH=/app/data/Geo.shp
EE_PROJECT=streamelit
```

Se o Codebook publicar a aplicacao por uma porta propria, use essa porta no
comando do Streamlit:

```bash
python -m streamlit run app.py --server.address 0.0.0.0 --server.port ${PORT:-8502}
```

O login nao depende de caminho fixo da maquina local: ele usa `APP_AUTH_CONFIG`
ou `CODEBOOK_AUTH_CONFIG` quando definidos, e so depois tenta `auth/config.yaml`
na pasta do projeto.

## Teste rapido

```powershell
python deployment\smoke_test.py
```

No container:

```powershell
docker compose run --rm plataforma-incendios python deployment/smoke_test.py
```

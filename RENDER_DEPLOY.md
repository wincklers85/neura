# NÈURA Cloud – deploy Render

## Metodo consigliato
1. Carica **il contenuto di questa cartella** nella radice della repository GitHub.
2. In Render scegli **New > Blueprint** e seleziona la repository.
3. Configura almeno `APP_PASSWORD` e `LLM_API_KEY`.
4. Avvia il deploy.

Il Dockerfile, `render.yaml`, `app.py` e `requirements.txt` devono essere visibili nella radice della repository, non dentro un'altra cartella.

## Se modifichi il servizio già esistente
Imposta:
- Runtime: Docker
- Dockerfile Path: `./Dockerfile`
- Health Check Path: `/health`

Non inserire manualmente una porta. Render passa la variabile `PORT` e NÈURA la usa automaticamente.

## Controllo
Quando il deploy è concluso, apri:
`https://TUO-SERVIZIO.onrender.com/health`

Deve rispondere con JSON contenente `"ok": true`.

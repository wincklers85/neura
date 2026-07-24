# NÈURA Cloud v4.0

Versione cloud per Render con memoria persistente, documenti, visione e configurazione del motore AI direttamente dall'interfaccia.

## Pubblicazione

1. Carica tutti i file nella root della repository GitHub.
2. Su Render crea un Blueprint dalla repository, oppure un Web Service Docker.
3. Imposta `APP_PASSWORD` quando Render lo richiede.
4. Avvia il deploy.
5. Entra in NÈURA, apri **Impostazioni → Motore AI**, scegli il fornitore, inserisci la chiave API e premi **Salva configurazione**, poi **Prova connessione**.

Non è più obbligatorio configurare `LLM_API_KEY` nella dashboard Render. È comunque possibile farlo: le variabili Render restano un fallback.

## Dati persistenti

Il Blueprint monta un disco in `/var/data`. Conversazioni, memorie, libreria, backup e configurazione cifrata del motore restano disponibili dopo i deploy.

## Variabili principali

- `APP_PASSWORD`: password d'accesso.
- `ENCRYPTION_KEY`: generata automaticamente dal Blueprint.
- `DATA_DIR=/var/data`.
- `TAVILY_API_KEY`: facoltativa, per la ricerca web.
- `LLM_API_KEY`, `LLM_API_BASE`, `MODEL_NAME`, `VISION_MODEL`: facoltative, come configurazione alternativa via Render.

# NÈURA Surface 2.0

Assistente personale locale per Windows e Surface Pro, con cronologia delle chat, memoria cifrata, Costituzione, libreria documenti, visione locale, laboratorio di programmazione, backup e rollback.

## Installazione

1. Estrai lo ZIP in una cartella stabile, per esempio `C:\NEURA`.
2. Clic destro su `Install-NEURA.ps1` e scegli **Esegui con PowerShell**.
3. Scegli una password.
4. Alla domanda sul modello visivo rispondi `S` per installare il riconoscimento immagini offline.
5. Avvia con `Start-NEURA.cmd`.

L'interfaccia si apre su `http://127.0.0.1:8000`.

## Funzioni principali

- Chat salvate automaticamente, ricercabili, rinominabili, archiviabili e riapribili.
- Ricerca nel contenuto delle conversazioni precedenti.
- Costituzione modificabile in italiano naturale.
- Internet disattivato per impostazione predefinita: l'autorizzazione vale per un solo messaggio.
- Libreria PDF, DOCX, TXT, MD, CSV, JSON, PY e HTML.
- Modalità **Solo lettura** oppure **Studia e impara**.
- Analisi di immagini tramite modello Ollama multimodale locale.
- Memoria permanente cifrata.
- Laboratorio con sandbox, validazione, backup e applicazione solo dopo conferma.
- Backup del database e snapshot del codice.

## Nota sui modelli

Il modello testuale predefinito è configurato in `.env` tramite `MODEL_NAME`. Il modello visivo usa `VISION_MODEL`. Puoi sostituirli con modelli Ollama compatibili con il tuo Surface.

## Internet

NÈURA non effettua ricerche Internet senza autorizzazione. Nell'interfaccia premi **Internet: no**, conferma, quindi invia il messaggio. L'autorizzazione si azzera subito dopo quella richiesta.

## Dati

Tutti i dati locali sono nella cartella `data`. Non cancellarla durante gli aggiornamenti. Prima di modificare il progetto usa la sezione **Backup**.

## Versione Cloud per Render

Questa variante non esegue più Ollama o un piccolo modello locale dentro Render. Usa invece un servizio AI cloud compatibile con l'endpoint `/v1/chat/completions`, evitando il disallineamento tra Ollama e llama.cpp presente nella versione Surface.

Variabili obbligatorie su Render:

- `APP_PASSWORD`: password di accesso a NÈURA.
- `LLM_API_KEY`: chiave del servizio AI.
- `LLM_API_BASE`: base API, normalmente `https://api.openai.com/v1`.
- `MODEL_NAME`: modello testuale.
- `VISION_MODEL`: modello che supporta immagini.

Il disco persistente montato su `/var/data` conserva chat, memoria, libreria e backup durante i nuovi deploy. È importante mantenere `WEB_WORKERS=1`, perché le sessioni di accesso sono conservate in memoria nel processo; il database rimane comunque persistente.

### Pubblicazione

1. Carica il progetto in una repository GitHub.
2. In Render scegli **New > Blueprint** e collega la repository.
3. Inserisci `APP_PASSWORD`, `LLM_API_KEY` e, facoltativamente, `TAVILY_API_KEY`.
4. Avvia il deploy e apri `/health` per verificare il servizio.
5. Dopo il login, controlla **Stato modello**: deve mostrare `ready: true`.

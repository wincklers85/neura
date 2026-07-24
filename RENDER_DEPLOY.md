# Deploy rapido su Render

Carica il contenuto di questa cartella nella root di GitHub. In Render seleziona **New → Blueprint**, collega la repository e conferma il servizio indicato da `render.yaml`.

Dopo il deploy:

1. apri l'indirizzo `.onrender.com`;
2. accedi con `APP_PASSWORD`;
3. apri **Impostazioni**;
4. configura il motore AI;
5. salva e prova la connessione.

Per aggiornare: carica i nuovi file su GitHub. Render farà il deploy automatico. Il disco `/var/data` non viene cancellato.

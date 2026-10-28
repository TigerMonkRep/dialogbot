# Admin (kun for Dialogbot-operatører)

Adresse: `/app/operator/admin` (menu: konto → Operatør → *Admin: overblik*). Alt er **kun læsning**.

| Side | Indhold |
|---|---|
| Overblik | Trafiklys (grøn/gul/rød), "kræver opmærksomhed", de vigtigste tal |
| Kunder | Søg; pr. kunde: medlemmer, fakturering, telefoni, ambassadør, opkald, kampagner, logbog + *Vis alle detaljer (avanceret)* med rå rækker |
| Brugere | Alle personer (kunder, kolleger, ambassadører) med *Se som* |
| Drift | Databaseversion vs. kode, opgavekø, fejlede opgaver, e-mails, global logbog |
| Værktøjer | Genveje til social, ambassadører, salg, telefoni, stemmer |

Hemmeligheder (adgangskode-hash, token-hash, krypteret CPR/bank, nøgler) returneres aldrig; rå visninger viser `<skjult>`.

## Se som kunde

*Se som* åbner kundens egen visning af appen (også ambassadørsiden): samme sider, samme data, samme roller som personen.

* **Skrivebeskyttet**: to uafhængige spærrer i `app/core/auth.py` – alle ikke-GET-kald afvises (`view_as_read_only`), og GET kører i en `READ ONLY`-databasetransaktion. Knapper, der ville ændre noget, giver derfor en fejl.
* **Tidsbegrænset**: 1 time. Operatørens egen session ligger parkeret i en separat httpOnly-cookie og genoprettes med *Afslut*.
* **Logget**: `admin.view_as.start` / `admin.view_as.end` i audit-loggen (hvem, hvem set, hvornår).
* Kan ikke startes af en visning, og operatører kan ikke ses som kunde.
* En sort bjælke øverst viser hele tiden, hvem du ser som.

Husk: adgang til kundekonti er adgang til personoplysninger. Nævn support-adgang i privatlivspolitikken/databehandleraftalen.

---
id: F-VF-03-PC-COPY
scenario: PC-CALL-EXTRA (tekst)
reported_by: verifier
severity: S3
status: new
owner_fix: fix-engineer
related: [F-PDEC-01-PC-CALL-EXTRA]
---

## Kort
Dobbelt punktum efter maksprisen: «… højst 17,50 kr.. (op til 3 min.)» og «… højst 17,50 kr.. Fyld op med …». Tokenet {pXMax} giver «17,50 kr.», og strengene slutter selv med «.».

## Hvor
privat.json (alle 8 sprog har «{pXMax}.» 4 steder: plan note, cost, prices, extraNote). Synligt i da/no (valutaen ender på «kr.»). Screenshots /home/claude/verifier-final/shots/desk-10-ekstra-opkald-kort.png og desk-12-fyld-op-ark.png.

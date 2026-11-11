# Lighthouse 12, mobil (simuleret throttling), lokal `next start` :3200, 2026-11-10

| Rute | Endte på | Perf | A11y | BP | SEO | LCP | CLS | TBT | Bemærkning |
|---|---|---|---|---|---|---|---|---|---|
| `/` | `/preview` (forsideporten – cookie blev ikke båret gennem /→/da-redirect) | 62 | 100 | 96 | 63 | 3.2 s | 0 | 1 910 ms | måler porten, ikke forsiden |
| `/da/erhverv` | `/da/erhverv` | 58 | 100 | 79 | 100 | **4.7 s** | 0 | 1 130 ms | 3. part `emrldtp.cc` (Travelpayouts Drive) 76 ms blokering; konsol: «config is not valid», en 403 og en 404 |
| `/privat` | `/privat` | 80 | 100 | 96 | 100 | 1.9 s | 0.007 | 790 ms | konsol: én 404 |

BP-point for `/da/erhverv` trækkes også af `is-on-https` (lokal http – ikke et fund). Container-CPU og ingen CDN: tallene er
indikative, ikke CWV. Rå JSON: `lh_*.json`.

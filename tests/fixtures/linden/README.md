# Testlyd til Linden-broen

Peters egen stemme (ElevenLabs, eleven_v4) – kendt dansk tekst, så genkendelsen kan måles uden telefon.

| Fil | Indhold | Format |
|---|---|---|
| `peter_steder_16k.wav` | "Hej, du har ringet til Fjord Gulvservice. Vi kører afslibning i Roskilde, Odense, Vejle, Lyngby, Ringkøbing og Grenå. Vores tømrer og mester ringer dig op i morgen." | 16 kHz mono |
| `peter_steder_8k_phone.wav` | samme, båndbegrænset 300–3400 Hz som en telefonlinje | 8 kHz mono |
| `berle_pool_16k.wav` | "Goddag, du har ringet til Berle Pool. Hvad kan jeg gøre for dig?" | 16 kHz mono |

Afspil gennem broen: `POST /api/v1/operator/telephony/linden/replay?fixture=peter_steder_8k_phone` (operatør).

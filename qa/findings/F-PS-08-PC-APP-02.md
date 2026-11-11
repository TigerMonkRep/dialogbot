---
id: F-PS-08-PC-APP-02
scenario: PC-APP-02
reported_by: security-privacy
severity: S2
status: new
owner_fix: fix-engineer
related: [F-PS-06-PC-WISH-11]
---

## Kort
Kvitteringsfotos i Garanti gemmes byte for byte – inklusive EXIF-GPS (hvor billedet er taget, typisk hjemme).

## Trin til at genskabe
1. Slå Garanti til, opret en ting.
2. `POST /privat/apps/garanti/items/{id}/photo` med en JPEG der har GPS-EXIF.
3. Læs den lagrede fil.

## Forventet
Dataminimering (GDPR art. 5(1)(c)): en kvittering skal ikke bære brugerens position. Ønskebilleder re-encodes allerede (wish_images.process) og mister EXIF.

## Faktisk
Den lagrede JPEG har GPS-IFD (0x8825). warranty.py:117-130 → `files.sniff` + `files.put(key, data, …)` uden re-encoding. Magic-byte-kontrol, 6 MB-loft og andens item → 404 virker.

## Evidens
- Test: tests/qa/test_qa_pd_sec.py::test_ps_app_02b_warranty_receipt_photo_keeps_gps_exif (rød)
- Test: tests/qa/test_qa_pd_sec.py::test_ps_app_02_warranty_photo_upload_checks (grøn)

## Rodårsag (forslag)
Kør kvitteringsfoto gennem samme pipeline som wish_images (Pillow: exif_transpose → re-encode JPEG/WebP uden EXIF; HEIC → konverter eller strip).

## Rettelse (udfyldes af fix-engineer)
- Filer:
- Commit:

## Verifikation (udfyldes af verifier)
- Gentest:
- Dom: closed | reopened

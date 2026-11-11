---
id: F-PS-06-PC-WISH-11
scenario: PC-WISH-11
reported_by: security-privacy
severity: S2
status: new
owner_fix: fix-engineer
related: []
---

## Kort
`POST /privat/wishes/images` har hverken app-krav, rate limit eller kvote, og billeder der aldrig gemmes på et ønske ryddes aldrig op.

## Trin til at genskabe
1. Gratis konto (ingen prøve): 40× `POST /privat/wishes/images` (PNG 120×100) i træk.

## Forventet
Scenariet: «rapportér manglende rate limit som S2 hvis lagring kan misbruges». Import har `_rate(...)`; upload bør have det samme og kræve Ønskelister.

## Faktisk
40/40 → 200. Hver upload dekodes (op til MAX_PIXELS) og gemmes som to WebP-filer i lageret; nøglen bindes først til et ønske ved «Gem ønske», ellers forbliver filerne for evigt. Kan bruges til lager-/CPU-misbrug.
Positivt: billeder re-encodes til WebP (EXIF/GPS fjernes), SVG/PDF afvises, > 6 MB afvises, cover på ikke-ønskeliste → 409.

## Evidens
- Test: tests/qa/test_qa_pd_sec.py::test_ps_wish_11b_wish_images_have_no_rate_limit_or_quota (rød)
- Test: tests/qa/test_qa_pd_sec.py::test_ps_wish_11_wish_images_validation_and_exif (grøn)

## Rodårsag (forslag)
wishes_router.py:155-159: tilføj `addons.require(db, ctx.ws_id, "oenskelister")` og `_rate(...)` (fx 30/time), og et oprydningsjob for nøgler uden ønske ældre end 24 t.

## Rettelse (udfyldes af fix-engineer)
- Filer:
- Commit:

## Verifikation (udfyldes af verifier)
- Gentest:
- Dom: closed | reopened

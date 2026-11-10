---
id: F-PBQ-07-PC-ENT-08
scenario: PC-ENT-08
reported_by: billing-qa
severity: S1
status: fixed
owner_fix: fix-engineer
related: []
---

## Kort
Familie (169 kr./md. eller 1.620 kr./år) sælges med «Op til 5 personer», men der findes ingen måde at give 4 andre adgang til planen. `people_limit` er kun et tal i API-svaret.

## Trin til at genskabe
1. Konto med Familie (aktiv).
2. `GET /privat/subscription` → `people_limit: 5`, og Familie-features har «Op til 5 personer».
3. Søg i OpenAPI (104 /privat-stier) efter household/husstand/family/plan-members: ingen.
4. `people_limit` bruges i app/modules/privat kun i `entitlements()` (subscriptions.py ~158) og læses ingen andre steder. Ingen model knytter brugere til en plan.

## Forventet
Hvad der sælges, findes: 4 husstandsmedlemmer kan få Familiens rettigheder (opkald fra fælles kvote, apps), eller også fjernes løftet fra plankortene.

## Faktisk
UI lover det på plankort, PlanSheet og landing:
- `plan.people`/`landing.pricing.features.people`: «Op til # personer»
- `apps.planFacts`: «… · op til # personer»
- `FEATURES["familie"]`: «Op til 5 personer»

Forskellen på Plus og Familie er derfor kun 15 opkald mere for 70 kr./md. mere. Det er også en mulig markedsføringsrisiko: et betalt løfte, der ikke leveres.

## Evidens
- Test: tests/qa/test_qa_pd_billing.py::test_pc_ent_08_familie_people_limit_has_no_way_to_add_people (fejler: «no household/family endpoint among 104 /privat routes; people_limit used only as …»)

## Beslutning nødvendig
Det er en produktbeslutning for Fürster, om husstandsdeling skal bygges nu, eller om «Op til 5 personer» skal fjernes eller markeres som «kommer snart». Indtil da bør fix-engineer/ui-ux-engineer fjerne eller markere løftet.

## Rodårsag (udfyldes af fix-engineer)
Husstanden var aldrig bygget: `people_limit` var kun et tal i `entitlements()`, og ingen model knyttede andre konti til en plan. Fürster besluttede 2026-11-10 21:59, at det skal bygges (A).

## Rettelse (udfyldes af fix-engineer #3)
- Model `PrivateHouseholdMember` (ejer-ws → medlems-ws, unik pr. medlem, CASCADE) + migration `c9e4a7d2b1f6` (reversibel, op/ned testet, `alembic check` ren).
- `household.py`: invitation via den eksisterende mekanisme (`private_invites.resource_type="household"`, SMS fra ejerens egen telefon), accept (opretter/bruger egen Privat-konto), grænse 5 i alt (låst pr. husstand: to samtidige accepter kan ikke give 6), dobbelt-accept = no-op, kan ikke være i to husstande, ejer fjerner, medlem forlader.
- `subscriptions.entitlements()`: et medlem uden egen plan låner ejerens Familie-rettigheder LIVE (fjernet, forladt, nedgraderet eller opsagt = væk ved næste request; rækken bliver ved nedgradering, så husstanden er «sat på pause»). Et medlem med egen plan bruger sin egen.
- **Opkaldskvote = pr. husstand.** Planbeskrivelsen er «25 opkald om måneden» for planen (Plus: 10 for én person), så de 25 deles af alle, der trækker på husstanden (`calls_used`/`plan_call_index` tæller over `household.quota_workspaces`).
- Isolation: medlemskab giver kun plan-rettigheder, aldrig adgang til data. Ejeren ser kun medlemmernes fornavne.
- Plan-apps for et medlem, der mister rettighederne, følger fix-engineer #2's regel for plan-apps (PC-ENT-02/03 i addons.py), som læser `entitlements()`. Data bevares.
- Endpoints: `GET /privat/household`, `POST /privat/household/invites`, `DELETE /privat/household/members/{id}`, `POST /privat/household/leave`; preview/accept i `invites.py`.
- Web: `components/privat/account-household.tsx` (Husstand-kort på Konto, kun Familie/medlem), invitationssidens husstandsgren i `public.tsx`, `lib/privat/account-api.ts`, i18n `familyHousehold.*` ×8.
- Test: `tests/test_privat_familie.py` (6/6 grønne: rettigheder + isolation, grænse 5, dobbelt-accept, fjernet mister adgang med det samme, nedgradering/opsigelse, fælles kvote).
- Kendt rest: to medlemmer, der godkender et opkald i præcis samme sekund, kan give 26 af 25 (approve låser kun egen profil). Det er ikke rettet, fordi det kræver calls.py, som #2 arbejder i.
- Commit: ingen (qa-lead committer). Med i mellemcommit 451d53b + arbejdskopien.

## Verifikation (udfyldes af verifier)
- Gentest:
- Fejler testen uden rettelsen? ja/nej
- Naboscenarier kørt:
- Dom: closed | reopened

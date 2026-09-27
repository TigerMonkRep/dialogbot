"""Register the two CoRal-TTS candidate voices and their rights records (idempotent).

    python -m scripts.voices_register_coral [--speakers <id_a> <id_b>]

Reads the pinned dataset revision from voice_pipeline/sources/coral_tts.lock.json (written by the importer).
Creates, if missing:
- rights records for code (chatterbox-tts), model weights (ResembleAI/chatterbox) and the dataset
  (CoRal-project/coral-tts) – all with status 'unreviewed'. A person reviews them via the operator API;
  this script never marks anything verified.
- two platform voice profiles in draft (no active version): "CoRal-TTS indtaler A" and "… B". Gender,
  dialect and age stay unknown until someone has listened to the recordings and documented the basis.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import select

from app.core.audit import record_audit
from app.db import get_session_factory
from app.models import VoiceProfile, VoiceRightsRecord

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "voice_pipeline" / "sources" / "coral_tts.lock.json"
SOURCE = ROOT / "voice_pipeline" / "sources" / "coral_tts.json"

RIGHTS = [
    dict(kind="code", subject="chatterbox-tts (Resemble AI) 0.1.7", license="MIT",
         source_url="https://pypi.org/project/chatterbox-tts/0.1.7/", revision="0.1.7",
         allowed_uses="Kode: brug, ændring og distribution efter MIT-licensens vilkår.",
         notes="MIT-licensteksten er læst i pakkens METADATA (PyPI-wheel 0.1.7) den 27/9 2026. Afhængigheder "
               "(torch, transformers, resemble-perth m.fl.) har egne licenser og skal gennemgås før produktion."),
    dict(kind="model", subject="ResembleAI/chatterbox – multilingual vægte (t3_mtl23ls_v2, s3gen, ve)",
         license="Ikke læst", source_url="https://huggingface.co/ResembleAI/chatterbox",
         notes="Modelkortet og vægtenes licens kunne ikke læses: huggingface.co er blokeret i udviklingsmiljøet. "
               "Skal læses fuldt (inkl. anvendelsesbegrænsninger) og revisionen fastlåses, før stemmen kan godkendes. "
               "Modellen påfører et Perth-vandmærke på al genereret lyd; det bevares."),
    dict(kind="dataset", subject="CoRal-project/coral-tts", license="CC0-1.0 (ifølge datasetkortet – ikke verificeret her)",
         source_url="https://huggingface.co/datasets/CoRal-project/coral-tts",
         allowed_uses="Talesyntese (datasettets erklærede formål).",
         notes="To professionelle danske indtalere (en mand, en kvinde, ca. 17 timer hver) ifølge opgavebeskrivelsen af "
               "datasætkortet. Kortet og revisionen skal læses og fastlåses ved import. Det store CoRal-ASR-datasæt "
               "(CoRal-project/coral) må IKKE bruges til talesyntese og indgår ikke. Åbne optagelser giver ikke "
               "Dialogbot eksklusive stemmer."),
]


def main(argv: list[str]) -> int:
    speakers = argv[argv.index("--speakers") + 1: argv.index("--speakers") + 3] if "--speakers" in argv else ["?", "?"]
    lock = json.loads(LOCK.read_text()) if LOCK.exists() else {}
    with get_session_factory()() as db:
        ids = []
        for r in RIGHTS:
            data = dict(r)
            if r["kind"] == "dataset" and lock.get("revision"):
                data["revision"] = lock["revision"]
            rec = db.scalar(select(VoiceRightsRecord).where(VoiceRightsRecord.subject == data["subject"]))
            if rec is None:
                rec = VoiceRightsRecord(**data, status="unreviewed")
                db.add(rec)
                db.flush()
                record_audit(db, workspace_id=None, actor_user_id=None, action="voice_rights.created",
                             object_type="voice_rights_record", object_id=rec.id, after={"subject": rec.subject, "via": "cli"})
            elif data.get("revision") and rec.revision != data["revision"]:
                rec.revision = data["revision"]
            ids.append(str(rec.id))
        for letter, spk in zip("ab", speakers, strict=True):
            slug = f"coral-tts-{letter}"
            if db.scalar(select(VoiceProfile.id).where(VoiceProfile.slug == slug)):
                continue
            p = VoiceProfile(slug=slug, display_name=f"CoRal-TTS indtaler {letter.upper()}", gender="unknown", dialect=None,
                             dialect_basis="Ikke vurderet endnu. Køn, dialekt og alder registreres først, når optagelserne "
                                           "er gennemlyttet, og begrundelsen er skrevet her.",
                             source=f"CoRal-project/coral-tts, speaker_id={spk}, revision={lock.get('revision') or 'ikke fastlåst'}",
                             visibility="platform", sample_text="Hej, du taler med en digital assistent. Hvordan kan jeg hjælpe dig i dag?")
            db.add(p)
            db.flush()
            record_audit(db, workspace_id=None, actor_user_id=None, action="voice.created", object_type="voice_profile",
                         object_id=p.id, after={"slug": slug, "via": "cli"})
        db.commit()
        print(json.dumps({"rights_record_ids": ids}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

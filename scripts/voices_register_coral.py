"""Register the two CoRal-TTS candidate voices and their rights records (idempotent).

    python -m scripts.voices_register_coral [--speakers <id_a> <id_b>]

Reads the pinned dataset revision from voice_pipeline/sources/coral_tts.lock.json (written by the importer).
Creates, if missing:
- rights records for code (chatterbox-tts), model weights (Røst-v3, CoRal-project/roest-v3-chatterbox-500m) and the dataset
  (CoRal-project/coral-tts) – all with status 'unreviewed'. A person reviews them via the operator API;
  this script never marks anything verified.
- two platform voice profiles in draft (no active version): "CoRal-TTS indtaler A" and "… B". Gender,
  dialect and age stay unknown until someone has listened to the recordings and documented the basis.
  Speakers default to the dataset's speaker_id values at the pinned revision: A = "mic", B = "nic".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import select

from app.core.audit import record_audit
from app.db import get_session_factory
from app.models import VoiceProfile, VoiceRightsRecord

SOURCE_URLS = {"code": ["https://github.com/resemble-ai/chatterbox", "https://pypi.org/project/chatterbox-tts/0.1.7/"],
               "model": ["https://huggingface.co/CoRal-project/roest-v3-chatterbox-500m", "https://huggingface.co/ResembleAI/chatterbox"],
               "dataset": ["https://huggingface.co/datasets/CoRal-project/coral-tts"]}
ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "voice_pipeline" / "sources" / "coral_tts.lock.json"
SOURCE = ROOT / "voice_pipeline" / "sources" / "coral_tts.json"

CHATTERBOX_COMMIT = "5de7a54aa4e5e2baadb0182dde554908b48b85c2"
MODEL_REVISION = "7ce205cea6b3b36d9f60f18abb88ff21fa04ea0d"

RIGHTS = [
    dict(kind="code", subject="chatterbox-tts (Resemble AI), GitHub resemble-ai/chatterbox", license="MIT",
         source_url="https://github.com/resemble-ai/chatterbox", revision=CHATTERBOX_COMMIT,
         allowed_uses="Kode: brug, ændring og distribution efter MIT-licensens vilkår.",
         notes="LICENSE-filen (MIT, Copyright (c) 2025 Resemble AI) er læst ved commit 5de7a54 den 27/9 2026. Koden "
               "installeres fra GitHub ved den commit, fordi PyPI 0.1.7 kun kan indlæse V2. Afhængigheder (torch, "
               "transformers, resemble-perth m.fl.) har egne licenser og skal gennemgås før produktion."),
    dict(kind="model", subject="CoRal-project/roest-v3-chatterbox-500m (Røst-v3, dansk Chatterbox)",
         license="Alexandra Instituttets softwarelicens (AI Pubs Open RAIL med brugsbegrænsninger, dansk ret)",
         source_url="https://huggingface.co/CoRal-project/roest-v3-chatterbox-500m", revision=MODEL_REVISION,
         allowed_uses="Kommerciel brug er tilladt efter licensen, men kun inden for brugsbegrænsningerne i Attachment A. "
                      "De skal videregives til Dialogbots kunder.",
         notes="Licensen er læst ved revision 7ce205c den 27/9 2026. KRÆVER JURIDISK GENNEMGANG af Attachment A: 4(c) "
               "oplysning og samtykke før autonom samtale, 3(b) fuldautomatiske bindende forpligtelser (bookinger), 4(b) "
               "efterligning af en persons stemme uden samtykke. Træningsdata: CoRal-TTS, ftspeech, nst-da og nota. "
               "Modelkortet angiver MOS 4,23 fra 20 danske lyttere (10 klip, Mic og Nic). Al lyd får et Perth-vandmærke."),
    dict(kind="dataset", subject="CoRal-project/coral-tts", license="CC0-1.0",
         source_url="https://huggingface.co/datasets/CoRal-project/coral-tts",
         allowed_uses="Talesyntese er datasættets erklærede formål (task_categories: text-to-speech).",
         notes="Datasætkortet er læst ved revision 3dd0718 den 27/9 2026: CC0-1.0, to professionelle danske indtalere "
               "(kvinde og mand, ca. 17 timer hver), optaget af Nota, tekster udvalgt af Alexandra Instituttet. "
               "speaker_id er 'mic' og 'nic'; kortet siger ikke, hvem der er kvinden. Det store CoRal-ASR-datasæt "
               "(CoRal-project/coral) må IKKE bruges til talesyntese og indgår ikke. Åbne optagelser giver ikke "
               "Dialogbot eksklusive stemmer."),
]


def main(argv: list[str]) -> int:
    speakers = argv[argv.index("--speakers") + 1: argv.index("--speakers") + 3] if "--speakers" in argv else ["mic", "nic"]
    lock = json.loads(LOCK.read_text()) if LOCK.exists() else {}
    with get_session_factory()() as db:
        ids = []
        for r in RIGHTS:
            data = dict(r)
            if r["kind"] == "dataset" and lock.get("revision"):
                data["revision"] = lock["revision"]
            rec = db.scalar(select(VoiceRightsRecord).where(VoiceRightsRecord.kind == data["kind"],
                                                            VoiceRightsRecord.source_url.in_(SOURCE_URLS[data["kind"]])))
            if rec is None:
                rec = VoiceRightsRecord(**data, status="unreviewed")
                db.add(rec)
                db.flush()
                record_audit(db, workspace_id=None, actor_user_id=None, action="voice_rights.created",
                             object_type="voice_rights_record", object_id=rec.id, after={"subject": rec.subject, "via": "cli"})
            elif rec.status == "unreviewed":  # refresh what we have read; a reviewed record is never touched
                for k, v in data.items():
                    setattr(rec, k, v)
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

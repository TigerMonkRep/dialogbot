"""Register designed voices built by voice_pipeline.design_voices (idempotent).

    python -m scripts.voices_register_designed /data/designed [--workspace <uuid>]

For every <dir>/<slug>/ with voice.json and conds.pt:
- uploads conds.pt to private storage under the voice's own prefix,
- creates (once) a rights record for the NST dataset (status 'unreviewed'; a person reviews it),
- creates the profile (origin 'designed', description, gender, age of the source speakers, dialect unknown),
- creates a draft version (method 'designed_blend') with the full provenance and runs the automatic checks,
  including the distinctness check. Nothing is approved or activated here.
Existing Røst/Chatterbox code and model rights records are reused by source URL.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from sqlalchemy import select

from app.core.audit import record_audit
from app.db import get_session_factory
from app.models import VoiceProfile, VoiceRightsRecord, VoiceVersion
from app.modules.voices import service, storage

NST = dict(kind="dataset", subject="alexandrainst/nst-da (NST dansk)", license="CC0-1.0",
           source_url="https://huggingface.co/datasets/alexandrainst/nst-da",
           allowed_uses="CC0: ingen ophavsretlige begrænsninger. Bruges kun til designede stemmer, der er blandet af "
                        "mindst 4 personer og har bestået lighedskontrollen; aldrig til at efterligne én person.",
           notes="Datasætkortet angiver CC0-1.0 (læst 27/9 2026). Oplæserne gav samtykke til et talekorpus, ikke til at "
                 "blive en kommerciel stemme. Derfor efterlignes ingen enkeltperson (Røst-licensen 4(b)). Om en blandet "
                 "stemme er uden for 4(b), skal en jurist bekræfte.")


def main(argv: list[str]) -> int:
    root = Path(argv[1])
    with get_session_factory()() as db:
        nst = db.scalar(select(VoiceRightsRecord).where(VoiceRightsRecord.source_url == NST["source_url"]))
        if nst is None:
            nst = VoiceRightsRecord(**NST, status="unreviewed")
            db.add(nst)
            db.flush()
        code = db.scalar(select(VoiceRightsRecord).where(VoiceRightsRecord.kind == "code"))
        model = db.scalar(select(VoiceRightsRecord).where(
            VoiceRightsRecord.source_url == "https://huggingface.co/CoRal-project/roest-v3-chatterbox-500m"))
        rights = [str(r.id) for r in (code, model, nst) if r is not None]
        done = []
        for d in sorted(p for p in root.iterdir() if (p / "voice.json").exists() and (p / "conds.pt").exists()):
            meta = json.loads((d / "voice.json").read_text(encoding="utf-8"))
            data = (d / "conds.pt").read_bytes()
            sha = hashlib.sha256(data).hexdigest()
            if sha != meta["provenance"]["checkpoint_sha256"]:
                raise SystemExit(f"{d.name}: conds.pt does not match voice.json")
            p = db.scalar(select(VoiceProfile).where(VoiceProfile.slug == meta["slug"]))
            if p is None:
                p = VoiceProfile(slug=meta["slug"], display_name=meta["display_name"], gender=meta["gender"],
                                 dialect=None, dialect_basis=meta["dialect_basis"], age_description=meta["age_description"],
                                 timbre=meta["timbre"], origin="designed", description=meta["description"],
                                 source=f"Designet af {len(meta['provenance']['sources'])} personer fra "
                                        f"{meta['provenance']['dataset']}@{meta['provenance']['dataset_revision'][:7]}",
                                 visibility="platform", sample_text=meta["sample_text"])
                db.add(p)
                db.flush()
                record_audit(db, workspace_id=None, actor_user_id=None, action="voice.created", object_type="voice_profile",
                             object_id=p.id, after={"slug": p.slug, "via": "cli", "origin": "designed"})
            if any((v.provenance or {}).get("checkpoint_sha256") == sha
                   for v in db.scalars(select(VoiceVersion).where(VoiceVersion.profile_id == p.id))):
                continue
            key = f"platform/voices/{p.slug}/conds-{sha[:16]}.pt"
            storage.put(key, data, "application/octet-stream")
            n = (db.scalar(select(VoiceVersion.version).where(VoiceVersion.profile_id == p.id)
                           .order_by(VoiceVersion.version.desc()).limit(1)) or 0) + 1
            prov = meta["provenance"]
            v = VoiceVersion(profile_id=p.id, version=n, engine="chatterbox-multilingual", method="designed_blend",
                             model_repo=prov["model"], model_revision=prov["model_revision"], checkpoint_key=key,
                             references=[], settings={}, rights_record_ids=rights, checks={}, provenance=prov,
                             notes=f"Bygget af {prov['tool']}")
            db.add(v)
            db.flush()
            checks = service.run_auto_checks(db, v)
            record_audit(db, workspace_id=None, actor_user_id=None, action="voice.version_created",
                         object_type="voice_profile", object_id=p.id,
                         after={"version": n, "via": "cli", "checks": {k: c.get("status") for k, c in checks.items()}})
            done.append({"slug": p.slug, "version": n, "checks": {k: c.get("status") for k, c in checks.items()}})
        db.commit()
    print(json.dumps(done, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

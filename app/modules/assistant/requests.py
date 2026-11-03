"""«Ønsker»: what a customer asked the assistant for that Dialogbot cannot do yet, so it can be built.

The assistant records one when the model answers "request" (the app cannot do it, or the person explicitly asks for a
feature). A repeat from the same workspace – the same wish in other words – is counted on the open row
(`times_asked`) instead of making a new one. Every new row is mailed to Dialogbot's operators (outbox, Danish) and
listed for them in /app/operator/oensker, where they set a status and a note."""
from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.audit import record_audit
from app.core.auth import WorkspaceContext
from app.models import ASSISTANT_REQUEST_CATEGORIES, AssistantRequest, User

CATEGORY_DA = {"phone": "Telefon", "voice": "Stemme", "knowledge": "Viden", "booking": "Booking", "webchat": "Webchat",
               "campaigns": "Kampagner", "reports": "Rapporter", "integrations": "Integrationer", "account": "Konto og betaling",
               "other": "Andet"}
OPEN = ("new", "planned")
DEDUPE_WINDOW = timedelta(days=180)
SIMILAR = 0.6
# Words that say nothing about the wish itself (Danish and English; the summary is always Danish).
_STOP = set("""at af alle bare de den der det dem du en er et for fra gerne godt har hej hvis hvor hvordan i ikke jeg kan
kunne man med mig min mine må og om op os på skal som så til ud vi vil være vores jer jeres the and for can you please
want would like our with have that this from need""".split())


def _tokens(*texts: str) -> set[str]:
    words = re.findall(r"[a-zæøåäöü0-9]+", " ".join(texts).lower())
    return {w for w in words if len(w) > 2 and w not in _STOP}


def _similar(a: set[str], b: set[str]) -> bool:
    if not a or not b:
        return False
    return len(a & b) / len(a | b) >= SIMILAR


def record(db: OrmSession, ctx: WorkspaceContext, *, text: str, summary: str, category: str, page: str | None,
           request_id: str | None) -> tuple[AssistantRequest, bool]:
    """Create the wish, or count a repeat on an open one from the same workspace. Returns (row, duplicate)."""
    text = re.sub(r"\s+", " ", text).strip()[:2000]
    summary = re.sub(r"\s+", " ", summary or "").strip()[:300] or text[:160]
    category = category if category in ASSISTANT_REQUEST_CATEGORIES else "other"
    mine = _tokens(summary), _tokens(text)
    since = datetime.now(UTC) - DEDUPE_WINDOW
    for row in db.scalars(select(AssistantRequest).where(
            AssistantRequest.workspace_id == ctx.workspace.id, AssistantRequest.status.in_(OPEN),
            AssistantRequest.created_at >= since).order_by(AssistantRequest.created_at.desc()).limit(200).with_for_update()):
        same = row.summary.strip().lower() == summary.lower() or row.text.strip().lower() == text.lower()
        if same or _similar(mine[0], _tokens(row.summary)) or _similar(mine[1], _tokens(row.text)):
            row.times_asked += 1
            row.updated_at = datetime.now(UTC)
            record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="assistant.request_repeated",
                         object_type="assistant_request", object_id=row.id, after={"times_asked": row.times_asked},
                         request_id=request_id)
            return row, True
    row = AssistantRequest(workspace_id=ctx.workspace.id, user_id=ctx.user_id, text=text, page=(page or None) and page[:200],
                           summary=summary, category=category, status="new", admin_note="", times_asked=1)
    db.add(row)
    db.flush()
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="assistant.request_created",
                 object_type="assistant_request", object_id=row.id, after={"summary": summary, "category": category},
                 request_id=request_id)
    _notify(db, ctx, row)
    return row, False


def _notify(db: OrmSession, ctx: WorkspaceContext, row: AssistantRequest) -> None:
    """One mail per operator per new wish, through the outbox (the same e-mail adapter as everything else)."""
    from app.core.outbox import enqueue
    from app.modules.integrations import email_templates as tpl

    operators = db.execute(select(User.id, User.email).where(User.is_platform_operator.is_(True))).all()
    if not operators:
        return
    link = f"{get_settings().frontend_base_url.rstrip('/')}/app/operator/oensker"
    subject = f"Nyt ønske fra {ctx.workspace.name}: {row.summary[:80]}"
    body = (f"{ctx.workspace.name} har bedt assistenten om noget, Dialogbot ikke kan endnu.\n\n"
            f"Kategori: {CATEGORY_DA.get(row.category, row.category)}\n"
            f"Med kundens egne ord: «{row.text[:600]}»\n\n"
            f"Se alle ønsker: {link}")
    mail = tpl.from_plain(subject, body, footer_reason="Du får denne mail, fordi du er Dialogbot-operatør.")
    for uid, email in operators:
        enqueue(db, event_type="email.branded", dedupe_key=f"assistant_request:{row.id}:{uid}",
                payload={"to_email": email, "email": tpl.to_payload(mail)})


def out(row: AssistantRequest, *, workspace_name: str | None = None, user: tuple[str, str] | None = None) -> dict:
    d = {"id": str(row.id), "workspace_id": str(row.workspace_id), "text": row.text, "page": row.page, "summary": row.summary,
         "category": row.category, "status": row.status, "admin_note": row.admin_note, "times_asked": row.times_asked,
         "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat() if row.updated_at else None}
    if workspace_name is not None:
        d["workspace_name"] = workspace_name
    if user is not None:
        d["user"] = {"email": user[0], "name": user[1]}
    return d


def get(db: OrmSession, rid: uuid.UUID) -> AssistantRequest | None:
    return db.get(AssistantRequest, rid)

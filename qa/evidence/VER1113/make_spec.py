import json
SUP="app/modules/support/service.py"; SR="app/modules/support/router.py"; OR="app/modules/support/operator_router.py"
OPS="app/modules/admin/operations.py"; CS="app/modules/customer/service.py"; CR="app/modules/customer/router.py"
WP="app/modules/webchat/public.py"
T_H=["tests/test_support.py","tests/qa/test_qa_H01.py"]
T_M=["tests/test_ops_m03.py","tests/qa/test_qa_M03.py"]
T_E=["tests/test_booking_messages.py","tests/qa/test_qa_integ_E07.py"]
T_W=["tests/qa/test_qa_w04_w09_w13.py"]
spec = {
 "h01_internal_notes_visible": {"edits":[[SUP,'SupportMessage.visibility == "public")','True)']], "tests":T_H},
 "h01_internal_attachment_download": {"edits":[[SR,', SupportMessage.visibility == "public"))','))']], "tests":T_H},
 "h01_no_tenant_filter": {"edits":[[SUP,"select(SupportTicket).where(SupportTicket.workspace_id == workspace_id, SupportTicket.number == number)","select(SupportTicket).where(SupportTicket.number == number)"]], "tests":T_H},
 "h01_reader_may_read": {"edits":[["app/core/auth.py",'"support.read": "staff"','"support.read": "reader"']], "tests":T_H},
 "h01_reader_may_write": {"edits":[["app/core/auth.py",'"support.write": "staff"','"support.write": "reader"']], "tests":T_H},
 "m06_non_operator_allowed": {"edits":[[OR,"from app.modules.voices.operator_router import operator","from app.core.auth import get_current_principal as operator"]], "tests":T_H},
 "m06_internal_note_mails_customer": {"edits":[[OR,'        mailed = svc.notify_customer(db, t, m.id)\n','        mailed = svc.notify_customer(db, t, m.id)\n    if body.visibility == "internal":\n        mailed = svc.notify_customer(db, t, m.id)\n']], "tests":T_H},
 "m03_rerun_done_job": {"edits":[[OPS,'elif ev.status == "done":','elif False:']], "tests":T_M},
 "m03_more_than_one_attempt": {"edits":[[OPS,"ev.max_attempts = ev.attempts + 1","ev.max_attempts = ev.attempts + 5"]], "tests":T_M},
 "m03_no_idempotency_replay": {"edits":[[OPS,"if guard.replay:","if False:",2]], "tests":T_M},
 "m03_blind_calendar_retry_after_timeout": {"edits":[[OPS,'if outcome == "unknown" and not body.confirm_not_created:','if False:']], "tests":T_M},
 "m03_retry_while_suspended": {"edits":[[OPS,"elif is_suspended(db, ev.workspace_id):","elif False:"]], "tests":T_M},
 "m03_worker_ignores_suspension": {"edits":[["app/worker/runner.py","q = q.where(or_(OutboxEvent.workspace_id.is_(None), OutboxEvent.workspace_id.not_in(suspended_ids())))","q = q"]], "tests":T_M},
 "m03_dialler_ignores_suspension": {"edits":[["app/modules/campaigns/service.py",", Campaign.workspace_id.not_in(suspended_ids()))",")"]], "tests":T_M},
 "m03_actions_ignore_suspension": {"edits":[["app/modules/integrations/actions.py","if ws.ops_suspended_at is not None:","if False:"]], "tests":T_M},
 "m03_non_operator_allowed": {"edits":[[OPS,"from app.modules.voices.operator_router import operator","from app.core.auth import get_current_principal as operator"]], "tests":T_M},
 "e07_preview_cross_tenant_booking": {"edits":[["app/modules/bookings/router.py","Booking.id == booking_id, Booking.workspace_id == ws.id","Booking.id == booking_id"]], "tests":T_E},
 "e07_preview_enqueues_mail": {"edits":[["app/modules/bookings/router.py",'    return {"lang": language, "default_lang": default_lang,','    from app.core.outbox import enqueue\n    enqueue(db, event_type="email.branded", dedupe_key=f"e07-preview-{uuid.uuid4()}", workspace_id=ws.id, payload={})\n    db.commit()\n    return {"lang": language, "default_lang": default_lang,']], "tests":T_E},
 "w04_contact_without_code": {"edits":[[WP,"        if verified_at is None:\n","        if False:\n"]], "tests":T_W},
 "w04_unlimited_attempts": {"edits":[[CS,"if v.attempts >= MAX_ATTEMPTS:","if False:"]], "tests":T_W},
 "w04_code_not_bound_to_scope": {"edits":[[CS,"wrong_scope = v is not None and (","wrong_scope = False and ("]], "tests":T_W},
 "w04_code_never_expires": {"edits":[[CS,"if v is None or wrong_scope or v.verified_at is not None or v.expires_at <= now:","if v is None or wrong_scope or v.verified_at is not None:"]], "tests":T_W},
 "w04_no_resend_cooldown": {"edits":[[CS,"if last is not None and now - last < RESEND_AFTER:","if False:"]], "tests":T_W},
 "w04_no_ip_limit": {"edits":[[CS,">= SMS_PER_IP_HOUR",">= 10**6"],[CS,">= SMS_PER_IP_DAY)",">= 10**6)"]], "tests":T_W},
 "w04_no_workspace_limit": {"edits":[[CS,">= SMS_PER_WORKSPACE_HOUR:",">= 10**6:"]], "tests":T_W},
 "w04_code_endpoint_any_origin": {"edits":[[WP,"    _require_frame_origin(origin)\n    s = service.by_key(db, key)\n    conv = service.visitor_conversation(db, s, conversation_id, x_visitor_token)\n    service._require_available(db, s)\n    phone = customer.normalize","    s = service.by_key(db, key)\n    conv = service.visitor_conversation(db, s, conversation_id, x_visitor_token)\n    service._require_available(db, s)\n    phone = customer.normalize"]], "tests":T_W},
 "tok_revoked_still_works": {"edits":[[CS,"if link is None or link.purpose != purpose or link.revoked_at is not None:","if link is None or link.purpose != purpose:"]], "tests":T_W},
 "tok_purpose_not_in_hmac_nor_checked": {"edits":[[CS,'token_hash=_h(f"link:{purpose}", token)','token_hash=_h("link", token)'],[CS,'_h(f"link:{purpose}", token or "")','_h("link", token or "")'],[CS,"if link is None or link.purpose != purpose or link.revoked_at is not None:","if link is None or link.revoked_at is not None:"]], "tests":T_W},
 "tok_never_expires": {"edits":[[CS,"if link.expires_at <= _now():","if False:"]], "tests":T_W},
 "tok_plain_sha_not_hmac": {"edits":[[CS,'return hmac.new(_key(), f"customer-{kind}:{value}".encode(), hashlib.sha256).hexdigest()','return hashlib.sha256(f"customer-{kind}:{value}".encode()).hexdigest()']], "tests":T_W},
 "w13_change_without_code": {"edits":[[CS,"if _booking_phone(b) is not None and not session_valid(db, link, session):","if False:"]], "tests":T_W},
 "w13_session_of_other_link": {"edits":[[CS,"return bool(v and v.link_id == link.id and ","return bool(v and "]], "tests":T_W},
 "w13_no_policy_cutoff": {"edits":[[CS,'if not p["can_change"]:','if False:']], "tests":T_W},
 "w13_calendar_failure_told_done": {"edits":[[CR,'if not calendar.mirror_update(db, ws.id, b) and b.confirmation != "pending":','if (calendar.mirror_update(db, ws.id, b) or True) and False:']], "tests":T_W},
 "w09_optin_removes_staff_dnc": {"edits":[[CS,'elif not opt_out and row is not None and row.source == "customer":','elif not opt_out and row is not None:']], "tests":T_W},
 "w09_view_leaks_note": {"edits":[[CS,'"can_opt_out": phone is not None, "expires_at": link.expires_at.isoformat()}','"can_opt_out": phone is not None, "expires_at": link.expires_at.isoformat(), "note": lead.need_summary}']], "tests":T_W},
}
json.dump(spec, open("/home/claude/ver1113/scripts/mutations.json","w"), indent=1)
print(len(spec))

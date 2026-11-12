"""Every fixed text in Dialogbot's e-mails, per language (app/core/languages.py). Danish is the source.

`t(lang, key, **values)` looks a text up and fills its `{placeholders}`; an unknown language falls back to Danish.
German, French, Italian and Spanish use the formal register (Sie, vous, Lei, usted); the Nordic languages and English
use the ordinary "du"/"you". `tests/test_email_texts.py` checks that every language has every key with the same
placeholders as Danish.

Who gets which language is decided where a mail is queued (see `user_language` and `workspace_language`):
account mails follow the user's own interface language, an invitation the inviting workspace's interface language,
and notifications to a workspace's users each recipient's interface language.
"""
from __future__ import annotations

import uuid

from app.core.languages import DEFAULT, LANGUAGES, normalize

TEXTS: dict[str, dict[str, str]] = {
    # ------------------------------------------------------------------------------------------------------ Danish
    "da": {
        # layout
        "open": "Åbn",
        "regards": "Venlig hilsen",
        "button_fallback": "Virker knappen ikke? Kopiér dette link ind i din browser:",
        "step": "Trin {n}",
        "footer_account": "Du får denne e-mail, fordi du har en konto hos Dialogbot.",
        "company_line": "Dialogbot · CVR-nr. 25632710 · Abildgade 18, 8200 Aarhus",
        "default_subject": "Besked fra Dialogbot",
        "greeting": "Hej {name}",
        # roles
        "role_owner": "ejer", "role_admin": "administrator", "role_staff": "medarbejder", "role_reader": "læser",
        # verify
        "verify_subject": "Bekræft din e-mail hos Dialogbot",
        "verify_preheader": "Ét klik, så er din konto klar.",
        "verify_heading": "Velkommen til Dialogbot",
        "verify_body": "Tak, fordi du har oprettet en konto. Bekræft din e-mailadresse, så kan du komme i gang med at "
                       "sætte din AI-receptionist op.",
        "verify_button": "Bekræft min e-mail",
        "verify_heading_privat": "Velkommen til Dialogbot Privat",
        "verify_body_privat": "Tak, fordi du har oprettet en konto. Bekræft din e-mailadresse, så kan du starte din prøveperiode på Dialogbot Privat.",
        # billing mails (F-PBQ-08) – Privat and Erhverv; de/es/fr/it formal like every mail (F-JP-15)
        "billing_footer": "Du får denne e-mail, fordi du har et abonnement hos Dialogbot.",
        "manage_button": "Se dit abonnement",
        "what_privat": "Dialogbot Privat",
        "what_erhverv": "Dialogbot",
        "receipt_subject": "Kvittering: {amount} er betalt",
        "receipt_heading": "Tak – betalingen er gennemført",
        "receipt_body": "Vi har modtaget {amount} for {what}. Kvitteringen og fakturaen finder du under «Administrér abonnement».",
        "failed_subject": "Betalingen på {amount} gik ikke igennem",
        "failed_heading": "Betalingen gik ikke igennem",
        "failed_body": "Vi kunne ikke trække {amount} for {what}. Opdatér dit betalingskort, så fortsætter alt som før. Der bliver prøvet igen de næste dage.",
        "refund_subject": "Refusion: {amount} er sendt tilbage",
        "refund_heading": "Pengene er på vej tilbage",
        "refund_body": "Vi har refunderet {amount} for {what}. Det tager normalt 5–10 bankdage, før beløbet står på din konto.",
        "trial_subject": "Din prøveperiode slutter om 3 dage",
        "trial_heading": "Prøveperioden slutter {date}",
        "trial_body": "Den {date} går din prøveperiode på {plan} over i et betalt abonnement til {amount}. Vil du ikke fortsætte, så opsig før da – så trækker vi intet.",
        "grace0_subject": "Opdatér betalingskortet – Dialogbot kører videre til og med {date}",
        "grace0_heading": "Abonnementet er ikke betalt lige nu",
        "grace0_body": "Kortet er udløbet eller fjernet, eller betalingen gik ikke igennem. Chat og telefon kører videre til og med {date}. Opdatér betalingskortet, så fortsætter alt som før.",
        "grace1_subject": "Påmindelse: opdatér betalingskortet før {date}",
        "grace1_heading": "Husk at opdatere betalingskortet",
        "grace1_body": "Abonnementet er stadig ikke betalt. Chat og telefon kører videre til og med {date} – derefter stopper de. Opdatér betalingskortet, så fortsætter alt som før.",
        "grace2_subject": "I morgen stopper chat og telefon – opdatér betalingskortet",
        "grace2_heading": "Sidste dag: {date}",
        "grace2_body": "Abonnementet er stadig ikke betalt. Efter {date} svarer chatten ikke længere besøgende, og telefonen stopper. Opdatér betalingskortet i dag, så fortsætter alt som før.",
        "verify_note": "Linket virker i 48 timer. Har du ikke oprettet en konto hos Dialogbot, kan du se bort fra denne "
                       "e-mail.",
        "verify_footer": "Du får denne e-mail, fordi nogen har oprettet en konto hos Dialogbot med din adresse.",
        # reset
        "reset_subject": "Nulstil din adgangskode hos Dialogbot",
        "reset_preheader": "Vælg en ny adgangskode – linket virker i 1 time.",
        "reset_heading": "Nulstil din adgangskode",
        "reset_body": "Vi har fået en anmodning om at nulstille adgangskoden til din Dialogbot-konto. Klik på knappen "
                      "for at vælge en ny.",
        "reset_button": "Vælg ny adgangskode",
        "reset_note": "Linket virker i 1 time og kan kun bruges én gang. Har du ikke bedt om det, kan du se bort fra "
                      "denne e-mail – din adgangskode forbliver uændret.",
        # invitation
        "invitation_subject": "{invited_by} har inviteret dig til {workspace} på Dialogbot",
        "invitation_preheader": "Du er inviteret som {role}.",
        "invitation_heading": "Du er inviteret til {workspace}",
        "invitation_body": "{invited_by} har inviteret dig til {workspace} på Dialogbot som {role}. Som medlem kan du se "
                           "henvendelser, samtaler og opgaver.",
        "invitation_button": "Acceptér invitationen",
        "invitation_note": "Invitationen virker i 72 timer. Har du ikke en konto endnu, opretter du den undervejs.",
        "invitation_footer": "Du får denne e-mail, fordi {invited_by} har inviteret dig til Dialogbot.",
        # new lead
        "lead_someone": "En kunde",
        "lead_subject": "Ny henvendelse: {name}",
        "lead_preheader": "{name} vil gerne kontaktes.",
        "lead_heading": "Ny henvendelse",
        "lead_body": "{name} vil gerne kontaktes af {workspace}.",
        "lead_need": "Behov: {need}",
        "lead_need_missing": "(ikke angivet)",
        "lead_button": "Se henvendelsen",
        "lead_footer": "Du får denne e-mail, fordi du er tilknyttet {workspace} på Dialogbot.",
        # daily report (the mail) and its summary (built in app/modules/reports/service.py)
        "report_preheader": "Gårsdagens henvendelser, samtaler og opgaver.",
        "report_button": "Se hele rapporten",
        "report_footer": "Du får denne e-mail, fordi dagsrapporten er slået til for jeres arbejdsrum. Du kan slå den fra "
                         "under Rapporter.",
        "report_subject": "Dagsrapport {date} – {workspace}",
        "report_title": "Dagsrapport for {workspace} – {date}",
        "report_conversations": "Samtaler: {started} (kundebeskeder: {messages})",
        "report_ai_label": "AI-svar",
        "report_ai": "{ok} ok, {refused} afvist, {error} fejl",
        "report_new_leads": "Nye henvendelser: {n}",
        "report_approved": "Godkendte henvendelser: {n} ({amount} ekskl. moms)",
        "report_amount": "{amount} kr.",
        "report_tasks": "Opgaver: {created} oprettet, {done} løst, {overdue} åbne over frist",
        "report_new_list": "Nye henvendelser:",
        "report_unnamed": "(uden navn)",
        # ambassador programme
        "amb_parent_subject": "{first} vil være ambassadør for Dialogbot – vil du godkende?",
        "amb_parent_preheader": "{first} er under 18, så vi har brug for din godkendelse, før vi udbetaler bonus.",
        "amb_parent_p1": "{ambassador_name} ({ambassador_email}) har meldt sig som ambassadør for Dialogbot. Som "
                         "ambassadør anbefaler man Dialogbot – en dansk AI-receptionist – til virksomheder, man kender, og "
                         "får en bonus, når de bliver betalende kunder.",
        "amb_parent_p2": "Bonussen er {bonus} pr. ny kunde plus {share} af det, kunden betaler, i {months} måneder. Den "
                         "udbetales til {first}s bankkonto som B-indkomst, som vi indberetter til Skattestyrelsen. "
                         "Der trækkes ikke skat.",
        "amb_parent_p3": "Fordi {first} er under 18, udbetaler vi først, når du har godkendt aftalen. {first} kan godt "
                         "dele sit link imens.",
        "amb_parent_p4": "Reglerne {first} har sagt ja til:\n{rules}",
        "amb_parent_button": "Læs og godkend aftalen",
        "amb_parent_note": "Har du spørgsmål, eller vil du ikke godkende, så svar bare på denne e-mail.",
        "amb_parent_footer": "Du får denne e-mail, fordi {ambassador_name} har oplyst dig som forælder eller værge.",
        "amb_approved_subject": "Velkommen som Dialogbot-ambassadør",
        "amb_approved_preheader": "Dit personlige link og din kode {code} er klar.",
        "amb_approved_heading": "Velkommen som ambassadør, {first_name}",
        "amb_approved_p1": "Du er godkendt. Del dit personlige link med virksomheder, du kender:",
        "amb_approved_code": "{link}\nDin kode: {code}",
        "amb_approved_p3": "Rabat, bonus, saldo og færdige tekster ligger på din side. Skriv altid, at det er reklame, og at "
                           "du får bonus – og send kun til folk, du kender.",
        "amb_approved_button": "Gå til min ambassadørside",
        "amb_footer_signed_up": "Du får denne e-mail, fordi du har meldt dig som ambassadør for Dialogbot.",
        "amb_rejected_subject": "Din tilmelding som Dialogbot-ambassadør",
        "amb_rejected_p1": "Tak for din interesse i at blive ambassadør for Dialogbot. Vi kan desværre ikke godkende din "
                           "tilmelding lige nu.",
        "amb_reply": "Har du spørgsmål, så svar bare på denne e-mail.",
        "amb_paid_transfer": "Vi har overført {amount} til din bankkonto{bank}. Pengene er normalt på kontoen inden for "
                             "1–2 bankdage.",
        "amb_paid_bank": ", der slutter på {last4}",
        "amb_paid_statement": "Afregningsbilag nr. {number} ligger på din ambassadørside.",
        "amb_paid_b_income": "Beløbet er B-indkomst, og vi indberetter det til Skattestyrelsen. Der er ikke trukket skat, så "
                             "husk at tjekke din forskudsopgørelse.",
        "amb_paid_thanks": "Tak, fordi du anbefaler Dialogbot!",
        "amb_paid_subject": "Din ambassadørbonus på {amount} er på vej",
        "amb_paid_preheader": "Se afregningsbilaget på din side.",
        "amb_paid_heading": "Hej {first_name}, din bonus er på vej",
        "amb_paid_button": "Se afregningsbilaget",
        "amb_paid_footer": "Du får denne e-mail, fordi du er ambassadør for Dialogbot.",
        # operator: social drafts
        "social_subject_one": "1 opslag venter på din godkendelse",
        "social_subject_many": "{n} opslag venter på din godkendelse",
        "social_preheader": "Godkend dem i operatør-oversigten, før tidspunktet.",
        "social_heading": "Opslag venter på dig",
        "social_body": "Disse kladder er ikke godkendt endnu. Kig på billede og tekst, ret om nødvendigt, og tryk Godkend.",
        "social_button": "Gennemse og godkend",
        "social_note": "Intet bliver postet uden din godkendelse. Er et opslag ikke godkendt {hours} timer efter "
                       "tidspunktet, springes det over.",
        "social_footer": "Du får denne e-mail, fordi du er operatør hos Dialogbot.",
    },
    # ----------------------------------------------------------------------------------------------------- English
    "en": {
        "open": "Open",
        "regards": "Kind regards",
        "button_fallback": "Button not working? Copy this link into your browser:",
        "step": "Step {n}",
        "footer_account": "You are receiving this e-mail because you have an account with Dialogbot.",
        "company_line": "Dialogbot · CVR no. 25632710 · Abildgade 18, 8200 Aarhus, Denmark",
        "default_subject": "Message from Dialogbot",
        "greeting": "Hi {name}",
        "role_owner": "owner", "role_admin": "administrator", "role_staff": "staff member", "role_reader": "reader",
        "verify_subject": "Confirm your e-mail address for Dialogbot",
        "verify_preheader": "One click and your account is ready.",
        "verify_heading": "Welcome to Dialogbot",
        "verify_body": "Thank you for creating an account. Confirm your e-mail address and you can start setting up your "
                       "AI receptionist.",
        "verify_button": "Confirm my e-mail",
        "verify_heading_privat": "Welcome to Dialogbot Privat",
        "verify_body_privat": "Thank you for creating an account. Confirm your e-mail address, and you can start your Dialogbot Privat trial.",
        # billing mails (F-PBQ-08) – Privat and Erhverv; de/es/fr/it formal like every mail (F-JP-15)
        "billing_footer": "You receive this e-mail because you have a subscription with Dialogbot.",
        "manage_button": "See your subscription",
        "what_privat": "Dialogbot Privat",
        "what_erhverv": "Dialogbot",
        "receipt_subject": "Receipt: {amount} paid",
        "receipt_heading": "Thank you – the payment went through",
        "receipt_body": "We have received {amount} for {what}. You find the receipt and the invoice under «Manage subscription».",
        "failed_subject": "The payment of {amount} did not go through",
        "failed_heading": "The payment did not go through",
        "failed_body": "We could not charge {amount} for {what}. Update your payment card and everything continues as before. We will try again over the next days.",
        "refund_subject": "Refund: {amount} sent back",
        "refund_heading": "The money is on its way back",
        "refund_body": "We have refunded {amount} for {what}. It usually takes 5–10 banking days before the amount is in your account.",
        "trial_subject": "Your trial ends in 3 days",
        "trial_heading": "The trial ends on {date}",
        "trial_body": "On {date} your {plan} trial becomes a paid subscription at {amount}. If you don't want to continue, cancel before then – and nothing is charged.",
        "grace0_subject": "Update your payment card – Dialogbot keeps running until {date}",
        "grace0_heading": "Your subscription is not paid right now",
        "grace0_body": "The card has expired or was removed, or the payment did not go through. Chat and phone keep running until and including {date}. Update your payment card and everything continues as before.",
        "grace1_subject": "Reminder: update your payment card before {date}",
        "grace1_heading": "Remember to update your payment card",
        "grace1_body": "The subscription is still not paid. Chat and phone keep running until and including {date} – then they stop. Update your payment card and everything continues as before.",
        "grace2_subject": "Chat and phone stop tomorrow – update your payment card",
        "grace2_heading": "Last day: {date}",
        "grace2_body": "The subscription is still not paid. After {date} the chat no longer answers visitors and the phone stops. Update your payment card today and everything continues as before.",
        "verify_note": "The link is valid for 48 hours. If you did not create an account with Dialogbot, you can ignore "
                       "this e-mail.",
        "verify_footer": "You are receiving this e-mail because someone created a Dialogbot account with your address.",
        "reset_subject": "Reset your Dialogbot password",
        "reset_preheader": "Choose a new password – the link is valid for 1 hour.",
        "reset_heading": "Reset your password",
        "reset_body": "We received a request to reset the password for your Dialogbot account. Click the button to choose "
                      "a new one.",
        "reset_button": "Choose a new password",
        "reset_note": "The link is valid for 1 hour and can only be used once. If you did not request this, you can ignore "
                      "this e-mail – your password stays the same.",
        "invitation_subject": "{invited_by} has invited you to {workspace} on Dialogbot",
        "invitation_preheader": "You have been invited as {role}.",
        "invitation_heading": "You have been invited to {workspace}",
        "invitation_body": "{invited_by} has invited you to {workspace} on Dialogbot as {role}. As a member you can see "
                           "enquiries, conversations and tasks.",
        "invitation_button": "Accept the invitation",
        "invitation_note": "The invitation is valid for 72 hours. If you do not have an account yet, you will create one "
                           "along the way.",
        "invitation_footer": "You are receiving this e-mail because {invited_by} invited you to Dialogbot.",
        "lead_someone": "A customer",
        "lead_subject": "New enquiry: {name}",
        "lead_preheader": "{name} would like to be contacted.",
        "lead_heading": "New enquiry",
        "lead_body": "{name} would like to be contacted by {workspace}.",
        "lead_need": "Needs: {need}",
        "lead_need_missing": "(not specified)",
        "lead_button": "View the enquiry",
        "lead_footer": "You are receiving this e-mail because you are a member of {workspace} on Dialogbot.",
        "report_preheader": "Yesterday's enquiries, conversations and tasks.",
        "report_button": "View the full report",
        "report_footer": "You are receiving this e-mail because the daily report is switched on for your workspace. You "
                         "can switch it off under Reports.",
        "report_subject": "Daily report {date} – {workspace}",
        "report_title": "Daily report for {workspace} – {date}",
        "report_conversations": "Conversations: {started} (customer messages: {messages})",
        "report_ai_label": "AI replies",
        "report_ai": "{ok} ok, {refused} declined, {error} errors",
        "report_new_leads": "New enquiries: {n}",
        "report_approved": "Approved enquiries: {n} ({amount} excl. VAT)",
        "report_amount": "DKK {amount}",
        "report_tasks": "Tasks: {created} created, {done} completed, {overdue} open and overdue",
        "report_new_list": "New enquiries:",
        "report_unnamed": "(no name)",
        "amb_parent_subject": "{first} wants to become a Dialogbot ambassador – will you approve?",
        "amb_parent_preheader": "{first} is under 18, so we need your approval before we pay out any bonus.",
        "amb_parent_p1": "{ambassador_name} ({ambassador_email}) has signed up as an ambassador for Dialogbot. As an "
                         "ambassador, you recommend Dialogbot – a Danish AI receptionist – to businesses you know and "
                         "receive a bonus when they become paying customers.",
        "amb_parent_p2": "The bonus is {bonus} per new customer plus {share} of what the customer pays, for {months} "
                         "months. It is paid to {first}'s bank account as B-income (B-indkomst), which we report to the "
                         "Danish Tax Agency (Skattestyrelsen). No tax is withheld.",
        "amb_parent_p3": "Because {first} is under 18, we only pay out once you have approved the agreement. {first} is "
                         "welcome to share their link in the meantime.",
        "amb_parent_p4": "The rules {first} has agreed to:\n{rules}",
        "amb_parent_button": "Read and approve the agreement",
        "amb_parent_note": "If you have any questions, or do not want to approve, simply reply to this e-mail.",
        "amb_parent_footer": "You are receiving this e-mail because {ambassador_name} gave your address as their parent "
                             "or guardian.",
        "amb_approved_subject": "Welcome as a Dialogbot ambassador",
        "amb_approved_preheader": "Your personal link and your code {code} are ready.",
        "amb_approved_heading": "Welcome as an ambassador, {first_name}",
        "amb_approved_p1": "You have been approved. Share your personal link with businesses you know:",
        "amb_approved_code": "{link}\nYour code: {code}",
        "amb_approved_p3": "Discount, bonus, balance and ready-made texts are on your page. Always say that it is an "
                           "advertisement and that you receive a bonus – and only send it to people you know.",
        "amb_approved_button": "Go to my ambassador page",
        "amb_footer_signed_up": "You are receiving this e-mail because you signed up as a Dialogbot ambassador.",
        "amb_rejected_subject": "Your application as a Dialogbot ambassador",
        "amb_rejected_p1": "Thank you for your interest in becoming a Dialogbot ambassador. Unfortunately, we cannot "
                           "approve your application at the moment.",
        "amb_reply": "If you have any questions, simply reply to this e-mail.",
        "amb_paid_transfer": "We have transferred {amount} to your bank account{bank}. The money usually arrives within "
                             "1–2 banking days.",
        "amb_paid_bank": " ending in {last4}",
        "amb_paid_statement": "Statement no. {number} is on your ambassador page.",
        "amb_paid_b_income": "The amount is B-income (B-indkomst), and we report it to the Danish Tax Agency "
                             "(Skattestyrelsen). No tax has been withheld, so remember to check your preliminary income "
                             "assessment (forskudsopgørelse).",
        "amb_paid_thanks": "Thank you for recommending Dialogbot!",
        "amb_paid_subject": "Your ambassador bonus of {amount} is on its way",
        "amb_paid_preheader": "See the statement on your page.",
        "amb_paid_heading": "Hi {first_name}, your bonus is on its way",
        "amb_paid_button": "View the statement",
        "amb_paid_footer": "You are receiving this e-mail because you are a Dialogbot ambassador.",
        "social_subject_one": "1 post is waiting for your approval",
        "social_subject_many": "{n} posts are waiting for your approval",
        "social_preheader": "Approve them in the operator overview before their time slot.",
        "social_heading": "Posts are waiting for you",
        "social_body": "These drafts have not been approved yet. Check the image and text, edit if needed, and press "
                       "Approve.",
        "social_button": "Review and approve",
        "social_note": "Nothing is posted without your approval. If a post has not been approved {hours} hours after its "
                       "time slot, it is skipped.",
        "social_footer": "You are receiving this e-mail because you are an operator at Dialogbot.",
    },
    # ------------------------------------------------------------------------------------------------------ German
    "de": {
        "open": "Öffnen",
        "regards": "Mit freundlichen Grüßen",
        "button_fallback": "Funktioniert die Schaltfläche nicht? Kopieren Sie diesen Link in Ihren Browser:",
        "step": "Schritt {n}",
        "footer_account": "Sie erhalten diese E-Mail, weil Sie ein Konto bei Dialogbot haben.",
        "company_line": "Dialogbot · CVR-Nr. 25632710 · Abildgade 18, 8200 Aarhus, Dänemark",
        "default_subject": "Nachricht von Dialogbot",
        "greeting": "Hallo {name}",
        "role_owner": "Inhaber", "role_admin": "Administrator", "role_staff": "Mitarbeiter", "role_reader": "Leser",
        "verify_subject": "Bestätigen Sie Ihre E-Mail-Adresse bei Dialogbot",
        "verify_preheader": "Ein Klick, und Ihr Konto ist bereit.",
        "verify_heading": "Willkommen bei Dialogbot",
        "verify_body": "Vielen Dank, dass Sie ein Konto erstellt haben. Bestätigen Sie Ihre E-Mail-Adresse, dann können "
                       "Sie mit der Einrichtung Ihrer KI-Rezeption beginnen.",
        "verify_button": "E-Mail-Adresse bestätigen",
        "verify_heading_privat": "Willkommen bei Dialogbot Privat",
        "verify_body_privat": "Vielen Dank, dass Sie ein Konto erstellt haben. Bestätigen Sie Ihre E-Mail-Adresse, dann können "
                              "Sie Ihre Testphase von Dialogbot Privat starten.",
        # billing mails (F-PBQ-08) – Privat and Erhverv; de/es/fr/it formal like every mail (F-JP-15)
        "billing_footer": "Sie erhalten diese E-Mail, weil Sie ein Abonnement bei Dialogbot haben.",
        "manage_button": "Abonnement ansehen",
        "what_privat": "Dialogbot Privat",
        "what_erhverv": "Dialogbot",
        "receipt_subject": "Beleg: {amount} bezahlt",
        "receipt_heading": "Danke – die Zahlung ist eingegangen",
        "receipt_body": "Wir haben {amount} für {what} erhalten. Beleg und Rechnung finden Sie unter «Abonnement verwalten».",
        "failed_subject": "Die Zahlung von {amount} ist fehlgeschlagen",
        "failed_heading": "Die Zahlung ist fehlgeschlagen",
        "failed_body": "Wir konnten {amount} für {what} nicht abbuchen. Aktualisieren Sie Ihre Zahlungskarte, dann läuft alles weiter wie bisher. Wir versuchen es in den nächsten Tagen erneut.",
        "refund_subject": "Erstattung: {amount} zurückgezahlt",
        "refund_heading": "Das Geld ist auf dem Weg zurück",
        "refund_body": "Wir haben {amount} für {what} erstattet. Es dauert normalerweise 5–10 Bankarbeitstage, bis der Betrag auf Ihrem Konto ist.",
        "trial_subject": "Ihre Testphase endet in 3 Tagen",
        "trial_heading": "Die Testphase endet am {date}",
        "trial_body": "Am {date} wird Ihre Testphase von {plan} zu einem bezahlten Abonnement für {amount}. Wenn Sie nicht weitermachen möchten, kündigen Sie vorher – dann wird nichts abgebucht.",
        "grace0_subject": "Aktualisieren Sie Ihre Zahlungskarte – Dialogbot läuft bis einschließlich {date} weiter",
        "grace0_heading": "Ihr Abonnement ist derzeit nicht bezahlt",
        "grace0_body": "Die Karte ist abgelaufen oder wurde entfernt, oder die Zahlung ist fehlgeschlagen. Chat und Telefon laufen bis einschließlich {date} weiter. Aktualisieren Sie Ihre Zahlungskarte, dann läuft alles weiter wie bisher.",
        "grace1_subject": "Erinnerung: Aktualisieren Sie Ihre Zahlungskarte vor dem {date}",
        "grace1_heading": "Denken Sie an Ihre Zahlungskarte",
        "grace1_body": "Das Abonnement ist weiterhin nicht bezahlt. Chat und Telefon laufen bis einschließlich {date} weiter – danach stoppen sie. Aktualisieren Sie Ihre Zahlungskarte, dann läuft alles weiter wie bisher.",
        "grace2_subject": "Morgen stoppen Chat und Telefon – aktualisieren Sie Ihre Zahlungskarte",
        "grace2_heading": "Letzter Tag: {date}",
        "grace2_body": "Das Abonnement ist weiterhin nicht bezahlt. Nach dem {date} antwortet der Chat den Besuchern nicht mehr, und das Telefon stoppt. Aktualisieren Sie Ihre Zahlungskarte heute, dann läuft alles weiter wie bisher.",
        "verify_note": "Der Link ist 48 Stunden gültig. Wenn Sie kein Konto bei Dialogbot erstellt haben, können Sie diese "
                       "E-Mail ignorieren.",
        "verify_footer": "Sie erhalten diese E-Mail, weil jemand mit Ihrer Adresse ein Konto bei Dialogbot erstellt hat.",
        "reset_subject": "Setzen Sie Ihr Passwort bei Dialogbot zurück",
        "reset_preheader": "Wählen Sie ein neues Passwort – der Link ist 1 Stunde gültig.",
        "reset_heading": "Passwort zurücksetzen",
        "reset_body": "Wir haben eine Anfrage erhalten, das Passwort für Ihr Dialogbot-Konto zurückzusetzen. Klicken Sie "
                      "auf die Schaltfläche, um ein neues zu wählen.",
        "reset_button": "Neues Passwort wählen",
        "reset_note": "Der Link ist 1 Stunde gültig und kann nur einmal verwendet werden. Wenn Sie dies nicht angefordert "
                      "haben, können Sie diese E-Mail ignorieren – Ihr Passwort bleibt unverändert.",
        "invitation_subject": "{invited_by} hat Sie zu {workspace} auf Dialogbot eingeladen",
        "invitation_preheader": "Sie sind als {role} eingeladen.",
        "invitation_heading": "Sie sind zu {workspace} eingeladen",
        "invitation_body": "{invited_by} hat Sie als {role} zu {workspace} auf Dialogbot eingeladen. Als Mitglied sehen "
                           "Sie Anfragen, Gespräche und Aufgaben.",
        "invitation_button": "Einladung annehmen",
        "invitation_note": "Die Einladung ist 72 Stunden gültig. Wenn Sie noch kein Konto haben, erstellen Sie es dabei.",
        "invitation_footer": "Sie erhalten diese E-Mail, weil {invited_by} Sie zu Dialogbot eingeladen hat.",
        "lead_someone": "Ein Kunde",
        "lead_subject": "Neue Anfrage: {name}",
        "lead_preheader": "{name} möchte kontaktiert werden.",
        "lead_heading": "Neue Anfrage",
        "lead_body": "{name} möchte von {workspace} kontaktiert werden.",
        "lead_need": "Anliegen: {need}",
        "lead_need_missing": "(nicht angegeben)",
        "lead_button": "Anfrage ansehen",
        "lead_footer": "Sie erhalten diese E-Mail, weil Sie {workspace} auf Dialogbot angehören.",
        "report_preheader": "Die Anfragen, Gespräche und Aufgaben von gestern.",
        "report_button": "Ganzen Bericht ansehen",
        "report_footer": "Sie erhalten diese E-Mail, weil der Tagesbericht für Ihren Arbeitsbereich aktiviert ist. Sie "
                         "können ihn unter Berichte deaktivieren.",
        "report_subject": "Tagesbericht {date} – {workspace}",
        "report_title": "Tagesbericht für {workspace} – {date}",
        "report_conversations": "Gespräche: {started} (Kundennachrichten: {messages})",
        "report_ai_label": "KI-Antworten",
        "report_ai": "{ok} ok, {refused} abgelehnt, {error} Fehler",
        "report_new_leads": "Neue Anfragen: {n}",
        "report_approved": "Genehmigte Anfragen: {n} ({amount} zzgl. MwSt.)",
        "report_amount": "{amount} DKK",
        "report_tasks": "Aufgaben: {created} erstellt, {done} erledigt, {overdue} offen und überfällig",
        "report_new_list": "Neue Anfragen:",
        "report_unnamed": "(ohne Namen)",
        "amb_parent_subject": "{first} möchte Botschafter für Dialogbot werden – stimmen Sie zu?",
        "amb_parent_preheader": "{first} ist unter 18, daher benötigen wir Ihre Zustimmung, bevor wir einen Bonus "
                                "auszahlen.",
        "amb_parent_p1": "{ambassador_name} ({ambassador_email}) hat sich als Botschafter für Dialogbot angemeldet. Als "
                         "Botschafter empfiehlt man Dialogbot – eine dänische KI-Rezeption – Unternehmen, die man kennt, "
                         "und erhält einen Bonus, wenn sie zahlende Kunden werden.",
        "amb_parent_p2": "Der Bonus beträgt {bonus} pro Neukunde plus {share} dessen, was der Kunde zahlt, für {months} "
                         "Monate. Er wird als B-Einkommen (B-indkomst) auf das Bankkonto von {first} ausgezahlt, das wir "
                         "der dänischen Steuerbehörde (Skattestyrelsen) melden. Es wird keine Steuer einbehalten.",
        "amb_parent_p3": "Da {first} unter 18 ist, zahlen wir erst aus, wenn Sie der Vereinbarung zugestimmt haben. {first} "
                         "kann den eigenen Link in der Zwischenzeit bereits teilen.",
        "amb_parent_p4": "Die Regeln, denen {first} zugestimmt hat:\n{rules}",
        "amb_parent_button": "Vereinbarung lesen und zustimmen",
        "amb_parent_note": "Wenn Sie Fragen haben oder nicht zustimmen möchten, antworten Sie einfach auf diese E-Mail.",
        "amb_parent_footer": "Sie erhalten diese E-Mail, weil {ambassador_name} Sie als Elternteil oder Vormund angegeben "
                             "hat.",
        "amb_approved_subject": "Willkommen als Dialogbot-Botschafter",
        "amb_approved_preheader": "Ihr persönlicher Link und Ihr Code {code} sind bereit.",
        "amb_approved_heading": "Willkommen als Botschafter, {first_name}",
        "amb_approved_p1": "Sie sind freigeschaltet. Teilen Sie Ihren persönlichen Link mit Unternehmen, die Sie kennen:",
        "amb_approved_code": "{link}\nIhr Code: {code}",
        "amb_approved_p3": "Rabatt, Bonus, Guthaben und fertige Texte finden Sie auf Ihrer Seite. Weisen Sie immer darauf "
                           "hin, dass es sich um Werbung handelt und dass Sie einen Bonus erhalten – und senden Sie nur an "
                           "Personen, die Sie kennen.",
        "amb_approved_button": "Zu meiner Botschafterseite",
        "amb_footer_signed_up": "Sie erhalten diese E-Mail, weil Sie sich als Botschafter für Dialogbot angemeldet haben.",
        "amb_rejected_subject": "Ihre Anmeldung als Dialogbot-Botschafter",
        "amb_rejected_p1": "Vielen Dank für Ihr Interesse, Botschafter für Dialogbot zu werden. Leider können wir Ihre "
                           "Anmeldung derzeit nicht annehmen.",
        "amb_reply": "Wenn Sie Fragen haben, antworten Sie einfach auf diese E-Mail.",
        "amb_paid_transfer": "Wir haben {amount} auf Ihr Bankkonto{bank} überwiesen. Das Geld ist in der Regel innerhalb "
                             "von 1–2 Bankarbeitstagen auf dem Konto.",
        "amb_paid_bank": " mit der Endung {last4}",
        "amb_paid_statement": "Abrechnung Nr. {number} finden Sie auf Ihrer Botschafterseite.",
        "amb_paid_b_income": "Der Betrag ist B-Einkommen (B-indkomst), und wir melden ihn der dänischen Steuerbehörde "
                             "(Skattestyrelsen). Es wurde keine Steuer einbehalten. Denken Sie daher daran, Ihre "
                             "vorläufige Steuerveranlagung (forskudsopgørelse) zu prüfen.",
        "amb_paid_thanks": "Vielen Dank, dass Sie Dialogbot empfehlen!",
        "amb_paid_subject": "Ihr Botschafterbonus von {amount} ist unterwegs",
        "amb_paid_preheader": "Die Abrechnung finden Sie auf Ihrer Seite.",
        "amb_paid_heading": "Hallo {first_name}, Ihr Bonus ist unterwegs",
        "amb_paid_button": "Abrechnung ansehen",
        "amb_paid_footer": "Sie erhalten diese E-Mail, weil Sie Botschafter für Dialogbot sind.",
        "social_subject_one": "1 Beitrag wartet auf Ihre Freigabe",
        "social_subject_many": "{n} Beiträge warten auf Ihre Freigabe",
        "social_preheader": "Geben Sie sie vor dem geplanten Zeitpunkt in der Operator-Übersicht frei.",
        "social_heading": "Beiträge warten auf Sie",
        "social_body": "Diese Entwürfe sind noch nicht freigegeben. Prüfen Sie Bild und Text, korrigieren Sie bei Bedarf "
                       "und klicken Sie auf Freigeben.",
        "social_button": "Prüfen und freigeben",
        "social_note": "Ohne Ihre Freigabe wird nichts veröffentlicht. Ist ein Beitrag {hours} Stunden nach dem geplanten "
                       "Zeitpunkt nicht freigegeben, wird er übersprungen.",
        "social_footer": "Sie erhalten diese E-Mail, weil Sie Operator bei Dialogbot sind.",
    },
    # ----------------------------------------------------------------------------------------------------- Spanish
    "es": {
        "open": "Abrir",
        "regards": "Saludos cordiales",
        "button_fallback": "¿No funciona el botón? Copie este enlace en su navegador:",
        "step": "Paso {n}",
        "footer_account": "Recibe este correo electrónico porque tiene una cuenta en Dialogbot.",
        "company_line": "Dialogbot · CVR n.º 25632710 · Abildgade 18, 8200 Aarhus, Dinamarca",
        "default_subject": "Mensaje de Dialogbot",
        "greeting": "Hola, {name}",
        "role_owner": "propietario", "role_admin": "administrador", "role_staff": "empleado", "role_reader": "lector",
        "verify_subject": "Confirme su correo electrónico en Dialogbot",
        "verify_preheader": "Un clic y su cuenta estará lista.",
        "verify_heading": "Bienvenido a Dialogbot",
        "verify_body": "Gracias por crear una cuenta. Confirme su dirección de correo electrónico y podrá empezar a "
                       "configurar su recepcionista con IA.",
        "verify_button": "Confirmar mi correo",
        "verify_heading_privat": "Bienvenido a Dialogbot Privat",
        "verify_body_privat": "Gracias por crear una cuenta. Confirme su dirección de correo electrónico y podrá empezar su "
                              "prueba de Dialogbot Privat.",
        # billing mails (F-PBQ-08) – Privat and Erhverv; de/es/fr/it formal like every mail (F-JP-15)
        "billing_footer": "Recibe este correo porque tiene una suscripción con Dialogbot.",
        "manage_button": "Ver su suscripción",
        "what_privat": "Dialogbot Privat",
        "what_erhverv": "Dialogbot",
        "receipt_subject": "Recibo: {amount} pagado",
        "receipt_heading": "Gracias: el pago se ha realizado",
        "receipt_body": "Hemos recibido {amount} por {what}. El recibo y la factura están en «Gestionar suscripción».",
        "failed_subject": "El pago de {amount} no se ha realizado",
        "failed_heading": "El pago no se ha realizado",
        "failed_body": "No pudimos cobrar {amount} por {what}. Actualice su tarjeta de pago y todo seguirá igual. Lo intentaremos de nuevo en los próximos días.",
        "refund_subject": "Reembolso: {amount} devuelto",
        "refund_heading": "El dinero está de vuelta en camino",
        "refund_body": "Hemos reembolsado {amount} por {what}. Normalmente tarda entre 5 y 10 días hábiles en aparecer en su cuenta.",
        "trial_subject": "Su prueba termina en 3 días",
        "trial_heading": "La prueba termina el {date}",
        "trial_body": "El {date} su prueba de {plan} pasa a ser una suscripción de pago por {amount}. Si no desea continuar, cancele antes y no se cobrará nada.",
        "grace0_subject": "Actualice su tarjeta de pago: Dialogbot sigue funcionando hasta el {date} inclusive",
        "grace0_heading": "Su suscripción no está pagada ahora mismo",
        "grace0_body": "La tarjeta ha caducado o se ha eliminado, o el pago no se ha realizado. El chat y el teléfono siguen funcionando hasta el {date} inclusive. Actualice su tarjeta de pago y todo seguirá igual.",
        "grace1_subject": "Recordatorio: actualice su tarjeta de pago antes del {date}",
        "grace1_heading": "Recuerde actualizar su tarjeta de pago",
        "grace1_body": "La suscripción sigue sin pagarse. El chat y el teléfono siguen funcionando hasta el {date} inclusive; después se detienen. Actualice su tarjeta de pago y todo seguirá igual.",
        "grace2_subject": "Mañana se detienen el chat y el teléfono: actualice su tarjeta de pago",
        "grace2_heading": "Último día: {date}",
        "grace2_body": "La suscripción sigue sin pagarse. Después del {date}, el chat dejará de responder a los visitantes y el teléfono se detendrá. Actualice hoy su tarjeta de pago y todo seguirá igual.",
        "verify_note": "El enlace es válido durante 48 horas. Si no ha creado una cuenta en Dialogbot, puede ignorar este "
                       "correo.",
        "verify_footer": "Recibe este correo electrónico porque alguien ha creado una cuenta en Dialogbot con su dirección.",
        "reset_subject": "Restablezca su contraseña de Dialogbot",
        "reset_preheader": "Elija una nueva contraseña: el enlace es válido durante 1 hora.",
        "reset_heading": "Restablecer su contraseña",
        "reset_body": "Hemos recibido una solicitud para restablecer la contraseña de su cuenta de Dialogbot. Haga clic en "
                      "el botón para elegir una nueva.",
        "reset_button": "Elegir nueva contraseña",
        "reset_note": "El enlace es válido durante 1 hora y solo puede usarse una vez. Si no lo ha solicitado, puede "
                      "ignorar este correo: su contraseña no cambiará.",
        "invitation_subject": "{invited_by} le ha invitado a {workspace} en Dialogbot",
        "invitation_preheader": "Ha sido invitado como {role}.",
        "invitation_heading": "Ha sido invitado a {workspace}",
        "invitation_body": "{invited_by} le ha invitado a {workspace} en Dialogbot como {role}. Como miembro, podrá ver "
                           "solicitudes, conversaciones y tareas.",
        "invitation_button": "Aceptar la invitación",
        "invitation_note": "La invitación es válida durante 72 horas. Si todavía no tiene una cuenta, la creará durante el "
                           "proceso.",
        "invitation_footer": "Recibe este correo electrónico porque {invited_by} le ha invitado a Dialogbot.",
        "lead_someone": "Un cliente",
        "lead_subject": "Nueva solicitud: {name}",
        "lead_preheader": "{name} desea que le contacten.",
        "lead_heading": "Nueva solicitud",
        "lead_body": "{name} desea que {workspace} se ponga en contacto.",
        "lead_need": "Necesidad: {need}",
        "lead_need_missing": "(no indicada)",
        "lead_button": "Ver la solicitud",
        "lead_footer": "Recibe este correo electrónico porque está vinculado a {workspace} en Dialogbot.",
        "report_preheader": "Las solicitudes, conversaciones y tareas de ayer.",
        "report_button": "Ver el informe completo",
        "report_footer": "Recibe este correo electrónico porque el informe diario está activado para su espacio de "
                         "trabajo. Puede desactivarlo en Informes.",
        "report_subject": "Informe diario {date} – {workspace}",
        "report_title": "Informe diario de {workspace} – {date}",
        "report_conversations": "Conversaciones: {started} (mensajes de clientes: {messages})",
        "report_ai_label": "Respuestas de IA",
        "report_ai": "{ok} correctas, {refused} rechazadas, {error} errores",
        "report_new_leads": "Nuevas solicitudes: {n}",
        "report_approved": "Solicitudes aprobadas: {n} ({amount} sin IVA)",
        "report_amount": "{amount} DKK",
        "report_tasks": "Tareas: {created} creadas, {done} completadas, {overdue} abiertas y vencidas",
        "report_new_list": "Nuevas solicitudes:",
        "report_unnamed": "(sin nombre)",
        "amb_parent_subject": "{first} quiere ser embajador de Dialogbot: ¿da usted su aprobación?",
        "amb_parent_preheader": "{first} es menor de 18 años, por lo que necesitamos su aprobación antes de pagar ninguna "
                                "bonificación.",
        "amb_parent_p1": "{ambassador_name} ({ambassador_email}) se ha inscrito como embajador de Dialogbot. Como "
                         "embajador, se recomienda Dialogbot –una recepcionista con IA danesa– a empresas conocidas y se "
                         "recibe una bonificación cuando se convierten en clientes de pago.",
        "amb_parent_p2": "La bonificación es de {bonus} por cada cliente nuevo más el {share} de lo que paga el cliente "
                         "durante {months} meses. Se abona en la cuenta bancaria de {first} como ingreso B (B-indkomst), "
                         "que declaramos a la Agencia Tributaria danesa (Skattestyrelsen). No se practica retención.",
        "amb_parent_p3": "Como {first} es menor de 18 años, solo pagaremos cuando usted haya aprobado el acuerdo. Mientras "
                         "tanto, {first} ya puede compartir su enlace.",
        "amb_parent_p4": "Las normas que {first} ha aceptado:\n{rules}",
        "amb_parent_button": "Leer y aprobar el acuerdo",
        "amb_parent_note": "Si tiene alguna pregunta o no desea dar su aprobación, simplemente responda a este correo.",
        "amb_parent_footer": "Recibe este correo electrónico porque {ambassador_name} le ha indicado como padre, madre o "
                             "tutor.",
        "amb_approved_subject": "Bienvenido como embajador de Dialogbot",
        "amb_approved_preheader": "Su enlace personal y su código {code} ya están listos.",
        "amb_approved_heading": "Bienvenido como embajador, {first_name}",
        "amb_approved_p1": "Su inscripción ha sido aprobada. Comparta su enlace personal con empresas que conozca:",
        "amb_approved_code": "{link}\nSu código: {code}",
        "amb_approved_p3": "El descuento, la bonificación, el saldo y los textos preparados están en su página. Indique "
                           "siempre que se trata de publicidad y que recibe una bonificación, y envíelo solo a personas "
                           "que conozca.",
        "amb_approved_button": "Ir a mi página de embajador",
        "amb_footer_signed_up": "Recibe este correo electrónico porque se ha inscrito como embajador de Dialogbot.",
        "amb_rejected_subject": "Su inscripción como embajador de Dialogbot",
        "amb_rejected_p1": "Gracias por su interés en ser embajador de Dialogbot. Lamentablemente, no podemos aprobar su "
                           "inscripción en este momento.",
        "amb_reply": "Si tiene alguna pregunta, simplemente responda a este correo.",
        "amb_paid_transfer": "Hemos transferido {amount} a su cuenta bancaria{bank}. Normalmente, el dinero llega en un "
                             "plazo de 1–2 días hábiles.",
        "amb_paid_bank": " que termina en {last4}",
        "amb_paid_statement": "La liquidación n.º {number} está disponible en su página de embajador.",
        "amb_paid_b_income": "El importe es un ingreso B (B-indkomst) y lo declaramos a la Agencia Tributaria danesa "
                             "(Skattestyrelsen). No se ha practicado retención, así que recuerde revisar su estimación "
                             "fiscal anticipada (forskudsopgørelse).",
        "amb_paid_thanks": "¡Gracias por recomendar Dialogbot!",
        "amb_paid_subject": "Su bonificación de embajador de {amount} está en camino",
        "amb_paid_preheader": "Consulte la liquidación en su página.",
        "amb_paid_heading": "Hola, {first_name}: su bonificación está en camino",
        "amb_paid_button": "Ver la liquidación",
        "amb_paid_footer": "Recibe este correo electrónico porque es embajador de Dialogbot.",
        "social_subject_one": "1 publicación espera su aprobación",
        "social_subject_many": "{n} publicaciones esperan su aprobación",
        "social_preheader": "Apruébelas en el panel de operador antes de la hora prevista.",
        "social_heading": "Hay publicaciones esperándole",
        "social_body": "Estos borradores aún no se han aprobado. Revise la imagen y el texto, corríjalos si es necesario y "
                       "pulse Aprobar.",
        "social_button": "Revisar y aprobar",
        "social_note": "No se publica nada sin su aprobación. Si una publicación no se ha aprobado {hours} horas después de "
                       "la hora prevista, se omite.",
        "social_footer": "Recibe este correo electrónico porque es operador en Dialogbot.",
    },
    # ------------------------------------------------------------------------------------------------------ French
    "fr": {
        "open": "Ouvrir",
        "regards": "Cordialement",
        "button_fallback": "Le bouton ne fonctionne pas ? Copiez ce lien dans votre navigateur :",
        "step": "Étape {n}",
        "footer_account": "Vous recevez cet e-mail parce que vous avez un compte Dialogbot.",
        "company_line": "Dialogbot · n° CVR 25632710 · Abildgade 18, 8200 Aarhus, Danemark",
        "default_subject": "Message de Dialogbot",
        "greeting": "Bonjour {name}",
        "role_owner": "propriétaire", "role_admin": "administrateur", "role_staff": "collaborateur", "role_reader": "lecteur",
        "verify_subject": "Confirmez votre adresse e-mail chez Dialogbot",
        "verify_preheader": "Un clic, et votre compte est prêt.",
        "verify_heading": "Bienvenue chez Dialogbot",
        "verify_body": "Merci d'avoir créé un compte. Confirmez votre adresse e-mail pour commencer à configurer votre "
                       "réceptionniste IA.",
        "verify_button": "Confirmer mon adresse e-mail",
        "verify_heading_privat": "Bienvenue sur Dialogbot Privat",
        "verify_body_privat": "Merci d'avoir créé un compte. Confirmez votre adresse e-mail pour commencer votre essai de "
                              "Dialogbot Privat.",
        # billing mails (F-PBQ-08) – Privat and Erhverv; de/es/fr/it formal like every mail (F-JP-15)
        "billing_footer": "Vous recevez cet e-mail parce que vous avez un abonnement chez Dialogbot.",
        "manage_button": "Voir votre abonnement",
        "what_privat": "Dialogbot Privat",
        "what_erhverv": "Dialogbot",
        "receipt_subject": "Reçu : {amount} payé",
        "receipt_heading": "Merci – le paiement est passé",
        "receipt_body": "Nous avons reçu {amount} pour {what}. Le reçu et la facture se trouvent sous « Gérer l'abonnement ».",
        "failed_subject": "Le paiement de {amount} n'est pas passé",
        "failed_heading": "Le paiement n'est pas passé",
        "failed_body": "Nous n'avons pas pu prélever {amount} pour {what}. Mettez à jour votre carte de paiement et tout continue comme avant. Nous réessaierons dans les prochains jours.",
        "refund_subject": "Remboursement : {amount} renvoyé",
        "refund_heading": "L'argent est en route",
        "refund_body": "Nous avons remboursé {amount} pour {what}. Il faut généralement 5 à 10 jours ouvrables avant que le montant apparaisse sur votre compte.",
        "trial_subject": "Votre essai se termine dans 3 jours",
        "trial_heading": "L'essai se termine le {date}",
        "trial_body": "Le {date}, votre essai de {plan} devient un abonnement payant à {amount}. Si vous ne souhaitez pas continuer, résiliez avant – et rien ne sera prélevé.",
        "grace0_subject": "Mettez à jour votre carte de paiement – Dialogbot continue jusqu'au {date} inclus",
        "grace0_heading": "Votre abonnement n'est pas payé pour le moment",
        "grace0_body": "La carte a expiré ou a été supprimée, ou le paiement n'est pas passé. Le chat et le téléphone continuent jusqu'au {date} inclus. Mettez à jour votre carte de paiement et tout continue comme avant.",
        "grace1_subject": "Rappel : mettez à jour votre carte de paiement avant le {date}",
        "grace1_heading": "Pensez à mettre à jour votre carte de paiement",
        "grace1_body": "L'abonnement n'est toujours pas payé. Le chat et le téléphone continuent jusqu'au {date} inclus, puis s'arrêtent. Mettez à jour votre carte de paiement et tout continue comme avant.",
        "grace2_subject": "Demain, le chat et le téléphone s'arrêtent – mettez à jour votre carte de paiement",
        "grace2_heading": "Dernier jour : {date}",
        "grace2_body": "L'abonnement n'est toujours pas payé. Après le {date}, le chat ne répond plus aux visiteurs et le téléphone s'arrête. Mettez à jour votre carte de paiement aujourd'hui et tout continue comme avant.",
        "verify_note": "Le lien est valable 48 heures. Si vous n'avez pas créé de compte chez Dialogbot, vous pouvez "
                       "ignorer cet e-mail.",
        "verify_footer": "Vous recevez cet e-mail parce que quelqu'un a créé un compte Dialogbot avec votre adresse.",
        "reset_subject": "Réinitialisez votre mot de passe Dialogbot",
        "reset_preheader": "Choisissez un nouveau mot de passe – le lien est valable 1 heure.",
        "reset_heading": "Réinitialiser votre mot de passe",
        "reset_body": "Nous avons reçu une demande de réinitialisation du mot de passe de votre compte Dialogbot. Cliquez "
                      "sur le bouton pour en choisir un nouveau.",
        "reset_button": "Choisir un nouveau mot de passe",
        "reset_note": "Le lien est valable 1 heure et ne peut être utilisé qu'une seule fois. Si vous n'avez pas fait "
                      "cette demande, vous pouvez ignorer cet e-mail – votre mot de passe reste inchangé.",
        "invitation_subject": "{invited_by} vous a invité à rejoindre {workspace} sur Dialogbot",
        "invitation_preheader": "Vous êtes invité en tant que {role}.",
        "invitation_heading": "Vous êtes invité à rejoindre {workspace}",
        "invitation_body": "{invited_by} vous a invité à rejoindre {workspace} sur Dialogbot en tant que {role}. En tant "
                           "que membre, vous pouvez consulter les demandes, les conversations et les tâches.",
        "invitation_button": "Accepter l'invitation",
        "invitation_note": "L'invitation est valable 72 heures. Si vous n'avez pas encore de compte, vous le créerez en "
                           "chemin.",
        "invitation_footer": "Vous recevez cet e-mail parce que {invited_by} vous a invité sur Dialogbot.",
        "lead_someone": "Un client",
        "lead_subject": "Nouvelle demande : {name}",
        "lead_preheader": "{name} souhaite être contacté.",
        "lead_heading": "Nouvelle demande",
        "lead_body": "{name} souhaite être contacté par {workspace}.",
        "lead_need": "Besoin : {need}",
        "lead_need_missing": "(non précisé)",
        "lead_button": "Voir la demande",
        "lead_footer": "Vous recevez cet e-mail parce que vous êtes rattaché à {workspace} sur Dialogbot.",
        "report_preheader": "Les demandes, conversations et tâches d'hier.",
        "report_button": "Voir le rapport complet",
        "report_footer": "Vous recevez cet e-mail parce que le rapport quotidien est activé pour votre espace de travail. "
                         "Vous pouvez le désactiver dans Rapports.",
        "report_subject": "Rapport quotidien {date} – {workspace}",
        "report_title": "Rapport quotidien de {workspace} – {date}",
        "report_conversations": "Conversations : {started} (messages clients : {messages})",
        "report_ai_label": "Réponses IA",
        "report_ai": "{ok} ok, {refused} refusées, {error} erreurs",
        "report_new_leads": "Nouvelles demandes : {n}",
        "report_approved": "Demandes approuvées : {n} ({amount} HT)",
        "report_amount": "{amount} DKK",
        "report_tasks": "Tâches : {created} créées, {done} terminées, {overdue} ouvertes et en retard",
        "report_new_list": "Nouvelles demandes :",
        "report_unnamed": "(sans nom)",
        "amb_parent_subject": "{first} souhaite devenir ambassadeur de Dialogbot – donnez-vous votre accord ?",
        "amb_parent_preheader": "{first} a moins de 18 ans : nous avons besoin de votre accord avant de verser une prime.",
        "amb_parent_p1": "{ambassador_name} ({ambassador_email}) s'est inscrit comme ambassadeur de Dialogbot. Un "
                         "ambassadeur recommande Dialogbot – une réceptionniste IA danoise – à des entreprises qu'il "
                         "connaît et reçoit une prime lorsqu'elles deviennent clientes payantes.",
        "amb_parent_p2": "La prime est de {bonus} par nouveau client, plus {share} de ce que paie le client pendant "
                         "{months} mois. Elle est versée sur le compte bancaire de {first} en tant que revenu B "
                         "(B-indkomst), que nous déclarons à l'administration fiscale danoise (Skattestyrelsen). Aucun "
                         "impôt n'est prélevé à la source.",
        "amb_parent_p3": "Comme {first} a moins de 18 ans, nous ne versons rien tant que vous n'avez pas approuvé "
                         "l'accord. {first} peut déjà partager son lien en attendant.",
        "amb_parent_p4": "Les règles que {first} a acceptées :\n{rules}",
        "amb_parent_button": "Lire et approuver l'accord",
        "amb_parent_note": "Si vous avez des questions ou ne souhaitez pas donner votre accord, répondez simplement à cet "
                           "e-mail.",
        "amb_parent_footer": "Vous recevez cet e-mail parce que {ambassador_name} vous a indiqué comme parent ou tuteur.",
        "amb_approved_subject": "Bienvenue parmi les ambassadeurs Dialogbot",
        "amb_approved_preheader": "Votre lien personnel et votre code {code} sont prêts.",
        "amb_approved_heading": "Bienvenue parmi les ambassadeurs, {first_name}",
        "amb_approved_p1": "Votre inscription est approuvée. Partagez votre lien personnel avec des entreprises que vous "
                           "connaissez :",
        "amb_approved_code": "{link}\nVotre code : {code}",
        "amb_approved_p3": "Remise, prime, solde et textes prêts à l'emploi se trouvent sur votre page. Indiquez toujours "
                           "qu'il s'agit de publicité et que vous recevez une prime – et n'envoyez qu'à des personnes que "
                           "vous connaissez.",
        "amb_approved_button": "Accéder à ma page ambassadeur",
        "amb_footer_signed_up": "Vous recevez cet e-mail parce que vous vous êtes inscrit comme ambassadeur de Dialogbot.",
        "amb_rejected_subject": "Votre inscription comme ambassadeur Dialogbot",
        "amb_rejected_p1": "Merci de l'intérêt que vous portez au programme d'ambassadeurs Dialogbot. Malheureusement, nous "
                           "ne pouvons pas approuver votre inscription pour le moment.",
        "amb_reply": "Si vous avez des questions, répondez simplement à cet e-mail.",
        "amb_paid_transfer": "Nous avons viré {amount} sur votre compte bancaire{bank}. L'argent arrive généralement sous "
                             "1 à 2 jours ouvrés.",
        "amb_paid_bank": " se terminant par {last4}",
        "amb_paid_statement": "Le relevé n° {number} est disponible sur votre page ambassadeur.",
        "amb_paid_b_income": "Ce montant est un revenu B (B-indkomst) que nous déclarons à l'administration fiscale "
                             "danoise (Skattestyrelsen). Aucun impôt n'a été prélevé : pensez donc à vérifier votre "
                             "estimation fiscale provisoire (forskudsopgørelse).",
        "amb_paid_thanks": "Merci de recommander Dialogbot !",
        "amb_paid_subject": "Votre prime d'ambassadeur de {amount} est en route",
        "amb_paid_preheader": "Consultez le relevé sur votre page.",
        "amb_paid_heading": "Bonjour {first_name}, votre prime est en route",
        "amb_paid_button": "Voir le relevé",
        "amb_paid_footer": "Vous recevez cet e-mail parce que vous êtes ambassadeur de Dialogbot.",
        "social_subject_one": "1 publication attend votre approbation",
        "social_subject_many": "{n} publications attendent votre approbation",
        "social_preheader": "Approuvez-les dans la vue opérateur avant l'heure prévue.",
        "social_heading": "Des publications vous attendent",
        "social_body": "Ces brouillons ne sont pas encore approuvés. Vérifiez l'image et le texte, corrigez si nécessaire, "
                       "puis cliquez sur Approuver.",
        "social_button": "Vérifier et approuver",
        "social_note": "Rien n'est publié sans votre approbation. Une publication non approuvée {hours} heures après "
                       "l'heure prévue est ignorée.",
        "social_footer": "Vous recevez cet e-mail parce que vous êtes opérateur chez Dialogbot.",
    },
    # ----------------------------------------------------------------------------------------------------- Italian
    "it": {
        "open": "Apri",
        "regards": "Cordiali saluti",
        "button_fallback": "Il pulsante non funziona? Copi questo link nel Suo browser:",
        "step": "Passo {n}",
        "footer_account": "Riceve questa e-mail perché ha un account su Dialogbot.",
        "company_line": "Dialogbot · CVR n. 25632710 · Abildgade 18, 8200 Aarhus, Danimarca",
        "default_subject": "Messaggio da Dialogbot",
        "greeting": "Buongiorno {name}",
        "role_owner": "titolare", "role_admin": "amministratore", "role_staff": "collaboratore", "role_reader": "lettore",
        "verify_subject": "Confermi il Suo indirizzo e-mail su Dialogbot",
        "verify_preheader": "Un clic e il Suo account è pronto.",
        "verify_heading": "Benvenuto in Dialogbot",
        "verify_body": "Grazie per aver creato un account. Confermi il Suo indirizzo e-mail per iniziare a configurare il "
                       "Suo receptionist IA.",
        "verify_button": "Conferma il mio indirizzo e-mail",
        "verify_heading_privat": "Benvenuto in Dialogbot Privat",
        "verify_body_privat": "Grazie per aver creato un account. Confermi il Suo indirizzo e-mail per iniziare la prova di "
                              "Dialogbot Privat.",
        # billing mails (F-PBQ-08) – Privat and Erhverv; de/es/fr/it formal like every mail (F-JP-15)
        "billing_footer": "Riceve questa e-mail perché ha un abbonamento con Dialogbot.",
        "manage_button": "Veda il Suo abbonamento",
        "what_privat": "Dialogbot Privat",
        "what_erhverv": "Dialogbot",
        "receipt_subject": "Ricevuta: {amount} pagato",
        "receipt_heading": "Grazie – il pagamento è andato a buon fine",
        "receipt_body": "Abbiamo ricevuto {amount} per {what}. Ricevuta e fattura sono in «Gestisci abbonamento».",
        "failed_subject": "Il pagamento di {amount} non è andato a buon fine",
        "failed_heading": "Il pagamento non è andato a buon fine",
        "failed_body": "Non siamo riusciti ad addebitare {amount} per {what}. Aggiorni la Sua carta di pagamento e tutto continua come prima. Riproveremo nei prossimi giorni.",
        "refund_subject": "Rimborso: {amount} restituito",
        "refund_heading": "Il denaro sta tornando indietro",
        "refund_body": "Abbiamo rimborsato {amount} per {what}. Di solito servono 5–10 giorni lavorativi prima che l'importo sia sul Suo conto.",
        "trial_subject": "La Sua prova termina tra 3 giorni",
        "trial_heading": "La prova termina il {date}",
        "trial_body": "Il {date} la Sua prova di {plan} diventa un abbonamento a pagamento di {amount}. Se non desidera continuare, disdica prima – e non verrà addebitato nulla.",
        "grace0_subject": "Aggiorni la Sua carta di pagamento – Dialogbot continua fino al {date} incluso",
        "grace0_heading": "Il Suo abbonamento non è pagato al momento",
        "grace0_body": "La carta è scaduta o è stata rimossa, oppure il pagamento non è andato a buon fine. Chat e telefono continuano fino al {date} incluso. Aggiorni la Sua carta di pagamento e tutto continua come prima.",
        "grace1_subject": "Promemoria: aggiorni la Sua carta di pagamento entro il {date}",
        "grace1_heading": "Si ricordi di aggiornare la carta di pagamento",
        "grace1_body": "L'abbonamento non è ancora pagato. Chat e telefono continuano fino al {date} incluso, poi si fermano. Aggiorni la Sua carta di pagamento e tutto continua come prima.",
        "grace2_subject": "Domani chat e telefono si fermano – aggiorni la Sua carta di pagamento",
        "grace2_heading": "Ultimo giorno: {date}",
        "grace2_body": "L'abbonamento non è ancora pagato. Dopo il {date} la chat non risponde più ai visitatori e il telefono si ferma. Aggiorni oggi la Sua carta di pagamento e tutto continua come prima.",
        "verify_note": "Il link è valido per 48 ore. Se non ha creato un account su Dialogbot, può ignorare questa e-mail.",
        "verify_footer": "Riceve questa e-mail perché qualcuno ha creato un account su Dialogbot con il Suo indirizzo.",
        "reset_subject": "Reimposti la Sua password di Dialogbot",
        "reset_preheader": "Scelga una nuova password – il link è valido per 1 ora.",
        "reset_heading": "Reimposti la Sua password",
        "reset_body": "Abbiamo ricevuto una richiesta di reimpostazione della password del Suo account Dialogbot. Clicchi "
                      "sul pulsante per sceglierne una nuova.",
        "reset_button": "Scegli una nuova password",
        "reset_note": "Il link è valido per 1 ora e può essere usato una sola volta. Se non ha fatto Lei la richiesta, può "
                      "ignorare questa e-mail – la Sua password resta invariata.",
        "invitation_subject": "{invited_by} La invita a unirsi a {workspace} su Dialogbot",
        "invitation_preheader": "Ruolo proposto: {role}.",
        "invitation_heading": "Un invito per {workspace}",
        "invitation_body": "{invited_by} La invita a unirsi a {workspace} su Dialogbot come {role}. Come membro potrà vedere "
                           "richieste, conversazioni e attività.",
        "invitation_button": "Accetta l'invito",
        "invitation_note": "L'invito è valido per 72 ore. Se non ha ancora un account, lo creerà durante la procedura.",
        "invitation_footer": "Riceve questa e-mail perché {invited_by} La invita a unirsi a Dialogbot.",
        "lead_someone": "Un cliente",
        "lead_subject": "Nuova richiesta: {name}",
        "lead_preheader": "{name} desidera essere ricontattato.",
        "lead_heading": "Nuova richiesta",
        "lead_body": "{name} desidera essere ricontattato da {workspace}.",
        "lead_need": "Esigenza: {need}",
        "lead_need_missing": "(non indicata)",
        "lead_button": "Vedi la richiesta",
        "lead_footer": "Riceve questa e-mail perché fa parte di {workspace} su Dialogbot.",
        "report_preheader": "Le richieste, le conversazioni e le attività di ieri.",
        "report_button": "Vedi il report completo",
        "report_footer": "Riceve questa e-mail perché il report giornaliero è attivo per il Suo spazio di lavoro. Può "
                         "disattivarlo in Report.",
        "report_subject": "Report giornaliero {date} – {workspace}",
        "report_title": "Report giornaliero di {workspace} – {date}",
        "report_conversations": "Conversazioni: {started} (messaggi dei clienti: {messages})",
        "report_ai_label": "Risposte IA",
        "report_ai": "{ok} ok, {refused} rifiutate, {error} errori",
        "report_new_leads": "Nuove richieste: {n}",
        "report_approved": "Richieste approvate: {n} ({amount} IVA esclusa)",
        "report_amount": "{amount} DKK",
        "report_tasks": "Attività: {created} create, {done} completate, {overdue} aperte e scadute",
        "report_new_list": "Nuove richieste:",
        "report_unnamed": "(senza nome)",
        "amb_parent_subject": "{first} vuole diventare ambasciatore di Dialogbot – vuole dare la Sua approvazione?",
        "amb_parent_preheader": "{first} ha meno di 18 anni, quindi ci serve la Sua approvazione prima di pagare un bonus.",
        "amb_parent_p1": "{ambassador_name} ({ambassador_email}) si è iscritto come ambasciatore di Dialogbot. "
                         "L'ambasciatore consiglia Dialogbot – un receptionist IA danese – alle aziende che conosce e riceve "
                         "un bonus quando diventano clienti paganti.",
        "amb_parent_p2": "Il bonus è di {bonus} per ogni nuovo cliente più il {share} di quanto paga il cliente per "
                         "{months} mesi. Viene versato sul conto bancario di {first} come reddito B (B-indkomst), che "
                         "dichiariamo all'Agenzia delle entrate danese (Skattestyrelsen). Non viene trattenuta alcuna "
                         "imposta.",
        "amb_parent_p3": "Poiché {first} ha meno di 18 anni, pagheremo solo dopo che Lei avrà approvato l'accordo. Nel "
                         "frattempo {first} può già condividere il proprio link.",
        "amb_parent_p4": "Le regole che {first} ha accettato:\n{rules}",
        "amb_parent_button": "Leggi e approva l'accordo",
        "amb_parent_note": "Se ha domande o non desidera dare la Sua approvazione, risponda semplicemente a questa e-mail.",
        "amb_parent_footer": "Riceve questa e-mail perché {ambassador_name} L'ha indicata come genitore o tutore.",
        "amb_approved_subject": "Benvenuto tra gli ambasciatori di Dialogbot",
        "amb_approved_preheader": "Il Suo link personale e il Suo codice {code} sono pronti.",
        "amb_approved_heading": "Benvenuto tra gli ambasciatori, {first_name}",
        "amb_approved_p1": "La Sua iscrizione è stata approvata. Condivida il Suo link personale con le aziende che conosce:",
        "amb_approved_code": "{link}\nIl Suo codice: {code}",
        "amb_approved_p3": "Sconto, bonus, saldo e testi pronti si trovano sulla Sua pagina. Indichi sempre che si tratta di "
                           "pubblicità e che riceve un bonus – e invii solo a persone che conosce.",
        "amb_approved_button": "Vai alla mia pagina ambasciatore",
        "amb_footer_signed_up": "Riceve questa e-mail perché si è iscritto come ambasciatore di Dialogbot.",
        "amb_rejected_subject": "La Sua iscrizione come ambasciatore di Dialogbot",
        "amb_rejected_p1": "Grazie per l'interesse a diventare ambasciatore di Dialogbot. Purtroppo al momento non possiamo "
                           "approvare la Sua iscrizione.",
        "amb_reply": "Se ha domande, risponda semplicemente a questa e-mail.",
        "amb_paid_transfer": "Abbiamo trasferito {amount} sul Suo conto bancario{bank}. Di solito il denaro arriva entro "
                             "1–2 giorni lavorativi.",
        "amb_paid_bank": " che termina con {last4}",
        "amb_paid_statement": "Il rendiconto n. {number} è disponibile sulla Sua pagina ambasciatore.",
        "amb_paid_b_income": "L'importo è reddito B (B-indkomst) e lo dichiariamo all'Agenzia delle entrate danese "
                             "(Skattestyrelsen). Non è stata trattenuta alcuna imposta, quindi si ricordi di controllare la "
                             "Sua stima fiscale preliminare (forskudsopgørelse).",
        "amb_paid_thanks": "Grazie per consigliare Dialogbot!",
        "amb_paid_subject": "Il Suo bonus ambasciatore di {amount} è in arrivo",
        "amb_paid_preheader": "Veda il rendiconto sulla Sua pagina.",
        "amb_paid_heading": "Buongiorno {first_name}, il Suo bonus è in arrivo",
        "amb_paid_button": "Vedi il rendiconto",
        "amb_paid_footer": "Riceve questa e-mail perché è ambasciatore di Dialogbot.",
        "social_subject_one": "1 post è in attesa della Sua approvazione",
        "social_subject_many": "{n} post sono in attesa della Sua approvazione",
        "social_preheader": "Li approvi nella panoramica operatore prima dell'orario previsto.",
        "social_heading": "Ci sono post in attesa",
        "social_body": "Queste bozze non sono ancora state approvate. Controlli immagine e testo, corregga se necessario e "
                       "prema Approva.",
        "social_button": "Rivedi e approva",
        "social_note": "Nulla viene pubblicato senza la Sua approvazione. Se un post non è approvato entro {hours} ore "
                       "dall'orario previsto, viene saltato.",
        "social_footer": "Riceve questa e-mail perché è operatore presso Dialogbot.",
    },
    # --------------------------------------------------------------------------------------------------- Norwegian
    "no": {
        "open": "Åpne",
        "regards": "Vennlig hilsen",
        "button_fallback": "Virker ikke knappen? Kopier denne lenken inn i nettleseren din:",
        "step": "Trinn {n}",
        "footer_account": "Du får denne e-posten fordi du har en konto hos Dialogbot.",
        "company_line": "Dialogbot · CVR-nr. 25632710 · Abildgade 18, 8200 Aarhus, Danmark",
        "default_subject": "Melding fra Dialogbot",
        "greeting": "Hei {name}",
        "role_owner": "eier", "role_admin": "administrator", "role_staff": "medarbeider", "role_reader": "leser",
        "verify_subject": "Bekreft e-postadressen din hos Dialogbot",
        "verify_preheader": "Ett klikk, så er kontoen din klar.",
        "verify_heading": "Velkommen til Dialogbot",
        "verify_body": "Takk for at du har opprettet en konto. Bekreft e-postadressen din, så kan du begynne å sette opp "
                       "AI-resepsjonisten din.",
        "verify_button": "Bekreft e-postadressen min",
        "verify_heading_privat": "Velkommen til Dialogbot Privat",
        "verify_body_privat": "Takk for at du har opprettet en konto. Bekreft e-postadressen din, så kan du starte prøveperioden på Dialogbot Privat.",
        # billing mails (F-PBQ-08) – Privat and Erhverv; de/es/fr/it formal like every mail (F-JP-15)
        "billing_footer": "Du får denne e-posten fordi du har et abonnement hos Dialogbot.",
        "manage_button": "Se abonnementet ditt",
        "what_privat": "Dialogbot Privat",
        "what_erhverv": "Dialogbot",
        "receipt_subject": "Kvittering: {amount} er betalt",
        "receipt_heading": "Takk – betalingen er gjennomført",
        "receipt_body": "Vi har mottatt {amount} for {what}. Kvitteringen og fakturaen finner du under «Administrer abonnement».",
        "failed_subject": "Betalingen på {amount} gikk ikke gjennom",
        "failed_heading": "Betalingen gikk ikke gjennom",
        "failed_body": "Vi kunne ikke trekke {amount} for {what}. Oppdater betalingskortet ditt, så fortsetter alt som før. Vi prøver igjen de neste dagene.",
        "refund_subject": "Refusjon: {amount} er sendt tilbake",
        "refund_heading": "Pengene er på vei tilbake",
        "refund_body": "Vi har refundert {amount} for {what}. Det tar vanligvis 5–10 bankdager før beløpet står på kontoen din.",
        "trial_subject": "Prøveperioden din slutter om 3 dager",
        "trial_heading": "Prøveperioden slutter {date}",
        "trial_body": "Den {date} går prøveperioden din på {plan} over i et betalt abonnement til {amount}. Vil du ikke fortsette, si opp før det – da trekker vi ingenting.",
        "grace0_subject": "Oppdater betalingskortet – Dialogbot fortsetter til og med {date}",
        "grace0_heading": "Abonnementet er ikke betalt akkurat nå",
        "grace0_body": "Kortet er utløpt eller fjernet, eller betalingen gikk ikke gjennom. Chat og telefon fortsetter til og med {date}. Oppdater betalingskortet, så fortsetter alt som før.",
        "grace1_subject": "Påminnelse: oppdater betalingskortet før {date}",
        "grace1_heading": "Husk å oppdatere betalingskortet",
        "grace1_body": "Abonnementet er fortsatt ikke betalt. Chat og telefon fortsetter til og med {date} – deretter stopper de. Oppdater betalingskortet, så fortsetter alt som før.",
        "grace2_subject": "I morgen stopper chat og telefon – oppdater betalingskortet",
        "grace2_heading": "Siste dag: {date}",
        "grace2_body": "Abonnementet er fortsatt ikke betalt. Etter {date} svarer ikke chatten lenger besøkende, og telefonen stopper. Oppdater betalingskortet i dag, så fortsetter alt som før.",
        "verify_note": "Lenken er gyldig i 48 timer. Har du ikke opprettet en konto hos Dialogbot, kan du se bort fra denne "
                       "e-posten.",
        "verify_footer": "Du får denne e-posten fordi noen har opprettet en konto hos Dialogbot med adressen din.",
        "reset_subject": "Tilbakestill passordet ditt hos Dialogbot",
        "reset_preheader": "Velg et nytt passord – lenken er gyldig i 1 time.",
        "reset_heading": "Tilbakestill passordet ditt",
        "reset_body": "Vi har mottatt en forespørsel om å tilbakestille passordet til Dialogbot-kontoen din. Klikk på "
                      "knappen for å velge et nytt.",
        "reset_button": "Velg nytt passord",
        "reset_note": "Lenken er gyldig i 1 time og kan bare brukes én gang. Har du ikke bedt om dette, kan du se bort fra "
                      "denne e-posten – passordet ditt forblir uendret.",
        "invitation_subject": "{invited_by} har invitert deg til {workspace} på Dialogbot",
        "invitation_preheader": "Du er invitert som {role}.",
        "invitation_heading": "Du er invitert til {workspace}",
        "invitation_body": "{invited_by} har invitert deg til {workspace} på Dialogbot som {role}. Som medlem kan du se "
                           "henvendelser, samtaler og oppgaver.",
        "invitation_button": "Godta invitasjonen",
        "invitation_note": "Invitasjonen er gyldig i 72 timer. Har du ikke en konto ennå, oppretter du den underveis.",
        "invitation_footer": "Du får denne e-posten fordi {invited_by} har invitert deg til Dialogbot.",
        "lead_someone": "En kunde",
        "lead_subject": "Ny henvendelse: {name}",
        "lead_preheader": "{name} ønsker å bli kontaktet.",
        "lead_heading": "Ny henvendelse",
        "lead_body": "{name} ønsker å bli kontaktet av {workspace}.",
        "lead_need": "Behov: {need}",
        "lead_need_missing": "(ikke oppgitt)",
        "lead_button": "Se henvendelsen",
        "lead_footer": "Du får denne e-posten fordi du er knyttet til {workspace} på Dialogbot.",
        "report_preheader": "Gårsdagens henvendelser, samtaler og oppgaver.",
        "report_button": "Se hele rapporten",
        "report_footer": "Du får denne e-posten fordi dagsrapporten er slått på for arbeidsområdet deres. Du kan slå den av "
                         "under Rapporter.",
        "report_subject": "Dagsrapport {date} – {workspace}",
        "report_title": "Dagsrapport for {workspace} – {date}",
        "report_conversations": "Samtaler: {started} (kundemeldinger: {messages})",
        "report_ai_label": "AI-svar",
        "report_ai": "{ok} ok, {refused} avvist, {error} feil",
        "report_new_leads": "Nye henvendelser: {n}",
        "report_approved": "Godkjente henvendelser: {n} ({amount} ekskl. mva.)",
        "report_amount": "{amount} DKK",
        "report_tasks": "Oppgaver: {created} opprettet, {done} løst, {overdue} åpne over frist",
        "report_new_list": "Nye henvendelser:",
        "report_unnamed": "(uten navn)",
        "amb_parent_subject": "{first} vil bli ambassadør for Dialogbot – vil du godkjenne?",
        "amb_parent_preheader": "{first} er under 18, så vi trenger godkjenningen din før vi betaler ut bonus.",
        "amb_parent_p1": "{ambassador_name} ({ambassador_email}) har meldt seg som ambassadør for Dialogbot. Som "
                         "ambassadør anbefaler man Dialogbot – en dansk AI-resepsjonist – til bedrifter man kjenner, og "
                         "får en bonus når de blir betalende kunder.",
        "amb_parent_p2": "Bonusen er {bonus} per ny kunde pluss {share} av det kunden betaler, i {months} måneder. Den "
                         "utbetales til bankkontoen til {first} som B-inntekt (B-indkomst), som vi rapporterer til de "
                         "danske skattemyndighetene (Skattestyrelsen). Det trekkes ikke skatt.",
        "amb_parent_p3": "Fordi {first} er under 18, betaler vi først ut når du har godkjent avtalen. {first} kan gjerne "
                         "dele lenken sin i mellomtiden.",
        "amb_parent_p4": "Reglene {first} har sagt ja til:\n{rules}",
        "amb_parent_button": "Les og godkjenn avtalen",
        "amb_parent_note": "Har du spørsmål, eller vil du ikke godkjenne, kan du bare svare på denne e-posten.",
        "amb_parent_footer": "Du får denne e-posten fordi {ambassador_name} har oppgitt deg som forelder eller verge.",
        "amb_approved_subject": "Velkommen som Dialogbot-ambassadør",
        "amb_approved_preheader": "Den personlige lenken din og koden din {code} er klare.",
        "amb_approved_heading": "Velkommen som ambassadør, {first_name}",
        "amb_approved_p1": "Du er godkjent. Del den personlige lenken din med bedrifter du kjenner:",
        "amb_approved_code": "{link}\nKoden din: {code}",
        "amb_approved_p3": "Rabatt, bonus, saldo og ferdige tekster finner du på siden din. Skriv alltid at det er reklame, "
                           "og at du får bonus – og send bare til folk du kjenner.",
        "amb_approved_button": "Gå til ambassadørsiden min",
        "amb_footer_signed_up": "Du får denne e-posten fordi du har meldt deg som ambassadør for Dialogbot.",
        "amb_rejected_subject": "Påmeldingen din som Dialogbot-ambassadør",
        "amb_rejected_p1": "Takk for at du vil bli ambassadør for Dialogbot. Vi kan dessverre ikke godkjenne påmeldingen "
                           "din akkurat nå.",
        "amb_reply": "Har du spørsmål, kan du bare svare på denne e-posten.",
        "amb_paid_transfer": "Vi har overført {amount} til bankkontoen din{bank}. Pengene er vanligvis på kontoen innen "
                             "1–2 virkedager.",
        "amb_paid_bank": " som slutter på {last4}",
        "amb_paid_statement": "Avregningsbilag nr. {number} ligger på ambassadørsiden din.",
        "amb_paid_b_income": "Beløpet er B-inntekt (B-indkomst), og vi rapporterer det til de danske skattemyndighetene "
                             "(Skattestyrelsen). Det er ikke trukket skatt, så husk å sjekke forskuddsoppgjøret ditt "
                             "(forskudsopgørelse).",
        "amb_paid_thanks": "Takk for at du anbefaler Dialogbot!",
        "amb_paid_subject": "Ambassadørbonusen din på {amount} er på vei",
        "amb_paid_preheader": "Se avregningsbilaget på siden din.",
        "amb_paid_heading": "Hei {first_name}, bonusen din er på vei",
        "amb_paid_button": "Se avregningsbilaget",
        "amb_paid_footer": "Du får denne e-posten fordi du er ambassadør for Dialogbot.",
        "social_subject_one": "1 innlegg venter på godkjenningen din",
        "social_subject_many": "{n} innlegg venter på godkjenningen din",
        "social_preheader": "Godkjenn dem i operatøroversikten før tidspunktet.",
        "social_heading": "Innlegg venter på deg",
        "social_body": "Disse utkastene er ikke godkjent ennå. Se på bilde og tekst, rett ved behov, og trykk Godkjenn.",
        "social_button": "Gå gjennom og godkjenn",
        "social_note": "Ingenting blir publisert uten godkjenningen din. Er et innlegg ikke godkjent {hours} timer etter "
                       "tidspunktet, hoppes det over.",
        "social_footer": "Du får denne e-posten fordi du er operatør hos Dialogbot.",
    },
    # ----------------------------------------------------------------------------------------------------- Swedish
    "sv": {
        "open": "Öppna",
        "regards": "Vänliga hälsningar",
        "button_fallback": "Fungerar inte knappen? Kopiera den här länken till din webbläsare:",
        "step": "Steg {n}",
        "footer_account": "Du får det här mejlet eftersom du har ett konto hos Dialogbot.",
        "company_line": "Dialogbot · CVR-nr 25632710 · Abildgade 18, 8200 Aarhus, Danmark",
        "default_subject": "Meddelande från Dialogbot",
        "greeting": "Hej {name}",
        "role_owner": "ägare", "role_admin": "administratör", "role_staff": "medarbetare", "role_reader": "läsare",
        "verify_subject": "Bekräfta din e-postadress hos Dialogbot",
        "verify_preheader": "Ett klick, så är ditt konto klart.",
        "verify_heading": "Välkommen till Dialogbot",
        "verify_body": "Tack för att du har skapat ett konto. Bekräfta din e-postadress, så kan du börja ställa in din "
                       "AI-receptionist.",
        "verify_button": "Bekräfta min e-postadress",
        "verify_heading_privat": "Välkommen till Dialogbot Privat",
        "verify_body_privat": "Tack för att du har skapat ett konto. Bekräfta din e-postadress, så kan du starta din provperiod på Dialogbot Privat.",
        # billing mails (F-PBQ-08) – Privat and Erhverv; de/es/fr/it formal like every mail (F-JP-15)
        "billing_footer": "Du får detta e-postmeddelande eftersom du har ett abonnemang hos Dialogbot.",
        "manage_button": "Se ditt abonnemang",
        "what_privat": "Dialogbot Privat",
        "what_erhverv": "Dialogbot",
        "receipt_subject": "Kvitto: {amount} är betalt",
        "receipt_heading": "Tack – betalningen är genomförd",
        "receipt_body": "Vi har tagit emot {amount} för {what}. Kvittot och fakturan hittar du under «Hantera abonnemang».",
        "failed_subject": "Betalningen på {amount} gick inte igenom",
        "failed_heading": "Betalningen gick inte igenom",
        "failed_body": "Vi kunde inte dra {amount} för {what}. Uppdatera ditt betalkort, så fortsätter allt som förut. Vi försöker igen de närmaste dagarna.",
        "refund_subject": "Återbetalning: {amount} har skickats tillbaka",
        "refund_heading": "Pengarna är på väg tillbaka",
        "refund_body": "Vi har återbetalat {amount} för {what}. Det tar normalt 5–10 bankdagar innan beloppet syns på ditt konto.",
        "trial_subject": "Din provperiod slutar om 3 dagar",
        "trial_heading": "Provperioden slutar {date}",
        "trial_body": "Den {date} övergår din provperiod på {plan} till ett betalt abonnemang för {amount}. Vill du inte fortsätta, säg upp före dess – då dras ingenting.",
        "grace0_subject": "Uppdatera betalkortet – Dialogbot fortsätter till och med {date}",
        "grace0_heading": "Abonnemanget är inte betalt just nu",
        "grace0_body": "Kortet har gått ut eller tagits bort, eller betalningen gick inte igenom. Chatt och telefon fortsätter till och med {date}. Uppdatera betalkortet så fortsätter allt som förut.",
        "grace1_subject": "Påminnelse: uppdatera betalkortet före {date}",
        "grace1_heading": "Kom ihåg att uppdatera betalkortet",
        "grace1_body": "Abonnemanget är fortfarande inte betalt. Chatt och telefon fortsätter till och med {date} – sedan stoppar de. Uppdatera betalkortet så fortsätter allt som förut.",
        "grace2_subject": "I morgon stoppar chatt och telefon – uppdatera betalkortet",
        "grace2_heading": "Sista dagen: {date}",
        "grace2_body": "Abonnemanget är fortfarande inte betalt. Efter {date} svarar chatten inte längre besökare och telefonen stoppar. Uppdatera betalkortet i dag så fortsätter allt som förut.",
        "verify_note": "Länken gäller i 48 timmar. Om du inte har skapat ett konto hos Dialogbot kan du bortse från det här "
                       "mejlet.",
        "verify_footer": "Du får det här mejlet eftersom någon har skapat ett konto hos Dialogbot med din adress.",
        "reset_subject": "Återställ ditt lösenord hos Dialogbot",
        "reset_preheader": "Välj ett nytt lösenord – länken gäller i 1 timme.",
        "reset_heading": "Återställ ditt lösenord",
        "reset_body": "Vi har fått en begäran om att återställa lösenordet till ditt Dialogbot-konto. Klicka på knappen "
                      "för att välja ett nytt.",
        "reset_button": "Välj nytt lösenord",
        "reset_note": "Länken gäller i 1 timme och kan bara användas en gång. Om du inte har bett om det kan du bortse från "
                      "det här mejlet – ditt lösenord förblir oförändrat.",
        "invitation_subject": "{invited_by} har bjudit in dig till {workspace} på Dialogbot",
        "invitation_preheader": "Du är inbjuden som {role}.",
        "invitation_heading": "Du är inbjuden till {workspace}",
        "invitation_body": "{invited_by} har bjudit in dig till {workspace} på Dialogbot som {role}. Som medlem kan du se "
                           "förfrågningar, samtal och uppgifter.",
        "invitation_button": "Acceptera inbjudan",
        "invitation_note": "Inbjudan gäller i 72 timmar. Om du inte har ett konto än skapar du det under tiden.",
        "invitation_footer": "Du får det här mejlet eftersom {invited_by} har bjudit in dig till Dialogbot.",
        "lead_someone": "En kund",
        "lead_subject": "Ny förfrågan: {name}",
        "lead_preheader": "{name} vill bli kontaktad.",
        "lead_heading": "Ny förfrågan",
        "lead_body": "{name} vill bli kontaktad av {workspace}.",
        "lead_need": "Behov: {need}",
        "lead_need_missing": "(inte angivet)",
        "lead_button": "Visa förfrågan",
        "lead_footer": "Du får det här mejlet eftersom du är kopplad till {workspace} på Dialogbot.",
        "report_preheader": "Gårdagens förfrågningar, samtal och uppgifter.",
        "report_button": "Visa hela rapporten",
        "report_footer": "Du får det här mejlet eftersom dagsrapporten är aktiverad för er arbetsyta. Du kan stänga av den "
                         "under Rapporter.",
        "report_subject": "Dagsrapport {date} – {workspace}",
        "report_title": "Dagsrapport för {workspace} – {date}",
        "report_conversations": "Samtal: {started} (kundmeddelanden: {messages})",
        "report_ai_label": "AI-svar",
        "report_ai": "{ok} ok, {refused} avvisade, {error} fel",
        "report_new_leads": "Nya förfrågningar: {n}",
        "report_approved": "Godkända förfrågningar: {n} ({amount} exkl. moms)",
        "report_amount": "{amount} DKK",
        "report_tasks": "Uppgifter: {created} skapade, {done} lösta, {overdue} öppna efter tidsfrist",
        "report_new_list": "Nya förfrågningar:",
        "report_unnamed": "(utan namn)",
        "amb_parent_subject": "{first} vill bli ambassadör för Dialogbot – vill du godkänna?",
        "amb_parent_preheader": "{first} är under 18, så vi behöver ditt godkännande innan vi betalar ut någon bonus.",
        "amb_parent_p1": "{ambassador_name} ({ambassador_email}) har anmält sig som ambassadör för Dialogbot. Som "
                         "ambassadör rekommenderar man Dialogbot – en dansk AI-receptionist – till företag man känner och "
                         "får en bonus när de blir betalande kunder.",
        "amb_parent_p2": "Bonusen är {bonus} per ny kund plus {share} av det kunden betalar, i {months} månader. Den "
                         "betalas ut till {first}s bankkonto som B-inkomst (B-indkomst), som vi rapporterar till den "
                         "danska skattemyndigheten (Skattestyrelsen). Ingen skatt dras.",
        "amb_parent_p3": "Eftersom {first} är under 18 betalar vi ut först när du har godkänt avtalet. {first} kan gärna "
                         "dela sin länk under tiden.",
        "amb_parent_p4": "Reglerna som {first} har godkänt:\n{rules}",
        "amb_parent_button": "Läs och godkänn avtalet",
        "amb_parent_note": "Om du har frågor, eller inte vill godkänna, svarar du bara på det här mejlet.",
        "amb_parent_footer": "Du får det här mejlet eftersom {ambassador_name} har angett dig som förälder eller "
                             "vårdnadshavare.",
        "amb_approved_subject": "Välkommen som Dialogbot-ambassadör",
        "amb_approved_preheader": "Din personliga länk och din kod {code} är klara.",
        "amb_approved_heading": "Välkommen som ambassadör, {first_name}",
        "amb_approved_p1": "Du är godkänd. Dela din personliga länk med företag du känner:",
        "amb_approved_code": "{link}\nDin kod: {code}",
        "amb_approved_p3": "Rabatt, bonus, saldo och färdiga texter finns på din sida. Skriv alltid att det är reklam och "
                           "att du får bonus – och skicka bara till personer du känner.",
        "amb_approved_button": "Gå till min ambassadörssida",
        "amb_footer_signed_up": "Du får det här mejlet eftersom du har anmält dig som ambassadör för Dialogbot.",
        "amb_rejected_subject": "Din anmälan som Dialogbot-ambassadör",
        "amb_rejected_p1": "Tack för ditt intresse för att bli ambassadör för Dialogbot. Tyvärr kan vi inte godkänna din "
                           "anmälan just nu.",
        "amb_reply": "Om du har frågor svarar du bara på det här mejlet.",
        "amb_paid_transfer": "Vi har överfört {amount} till ditt bankkonto{bank}. Pengarna brukar finnas på kontot inom "
                             "1–2 bankdagar.",
        "amb_paid_bank": " som slutar på {last4}",
        "amb_paid_statement": "Avräkningsunderlag nr {number} finns på din ambassadörssida.",
        "amb_paid_b_income": "Beloppet är B-inkomst (B-indkomst), och vi rapporterar det till den danska skattemyndigheten "
                             "(Skattestyrelsen). Ingen skatt har dragits, så kom ihåg att kontrollera din preliminära "
                             "skatteberäkning (forskudsopgørelse).",
        "amb_paid_thanks": "Tack för att du rekommenderar Dialogbot!",
        "amb_paid_subject": "Din ambassadörsbonus på {amount} är på väg",
        "amb_paid_preheader": "Se avräkningsunderlaget på din sida.",
        "amb_paid_heading": "Hej {first_name}, din bonus är på väg",
        "amb_paid_button": "Se avräkningsunderlaget",
        "amb_paid_footer": "Du får det här mejlet eftersom du är ambassadör för Dialogbot.",
        "social_subject_one": "1 inlägg väntar på ditt godkännande",
        "social_subject_many": "{n} inlägg väntar på ditt godkännande",
        "social_preheader": "Godkänn dem i operatörsöversikten före tidpunkten.",
        "social_heading": "Inlägg väntar på dig",
        "social_body": "De här utkasten är inte godkända än. Titta på bild och text, rätta vid behov och tryck Godkänn.",
        "social_button": "Granska och godkänn",
        "social_note": "Inget publiceras utan ditt godkännande. Om ett inlägg inte är godkänt {hours} timmar efter "
                       "tidpunkten hoppas det över.",
        "social_footer": "Du får det här mejlet eftersom du är operatör hos Dialogbot.",
    },
}

# Digit grouping and decimal mark for amounts in the daily report (Danish: 1.234,56).
NUMBER_SEPARATORS: dict[str, tuple[str, str]] = {
    "da": (".", ","), "en": (",", "."), "de": (".", ","), "es": (".", ","), "fr": (" ", ","), "it": (".", ","),
    "no": (" ", ","), "sv": (" ", ","),
}

# The words a free-text mail (`from_plain`) may open with as a greeting line, and its closing line.
GREETING_WORDS: dict[str, tuple[str, ...]] = {
    "da": ("Hej", "Kære"), "en": ("Hi", "Hello", "Dear"), "de": ("Hallo", "Guten Tag", "Liebe", "Lieber", "Sehr geehrte"),
    "es": ("Hola", "Estimado", "Estimada"), "fr": ("Bonjour", "Cher", "Chère", "Madame", "Monsieur"),
    "it": ("Buongiorno", "Ciao", "Gentile", "Caro", "Cara"), "no": ("Hei", "Kjære"), "sv": ("Hej", "Kära"),
}

# Dialogbot Privat's texts (service mails, the funnel welcome, the SMS code) live in their own file, same mechanism.
from app.modules.integrations.email_texts_privat import PRIVAT_TEXTS  # noqa: E402

for _lang, _table in PRIVAT_TEXTS.items():
    TEXTS[_lang].update(_table)


def t(lang: str | None, key: str, **values) -> str:
    """The text `key` in `lang` (Danish when the language or the key is unknown), with its placeholders filled."""
    table = TEXTS.get(normalize(lang)) or TEXTS[DEFAULT]
    text = table.get(key, TEXTS[DEFAULT][key])
    return text.format(**values) if values else text


def money(lang: str | None, minor: int) -> str:
    """An amount in øre as the language writes it, with the currency: "447,00 kr." / "DKK 447.00"."""
    thousands, decimal = NUMBER_SEPARATORS.get(normalize(lang), NUMBER_SEPARATORS[DEFAULT])
    s = f"{minor / 100:,.2f}".replace(",", "X").replace(".", decimal).replace("X", thousands)
    return t(lang, "report_amount", amount=s)


# --------------------------------------------------------------------------- who gets which language

def user_language(db, user_id: uuid.UUID | str | None) -> str:
    """The user's own interface language (Danish when the user is unknown)."""
    from app.models import User

    if not user_id:
        return DEFAULT
    try:
        u = db.get(User, uuid.UUID(str(user_id)))
    except (ValueError, TypeError):
        return DEFAULT
    return normalize(u.interface_language if u is not None else None)


def workspace_language(db, workspace_id: uuid.UUID | str | None, which: str = "interface_language") -> str:
    """One of the workspace's language levels (`interface_language`, `default_conversation_language`,
    `report_language`); Danish when the workspace has no language settings."""
    from app.models import LanguageSettings

    if not workspace_id:
        return DEFAULT
    try:
        ls = db.get(LanguageSettings, uuid.UUID(str(workspace_id)))
    except (ValueError, TypeError):
        return DEFAULT
    return normalize(getattr(ls, which, None) if ls is not None else None)


__all__ = ["LANGUAGES", "NUMBER_SEPARATORS", "TEXTS", "money", "t", "user_language", "workspace_language"]

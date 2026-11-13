"""E07 – booking communication templates, with previews that never send.

Eight variants. Six go to the business's customer, by SMS and e-mail, in the business's name (never Dialogbot's
brand, same rules as app/modules/integrations/sms_templates.py: ≤ 160 characters for a normal business name, no
emoji, no «!», no links, signed «Vh {business}»):
  request_receipt · confirmed · reminder · proposed_change · rescheduled · cancelled
Two go to the business (owner/staff) by e-mail from Dialogbot:
  owner_attention (a booking needs a person: the calendar write failed, or it awaits confirmation)
  delivery_failure (a message to the customer could not be delivered)

All eight exist in the eight languages of app/core/languages.py (Danish is the source; German, French, Italian and
Spanish use the formal register). `render()` builds a message; `preview()` fills it with a booking of the workspace
or with sample data. Nothing in this module queues, sends or writes anything – the preview endpoint
(GET /workspaces/{id}/bookings/messages) is read-only and is tested to leave the outbox, the SMS provider and the
mail log untouched. When each message is sent automatically is not decided here (see qa/ledger.md, E07)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.languages import DEFAULT, normalize
from app.modules.integrations import sms_templates as sms
from app.modules.integrations.email_templates import Email

CUSTOMER_VARIANTS = ("request_receipt", "confirmed", "reminder", "proposed_change", "rescheduled", "cancelled")
OWNER_VARIANTS = ("owner_attention", "delivery_failure")
VARIANTS = CUSTOMER_VARIANTS + OWNER_VARIANTS
REASONS = ("calendar_failed", "needs_confirmation")

# GSM-7 basic alphabet (3GPP TS 23.038) plus the extension table (each extension character costs two septets).
_GSM = set("@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿"
           "abcdefghijklmnopqrstuvwxyzäöñüà")
_GSM_EXT = set("^{}\\[~]|€")

TEXTS: dict[str, dict] = {
    "da": {
        "labels": {"request_receipt": "Anmodning modtaget", "confirmed": "Aftale bekræftet", "reminder": "Påmindelse",
                   "proposed_change": "Forslag til ny tid", "rescheduled": "Aftale flyttet", "cancelled": "Aftale aflyst",
                   "owner_attention": "Kræver din opmærksomhed", "delivery_failure": "Levering fejlede"},
        "request_receipt": {"sms": "{greeting}Vi har modtaget din forespørgsel om {what} {when}. Vi bekræfter tiden hurtigst muligt.",
                            "subject": "Vi har modtaget din forespørgsel – {business}", "heading": "Vi har modtaget din forespørgsel",
                            "body": "Vi har registreret din forespørgsel om {what} {when}. Tiden er ikke endelig, før vi har bekræftet den – du hører fra os hurtigst muligt."},
        "confirmed": {"sms": "{greeting}Din tid hos {business} er bekræftet: {what} {when}.",
                      "subject": "Din tid er bekræftet – {business}", "heading": "Din tid er bekræftet",
                      "body": "Vi glæder os til at se dig. Kontakt os, hvis tiden ikke længere passer."},
        "reminder": {"sms": "{greeting}Påmindelse: Du har en tid hos {business} {when} ({what}).",
                     "subject": "Påmindelse: din tid {when}", "heading": "Påmindelse om din tid",
                     "body": "Du har en tid hos {business} {when}. Giv os besked i god tid, hvis du bliver forhindret."},
        "proposed_change": {"sms": "{greeting}{business} foreslår at flytte din tid til {new_when}. Kontakt os og sig, om det passer.",
                            "subject": "Forslag til ny tid – {business}", "heading": "Vi foreslår en ny tid",
                            "body": "Vi foreslår at flytte din tid ({what}) fra {when} til {new_when}. Din nuværende tid gælder, indtil du har svaret os."},
        "rescheduled": {"sms": "{greeting}Din tid hos {business} er flyttet til {new_when} ({what}).",
                        "subject": "Din tid er flyttet – {business}", "heading": "Din tid er flyttet",
                        "body": "Din tid ({what}) er flyttet fra {when} til {new_when}."},
        "cancelled": {"sms": "{greeting}Din tid hos {business} {when} er aflyst. Kontakt os, hvis du vil have en ny tid.",
                      "subject": "Din tid er aflyst – {business}", "heading": "Din tid er aflyst",
                      "body": "Din tid ({what}) {when} er aflyst. Kontakt os, hvis du vil have en ny tid."},
        "owner_attention": {"subject": "En aftale kræver din opmærksomhed – {customer}", "heading": "En aftale kræver din opmærksomhed",
                            "body": "{reason} Åbn aftalen og tag stilling."},
        "delivery_failure": {"subject": "En besked til {customer} kunne ikke leveres", "heading": "En besked kunne ikke leveres",
                             "body": "Beskeden «{message}» til {customer} ({channel}) blev ikke leveret: {error}. Kontakt kunden på anden vis, så aftalen ikke går tabt."},
        "reasons": {"calendar_failed": "Aftalen står i Dialogbot, men kunne ikke skrives i jeres kalender.",
                    "needs_confirmation": "Aftalen blev lavet, mens kalenderen ikke kunne læses, og skal bekræftes af en medarbejder."},
        "rows": {"what": "Hvad", "when": "Hvornår", "new_when": "Ny tid", "customer": "Kunde", "channel": "Kanal"},
        "channels": {"sms": "SMS", "email": "e-mail"},
        "hello": "Hej {first},", "button": "Åbn aftaler",
        "footer": "Du får denne besked, fordi du har en aftale hos {business}. Sendt via Dialogbot.",
        "sample": {"customer": "Mette Nielsen", "what": "Besigtigelse", "error": "nummeret findes ikke"},
    },
    "en": {
        "labels": {"request_receipt": "Request received", "confirmed": "Appointment confirmed", "reminder": "Reminder",
                   "proposed_change": "Proposed new time", "rescheduled": "Appointment moved", "cancelled": "Appointment cancelled",
                   "owner_attention": "Needs your attention", "delivery_failure": "Delivery failed"},
        "request_receipt": {"sms": "{greeting}We have received your request for {what}, {when}. We will confirm the time as soon as possible.",
                            "subject": "We have received your request – {business}", "heading": "We have received your request",
                            "body": "We have registered your request for {what}, {when}. The time is not final until we have confirmed it – you will hear from us as soon as possible."},
        "confirmed": {"sms": "{greeting}Your appointment at {business} is confirmed: {what}, {when}.",
                      "subject": "Your appointment is confirmed – {business}", "heading": "Your appointment is confirmed",
                      "body": "We look forward to seeing you. Please contact us if the time no longer suits you."},
        "reminder": {"sms": "{greeting}Reminder: your appointment at {business} is on {when} ({what}).",
                     "subject": "Reminder: your appointment on {when}", "heading": "Appointment reminder",
                     "body": "You have an appointment at {business} on {when}. Please let us know in good time if you cannot make it."},
        "proposed_change": {"sms": "{greeting}{business} proposes moving your appointment to {new_when}. Please tell us if that suits you.",
                            "subject": "Proposed new time – {business}", "heading": "We propose a new time",
                            "body": "We propose moving your appointment ({what}) from {when} to {new_when}. Your current time stands until you have replied."},
        "rescheduled": {"sms": "{greeting}Your appointment at {business} has been moved to {new_when} ({what}).",
                        "subject": "Your appointment has been moved – {business}", "heading": "Your appointment has been moved",
                        "body": "Your appointment ({what}) has been moved from {when} to {new_when}."},
        "cancelled": {"sms": "{greeting}Your appointment at {business} on {when} is cancelled. Contact us for a new time.",
                      "subject": "Your appointment has been cancelled – {business}", "heading": "Your appointment has been cancelled",
                      "body": "Your appointment ({what}) on {when} has been cancelled. Contact us if you would like a new time."},
        "owner_attention": {"subject": "A booking needs your attention – {customer}", "heading": "A booking needs your attention",
                            "body": "{reason} Open the booking and decide what to do."},
        "delivery_failure": {"subject": "A message to {customer} could not be delivered", "heading": "A message could not be delivered",
                             "body": "The message «{message}» to {customer} ({channel}) was not delivered: {error}. Contact the customer another way so the appointment is not lost."},
        "reasons": {"calendar_failed": "The booking is in Dialogbot but could not be written to your calendar.",
                    "needs_confirmation": "The booking was made while your calendar could not be read and must be confirmed by a member of staff."},
        "rows": {"what": "What", "when": "When", "new_when": "New time", "customer": "Customer", "channel": "Channel"},
        "channels": {"sms": "SMS", "email": "email"},
        "hello": "Hi {first},", "button": "Open bookings",
        "footer": "You are receiving this message because you have an appointment with {business}. Sent via Dialogbot.",
        "sample": {"customer": "Emma Taylor", "what": "Inspection", "error": "the number does not exist"},
    },
    "de": {
        "labels": {"request_receipt": "Anfrage erhalten", "confirmed": "Termin bestätigt", "reminder": "Erinnerung",
                   "proposed_change": "Neuer Terminvorschlag", "rescheduled": "Termin verschoben", "cancelled": "Termin abgesagt",
                   "owner_attention": "Ihre Aufmerksamkeit nötig", "delivery_failure": "Zustellung fehlgeschlagen"},
        "request_receipt": {"sms": "{greeting}Wir haben Ihre Anfrage für {what}, {when}, erhalten. Wir bestätigen bald.",
                            "subject": "Wir haben Ihre Anfrage erhalten – {business}", "heading": "Wir haben Ihre Anfrage erhalten",
                            "body": "Wir haben Ihre Anfrage für {what}, {when}, registriert. Der Termin ist erst nach unserer Bestätigung verbindlich – Sie hören so schnell wie möglich von uns."},
        "confirmed": {"sms": "{greeting}Ihr Termin bei {business} ist bestätigt: {what}, {when}.",
                      "subject": "Ihr Termin ist bestätigt – {business}", "heading": "Ihr Termin ist bestätigt",
                      "body": "Wir freuen uns auf Sie. Bitte melden Sie sich, falls der Termin nicht mehr passt."},
        "reminder": {"sms": "{greeting}Erinnerung: Ihr Termin bei {business} ist am {when} ({what}).",
                     "subject": "Erinnerung: Ihr Termin am {when}", "heading": "Erinnerung an Ihren Termin",
                     "body": "Sie haben am {when} einen Termin bei {business}. Bitte sagen Sie rechtzeitig Bescheid, falls Sie verhindert sind."},
        "proposed_change": {"sms": "{greeting}{business} schlägt als neuen Termin {new_when} vor. Passt das?",
                            "subject": "Vorschlag für einen neuen Termin – {business}", "heading": "Wir schlagen einen neuen Termin vor",
                            "body": "Wir schlagen vor, Ihren Termin ({what}) von {when} auf {new_when} zu verlegen. Ihr bisheriger Termin gilt, bis Sie uns geantwortet haben."},
        "rescheduled": {"sms": "{greeting}Ihr Termin bei {business} wurde verlegt: {new_when} ({what}).",
                        "subject": "Ihr Termin wurde verlegt – {business}", "heading": "Ihr Termin wurde verlegt",
                        "body": "Ihr Termin ({what}) wurde von {when} auf {new_when} verlegt."},
        "cancelled": {"sms": "{greeting}Ihr Termin bei {business} am {when} wurde abgesagt.",
                      "subject": "Ihr Termin wurde abgesagt – {business}", "heading": "Ihr Termin wurde abgesagt",
                      "body": "Ihr Termin ({what}) am {when} wurde abgesagt. Melden Sie sich gern, wenn Sie einen neuen Termin möchten."},
        "owner_attention": {"subject": "Ein Termin braucht Ihre Aufmerksamkeit – {customer}", "heading": "Ein Termin braucht Ihre Aufmerksamkeit",
                            "body": "{reason} Öffnen Sie den Termin und entscheiden Sie, wie es weitergeht."},
        "delivery_failure": {"subject": "Eine Nachricht an {customer} konnte nicht zugestellt werden", "heading": "Eine Nachricht konnte nicht zugestellt werden",
                             "body": "Die Nachricht «{message}» an {customer} ({channel}) wurde nicht zugestellt: {error}. Kontaktieren Sie den Kunden auf anderem Weg, damit der Termin nicht verloren geht."},
        "reasons": {"calendar_failed": "Der Termin steht in Dialogbot, konnte aber nicht in Ihren Kalender eingetragen werden.",
                    "needs_confirmation": "Der Termin wurde gebucht, als Ihr Kalender nicht gelesen werden konnte, und muss von einem Teammitglied bestätigt werden."},
        "rows": {"what": "Was", "when": "Wann", "new_when": "Neuer Termin", "customer": "Kunde", "channel": "Kanal"},
        "channels": {"sms": "SMS", "email": "E-Mail"},
        "hello": "Hallo {first},", "button": "Termine öffnen",
        "footer": "Sie erhalten diese Nachricht, weil Sie einen Termin bei {business} haben. Gesendet über Dialogbot.",
        "sample": {"customer": "Anna Schmidt", "what": "Besichtigung", "error": "die Nummer existiert nicht"},
    },
    "es": {
        "labels": {"request_receipt": "Solicitud recibida", "confirmed": "Cita confirmada", "reminder": "Recordatorio",
                   "proposed_change": "Propuesta de nueva hora", "rescheduled": "Cita cambiada", "cancelled": "Cita cancelada",
                   "owner_attention": "Requiere su atención", "delivery_failure": "Entrega fallida"},
        "request_receipt": {"sms": "{greeting}Hemos recibido su solicitud de {what}, {when}. Le confirmaremos la hora pronto.",
                            "subject": "Hemos recibido su solicitud – {business}", "heading": "Hemos recibido su solicitud",
                            "body": "Hemos registrado su solicitud de {what}, {when}. La hora no es definitiva hasta que la confirmemos; le responderemos lo antes posible."},
        "confirmed": {"sms": "{greeting}Su cita en {business} está confirmada: {what}, {when}.",
                      "subject": "Su cita está confirmada – {business}", "heading": "Su cita está confirmada",
                      "body": "Le esperamos. Póngase en contacto con nosotros si la hora ya no le conviene."},
        "reminder": {"sms": "{greeting}Recordatorio: tiene una cita en {business} el {when} ({what}).",
                     "subject": "Recordatorio: su cita el {when}", "heading": "Recordatorio de su cita",
                     "body": "Tiene una cita en {business} el {when}. Avísenos con tiempo si no puede asistir."},
        "proposed_change": {"sms": "{greeting}{business} le propone cambiar su cita al {new_when}. Díganos si le conviene.",
                            "subject": "Propuesta de nueva hora – {business}", "heading": "Le proponemos una nueva hora",
                            "body": "Le proponemos cambiar su cita ({what}) del {when} al {new_when}. Su hora actual se mantiene hasta que nos responda."},
        "rescheduled": {"sms": "{greeting}Su cita en {business} se ha cambiado al {new_when} ({what}).",
                        "subject": "Su cita se ha cambiado – {business}", "heading": "Su cita se ha cambiado",
                        "body": "Su cita ({what}) se ha cambiado del {when} al {new_when}."},
        "cancelled": {"sms": "{greeting}Su cita en {business} del {when} se ha cancelado. Contáctenos para otra hora.",
                      "subject": "Su cita se ha cancelado – {business}", "heading": "Su cita se ha cancelado",
                      "body": "Su cita ({what}) del {when} se ha cancelado. Contáctenos si desea una nueva hora."},
        "owner_attention": {"subject": "Una cita requiere su atención – {customer}", "heading": "Una cita requiere su atención",
                            "body": "{reason} Abra la cita y decida qué hacer."},
        "delivery_failure": {"subject": "No se pudo entregar un mensaje a {customer}", "heading": "No se pudo entregar un mensaje",
                             "body": "El mensaje «{message}» a {customer} ({channel}) no se entregó: {error}. Contacte con el cliente por otra vía para no perder la cita."},
        "reasons": {"calendar_failed": "La cita está en Dialogbot, pero no se pudo guardar en su calendario.",
                    "needs_confirmation": "La cita se hizo cuando no se podía leer su calendario y debe confirmarla un empleado."},
        "rows": {"what": "Qué", "when": "Cuándo", "new_when": "Nueva hora", "customer": "Cliente", "channel": "Canal"},
        "channels": {"sms": "SMS", "email": "correo electrónico"},
        "hello": "Hola, {first}:", "button": "Abrir citas",
        "footer": "Recibe este mensaje porque tiene una cita con {business}. Enviado a través de Dialogbot.",
        "sample": {"customer": "Lucía García", "what": "Inspección", "error": "el número no existe"},
    },
    "fr": {
        "labels": {"request_receipt": "Demande reçue", "confirmed": "Rendez-vous confirmé", "reminder": "Rappel",
                   "proposed_change": "Nouvel horaire proposé", "rescheduled": "Rendez-vous déplacé", "cancelled": "Rendez-vous annulé",
                   "owner_attention": "Votre attention est requise", "delivery_failure": "Échec de l'envoi"},
        "request_receipt": {"sms": "{greeting}Votre demande pour {what}, {when}, est bien enregistrée. Nous confirmerons rapidement.",
                            "subject": "Nous avons bien reçu votre demande – {business}", "heading": "Nous avons bien reçu votre demande",
                            "body": "Nous avons enregistré votre demande pour {what}, {when}. L'horaire n'est définitif qu'après notre confirmation ; nous revenons vers vous au plus vite."},
        "confirmed": {"sms": "{greeting}Votre rendez-vous chez {business} est confirmé : {what}, {when}.",
                      "subject": "Votre rendez-vous est confirmé – {business}", "heading": "Votre rendez-vous est confirmé",
                      "body": "Au plaisir de vous voir. Contactez-nous si l'horaire ne vous convient plus."},
        "reminder": {"sms": "{greeting}Rappel : votre rendez-vous chez {business} est le {when} ({what}).",
                     "subject": "Rappel : votre rendez-vous le {when}", "heading": "Rappel de votre rendez-vous",
                     "body": "Vous avez rendez-vous chez {business} le {when}. Prévenez-nous à temps si vous êtes empêché."},
        "proposed_change": {"sms": "{greeting}{business} vous propose un nouvel horaire : {new_when}. Cela vous convient-il ?",
                            "subject": "Proposition de nouvel horaire – {business}", "heading": "Nous vous proposons un nouvel horaire",
                            "body": "Nous vous proposons de déplacer votre rendez-vous ({what}) du {when} au {new_when}. Votre horaire actuel reste valable jusqu'à votre réponse."},
        "rescheduled": {"sms": "{greeting}Votre rendez-vous chez {business} est déplacé au {new_when} ({what}).",
                        "subject": "Votre rendez-vous a été déplacé – {business}", "heading": "Votre rendez-vous a été déplacé",
                        "body": "Votre rendez-vous ({what}) a été déplacé du {when} au {new_when}."},
        "cancelled": {"sms": "{greeting}Votre rendez-vous chez {business} du {when} est annulé.",
                      "subject": "Votre rendez-vous est annulé – {business}", "heading": "Votre rendez-vous est annulé",
                      "body": "Votre rendez-vous ({what}) du {when} est annulé. Contactez-nous si vous souhaitez un nouvel horaire."},
        "owner_attention": {"subject": "Un rendez-vous demande votre attention – {customer}", "heading": "Un rendez-vous demande votre attention",
                            "body": "{reason} Ouvrez le rendez-vous et décidez de la suite."},
        "delivery_failure": {"subject": "Un message à {customer} n'a pas pu être remis", "heading": "Un message n'a pas pu être remis",
                             "body": "Le message « {message} » à {customer} ({channel}) n'a pas été remis : {error}. Contactez le client autrement pour ne pas perdre le rendez-vous."},
        "reasons": {"calendar_failed": "Le rendez-vous figure dans Dialogbot, mais n'a pas pu être inscrit dans votre agenda.",
                    "needs_confirmation": "Le rendez-vous a été pris alors que votre agenda était illisible ; un membre de l'équipe doit le confirmer."},
        "rows": {"what": "Quoi", "when": "Quand", "new_when": "Nouvel horaire", "customer": "Client", "channel": "Canal"},
        "channels": {"sms": "SMS", "email": "e-mail"},
        "hello": "Bonjour {first},", "button": "Ouvrir les rendez-vous",
        "footer": "Vous recevez ce message car vous avez un rendez-vous chez {business}. Envoyé via Dialogbot.",
        "sample": {"customer": "Camille Martin", "what": "Visite", "error": "le numéro n'existe pas"},
    },
    "it": {
        "labels": {"request_receipt": "Richiesta ricevuta", "confirmed": "Appuntamento confermato", "reminder": "Promemoria",
                   "proposed_change": "Nuovo orario proposto", "rescheduled": "Appuntamento spostato", "cancelled": "Appuntamento annullato",
                   "owner_attention": "Richiede la Sua attenzione", "delivery_failure": "Consegna non riuscita"},
        "request_receipt": {"sms": "{greeting}Abbiamo ricevuto la Sua richiesta per {what}, {when}. Le confermeremo presto.",
                            "subject": "Abbiamo ricevuto la Sua richiesta – {business}", "heading": "Abbiamo ricevuto la Sua richiesta",
                            "body": "Abbiamo registrato la Sua richiesta per {what}, {when}. L'orario è definitivo solo dopo la nostra conferma; La ricontatteremo il prima possibile."},
        "confirmed": {"sms": "{greeting}Il Suo appuntamento presso {business} è confermato: {what}, {when}.",
                      "subject": "Il Suo appuntamento è confermato – {business}", "heading": "Il Suo appuntamento è confermato",
                      "body": "La aspettiamo. Ci contatti se l'orario non Le va più bene."},
        "reminder": {"sms": "{greeting}Promemoria: il Suo appuntamento presso {business} è {when} ({what}).",
                     "subject": "Promemoria: il Suo appuntamento {when}", "heading": "Promemoria del Suo appuntamento",
                     "body": "Ha un appuntamento presso {business} {when}. Ci avvisi per tempo se non può venire."},
        "proposed_change": {"sms": "{greeting}{business} propone di spostare il Suo appuntamento a {new_when}. Le va bene?",
                            "subject": "Proposta di nuovo orario – {business}", "heading": "Le proponiamo un nuovo orario",
                            "body": "Le proponiamo di spostare il Suo appuntamento ({what}) da {when} a {new_when}. L'orario attuale resta valido finché non ci risponde."},
        "rescheduled": {"sms": "{greeting}Il Suo appuntamento presso {business} è spostato a {new_when} ({what}).",
                        "subject": "Il Suo appuntamento è stato spostato – {business}", "heading": "Il Suo appuntamento è stato spostato",
                        "body": "Il Suo appuntamento ({what}) è stato spostato da {when} a {new_when}."},
        "cancelled": {"sms": "{greeting}Il Suo appuntamento presso {business} di {when} è annullato.",
                      "subject": "Il Suo appuntamento è stato annullato – {business}", "heading": "Il Suo appuntamento è stato annullato",
                      "body": "Il Suo appuntamento ({what}) di {when} è stato annullato. Ci contatti se desidera un nuovo orario."},
        "owner_attention": {"subject": "Un appuntamento richiede la Sua attenzione – {customer}", "heading": "Un appuntamento richiede la Sua attenzione",
                            "body": "{reason} Apra l'appuntamento e decida come procedere."},
        "delivery_failure": {"subject": "Non è stato possibile consegnare un messaggio a {customer}", "heading": "Un messaggio non è stato consegnato",
                             "body": "Il messaggio «{message}» a {customer} ({channel}) non è stato consegnato: {error}. Contatti il cliente in altro modo, così l'appuntamento non va perso."},
        "reasons": {"calendar_failed": "L'appuntamento è in Dialogbot, ma non è stato possibile scriverlo nel Suo calendario.",
                    "needs_confirmation": "L'appuntamento è stato preso mentre il calendario non era leggibile e deve essere confermato da un collaboratore."},
        "rows": {"what": "Cosa", "when": "Quando", "new_when": "Nuovo orario", "customer": "Cliente", "channel": "Canale"},
        "channels": {"sms": "SMS", "email": "e-mail"},
        "hello": "Buongiorno {first},", "button": "Apri appuntamenti",
        "footer": "Riceve questo messaggio perché ha un appuntamento presso {business}. Inviato tramite Dialogbot.",
        "sample": {"customer": "Giulia Rossi", "what": "Sopralluogo", "error": "il numero non esiste"},
    },
    "no": {
        "labels": {"request_receipt": "Forespørsel mottatt", "confirmed": "Time bekreftet", "reminder": "Påminnelse",
                   "proposed_change": "Forslag til ny time", "rescheduled": "Time flyttet", "cancelled": "Time avlyst",
                   "owner_attention": "Krever din oppmerksomhet", "delivery_failure": "Levering mislyktes"},
        "request_receipt": {"sms": "{greeting}Vi har mottatt forespørselen din om {what} {when}. Vi bekrefter timen så snart som mulig.",
                            "subject": "Vi har mottatt forespørselen din – {business}", "heading": "Vi har mottatt forespørselen din",
                            "body": "Vi har registrert forespørselen din om {what} {when}. Timen er ikke endelig før vi har bekreftet den – du hører fra oss så snart som mulig."},
        "confirmed": {"sms": "{greeting}Timen din hos {business} er bekreftet: {what} {when}.",
                      "subject": "Timen din er bekreftet – {business}", "heading": "Timen din er bekreftet",
                      "body": "Vi gleder oss til å se deg. Ta kontakt hvis tiden ikke lenger passer."},
        "reminder": {"sms": "{greeting}Påminnelse: Du har time hos {business} {when} ({what}).",
                     "subject": "Påminnelse: timen din {when}", "heading": "Påminnelse om timen din",
                     "body": "Du har time hos {business} {when}. Gi oss beskjed i god tid hvis du blir forhindret."},
        "proposed_change": {"sms": "{greeting}{business} foreslår å flytte timen din til {new_when}. Ta kontakt og si om det passer.",
                            "subject": "Forslag til ny time – {business}", "heading": "Vi foreslår en ny time",
                            "body": "Vi foreslår å flytte timen din ({what}) fra {when} til {new_when}. Den nåværende timen gjelder til du har svart oss."},
        "rescheduled": {"sms": "{greeting}Timen din hos {business} er flyttet til {new_when} ({what}).",
                        "subject": "Timen din er flyttet – {business}", "heading": "Timen din er flyttet",
                        "body": "Timen din ({what}) er flyttet fra {when} til {new_when}."},
        "cancelled": {"sms": "{greeting}Timen din hos {business} {when} er avlyst. Ta kontakt hvis du vil ha en ny time.",
                      "subject": "Timen din er avlyst – {business}", "heading": "Timen din er avlyst",
                      "body": "Timen din ({what}) {when} er avlyst. Ta kontakt hvis du vil ha en ny time."},
        "owner_attention": {"subject": "En avtale krever din oppmerksomhet – {customer}", "heading": "En avtale krever din oppmerksomhet",
                            "body": "{reason} Åpne avtalen og ta stilling."},
        "delivery_failure": {"subject": "En melding til {customer} kunne ikke leveres", "heading": "En melding kunne ikke leveres",
                             "body": "Meldingen «{message}» til {customer} ({channel}) ble ikke levert: {error}. Kontakt kunden på annen måte, så avtalen ikke går tapt."},
        "reasons": {"calendar_failed": "Avtalen står i Dialogbot, men kunne ikke skrives i kalenderen deres.",
                    "needs_confirmation": "Avtalen ble laget mens kalenderen ikke kunne leses, og må bekreftes av en medarbeider."},
        "rows": {"what": "Hva", "when": "Når", "new_when": "Ny tid", "customer": "Kunde", "channel": "Kanal"},
        "channels": {"sms": "SMS", "email": "e-post"},
        "hello": "Hei {first},", "button": "Åpne avtaler",
        "footer": "Du får denne meldingen fordi du har en avtale hos {business}. Sendt via Dialogbot.",
        "sample": {"customer": "Ingrid Hansen", "what": "Befaring", "error": "nummeret finnes ikke"},
    },
    "sv": {
        "labels": {"request_receipt": "Förfrågan mottagen", "confirmed": "Tid bekräftad", "reminder": "Påminnelse",
                   "proposed_change": "Förslag på ny tid", "rescheduled": "Tid flyttad", "cancelled": "Tid avbokad",
                   "owner_attention": "Kräver din uppmärksamhet", "delivery_failure": "Leverans misslyckades"},
        "request_receipt": {"sms": "{greeting}Vi har tagit emot din förfrågan om {what} {when}. Vi bekräftar tiden så snart som möjligt.",
                            "subject": "Vi har tagit emot din förfrågan – {business}", "heading": "Vi har tagit emot din förfrågan",
                            "body": "Vi har registrerat din förfrågan om {what} {when}. Tiden är inte slutgiltig förrän vi har bekräftat den – du hör av oss så snart som möjligt."},
        "confirmed": {"sms": "{greeting}Din tid hos {business} är bekräftad: {what} {when}.",
                      "subject": "Din tid är bekräftad – {business}", "heading": "Din tid är bekräftad",
                      "body": "Vi ser fram emot att träffa dig. Hör av dig om tiden inte längre passar."},
        "reminder": {"sms": "{greeting}Påminnelse: Du har en tid hos {business} {when} ({what}).",
                     "subject": "Påminnelse: din tid {when}", "heading": "Påminnelse om din tid",
                     "body": "Du har en tid hos {business} {when}. Meddela oss i god tid om du får förhinder."},
        "proposed_change": {"sms": "{greeting}{business} föreslår att flytta din tid till {new_when}. Hör av dig och säg om det passar.",
                            "subject": "Förslag på ny tid – {business}", "heading": "Vi föreslår en ny tid",
                            "body": "Vi föreslår att flytta din tid ({what}) från {when} till {new_when}. Din nuvarande tid gäller tills du har svarat oss."},
        "rescheduled": {"sms": "{greeting}Din tid hos {business} är flyttad till {new_when} ({what}).",
                        "subject": "Din tid är flyttad – {business}", "heading": "Din tid är flyttad",
                        "body": "Din tid ({what}) är flyttad från {when} till {new_when}."},
        "cancelled": {"sms": "{greeting}Din tid hos {business} {when} är avbokad. Hör av dig om du vill boka en ny tid.",
                      "subject": "Din tid är avbokad – {business}", "heading": "Din tid är avbokad",
                      "body": "Din tid ({what}) {when} är avbokad. Hör av dig om du vill boka en ny tid."},
        "owner_attention": {"subject": "En bokning kräver din uppmärksamhet – {customer}", "heading": "En bokning kräver din uppmärksamhet",
                            "body": "{reason} Öppna bokningen och ta ställning."},
        "delivery_failure": {"subject": "Ett meddelande till {customer} kunde inte levereras", "heading": "Ett meddelande kunde inte levereras",
                             "body": "Meddelandet «{message}» till {customer} ({channel}) levererades inte: {error}. Kontakta kunden på annat sätt så att bokningen inte går förlorad."},
        "reasons": {"calendar_failed": "Bokningen finns i Dialogbot men kunde inte skrivas till er kalender.",
                    "needs_confirmation": "Bokningen gjordes medan kalendern inte kunde läsas och måste bekräftas av en medarbetare."},
        "rows": {"what": "Vad", "when": "När", "new_when": "Ny tid", "customer": "Kund", "channel": "Kanal"},
        "channels": {"sms": "SMS", "email": "e-post"},
        "hello": "Hej {first},", "button": "Öppna bokningar",
        "footer": "Du får det här meddelandet eftersom du har en bokning hos {business}. Skickat via Dialogbot.",
        "sample": {"customer": "Elin Andersson", "what": "Besiktning", "error": "numret finns inte"},
    },
}


@dataclass
class Context:
    """What a message is about. `when`/`new_when` are datetimes; they are written in the message's language."""
    business: str
    customer: str
    what: str
    when: datetime
    tz: str = "Europe/Copenhagen"
    new_when: datetime | None = None
    reason: str = "calendar_failed"  # owner_attention
    failed_variant: str = "confirmed"  # delivery_failure: which message did not arrive
    channel: str = "sms"  # delivery_failure
    error: str = ""  # delivery_failure: the provider's reason


def _table(lang: str | None) -> dict:
    return TEXTS.get(normalize(lang)) or TEXTS[DEFAULT]


def segments(text: str) -> dict:
    """How the text travels as SMS: GSM-7 (160 / 153 per part) or UCS-2 (70 / 67 per part)."""
    if all(c in _GSM or c in _GSM_EXT for c in text):
        units, single, multi, enc = sum(2 if c in _GSM_EXT else 1 for c in text), 160, 153, "GSM-7"
    else:
        units, single, multi, enc = len(text), 70, 67, "UCS-2"
    parts = 1 if units <= single else -(-units // multi)
    return {"chars": len(text), "encoding": enc, "segments": parts}


def _values(ctx: Context, lang: str) -> dict:
    first = (ctx.customer or "").strip().split(" ")[0]
    return {"business": ctx.business, "customer": ctx.customer or "–", "what": ctx.what, "first": first,
            "when": sms.when(ctx.when, ctx.tz, lang),
            "new_when": sms.when(ctx.new_when or ctx.when, ctx.tz, lang),
            "greeting": sms._t(lang, "greeting", first=first) if first else ""}


def render(variant: str, lang: str | None, ctx: Context) -> dict:
    """One message in one language: {"variant", "audience", "lang", "label", "sms": {...} | None, "email": Email}."""
    if variant not in VARIANTS:
        raise ValueError(f"unknown booking message variant: {variant}")
    lang = normalize(lang)
    tb = _table(lang)
    v = _values(ctx, lang)
    t = tb[variant]
    rows_l = tb["rows"]
    if variant in CUSTOMER_VARIANTS:
        text = sms.sign(t["sms"].format(**v), ctx.business, lang)
        rows = [(rows_l["what"], ctx.what), (rows_l["when"], v["when"])]
        if variant in ("proposed_change", "rescheduled"):
            rows.append((rows_l["new_when"], v["new_when"]))
        paragraphs = ([tb["hello"].format(first=v["first"])] if v["first"] else []) + [t["body"].format(**v)]
        mail = Email(subject=t["subject"].format(**v), heading=t["heading"].format(**v), paragraphs=paragraphs, rows=rows,
                     footer_reason=tb["footer"].format(**v), lang=lang, sender=ctx.business,
                     footer_line=ctx.business, preheader=t["body"].format(**v)[:120])
        return {"variant": variant, "audience": "customer", "lang": lang, "label": tb["labels"][variant],
                "sms": {"text": text, **segments(text)}, "email": mail}
    from app.config import get_settings
    from app.modules.integrations.email_texts import t as et

    extra = {"reason": tb["reasons"].get(ctx.reason, tb["reasons"]["calendar_failed"]),
             "message": tb["labels"].get(ctx.failed_variant, ctx.failed_variant),
             "channel": tb["channels"].get(ctx.channel, ctx.channel), "error": ctx.error or "–"}
    rows = [(rows_l["customer"], v["customer"]), (rows_l["what"], ctx.what), (rows_l["when"], v["when"])]
    if variant == "delivery_failure":
        rows.append((rows_l["channel"], extra["channel"]))
    link = f"{get_settings().frontend_base_url.rstrip('/')}/app/aftaler"
    mail = Email(subject=t["subject"].format(**v, **extra), heading=t["heading"].format(**v, **extra),
                 paragraphs=[t["body"].format(**v, **extra)], rows=rows, button_label=tb["button"], button_url=link,
                 footer_reason=et(lang, "footer_account"), lang=lang)
    return {"variant": variant, "audience": "owner", "lang": lang, "label": tb["labels"][variant], "sms": None, "email": mail}


def sample_context(lang: str | None, business: str = "Hansen VVS", tz: str = "Europe/Copenhagen") -> Context:
    s = _table(lang)["sample"]
    return Context(business=business, customer=s["customer"], what=s["what"], tz=tz,
                   when=datetime(2026, 11, 3, 9, 0, tzinfo=ZoneInfo("UTC")),  # Tuesday 3 November, 10:00 Copenhagen
                   new_when=datetime(2026, 11, 4, 13, 0, tzinfo=ZoneInfo("UTC")), error=s["error"])


def samples(lang: str = "da") -> dict[str, dict]:
    """Every variant with sample data (scripts, tests, the e-mail preview registry)."""
    ctx = sample_context(lang)
    return {v: render(v, lang, ctx) for v in VARIANTS}

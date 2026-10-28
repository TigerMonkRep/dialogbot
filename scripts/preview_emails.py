"""Write every outgoing e-mail and SMS template to a folder so they can be looked at (light, dark and phone width).

    python -m scripts.preview_emails [out-dir]        # default: var/email-preview
    open var/email-preview/index.html

`index.html` shows each mail three times: light, dark (the dark-mode rules switched on)
and at phone width. To take screenshots of all of them: `node web/scripts/shoot-emails.mjs`.
The samples come from `email_templates.samples()` and `sms_templates.samples()`; nothing is sent.
"""
from __future__ import annotations

import html
import sys
from pathlib import Path

from app.modules.integrations import email_templates, sms_templates

INDEX = """<!doctype html><html lang="da"><meta charset="utf-8"><title>E-mail-preview</title>
<style>body{{font:15px/1.5 Inter,system-ui,sans-serif;margin:24px;background:#fff;color:#14213D}}
h1{{font-size:26px}}h2{{margin:40px 0 4px;font-size:20px}}p.s{{margin:0 0 12px;color:#5B6475}}
.row{{display:flex;gap:20px;align-items:flex-start;flex-wrap:wrap}}
figure{{margin:0}}figcaption{{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:#5B6475;margin:0 0 6px}}
iframe{{border:1.5px solid #D6DEEA;border-radius:12px;background:#fff}}
.sms{{max-width:340px;background:#EEF4FB;border:1.5px solid #D6DEEA;border-radius:16px;padding:12px 14px;margin:6px 0}}
.sms small{{display:block;color:#5B6475}}</style>
<h1>E-mail- og SMS-skabeloner</h1><p class="s">Eksempeldata. Intet er sendt.</p>{body}</html>"""


def build(out: Path) -> list[str]:
    out.mkdir(parents=True, exist_ok=True)
    parts: list[str] = []
    for key, mail in email_templates.samples().items():
        (out / f"{key}.html").write_text(mail.html(), encoding="utf-8")
        (out / f"{key}.txt").write_text(mail.text(), encoding="utf-8")
        parts.append(
            f'<h2 id="{key}">{html.escape(key)}</h2><p class="s">Emne: {html.escape(mail.subject)}</p><div class="row">'
            f'<figure><figcaption>Lys</figcaption><iframe src="{key}.html" width="640" height="760" title="{key} lys"></iframe></figure>'
            f'<figure><figcaption>Mørk</figcaption><iframe src="{key}.dark.html" width="640" height="760" title="{key} mørk"></iframe></figure>'
            f'<figure><figcaption>Telefon (390 px)</figcaption><iframe src="{key}.html" width="390" height="760" title="{key} telefon"></iframe></figure></div>')
        # Dark twin: the same mail with the dark-mode rules switched on unconditionally (an iframe does not inherit
        # the parent's colour scheme, so `prefers-color-scheme` could not be forced from outside). Real dark-mode
        # rendering is covered by the screenshots, which emulate the scheme in the browser.
        (out / f"{key}.dark.html").write_text(
            mail.html().replace("@media (prefers-color-scheme: dark)", "@media all"), encoding="utf-8")
    sms = "".join(f'<div class="sms"><small>{html.escape(k)} · {len(v)} tegn</small>{html.escape(v)}</div>'
                  for k, v in sms_templates.samples().items())
    parts.append(f'<h2 id="sms">SMS</h2><p class="s">Afsender: virksomhedens navn (højst 11 tegn). Ét segment = 160 tegn.</p>{sms}')
    (out / "index.html").write_text(INDEX.format(body="".join(parts)), encoding="utf-8")
    return list(email_templates.samples())


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else Path("var/email-preview")
    keys = build(out)
    print(f"{len(keys)} e-mails og {len(sms_templates.samples())} SMS skrevet til {out}/ – åbn {out}/index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

"""`read_page()`: the page as compact accessibility-style text, never HTML.

A small script walks the DOM in document order, gives every interactive element a fresh `data-dbref="eN"` and returns
one line per element. Refs from an older read are removed, so a ref is only valid until the next `read_page()`.
Password values are never returned. The structured `elements` list stays inside the worker (the playbooks use it;
the LLM only sees the text).
"""
from __future__ import annotations

MAX_LINES = 400
MAX_CHARS = 16000

READ_JS = r"""
() => {
  document.querySelectorAll('[data-dbref]').forEach(e => e.removeAttribute('data-dbref'));
  const SKIP = new Set(['SCRIPT','STYLE','NOSCRIPT','TEMPLATE','HEAD','SVG','META','LINK']);
  const BTN_INPUT = new Set(['submit','button','reset','image']);
  const lines = [], elements = [];
  let n = 0;
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const hidden = el => {
    if (el.hidden || el.getAttribute('aria-hidden') === 'true') return true;
    const cs = getComputedStyle(el);
    return cs.display === 'none' || cs.visibility === 'hidden';
  };
  const labelOf = el => {
    const a = el.getAttribute('aria-label'); if (a) return clean(a);
    const lb = el.getAttribute('aria-labelledby');
    if (lb) { const t = lb.split(/\s+/).map(i => document.getElementById(i)).filter(Boolean).map(x => x.textContent).join(' '); if (clean(t)) return clean(t); }
    if (el.id) { const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]'); if (l) return clean(l.textContent); }
    const wrap = el.closest('label'); if (wrap) return clean(wrap.textContent);
    return '';
  };
  const roleOf = el => {
    const tag = el.tagName, type = (el.getAttribute('type') || '').toLowerCase();
    const r = el.getAttribute('role');
    if (tag === 'A' && el.hasAttribute('href')) return 'link';
    if (tag === 'BUTTON') return 'button';
    if (tag === 'INPUT') {
      if (type === 'hidden') return null;
      if (BTN_INPUT.has(type)) return 'button';
      if (type === 'checkbox') return 'checkbox';
      if (type === 'radio') return 'radio';
      return 'textbox';
    }
    if (tag === 'TEXTAREA') return 'textbox';
    if (tag === 'SELECT') return 'combobox';
    if (r && ['button','link','tab','menuitem','option','radio','checkbox','switch'].includes(r)) return r;
    return null;
  };
  const emit = (text) => { lines.push(text); };
  const walk = node => {
    if (node.nodeType === 3) { const t = clean(node.textContent); if (t) emit('text "' + t.slice(0, 200) + '"'); return; }
    if (node.nodeType !== 1) return;
    const el = node, tag = el.tagName;
    if (SKIP.has(tag.toUpperCase()) || hidden(el)) return;
    if (tag === 'IFRAME') {
      const ref = 'e' + (++n); el.setAttribute('data-dbref', ref);
      const src = el.getAttribute('src') || '';
      elements.push({ref, role: 'iframe', name: '', tag: 'iframe', src});
      emit('[' + ref + '] iframe src=' + JSON.stringify(src.slice(0, 120))); return;
    }
    if (/^H[1-6]$/.test(tag)) { const t = clean(el.textContent); if (t) emit('heading' + tag[1] + ' "' + t.slice(0, 200) + '"'); return; }
    const role = roleOf(el);
    if (role) {
      const type = (el.getAttribute('type') || (tag === 'TEXTAREA' ? 'textarea' : '')).toLowerCase();
      const label = labelOf(el);
      let name = label;
      if (!name && role !== 'textbox' && role !== 'combobox') name = clean(el.innerText || el.textContent);
      if (!name && tag === 'INPUT' && BTN_INPUT.has(type)) name = clean(el.value);
      if (!name) name = clean(el.getAttribute('placeholder') || el.getAttribute('title') || el.getAttribute('alt') || '');
      if (!name && role !== 'textbox') name = clean(el.innerText || el.textContent);
      if (el.getAttribute('type') !== 'checkbox' && el.getAttribute('type') !== 'radio' && !['textbox','combobox'].includes(role) && !name) {
        const img = el.querySelector('img[alt]'); if (img) name = clean(img.getAttribute('alt'));
      }
      const rect = el.getBoundingClientRect();
      const isChoice = role === 'checkbox' || role === 'radio';
      if (!isChoice && rect.width === 0 && rect.height === 0) return;
      const ref = 'e' + (++n); el.setAttribute('data-dbref', ref);
      const meta = {ref, role, name: name.slice(0, 200), tag: tag.toLowerCase(), type, field_name: el.getAttribute('name') || '',
                    autocomplete: el.getAttribute('autocomplete') || '', id: el.id || '', disabled: !!el.disabled};
      let extra = '';
      if (type && role === 'textbox') extra += ' type=' + type;
      if (el.required) extra += ' required';
      if (el.disabled) extra += ' disabled';
      if (isChoice && el.checked) extra += ' checked';
      if (role === 'textbox' && type !== 'password' && el.value) extra += ' value=' + JSON.stringify(el.value.slice(0, 100));
      if (role === 'link') { const h = el.getAttribute('href') || ''; meta.href = h; }
      if (role === 'combobox') {
        const opts = Array.from(el.options).map(o => ({value: o.value, label: clean(o.textContent)}));
        meta.options = opts;
        extra += ' options=[' + opts.map(o => JSON.stringify(o.label)).join(', ') + ']';
        const sel = el.options[el.selectedIndex]; if (sel) extra += ' selected=' + JSON.stringify(clean(sel.textContent));
      }
      elements.push(meta);
      emit('[' + ref + '] ' + role + ' ' + JSON.stringify(meta.name) + extra);
      return;
    }
    for (const c of el.childNodes) walk(c);
  };
  walk(document.body || document.documentElement);
  return {title: document.title, url: location.href, lines, elements};
}
"""

# Reads what an element IS (used right before click/type/select to decide, from the live DOM, not from the last read).
ELEMENT_FACTS_JS = r"""
el => {
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const labelOf = () => {
    const parts = [];
    if (el.labels) for (const l of el.labels) parts.push(clean(l.textContent));
    const lb = el.getAttribute('aria-labelledby');
    if (lb) lb.split(/\s+/).forEach(i => { const x = document.getElementById(i); if (x) parts.push(clean(x.textContent)); });
    return parts.join(' ');
  };
  return {
    tag: el.tagName.toLowerCase(), type: (el.getAttribute('type') || '').toLowerCase(),
    field_name: el.getAttribute('name') || '', id: el.id || '', autocomplete: el.getAttribute('autocomplete') || '',
    placeholder: el.getAttribute('placeholder') || '', aria_label: el.getAttribute('aria-label') || '',
    title: el.getAttribute('title') || '', label: labelOf(), value: el.tagName === 'INPUT' ? (el.value || '') : '',
    text: clean(el.innerText || el.textContent),
    img_alt: Array.from(el.querySelectorAll('img[alt]')).map(i => i.getAttribute('alt')).join(' '),
    disabled: !!el.disabled, readonly: !!el.readOnly,
    in_form_action: el.form ? (el.form.getAttribute('action') || '') : '',
  };
}
"""

CAPTCHA_LOGIN_JS = r"""
(captchaSelectors) => {
  const vis = el => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
                      return cs.display !== 'none' && cs.visibility !== 'hidden' && (r.width > 0 || r.height > 0); };
  const frames = Array.from(document.querySelectorAll('iframe')).map(f => f.getAttribute('src') || f.getAttribute('data-src') || '');
  const scripts = Array.from(document.querySelectorAll('script[src]')).map(s => s.getAttribute('src'));
  let marked = false;
  for (const s of captchaSelectors) { try { if (document.querySelector(s)) { marked = true; break; } } catch (e) {} }
  const pw = Array.from(document.querySelectorAll('input[type=password]')).some(vis);
  const text = (document.body ? document.body.innerText : '').slice(0, 20000);
  return {frames, scripts, marked, password_field: pw, text};
}
"""


def format_page(data: dict) -> str:
    lines = data["lines"]
    head = f'page {data["title"]!r} {data["url"]}'
    truncated = False
    if len(lines) > MAX_LINES:
        lines, truncated = lines[:MAX_LINES], True
    text = head + "\n" + "\n".join(lines)
    if len(text) > MAX_CHARS:
        text, truncated = text[:MAX_CHARS], True
    if truncated:
        text += "\n… (afkortet)"
    return text

import logging
import re

from django.conf import settings
from django.utils import translation as django_translation

logger = logging.getLogger(__name__)

# Matches gettext/format placeholders: %(name)s, %s, %d, %(count).2f, {name}, {name!s}
_PLACEHOLDER_RE = re.compile(
    r"%(?:\((?P<pct_name>[^)]+)\)[sd]|[-+ #0]*\d*(?:\.\d+)?[sd])"
    r"|(?<!\{)\{(?P<fmt_name>[a-zA-Z_][a-zA-Z0-9_]*)(?::[^{}]*)?\}(?!\})"
)

# lang -> (catalog object, payload); the catalog reference doubles as an
# invalidation token (Django rebuilds it when locale settings change).
_ENTRIES_CACHE = {}


def get_language_codes():
    try:
        codes = getattr(settings, "MODELTRANSLATION_LANGUAGES", None)
        if isinstance(codes, str):
            codes = [codes]
        if not codes:
            languages = getattr(settings, "LANGUAGES", None)
            if isinstance(languages, str):
                languages = [languages]
            if languages:
                codes = [
                    lang[0] if isinstance(lang, (tuple, list)) else str(lang)
                    for lang in languages
                ]
        if not codes:
            codes = ["en"]
        return [str(code) for code in codes]
    except Exception as exc:
        logger.warning("get_language_codes falling back to ['en']: %s", exc)
        return ["en"]


def translate_message(message, lang_code):
    try:
        # `message` may have been materialised in the active request language
        # (DRF evaluates its lazy error text when the exception is raised).
        # Resolve it back to its canonical English msgid first, so the lookup
        # never depends on the language the caller happened to run in.
        canonical = canonical_msgid(message)
        with django_translation.override(lang_code):
            translated = str(django_translation.gettext(canonical))
        if translated != canonical:
            return translated
        return _render_from_template(canonical, lang_code) or translated
    except Exception as exc:
        logger.warning("translate_message(%r, %r) failed: %s", message, lang_code, exc)
        return str(message)


def canonical_msgid(message, lang_code=None):
    """Return the canonical English msgid for `message`.

    `message` is usually in the currently active language. Django merges the
    project (LOCALE_PATHS), app and core catalogs into one catalog per
    language, so inverting that catalog maps a translated string back to its
    English msgid. Messages whose parameters were already substituted
    (``Method "GET" not allowed.``) fall back to matching the catalog's
    translated template. Unknown strings are returned unchanged.
    """
    message = str(message)
    if lang_code is None:
        lang_code = django_translation.get_language() or getattr(
            settings, "LANGUAGE_CODE", "en"
        )
    language = str(lang_code or "en").replace("_", "-")
    if language.split("-")[0].lower() == "en":
        # English is the source language: the message already is a msgid.
        return message

    try:
        _items, reverse, templates = _entries(language)
        msgid = reverse.get(message)
        if msgid is not None:
            return msgid
        best = None
        for pair in templates:
            msgstr_re = pair["msgstr_re"]
            if msgstr_re is None or pair["msgstr_literal_len"] == 0:
                continue
            match = msgstr_re.fullmatch(message)
            if match is None:
                continue
            score = (pair["msgstr_literal_len"], -pair["msgstr_nfields"])
            if best is None or score > best[0]:
                best = (score, pair, match)
        if best is not None:
            named, positional = _extract(best[2], best[1]["msgstr_fields"])
            return _fill(best[1]["msgid"], named, positional)
        return message
    except Exception as exc:
        logger.warning("canonical_msgid(%r, %r) failed: %s", message, language, exc)
        return message


# --------------------------------------------------------------------------- catalog access
def _entries(language):
    """Return ``(items, reverse, templates)`` for a language, cached per catalog."""
    from django.utils.translation import trans_real

    catalog = trans_real.translation(language)._catalog
    cached = _ENTRIES_CACHE.get(language)
    if cached is not None and cached[0] is catalog:
        return cached[1]

    items = []
    reverse = {}
    templates = []
    for msgid, msgstr in catalog.items():
        if not isinstance(msgid, str) or not msgid or not isinstance(msgstr, str):
            continue
        items.append((msgid, msgstr))
        reverse.setdefault(msgstr, msgid)
        msgid_re, msgid_fields, msgid_literal_len = _compile_template(msgid)
        msgstr_re, msgstr_fields, msgstr_literal_len = _compile_template(msgstr)
        if msgid_re is not None or msgstr_re is not None:
            templates.append(
                {
                    "msgid": msgid,
                    "msgstr": msgstr,
                    "msgid_re": msgid_re,
                    "msgid_fields": msgid_fields,
                    "msgid_literal_len": msgid_literal_len,
                    "msgid_nfields": len(msgid_fields or ()),
                    "msgstr_re": msgstr_re,
                    "msgstr_fields": msgstr_fields,
                    "msgstr_literal_len": msgstr_literal_len,
                    "msgstr_nfields": len(msgstr_fields or ()),
                }
            )

    payload = (items, reverse, templates)
    _ENTRIES_CACHE[language] = (catalog, payload)
    return payload


def _render_from_template(canonical, language):
    """Translate a parameterised message whose placeholders were already filled."""
    _items, _reverse, templates = _entries(language)
    best = None
    for pair in templates:
        msgid_re = pair["msgid_re"]
        if msgid_re is None or pair["msgid_literal_len"] == 0:
            continue
        match = msgid_re.fullmatch(canonical)
        if match is None:
            continue
        score = (pair["msgid_literal_len"], -pair["msgid_nfields"])
        if best is None or score > best[0]:
            best = (score, pair, match)
    if best is None:
        return None
    named, positional = _extract(best[2], best[1]["msgid_fields"])
    return _fill(best[1]["msgstr"], named, positional)


def _compile_template(template):
    """Compile a template into (regex, fields, literal_len), or (None, None, 0)."""
    fields = []
    parts = []
    literal_len = 0
    index = 0
    for match in _PLACEHOLDER_RE.finditer(template):
        literal = template[index : match.start()]
        literal_len += len(literal)
        parts.append(re.escape(literal))
        name = match.group("pct_name") or match.group("fmt_name")
        if name:
            fields.append(("named", name))
        else:
            fields.append(("pos", None))
        parts.append(f"(?P<ph{len(fields) - 1}>.*?)")
        index = match.end()
    if not fields:
        return None, None, 0
    tail = template[index:]
    literal_len += len(tail)
    parts.append(re.escape(tail))
    return re.compile("".join(parts), re.DOTALL), fields, literal_len


def _extract(match, fields):
    named = {}
    positional = []
    for position, (kind, name) in enumerate(fields):
        value = match.group(f"ph{position}")
        if kind == "named":
            named[name] = value
        else:
            positional.append(value)
    return named, positional


def _fill(template, named, positional):
    """Substitute values captured from a sibling template into `template`.

    The target is re-scanned so translations may reorder placeholders; named
    placeholders must keep their names (as gettext requires anyway).
    """
    parts = []
    index = 0
    position = 0
    for match in _PLACEHOLDER_RE.finditer(template):
        parts.append(template[index : match.start()])
        name = match.group("pct_name") or match.group("fmt_name")
        if name:
            parts.append(str(named.get(name, match.group(0))))
        elif position < len(positional):
            parts.append(str(positional[position]))
            position += 1
        else:
            parts.append(match.group(0))
        index = match.end()
    parts.append(template[index:])
    return "".join(parts)

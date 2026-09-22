"""Turning one line of typed or shared text into a name and a link.

Capture has to cost nothing, so the box takes a single string and this module
guesses the rest. Every guess it makes is editable in the triage screen, and
`Capture.raw` keeps the original either way — so the rules below are allowed to
be wrong, but they are not allowed to be clever. A parser that silently
reformats what the operator typed would cost more trust than it saves taps.
"""

import re
from urllib.parse import unquote, urlparse

# A bare http(s) token. Trailing punctuation is excluded from the match rather
# than stripped afterwards, so "see https://example.com/x, then call" does not
# file a URL ending in a comma.
_URL = re.compile(r"https?://[^\s<>\"']+[^\s<>\"'.,;:!?)\]}]")

# Profile URLs whose slug is reliably a person's name. Deliberately a short
# allowlist: guessing a name from an arbitrary path produces things like
# "Careers Apply Now", which is worse than an empty field because it looks
# filled in.
_PROFILE_PATHS = (
    ("linkedin.com", "/in/"),
    ("xing.com", "/profile/"),
)

# Slug segments that are an id rather than part of a name: LinkedIn appends a
# short hex disambiguator ("jane-doe-4b21"), and some exports append a counter.
_ID_SEGMENT = re.compile(r"^(?:[0-9]+|[0-9a-f]{4,})$", re.IGNORECASE)

# Separators people type around a link — dashes, pipes, bullets, commas. Lifting
# the URL out of the middle of a line leaves these stranded at the splice, so
# each side is trimmed on the edge that faced the URL as well as on its outer
# edge.
_EDGE_NOISE = re.compile(r"^[\s\-–—|•·,;:/]+|[\s\-–—|•·,;:/]+$")


def name_from_profile_url(url: str) -> str | None:
    """A person's name from a profile URL slug, when the host makes that safe.

    `https://www.linkedin.com/in/jane-doe-4b21/` -> `Jane Doe`.

    Returns None for any other URL. The caller treats that as "no name yet",
    which the triage screen shows as an empty field to fill in — an honest
    blank beats a confident guess at a person's name.
    """
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().removeprefix("www.")
    except ValueError:
        # urlparse raises on a malformed IPv6 literal. A capture is never worth
        # a 500, and `raw` still holds whatever this was.
        return None
    path = parsed.path
    for domain, prefix in _PROFILE_PATHS:
        if host != domain and not host.endswith(f".{domain}"):
            continue
        if not path.startswith(prefix):
            continue
        slug = unquote(path[len(prefix) :]).strip("/").split("/")[0]
        parts = [p for p in re.split(r"[-_]+", slug) if p]
        # Drop the trailing id, but only from the end: a name that *starts*
        # with digits is odd enough to leave alone for a human to look at.
        while parts and _ID_SEGMENT.match(parts[-1]):
            parts.pop()
        if not parts:
            return None
        # capitalize(), not title(): title() mangles "o'brien" into "O'Brien"
        # in some locales and "mcdonald" is wrong either way. One rule, applied
        # visibly, is easier to correct than several applied cleverly.
        return " ".join(p[:1].upper() + p[1:] for p in parts)
    return None


def parse_capture(raw: str) -> tuple[str | None, str | None]:
    """Split one captured line into `(name, url)`.

    In order:

    1. The first http(s) token becomes the url.
    2. Whatever text is left over becomes the name — so
       `"Jane Doe https://linkedin.com/in/janedoe"` yields both, in either
       order, which is what pasting from a phone actually produces.
    3. If nothing is left over and the url is a known profile link, the slug
       becomes a suggested name.
    4. No url at all: the whole line is the name.

    Never raises, and never returns an empty string in place of None — a blank
    field and an absent one have to look the same to the UI.
    """
    text = raw.strip()
    if not text:
        return None, None

    match = _URL.search(text)
    if match is None:
        return text, None

    url = match.group(0)
    # Trim each side separately. Trimming the concatenation instead would leave
    # the punctuation that faced the URL stranded in the middle of the name:
    # "Jane https://x, call her" would come out as "Jane , call her".
    before = _EDGE_NOISE.sub("", text[: match.start()])
    after = _EDGE_NOISE.sub("", text[match.end() :])
    # Collapse the whitespace the splice leaves behind, but only runs of it —
    # this is formatting, not interpretation.
    leftover = re.sub(r"\s{2,}", " ", " ".join(p for p in (before, after) if p)).strip()

    if leftover:
        return leftover, url
    return name_from_profile_url(url), url

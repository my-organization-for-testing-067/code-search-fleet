#!/usr/bin/env python3
"""Report each repo's ERROR AND RETRY POSTURE: on a non-2xx, what happens?

`cs strictness` answers "will this consumer REJECT an added field". This is the
second question with the same shape and the same declared-tier evidence, and it
decides a different class of review: WILL THIS CONSUMER EVEN READ THE RESPONSE
BODY?

Two findings it exists for, both from a review log, neither answerable by any
other verb here:

  1. A producer shipped a partial-failure contract -- a "here is what already
     succeeded" field, designed for a caller that reads it on error. The
     consumer discarded the body and auto-retried. The field was worthless, and
     that half was never in the diff.
  2. A producer changed an ERROR shape (a structured 400 body). The impact
     question was "who parses error responses", not "who parses success
     responses", and the additive/strictness framing does not fire on it at all.

Both are the same property: a field added to an error body is invisible to a
caller that calls raise_for_status() and never touches the payload, and a
retried request is a different failure mode from a rejected one.

The evidence is plentiful and declared. Measured across a 43-repo fleet, files
containing each marker: raise_for_status 323, tenacity 219, @Retryable 10,
Retryer 1. Those 323 files raise on a non-2xx WITHOUT reading the body -- every
one a consumer for which a structured error shape is unobservable, and none of
them distinguishable from an attentive consumer in a `cs uses` answer.

FOUR verdicts, and the ordering matters because the third is the one that turns
a producer-side contract into a no-op:

  READS ERROR BODY          some site branches on the status and parses the body
  DISCARDS                  raise-and-propagate; the body is never looked at
  RETRIES, BODY DISCARDED   the above, plus an automatic retry
  MIXED                     both postures in one repo -- the site list decides
  UNKNOWN                   no recognised error handling at all

UNKNOWN IS NOT "READS IT", for the same reason UNKNOWN is not LENIENT in
`cs strictness`: undetermined is not safe. And a wrong answer here is quieter
than a wrong strictness answer -- a rejected field crashes the consumer loudly,
while a discarded field simply never arrives and nobody gets paged.

WHAT IT CANNOT SEE, and says so: a retry configured at the INFRASTRUCTURE layer
-- a service mesh, an ingress, a client-side load balancer -- produces the same
observable behaviour with nothing in the repo to find.

Usage:
  resilience.py <fleet-root> audit           one verdict per repo
  resilience.py <fleet-root> repo <name>     the per-site evidence for one repo
Exit: 0 something was reported, 1 nothing found, 2 the root is unusable.
"""
import os
import pathlib
import re
import sys

# Kept in step with cs's CS_EXCLUDE_DIRS and with strictness.py: a vendored
# dependency's retry policy is not this repo's posture.
SKIP_DIRS = {
    ".git", ".origins", ".hg", ".svn", "node_modules", "bower_components",
    "vendor", "Pods", "DerivedData", "target", "build", "dist", "out", "bin",
    "obj", ".gradle", ".m2", ".venv", "venv", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".tox", ".ruff_cache", ".next", ".nuxt", ".parcel-cache",
    ".turbo", "coverage", ".nyc_output", ".terraform", ".serena", ".tokensave",
    ".idea", ".vscode-test",
}

MAX_BYTES = 2_000_000

SUFFIX_LANG = {
    ".py": "python", ".java": "jvm", ".kt": "jvm", ".kts": "jvm",
    ".scala": "jvm", ".ts": "ts", ".tsx": "ts", ".js": "ts", ".mjs": "ts",
    ".yaml": "config", ".yml": "config", ".properties": "config",
    ".toml": "manifest", ".txt": "manifest",
}

# ---- DISCARDS: the response is raised on, and the payload never read --------
PY_RAISE_FOR_STATUS = re.compile(r"\braise_for_status\s*\(")
TS_THROW_ON_STATUS = re.compile(
    r"if\s*\(\s*!\s*\w+\.ok\s*\)[^\n]*\n?[^\n]*\bthrow\b")
JVM_THROW_ON_STATUS = re.compile(
    r"\bthrow\s+new\s+\w*(?:Http|Rest|Api|Client|Server)\w*Exception\b")

# ---- READS: the status is branched on AND the body is parsed ----------------
# Two halves, deliberately: `response.json()` alone is the success path. What
# makes a site a READER is that it gets there on a NON-2xx.
PY_STATUS_BRANCH = re.compile(
    r"\b(?:resp(?:onse)?|r)\s*\.\s*(?:status_code|status|ok)\b")
PY_BODY_PARSE = re.compile(r"\b(?:resp(?:onse)?|r)\s*\.\s*(?:json|text|content)\b")
TS_ERR_BODY = re.compile(
    r"\berr(?:or)?\s*\.\s*response\s*\.\s*data\b|await\s+\w+\.json\s*\(\s*\)")
JVM_ERROR_DECODER = re.compile(r"\bErrorDecoder\b|\bResponseErrorHandler\b|"
                               r"\bhandleError\s*\(")

# ---- RETRIES ---------------------------------------------------------------
# An IMPORT is not a configuration. Counting `from tenacity import retry` and
# the `@retry` it enables as two retry sites overstates the posture, and the
# count is what a reader takes away -- so the import is recorded as evidence
# that the library is in play and is not tallied as a site.
PY_RETRY_IMPORT = re.compile(r"^\s*(?:from|import)\s+(?:tenacity|backoff)\b", re.M)
PY_TENACITY = re.compile(r"@(?:retry|backoff\.\w+)\b")
PY_URLLIB3_RETRY = re.compile(r"\bRetry\s*\(|max_retries\s*=")
JVM_RETRY = re.compile(r"@Retryable\b|\bRetryTemplate\b|\bRetryer\b|"
                       r"\bresilience4j\b|\bCircuitBreaker\b")
TS_RETRY = re.compile(r"\baxios-retry\b|\bretries\s*:\s*\d|\bp-retry\b")
CFG_RETRY = re.compile(r"^\s*(?:retry|retries|maxAttempts|max_attempts)\s*:",
                       re.M | re.I)

# Named in every answer: this is the one that produces the same observable
# behaviour with nothing in the repo to find.
INFRA_NOTE = ("a retry configured at the INFRASTRUCTURE layer — a service mesh, "
              "an ingress, a client-side load balancer — is invisible to this "
              "and produces the same observable behaviour with nothing in the "
              "repo to find")


def read(path):
    try:
        if path.stat().st_size > MAX_BYTES:
            return None
        return path.read_text(errors="replace")
    except OSError:
        return None


def walk(repo_dir):
    for dirpath, dirnames, filenames in os.walk(repo_dir):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            p = pathlib.Path(dirpath) / name
            if p.suffix.lower() in SUFFIX_LANG:
                yield p


def line_of(text, pos):
    return text[:pos].count("\n") + 1


def reads_error_body(text, lang):
    """Sites that branch on the status AND parse the body.

    Both halves are required and they must be near each other. `response.json()`
    on its own is the success path, and counting it as "reads the error body"
    would turn every HTTP client in the fleet into an attentive consumer --
    exactly the false comfort this verb exists to avoid.
    """
    hits = []
    if lang == "python":
        for m in PY_STATUS_BRANCH.finditer(text):
            window = text[m.start(): m.start() + 400]
            if PY_BODY_PARSE.search(window):
                hits.append((line_of(text, m.start()),
                             "branches on the status and then parses the body"))
    elif lang == "ts":
        for m in TS_ERR_BODY.finditer(text):
            hits.append((line_of(text, m.start()),
                         "inspects the error response body"))
    elif lang == "jvm":
        for m in JVM_ERROR_DECODER.finditer(text):
            hits.append((line_of(text, m.start()),
                         "an ErrorDecoder / error handler — the strongest "
                         "'reads the error body' signal there is"))
    return hits


def discards(text, lang):
    hits = []
    if lang == "python":
        for m in PY_RAISE_FOR_STATUS.finditer(text):
            hits.append((line_of(text, m.start()),
                         "raise_for_status() — raises on a non-2xx WITHOUT "
                         "reading the body"))
    elif lang == "ts":
        for m in TS_THROW_ON_STATUS.finditer(text):
            hits.append((line_of(text, m.start()),
                         "throws on !response.ok without reading the body"))
    elif lang == "jvm":
        for m in JVM_THROW_ON_STATUS.finditer(text):
            hits.append((line_of(text, m.start()),
                         "throws a client/server exception on the status"))
    return hits


def retries(text, lang):
    """Configured retry SITES. One per line at most: a decorator and the import
    that enables it are one policy, not two."""
    hits = {}
    pats = {"python": (PY_TENACITY, PY_URLLIB3_RETRY), "jvm": (JVM_RETRY,),
            "ts": (TS_RETRY,), "config": (CFG_RETRY,)}.get(lang, ())
    for rx in pats:
        for m in rx.finditer(text):
            line = line_of(text, m.start())
            hits.setdefault(line, "retry configured: " + m.group(0).strip())
    return sorted(hits.items())


def retry_library(text, lang):
    return lang == "python" and bool(PY_RETRY_IMPORT.search(text))


def classify_repo(repo_dir):
    """(verdict, [evidence lines], counts)."""
    ev = []
    n_read = n_discard = n_retry = 0

    for path in walk(repo_dir):
        text = read(path)
        if text is None:
            continue
        rel = path.relative_to(repo_dir).as_posix()
        lang = SUFFIX_LANG[path.suffix.lower()]
        if lang == "manifest":
            # A manifest declares the LIBRARY, not a site. Recorded because a
            # repo that depends on tenacity retries somewhere, and that is worth
            # knowing even when no decorator is where this looks.
            if re.search(r"\btenacity\b|\bbackoff\b|\baxios-retry\b|"
                         r"\bspring-retry\b|\bresilience4j\b", text):
                ev.append(f"{rel}: declares a retry library in its manifest")
            continue
        for line, why in reads_error_body(text, lang):
            n_read += 1
            ev.append(f"{rel}:{line}: {why} -> READS ERROR BODY")
        for line, why in discards(text, lang):
            n_discard += 1
            ev.append(f"{rel}:{line}: {why} -> DISCARDS")
        for line, why in retries(text, lang):
            n_retry += 1
            ev.append(f"{rel}:{line}: {why} -> RETRIES")
        if retry_library(text, lang) and not retries(text, lang):
            # Imported and used somewhere this does not recognise. Evidence, not
            # a site: it is the reason a repo with no visible decorator can
            # still retry.
            ev.append(f"{rel}: imports a retry library, with no retry site "
                      f"this recognises in the same file")

    if n_read and n_discard:
        verdict = "MIXED"
    elif n_read:
        verdict = "READS ERROR BODY"
    elif n_discard and n_retry:
        # The one that turns a producer-side contract into a no-op, and so the
        # one that gets its own name rather than being folded into DISCARDS.
        verdict = "RETRIES, BODY DISCARDED"
    elif n_discard:
        verdict = "DISCARDS"
    elif n_retry:
        verdict = "RETRIES, BODY POSTURE UNKNOWN"
    else:
        verdict = "UNKNOWN"
    return verdict, ev, {"read": n_read, "discard": n_discard, "retry": n_retry}


def summary_of(c):
    bits = []
    if c["read"]:
        bits.append(f"{c['read']} site(s) read the error body")
    if c["discard"]:
        bits.append(f"{c['discard']} raise-and-discard")
    if c["retry"]:
        bits.append(f"{c['retry']} retry configuration(s)")
    return ", ".join(bits) or "no recognised error handling found"


def repos_in(root):
    return sorted(d for d in root.iterdir()
                  if d.is_dir() and not d.name.startswith("."))


def main():
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    root = pathlib.Path(sys.argv[1])
    mode = sys.argv[2]
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    if mode == "repo":
        if len(sys.argv) < 4:
            print("resilience.py <root> repo <name>", file=sys.stderr)
            return 2
        name = sys.argv[3]
        d = root / name
        if not d.is_dir():
            print(f"no such repo: {name}", file=sys.stderr)
            return 2
        verdict, ev, counts = classify_repo(d)
        print(f"{name}: {verdict} — {summary_of(counts)}")
        for line in ev:
            print(f"{name}/{line}")
        print(INFRA_NOTE, file=sys.stderr)
        return 0 if ev else 1

    if mode != "audit":
        print(f"unknown mode: {mode}", file=sys.stderr)
        return 2

    found = 0
    unknown = []
    for d in repos_in(root):
        verdict, ev, counts = classify_repo(d)
        print(f"{d.name}: {verdict} — {summary_of(counts)}")
        found += 1
        if verdict == "UNKNOWN":
            unknown.append(d.name)
    if unknown:
        # stderr, like strictness.py's UNKNOWN roll-up and owners.py's gaps:
        # "we could not tell" is a finding about the scan, not a posture the
        # repo declared.
        print(f"UNKNOWN is not 'reads it': {len(unknown)} repo(s) have no "
              f"recognised error handling ({' '.join(unknown)}) — their posture "
              f"is undetermined, and a consumer that never reads an error body "
              f"looks exactly like one this could not classify", file=sys.stderr)
    print(INFRA_NOTE, file=sys.stderr)
    return 0 if found else 1


if __name__ == "__main__":
    sys.exit(main())

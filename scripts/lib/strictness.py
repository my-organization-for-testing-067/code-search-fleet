#!/usr/bin/env python3
"""Report each repo's DESERIALIZATION POSTURE: does it reject unknown fields?

The question this fills in: "if I add a field to this response, which consumers
reject unknown fields and crash?" Finding the consumers is well served (cs uses,
cs fields). Classifying each one's parser strictness was entirely manual -- open
every consumer, find its deserialization site, work out whether the model
forbids extras -- and it is the half where being wrong is most expensive. The
incident behind this class of review is an "additive, non-breaking" field
addition that crashed a consumer whose model was a plain dataclass splatted from
a dict.

It is a `declared` answer, in the same sense as deps.py and owners.py: strictness
is overwhelmingly declared in config and model metadata rather than inferred from
control flow, and what is reported is what the files say.

Why normalisation is the point rather than a nicety: the same semantics are
spelled several ways, and a caller grepping one form silently misses the others.
Measured across a 43-repo fleet, `extra="forbid"` and `extra='forbid'` -- one
setting, two quotings -- were counted separately by a naive grep, which is the
same silent-under-selection class cs already fixed for text answers.

FOUR verdicts, and UNKNOWN is not a synonym for LENIENT:

  STRICT   every recognised model rejects unknown fields
  LENIENT  every recognised model accepts and drops them
  MIXED    both, in the same repo -- the model list is the answer, not the
           rollup, so `strictness.py <root> repo <name>` lists them
  UNKNOWN  no recognised parser configuration at all. Distinguishing this from
           LENIENT is the whole point: collapsing them manufactures exactly the
           false comfort this tool exists to avoid.

ALLOW is tracked as its own state and never folded into "lenient". Pydantic's
extra='allow' RETAINS unknown fields on the model, so a consumer that persists
the object verbatim -- into a JSONB column, say -- stores them. That is a real
downstream effect and a different one from dropping them.

Usage:
  strictness.py <fleet-root> audit           one verdict per repo
  strictness.py <fleet-root> repo <name>     the per-model evidence for one repo
Exit: 0 something was reported, 1 nothing found, 2 the root is unusable.
"""
import os
import pathlib
import re
import sys

# Directories that are never the repo's own source. Kept in step with cs's
# CS_EXCLUDE_DIRS; a vendored dependency's strictness is not this repo's posture.
SKIP_DIRS = {
    ".git", ".origins", ".hg", ".svn", "node_modules", "bower_components",
    "vendor", "Pods", "DerivedData", "target", "build", "dist", "out", "bin",
    "obj", ".gradle", ".m2", ".venv", "venv", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".tox", ".ruff_cache", ".next", ".nuxt", ".parcel-cache",
    ".turbo", "coverage", ".nyc_output", ".terraform", ".serena", ".tokensave",
    ".idea", ".vscode-test",
}

MAX_BYTES = 2_000_000

# --- Python / Pydantic ------------------------------------------------------
# Both quotings in one pattern, which is the normalisation this file exists for.
# v2 spells it model_config = ConfigDict(extra=...); v1 spells it as a nested
# `class Config` attribute, optionally through the Extra enum.
PY_EXTRA = re.compile(
    r"""extra\s*[=:]\s*(?:Extra\.)?["']?(forbid|ignore|allow)["']?""")
PY_DATACLASS = re.compile(r"^\s*@dataclass\b", re.M)
PY_CLASSNAME = re.compile(r"^\s*class\s+([A-Za-z_]\w*)", re.M)
PY_BASEMODEL = re.compile(r"^\s*class\s+([A-Za-z_]\w*)\s*\([^)]*BaseModel", re.M)

# --- Java / Kotlin / Spring -------------------------------------------------
JACKSON_ANNOT = re.compile(
    r"@JsonIgnoreProperties\s*\(\s*(?:[^)]*?ignoreUnknown\s*=\s*(true|false))?")
SPRING_FAIL = re.compile(
    r"fail[-_]on[-_]unknown[-_]properties\s*[:=]\s*(true|false)", re.I)

# --- TypeScript -------------------------------------------------------------
# A zod/io-ts decoder validates at runtime; .passthrough() opts back out, and
# a bare `as T` cast is compile-time only and checks nothing at all.
TS_ZOD = re.compile(r"\bz\.object\s*\(")
TS_ZOD_PASSTHROUGH = re.compile(r"\.passthrough\s*\(")
TS_IOTS = re.compile(r"\bt\.(type|strict|interface)\s*\(")

# --- Generated OpenAPI clients ---------------------------------------------
OPENAPI_HINT = re.compile(
    r"(openapi-generator|swagger-codegen|THIS FILE IS AUTO-GENERATED)", re.I)
ADDITIONAL_PROPS = re.compile(r"additionalProperties")

SUFFIX_LANG = {
    ".py": "python", ".java": "java", ".kt": "kotlin", ".kts": "kotlin",
    ".ts": "ts", ".tsx": "ts", ".yaml": "config", ".yml": "config",
    ".properties": "config",
}


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


def pydantic_major(repo_dir):
    """1 or 2 from the manifest, or None. The DEFAULT differs between them --
    v1 allows unknown fields, v2 ignores them -- so a model with no explicit
    setting has a posture only once the version is known."""
    for manifest in ("pyproject.toml", "requirements.txt", "setup.cfg",
                     "Pipfile", "constraints.txt"):
        text = read(repo_dir / manifest)
        if not text:
            continue
        m = re.search(r"pydantic\s*[=><~^\"' ]*?(\d+)", text)
        if m:
            return int(m.group(1))
        if re.search(r"\bpydantic\b", text):
            return 0  # present, version unpinned
    return None


def classify_repo(repo_dir):
    """(verdict, [evidence lines])."""
    ev = []
    forbid = ignore = allow = 0
    strict_runtime = lenient_runtime = 0
    unresolved_models = 0

    pyd = pydantic_major(repo_dir)
    dataclass_names = set()
    splat_names = set()

    for path in walk(repo_dir):
        text = read(path)
        if text is None:
            continue
        rel = path.relative_to(repo_dir).as_posix()
        lang = SUFFIX_LANG[path.suffix.lower()]

        if lang == "python":
            for m in PY_EXTRA.finditer(text):
                mode = m.group(1)
                line = text[:m.start()].count("\n") + 1
                if mode == "forbid":
                    forbid += 1
                    ev.append(f"{rel}:{line}: pydantic extra=forbid -> STRICT")
                elif mode == "ignore":
                    ignore += 1
                    ev.append(f"{rel}:{line}: pydantic extra=ignore -> lenient")
                else:
                    allow += 1
                    ev.append(f"{rel}:{line}: pydantic extra=allow -> lenient, "
                              f"but unknown fields are RETAINED on the model")
            # BaseModel subclasses with no explicit extra= take the version
            # default, which is only knowable from the manifest.
            n_models = len(PY_BASEMODEL.findall(text))
            explicit = len(PY_EXTRA.findall(text))
            if n_models > explicit:
                if pyd == 1:
                    allow += n_models - explicit
                elif pyd == 2:
                    ignore += n_models - explicit
                else:
                    unresolved_models += n_models - explicit
            if PY_DATACLASS.search(text):
                for cm in PY_CLASSNAME.finditer(text):
                    dataclass_names.add(cm.group(1))
            for sm in re.finditer(r"\b([A-Z]\w*)\s*\(\s*\*\*", text):
                splat_names.add((sm.group(1), rel,
                                 text[:sm.start()].count("\n") + 1))

        elif lang in ("java", "kotlin"):
            for m in JACKSON_ANNOT.finditer(text):
                line = text[:m.start()].count("\n") + 1
                val = m.group(1)
                if val == "true":
                    ignore += 1
                    ev.append(f"{rel}:{line}: @JsonIgnoreProperties("
                              f"ignoreUnknown=true) -> lenient")
                else:
                    forbid += 1
                    ev.append(f"{rel}:{line}: @JsonIgnoreProperties("
                              f"ignoreUnknown={val or 'unset'}) -> STRICT")

        elif lang == "config":
            for m in SPRING_FAIL.finditer(text):
                line = text[:m.start()].count("\n") + 1
                if m.group(1).lower() == "true":
                    forbid += 1
                    ev.append(f"{rel}:{line}: spring fail-on-unknown-properties"
                              f"=true -> STRICT")
                else:
                    ignore += 1
                    ev.append(f"{rel}:{line}: spring fail-on-unknown-properties"
                              f"=false -> lenient (also Spring Boot's default)")

        elif lang == "ts":
            if OPENAPI_HINT.search(text):
                if ADDITIONAL_PROPS.search(text):
                    lenient_runtime += 1
                    ev.append(f"{rel}: generated client WITH additionalProperties"
                              f" -> lenient")
                else:
                    strict_runtime += 1
                    ev.append(f"{rel}: generated client, no additionalProperties"
                              f" -> STRICT (and a frozen schema: its staleness "
                              f"is a separate risk)")
            n_zod = len(TS_ZOD.findall(text))
            if n_zod:
                if TS_ZOD_PASSTHROUGH.search(text):
                    lenient_runtime += n_zod
                    ev.append(f"{rel}: zod object with .passthrough() -> lenient")
                else:
                    strict_runtime += n_zod
                    ev.append(f"{rel}: {n_zod} zod object(s) -> STRICT "
                              f"(unknown keys are stripped; .strict() rejects)")
            n_iots = len(TS_IOTS.findall(text))
            if n_iots:
                strict_runtime += n_iots
                ev.append(f"{rel}: {n_iots} io-ts decoder(s) -> STRICT")

    # The nastiest case, and the one from the incident: a plain @dataclass built
    # as Cls(**payload) raises TypeError on an unknown key. Nothing in the class
    # declares that, so no config scan finds it -- it takes both halves.
    for name, rel, line in sorted(splat_names):
        if name in dataclass_names:
            forbid += 1
            ev.append(f"{rel}:{line}: {name}(**payload) on a @dataclass -> "
                      f"STRICT (TypeError on an unknown key; nothing in the "
                      f"class declares this)")

    strict = forbid + strict_runtime
    lenient = ignore + allow + lenient_runtime
    if strict and lenient:
        verdict = "MIXED"
    elif strict:
        verdict = "STRICT"
    elif lenient:
        verdict = "LENIENT"
    else:
        verdict = "UNKNOWN"

    if unresolved_models and verdict != "UNKNOWN":
        ev.append(f"(pydantic version not pinned in any manifest, so "
                  f"{unresolved_models} model(s) with no explicit extra= have "
                  f"no determinable default: v1 allows, v2 ignores)")
    elif unresolved_models:
        ev.append(f"({unresolved_models} pydantic model(s) found, but the "
                  f"version is not pinned in any manifest and none sets extra=, "
                  f"so the default is undeterminable)")
    return verdict, ev, {"strict": strict, "lenient": lenient,
                         "allow": allow, "unresolved": unresolved_models}


def summary_of(counts):
    bits = []
    if counts["strict"]:
        bits.append(f"{counts['strict']} strict")
    if counts["lenient"]:
        bits.append(f"{counts['lenient']} lenient")
    if counts["allow"]:
        bits.append(f"{counts['allow']} of them extra=allow (fields RETAINED)")
    if counts["unresolved"]:
        bits.append(f"{counts['unresolved']} undeterminable")
    return ", ".join(bits) or "no recognised parser configuration"


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
            print("strictness.py <root> repo <name>", file=sys.stderr)
            return 2
        name = sys.argv[3]
        d = root / name
        if not d.is_dir():
            print(f"no such repo: {name}", file=sys.stderr)
            return 2
        verdict, ev, counts = classify_repo(d)
        print(f"{name}: {verdict} — {summary_of(counts)}")
        for line in ev:
            print(f"{name}/{line}" if ":" in line and not line.startswith("(")
                  else f"  {line}")
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
        # stderr, like owners.py's gaps: "we could not tell" is a finding about
        # the scan, not a posture the repo declared.
        print(f"UNKNOWN is not lenient: {len(unknown)} repo(s) declare no "
              f"parser configuration this recognises ({' '.join(unknown)}) — "
              f"their posture is undetermined, not permissive", file=sys.stderr)
    return 0 if found else 1


if __name__ == "__main__":
    sys.exit(main())

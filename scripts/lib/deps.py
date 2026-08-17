#!/usr/bin/env python3
"""Map package coordinates to the fleet repos that publish and consume them.

The gap this fills: "which of these two same-named classes does checkout
actually use" is not a code-search question at all. The answer lives in build
manifests -- a Gradle coordinate, an npm name, a NuGet id -- and no code search
engine reads those. Without this, the question is unanswerable no matter how
good the search is.

Publishers are read from each repo's own manifest; consumers from their
declared dependencies. A coordinate naming no publisher in the fleet is
external, which is itself worth seeing.

Usage:
  deps.py <fleet-root> publishes            list what each repo publishes
  deps.py <fleet-root> provides <coord>     which repo publishes a coordinate
  deps.py <fleet-root> deps [repo]          fleet dependency edges
  deps.py <fleet-root> versions [coord]     which version each repo pins
"""
import json
import pathlib
import re
import sys


def _read(path):
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


# A package name can be spelled several ways and mean one distribution, and only
# the publisher's ECOSYSTEM knows which of those differences are meaningless.
# Comparing literally made `cs provides kit-service` report "no fleet repo
# publishes this (external dependency?)" for a repo whose pyproject.toml says
# `name = "Kit Service"` -- a confident wrong negative in the `declared` tier,
# which the skill documents as the strongest kind for a negative and the one
# most likely to be repeated to a person as fact. The parenthetical then points
# the reader at the wrong conclusion: they stop looking, because it reads as
# third-party.
#
# The rules are NOT symmetrical, and folding them together would trade this bug
# for a worse one:
#
#   pypi   PEP 503 -- [-_.] runs collapse to '-', case-insensitive
#   npm    lowercase only; the @scope/ prefix is significant
#   nuget  case-insensitive
#   maven  groupId:artifactId is CASE-SENSITIVE -- must not be folded, or two
#          genuinely different artifacts merge into one
def normalize_coord(name, eco):
    name = name.strip()
    if eco == "pypi":
        # Whitespace is folded as well as [-_.], which is a superset of PEP 503.
        # Strict PEP 503 leaves a space alone -- so `Kit Service` normalizes to
        # `kit service` and still fails to match `kit-service`, which is the
        # exact case reported. A space is invalid in a name per PEP 508 anyway;
        # the packaging tools collapse it when building the distribution, which
        # is why consumers end up writing the hyphenated form.
        return re.sub(r"[-_.\s]+", "-", name).lower()
    if eco in ("npm", "nuget"):
        return name.lower()
    return name  # maven, and anything unrecognised: compare exactly


def publishes_tagged(repo):
    """(coordinate, ecosystem, manifest-path) for everything this repo publishes."""
    out = []

    for gradle in list(repo.glob("build.gradle.kts")) + list(repo.glob("build.gradle")):
        text = _read(gradle)
        group = re.search(r'^\s*group\s*=\s*["\']([^"\']+)["\']', text, re.M)
        artifact = re.search(r'artifactId\s*=\s*["\']([^"\']+)["\']', text)
        if group and artifact:
            out.append((f"{group.group(1)}:{artifact.group(1)}", "maven", gradle))

    for pom in repo.glob("pom.xml"):
        text = _read(pom)
        g = re.search(r"<groupId>([^<]+)</groupId>", text)
        a = re.search(r"<artifactId>([^<]+)</artifactId>", text)
        if g and a:
            out.append((f"{g.group(1)}:{a.group(1)}", "maven", pom))

    for pkg in list(repo.glob("package.json")) + list(repo.glob("*/package.json")):
        try:
            data = json.loads(_read(pkg) or "{}")
        except json.JSONDecodeError:
            continue
        if data.get("name") and not data.get("private"):
            out.append((data["name"], "npm", pkg))

    for pyproject in repo.glob("pyproject.toml"):
        name = re.search(r'^\s*name\s*=\s*["\']([^"\']+)["\']', _read(pyproject), re.M)
        if name:
            out.append((name.group(1), "pypi", pyproject))

    for csproj in repo.rglob("*.csproj"):
        pkg_id = re.search(r"<PackageId>([^<]+)</PackageId>", _read(csproj))
        if pkg_id:
            out.append((pkg_id.group(1), "nuget", csproj))

    return out


def publishes(repo):
    """Coordinates this repo publishes, as a list of strings."""
    return sorted({coord for coord, _eco, _path in publishes_tagged(repo)})


def consumes(repo):
    """Coordinates this repo declares a dependency on."""
    out = []

    for gradle in list(repo.glob("build.gradle.kts")) + list(repo.glob("build.gradle")):
        for m in re.finditer(r'["\']([\w.\-]+:[\w.\-]+):[\w.\-]+["\']', _read(gradle)):
            out.append(m.group(1))

    for pom in repo.glob("pom.xml"):
        text = _read(pom)
        for dep in re.finditer(
            r"<dependency>\s*<groupId>([^<]+)</groupId>\s*<artifactId>([^<]+)</artifactId>",
            text,
        ):
            out.append(f"{dep.group(1)}:{dep.group(2)}")

    for pkg in list(repo.glob("package.json")) + list(repo.glob("*/package.json")):
        try:
            data = json.loads(_read(pkg) or "{}")
        except json.JSONDecodeError:
            continue
        for section in ("dependencies", "devDependencies", "peerDependencies"):
            out.extend((data.get(section) or {}).keys())

    for pyproject in repo.glob("pyproject.toml"):
        text = _read(pyproject)
        block = re.search(r"dependencies\s*=\s*\[(.*?)\]", text, re.S)
        if block:
            for m in re.finditer(r'["\']([A-Za-z0-9_.\-]+)', block.group(1)):
                out.append(m.group(1))

    for csproj in repo.rglob("*.csproj"):
        for m in re.finditer(r'PackageReference\s+Include="([^"]+)"', _read(csproj)):
            out.append(m.group(1))

    return sorted(set(out))


def consumes_versioned(repo):
    """[(coordinate, version, manifest-relative-path)] this repo declares.

    consumes() deliberately drops the version, because "who depends on what" does
    not need it. "Is the fleet agreed on a version" is a different question and
    cannot be answered without it -- and it is the question that catches a repo
    left behind by an upgrade, which is a real bug shape rather than a tidiness
    complaint.
    """
    out = []

    def rel(p):
        try:
            return str(p.relative_to(repo))
        except ValueError:
            return p.name

    for gradle in list(repo.glob("build.gradle.kts")) + list(repo.glob("build.gradle")):
        for m in re.finditer(r'["\']([\w.\-]+:[\w.\-]+):([\w.\-]+)["\']', _read(gradle)):
            out.append((m.group(1), m.group(2), rel(gradle)))

    for pom in repo.glob("pom.xml"):
        for dep in re.finditer(
            r"<dependency>\s*<groupId>([^<]+)</groupId>\s*"
            r"<artifactId>([^<]+)</artifactId>\s*(?:<version>([^<]+)</version>)?",
            _read(pom),
        ):
            out.append((f"{dep.group(1)}:{dep.group(2)}",
                        (dep.group(3) or "(inherited)").strip(), rel(pom)))

    for pkg in list(repo.glob("package.json")) + list(repo.glob("*/package.json")):
        try:
            data = json.loads(_read(pkg) or "{}")
        except json.JSONDecodeError:
            continue
        for section in ("dependencies", "devDependencies", "peerDependencies"):
            for name, ver in (data.get(section) or {}).items():
                out.append((name, str(ver), rel(pkg)))

    for pyproject in repo.glob("pyproject.toml"):
        block = re.search(r"dependencies\s*=\s*\[(.*?)\]", _read(pyproject), re.S)
        if block:
            for m in re.finditer(
                r'["\']([A-Za-z0-9_.\-]+)\s*([=<>!~^]*\s*[0-9][\w.\-*]*)?', block.group(1)
            ):
                out.append((m.group(1), (m.group(2) or "(unpinned)").strip(), rel(pyproject)))

    for csproj in repo.rglob("*.csproj"):
        for m in re.finditer(
            r'PackageReference\s+Include="([^"]+)"(?:\s+Version="([^"]+)")?', _read(csproj)
        ):
            out.append((m.group(1), m.group(2) or "(inherited)", rel(csproj)))

    return out


def normalize_version(v):
    """Strip a constraint prefix so versions can be compared across ecosystems.

    `==2.4.0` (pip), `^2.4.0` (npm caret), `~2.4.0`, `v2.4.0` and `2.4.0` all
    name the same release; only the dialect differs. This deliberately does NOT
    try to interpret range semantics -- `>=2.0` and `2.0` really are different
    promises -- it only removes the spelling, so that a repo genuinely left
    behind by an upgrade stands out from four repos agreeing in four syntaxes.
    """
    return re.sub(r"^[\s=<>!~^v]+", "", v.strip()).strip()


def repos(root):
    return sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))


def main():
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    root = pathlib.Path(sys.argv[1])
    cmd = sys.argv[2]

    if not root.is_dir():
        print(f"no such fleet root: {root}", file=sys.stderr)
        return 2

    publisher = {}
    # Parallel index keyed on the ECOSYSTEM-normalized name, so a coordinate
    # that differs from its manifest spelling only by normalization still
    # resolves. Carries the raw spelling and manifest path so a match found this
    # way can say what the manifest actually declares -- a name that needs
    # normalizing is usually a small bug in that repo too, and surfacing it
    # beats silently papering over it.
    publisher_norm = {}
    for repo in repos(root):
        for coord, eco, path in publishes_tagged(repo):
            publisher[coord] = repo.name
            try:
                rel = path.relative_to(root)
            except ValueError:
                rel = path
            publisher_norm.setdefault(
                normalize_coord(coord, eco), (repo.name, coord, eco, str(rel))
            )

    def resolve(want):
        """(repo, note) for whoever publishes `want`, or (None, None)."""
        if want in publisher:
            return publisher[want], None
        # A bare artifact id, so "pricing-lib" resolves as well as the full
        # "com.acme:pricing-lib".
        for coord, owner in publisher.items():
            if coord.split(":")[-1] == want:
                return owner, None
        # Normalized -- but each candidate is compared under ITS OWN ecosystem's
        # rules, never under a rule borrowed from another. Trying the query
        # against every ruleset in turn instead let npm's lowercasing match a
        # Maven key, so `com.acme:Pricing-Lib` resolved to `com.acme:pricing-lib`
        # -- exactly the case-folding that ecosystem forbids, and the merge of
        # two genuinely different artifacts the rules exist to prevent.
        for key, (owner, raw, raw_eco, rel) in publisher_norm.items():
            if normalize_coord(want, raw_eco) == key:
                if raw != want:
                    return owner, f"{want} -> declared as '{raw}' in {rel} ({raw_eco} normalization)"
                return owner, None
        # And a bare artifact id on the normalized side too.
        for key, (owner, raw, raw_eco, rel) in publisher_norm.items():
            if key.split(":")[-1] == normalize_coord(want, raw_eco):
                return owner, f"{want} -> declared as '{raw}' in {rel} ({raw_eco} normalization)"
        return None, None

    if cmd == "publishes":
        for coord, name in sorted(publisher.items()):
            print(f"{name}\tpublishes\t{coord}")
        return 0

    if cmd == "provides":
        if len(sys.argv) < 4:
            print("usage: deps.py <root> provides <coordinate>", file=sys.stderr)
            return 2
        want = sys.argv[3]
        name, note = resolve(want)
        if name:
            if note:
                print(note, file=sys.stderr)
            print(name)
            return 0
        print(f"no fleet repo publishes '{want}' (external dependency?)", file=sys.stderr)
        return 1

    if cmd == "deps":
        only = sys.argv[3] if len(sys.argv) > 3 else None
        for repo in repos(root):
            if only and repo.name != only:
                continue
            for coord in consumes(repo):
                # Same resolution as `provides`, so an intra-fleet edge is not
                # invisible purely because the two manifests spell the name
                # differently. Without this, any edge involving a
                # non-normalized publish name could never be detected.
                owner, _note = resolve(coord)
                if owner and owner != repo.name:
                    print(f"{repo.name}\t->\t{owner}\t({coord})")
        return 0

    if cmd == "versions":
        want = sys.argv[3] if len(sys.argv) > 3 else None
        rows = []
        for repo in repos(root):
            for coord, ver, manifest in consumes_versioned(repo):
                if want and coord != want and coord.split(":")[-1] != want:
                    continue
                rows.append((repo.name, coord, ver, manifest))
        if not rows:
            if want:
                print(f"no repo in the fleet declares a dependency on '{want}'",
                      file=sys.stderr)
            return 1
        # Grouped by coordinate so the comparison is adjacent; the point of the
        # command is the disagreement, and a flat list buries it.
        for coord in sorted({r[1] for r in rows}):
            mine = [r for r in rows if r[1] == coord]
            # Compared on the version NUMBER, not the raw declaration. Each
            # ecosystem spells a pin differently -- `==2.4.0` in pyproject.toml
            # and `2.4.0` in package.json are the same version -- and reporting
            # that as drift is a false positive in the one command whose entire
            # value is that its findings are worth acting on.
            pinned = {normalize_version(r[2]) for r in mine
                      if not r[2].startswith("(")}
            unknown = [r for r in mine if r[2].startswith("(")]
            spellings = {r[2] for r in mine}

            if len(pinned) > 1:
                flag, detail = "DRIFT", f"{len(pinned)} version(s)"
            elif pinned:
                flag, detail = "AGREED", f"{len(pinned)} version(s)"
                if len(spellings) > len(pinned):
                    detail += ", spelled differently per ecosystem"
            else:
                flag, detail = "UNPINNED", "no explicit version"

            owner = publisher.get(coord) or next(
                (o for c, o in publisher.items() if c.split(":")[-1] == coord), None
            )
            line = f"{coord}\t{flag}\t{detail}"
            line += f"\tpublished by {owner}" if owner else "\texternal"
            if unknown and flag != "UNPINNED":
                line += f" ({len(unknown)} declaration(s) inherit or float)"
            print(line)
            for name, _c, ver, manifest in sorted(mine):
                print(f"  {name}\t{ver}\t{manifest}")
        return 0

    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())

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


def publishes(repo):
    """Coordinates this repo publishes, as a list of strings."""
    out = []

    for gradle in list(repo.glob("build.gradle.kts")) + list(repo.glob("build.gradle")):
        text = _read(gradle)
        group = re.search(r'^\s*group\s*=\s*["\']([^"\']+)["\']', text, re.M)
        artifact = re.search(r'artifactId\s*=\s*["\']([^"\']+)["\']', text)
        if group and artifact:
            out.append(f"{group.group(1)}:{artifact.group(1)}")

    for pom in repo.glob("pom.xml"):
        text = _read(pom)
        g = re.search(r"<groupId>([^<]+)</groupId>", text)
        a = re.search(r"<artifactId>([^<]+)</artifactId>", text)
        if g and a:
            out.append(f"{g.group(1)}:{a.group(1)}")

    for pkg in list(repo.glob("package.json")) + list(repo.glob("*/package.json")):
        try:
            data = json.loads(_read(pkg) or "{}")
        except json.JSONDecodeError:
            continue
        if data.get("name") and not data.get("private"):
            out.append(data["name"])

    for pyproject in repo.glob("pyproject.toml"):
        name = re.search(r'^\s*name\s*=\s*["\']([^"\']+)["\']', _read(pyproject), re.M)
        if name:
            out.append(name.group(1))

    for csproj in repo.rglob("*.csproj"):
        pkg_id = re.search(r"<PackageId>([^<]+)</PackageId>", _read(csproj))
        if pkg_id:
            out.append(pkg_id.group(1))

    return sorted(set(out))


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
    for repo in repos(root):
        for coord in publishes(repo):
            publisher[coord] = repo.name

    if cmd == "publishes":
        for coord, name in sorted(publisher.items()):
            print(f"{name}\tpublishes\t{coord}")
        return 0

    if cmd == "provides":
        if len(sys.argv) < 4:
            print("usage: deps.py <root> provides <coordinate>", file=sys.stderr)
            return 2
        want = sys.argv[3]
        name = publisher.get(want)
        if name:
            print(name)
            return 0
        # Match a bare artifact id too, so "pricing-lib" resolves as well as
        # the full "com.acme:pricing-lib".
        for coord, owner in publisher.items():
            if coord.split(":")[-1] == want:
                print(owner)
                return 0
        print(f"no fleet repo publishes '{want}' (external dependency?)", file=sys.stderr)
        return 1

    if cmd == "deps":
        only = sys.argv[3] if len(sys.argv) > 3 else None
        for repo in repos(root):
            if only and repo.name != only:
                continue
            for coord in consumes(repo):
                owner = publisher.get(coord)
                if not owner:
                    owner = next(
                        (o for c, o in publisher.items() if c.split(":")[-1] == coord),
                        None,
                    )
                if owner and owner != repo.name:
                    print(f"{repo.name}\t->\t{owner}\t({coord})")
        return 0

    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())

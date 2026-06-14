#!/usr/bin/env python3
"""Migrate a unitysvc-services-* repo from the nested ``data/`` layout to the
flat ``specs/`` layout (unitysvc#1263).

Run from the repo root (or pass the path):

    python migrate_to_specs.py [REPO_ROOT] [--dry-run]

Transforms, per provider under ``data/<provider>/``:

- ``data/`` → ``specs/`` ; ``data/<provider>/docs/`` → top-level ``docs/`` ;
  ``data/<provider>/scripts/`` → top-level ``scripts/`` (renaming
  ``*services*.py`` → ``*specs*.py``; the populator's *content* must be updated
  by hand afterwards) ; ``data/README.md`` → ``specs/README.md``.
- each ``data/<provider>/services/<svc>/`` → ``specs/<provider>/<name>/`` where
  ``name`` is the (namespaced) service name; one folder per *Service* (per
  listing file).
- per service folder: ``schema`` field dropped from every spec; ``listing.name``
  set to ``<provider>/<short>`` ; ``provider.toml`` inlined as ``provider.json``
  (TOML→JSON) ; ``<listing>.override.json`` → ``service.json`` (keeps
  ``service_id``; ``name`` moves into the listing). Offering/listing keep their
  original format (json or toml).

Only ``.json``/``.toml`` sources are processed (gitignored test artifacts like
``listing_*.sh`` / ``*.out`` are ignored). After it runs, ``git add -A`` (git
detects the renames) and commit.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sys
import tomllib

OFFERING_NAMES = ("offering.json", "offering.toml")


def load_any(path: pathlib.Path) -> dict:
    if path.suffix == ".toml":
        return tomllib.loads(path.read_text())
    return json.loads(path.read_text())


def write_json(path: pathlib.Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def strip_toml_keys(text: str, drop: set[str], setkv: dict[str, str]) -> str:
    """Line-based TOML edit: drop top-level keys in ``drop``; set/replace
    top-level keys in ``setkv`` (added at end if absent). Good enough for the
    simple top-level scalar keys we touch (``schema``, ``name``)."""
    out, seen = [], set()
    for line in text.splitlines():
        key = line.split("=", 1)[0].strip() if "=" in line else None
        if key in drop:
            continue
        if key in setkv:
            out.append(f'{key} = "{setkv[key]}"')
            seen.add(key)
        else:
            out.append(line)
    for k, v in setkv.items():
        if k not in seen:
            out.append(f'{k} = "{v}"')
    return "\n".join(out).rstrip("\n") + "\n"


def listing_files(svc_dir: pathlib.Path) -> list[pathlib.Path]:
    files = []
    for p in sorted(svc_dir.iterdir()):
        if not p.is_file() or p.suffix not in (".json", ".toml"):
            continue
        if p.name.endswith(".override.json") or p.name in OFFERING_NAMES:
            continue
        if p.name.startswith("listing"):
            files.append(p)
    return files


def migrate(root: pathlib.Path, dry_run: bool) -> int:
    data = root / "data"
    specs = root / "specs"
    if not data.is_dir():
        sys.exit(f"no data/ directory in {root}")
    if specs.exists():
        sys.exit("specs/ already exists — refusing to clobber")

    actions: list[str] = []
    n_services = 0
    providers = [
        p
        for p in sorted(data.iterdir())
        if p.is_dir() and ((p / "provider.toml").exists() or (p / "provider.json").exists())
    ]
    if not providers:
        sys.exit("no data/<provider>/provider.{toml,json} found")

    for prov_dir in providers:
        prov_name = prov_dir.name
        prov_src = prov_dir / "provider.toml"
        if not prov_src.exists():
            prov_src = prov_dir / "provider.json"
        provider = load_any(prov_src)
        provider.pop("schema", None)
        # ``services_populator`` is repo/provider-level config, not per-service
        # provider identity — don't duplicate it into every folder. The populator
        # script itself is moved+renamed below; its invocation must be re-wired
        # by hand afterwards.
        if provider.pop("services_populator", None) is not None:
            actions.append(f"[note] dropped services_populator from {prov_name} provider (re-wire the moved populator by hand)")

        svc_root = prov_dir / "services"
        for svc_dir in sorted(p for p in svc_root.iterdir() if p.is_dir()):
            lst_files = listing_files(svc_dir)
            if not lst_files:
                continue
            offering = next((svc_dir / n for n in OFFERING_NAMES if (svc_dir / n).exists()), None)
            multi = len(lst_files) > 1

            for lst in lst_files:
                override = svc_dir / f"{lst.stem}.override.json"
                ov = json.loads(override.read_text()) if override.exists() else {}
                lst_data = load_any(lst)
                # Name precedence: the listing's own ``name`` (already
                # provider-namespaced in mature repos like parasail) > the
                # override's ``name`` > the folder name (single-listing only).
                raw = lst_data.get("name") or ov.get("name") or (None if multi else svc_dir.name)
                if not raw:
                    sys.exit(f"{lst}: multi-listing needs a name (in the listing or its override)")
                # Namespace under the provider unless it already is. The full
                # (possibly nested) name becomes the folder path under specs/.
                name = raw if raw.startswith(f"{prov_name}/") else f"{prov_name}/{raw}"
                out = specs / name
                actions.append(f"{svc_dir.relative_to(root)}/{lst.name} -> {out.relative_to(root)}/ (name={name})")
                if dry_run:
                    n_services += 1
                    continue
                out.mkdir(parents=True, exist_ok=True)

                write_json(out / "provider.json", provider)

                if offering is not None:
                    if offering.suffix == ".json":
                        off = json.loads(offering.read_text())
                        off.pop("schema", None)
                        write_json(out / "offering.json", off)
                    else:
                        (out / "offering.toml").write_text(
                            strip_toml_keys(offering.read_text(), {"schema"}, {})
                        )

                if lst.suffix == ".json":
                    d = dict(lst_data)
                    d.pop("schema", None)
                    d["name"] = name
                    write_json(out / "listing.json", d)
                else:
                    (out / "listing.toml").write_text(
                        strip_toml_keys(lst.read_text(), {"schema"}, {"name": name})
                    )

                ov.pop("name", None)
                write_json(out / "service.json", ov)
                n_services += 1

    # docs -> top level ; data/README.md -> specs/README.md
    for prov_dir in providers:
        d = prov_dir / "docs"
        if d.is_dir():
            for f in d.rglob("*"):
                if f.is_file():
                    actions.append(f"{f.relative_to(root)} -> docs/{f.relative_to(d)}")
                    if not dry_run:
                        dest = root / "docs" / f.relative_to(d)
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(f, dest)
    readme = data / "README.md"
    if readme.exists():
        actions.append("data/README.md -> specs/README.md")
        if not dry_run:
            (specs).mkdir(parents=True, exist_ok=True)
            shutil.copy2(readme, specs / "README.md")

    # templates/ -> top-level templates/ (the populator's render templates /
    # local templates). Moved verbatim; restructuring to the admin-shaped local
    # template format is later content work.
    def move_dir_to_top(name: str, rename=None) -> None:
        srcs = [p / name for p in providers if (p / name).is_dir()]
        if (data / name).is_dir():
            srcs.append(data / name)
        for sdir in srcs:
            for f in sorted(sdir.rglob("*")):
                if not f.is_file():
                    continue
                rel = f.relative_to(sdir)
                dest = root / name / rel
                if rename:
                    dest = rename(dest, f)
                actions.append(f"{f.relative_to(root)} -> {dest.relative_to(root)}")
                if not dry_run:
                    if dest.exists():
                        sys.exit(f"{name} collision: {dest}")
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, dest)

    move_dir_to_top("templates")
    # scripts/ -> top-level scripts/ ; rename *services*.py -> *specs*.py
    # (content of the renamed populator must be updated by hand afterwards).
    move_dir_to_top(
        "scripts",
        rename=lambda dest, f: dest.with_name(f.name.replace("services", "specs"))
        if f.suffix == ".py" and "services" in f.name
        else dest,
    )

    if not dry_run:
        shutil.rmtree(data)

    print("\n".join(actions))
    print(f"\n{'[dry-run] would migrate' if dry_run else 'migrated'} {n_services} service(s) "
          f"across {len(providers)} provider(s). Now: git add -A && review the diff.")
    return n_services


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", nargs="?", default=".", help="repo root (default: cwd)")
    ap.add_argument("--dry-run", action="store_true", help="print actions, change nothing")
    a = ap.parse_args()
    migrate(pathlib.Path(a.root).resolve(), a.dry_run)

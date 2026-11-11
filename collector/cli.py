"""Interface en ligne de commande : ``python -m collector <commande>``."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .config import CONFIG_DIR, ROOT, load_departments, load_settings, load_sources
from .geo import GeoIndex
from .log import setup_logging

DEFAULT_STATE = ROOT / "data" / "state"
DEFAULT_RAW = ROOT / "data" / "raw"
DEFAULT_PUBLIC = ROOT / "data" / "public"


def _shard(value: str) -> tuple[int, int]:
    i, n = value.split("/")
    if not (0 <= int(i) < int(n)):
        raise argparse.ArgumentTypeError("format attendu : index/total, ex. 0/2")
    return int(i), int(n)


def _filter_sources(args: argparse.Namespace):
    sources = load_sources(Path(args.config))
    if args.sources:
        wanted = set(args.sources.split(","))
        unknown = wanted - {s.id for s in sources}
        if unknown:
            sys.exit(f"Sources inconnues : {', '.join(sorted(unknown))}")
        # Une exécution explicite ignore le calendrier des sources (plage horaire, intervalle minimal).
        no_schedule = {"min_interval_hours": None, "run_hours_utc": None}
        sources = [
            s.model_copy(update={"enabled": True, "options": {**s.options, **no_schedule}})
            if s.id in wanted else s.model_copy(update={"enabled": False})
            for s in sources
        ]
    if args.max_details is not None:
        sources = [s.model_copy(update={"max_details_per_run": args.max_details}) for s in sources]
    return sources


def _departments(args: argparse.Namespace):
    deps = load_departments(Path(args.config))
    if getattr(args, "departments", None):
        wanted = set(args.departments.split(","))
        deps = [d for d in deps if d.code in wanted]
    return deps


def cmd_collect(args: argparse.Namespace) -> int:
    from .collect import run_collect
    from .pipeline.state import State

    deps = _departments(args)
    batches = run_collect(
        _filter_sources(args), GeoIndex.load(), {d.code for d in deps}, State.load(Path(args.state)),
        load_settings(Path(args.config)), Path(args.raw), shard=args.shard, workers=args.workers,
    )
    print(json.dumps([b.status.model_dump(exclude={"errors"}) for b in batches], ensure_ascii=False, indent=1))
    return 0


def cmd_process(args: argparse.Namespace) -> int:
    from .process import report_markdown, run_process

    report = run_process(
        Path(args.raw), Path(args.state), Path(args.public), load_sources(Path(args.config)),
        load_departments(Path(args.config)), GeoIndex.load(), load_settings(Path(args.config)),
    )
    md = report_markdown(report)
    print(md)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(md)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    import shutil

    raw = Path(args.raw)
    if raw.exists():
        shutil.rmtree(raw)
    cmd_collect(args)
    return cmd_process(args)


def cmd_refresh_geo(args: argparse.Namespace) -> int:
    from .geo_refresh import refresh_geo

    print(f"{refresh_geo(load_departments(Path(args.config)))} communes enregistrées")
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    from .discovery import discover_candidates

    urls = list(args.urls)
    if args.file:
        urls += [line.strip() for line in Path(args.file).read_text().splitlines() if line.strip() and not line.startswith("#")]
    out = discover_candidates(urls, load_settings(Path(args.config)), Path(args.config))
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


def cmd_sources(args: argparse.Namespace) -> int:
    for s in load_sources(Path(args.config), include_candidates=True):
        flag = "ON " if s.enabled else "off"
        print(f"[{flag}] {s.id:<24} {s.compatibility.value:<20} {s.method:<15} {s.domain}")
    return 0


def cmd_schema(args: argparse.Namespace) -> int:
    from .schema import export_schema

    for p in export_schema(Path(args.out)):
        print(p)
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    from .demo import build_demo

    report = build_demo(Path(args.out))
    print(f"Jeu de démonstration (fictif) écrit dans {args.out} : {report['active_listings']} annonces actives")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="collector", description="FindImmo Collector")
    p.add_argument("--config", default=str(CONFIG_DIR))
    p.add_argument("--log-level", default=os.environ.get("FINDIMMO_LOG_LEVEL", "INFO"))
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--state", default=str(DEFAULT_STATE))
        sp.add_argument("--raw", default=str(DEFAULT_RAW))
        sp.add_argument("--public", default=str(DEFAULT_PUBLIC))

    def collect_opts(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--shard", type=_shard, default=(0, 1), help="index/total, ex. 0/2")
        sp.add_argument("--sources", help="liste d'identifiants (force leur activation)")
        sp.add_argument("--departments", help="restreindre aux départements, ex. 77,83")
        sp.add_argument("--max-details", type=int, help="budget de pages détail par source")
        sp.add_argument("--workers", type=int, default=4)

    sp = sub.add_parser("collect", help="exécuter les connecteurs → lots bruts")
    common(sp)
    collect_opts(sp)
    sp.set_defaults(func=cmd_collect)
    sp = sub.add_parser("process", help="lots bruts + état → JSON publics")
    common(sp)
    sp.set_defaults(func=cmd_process)
    sp = sub.add_parser("run", help="collect puis process")
    common(sp)
    collect_opts(sp)
    sp.set_defaults(func=cmd_run)
    sp = sub.add_parser("refresh-geo", help="télécharger le référentiel des communes")
    sp.set_defaults(func=cmd_refresh_geo)
    sp = sub.add_parser("discover", help="évaluer des domaines d'agences candidats")
    sp.add_argument("urls", nargs="*")
    sp.add_argument("--file")
    sp.set_defaults(func=cmd_discover)
    sp = sub.add_parser("sources", help="lister le registre des sources")
    sp.set_defaults(func=cmd_sources)
    sp = sub.add_parser("demo", help="générer le jeu de données FICTIF de démonstration")
    sp.add_argument("--out", default=str(ROOT / "apps" / "web" / "public" / "demo-data"))
    sp.set_defaults(func=cmd_demo)
    sp = sub.add_parser("schema", help="exporter le JSON Schema du format publié")
    sp.add_argument("--out", default=str(ROOT / "packages" / "shared" / "schema"))
    sp.set_defaults(func=cmd_schema)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.log_level)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

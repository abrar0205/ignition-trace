import argparse
import json
import os
import tempfile
from pathlib import Path

from .engine import analyze, state_at
from .model import Budgets, ScenarioConfig, Trace
from .simulate import simulate


def save(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".trace-")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, allow_nan=False, separators=(",", ":"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def load(path: str):
    if Path(path).stat().st_size > 8 * 1024 * 1024:
        raise ValueError("Trace exceeds 8 MiB")
    return Trace.model_validate_json(Path(path).read_bytes())


def main():
    parser = argparse.ArgumentParser(description="IgnitionTrace evidence toolkit")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo")
    demo.add_argument("--scenario", default="mixed")
    demo.add_argument("--seed", type=int, default=42)
    demo.add_argument("--out", default="runs/demo")
    check = sub.add_parser("analyze")
    check.add_argument("trace")
    check.add_argument("--out", default="runs/analysis")
    check.add_argument("--budgets")
    check.add_argument("--fail-on-findings", action="store_true")
    replay = sub.add_parser("replay")
    replay.add_argument("trace")
    replay.add_argument("--at-ms", type=float, required=True)
    args = parser.parse_args()
    trace = (
        simulate(ScenarioConfig(scenario=args.scenario, seed=args.seed))
        if args.command == "demo"
        else load(args.trace)
    )
    if args.command == "replay":
        print(json.dumps(state_at(trace, args.at_ms)))
        return
    budgets = (
        Budgets.model_validate_json(Path(args.budgets).read_bytes())
        if getattr(args, "budgets", None)
        else Budgets()
    )
    report = analyze(trace, budgets)
    save(Path(args.out) / "trace.json", trace.model_dump())
    save(Path(args.out) / "report.json", report)
    print(
        json.dumps(
            {"events": report["event_count"], "findings": report["finding_count"], "out": args.out}
        )
    )
    if getattr(args, "fail_on_findings", False) and report["finding_count"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

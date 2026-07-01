import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="dlazy — minimal DFT workflow engine")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run a workflow")
    run.add_argument("param", help="param.json")
    run.add_argument("machine", help="machine.json")
    run.add_argument("--step", default=None, help="Only run a specific step by name")
    run.add_argument("--dry-run", action="store_true", help="Print tasks without submitting")
    run.add_argument("--retry-failed", action="store_true",
        help="Massive mode: retry only sids marked fail in --step's _summary.ndjson")
    run.add_argument("--only-sids", default=None,
        help="Massive mode: run only these sids (comma-separated)")

    collect = sub.add_parser("collect", help="Export SCF results to DeepH training format")
    collect.add_argument("param", help="param.json")
    collect.add_argument("machine", help="machine.json")
    collect.add_argument("--step", default=None, help="Only export one step")
    collect.add_argument("--all", action="store_true",
        help="Force collect ALL structures found on disk, ignoring structures file list")

    args = parser.parse_args()

    if args.command in ("run", "collect"):
        from .engine import Workflow
        wf = Workflow(args.param, args.machine)
        if args.command == "run":
            wf.run(step_filter=args.step, dry_run=args.dry_run,
                    retry_failed=args.retry_failed, only_sids=args.only_sids)
        else:
            wf.collect_results(step_filter=args.step, all_sids=args.all)


if __name__ == "__main__":
    main()

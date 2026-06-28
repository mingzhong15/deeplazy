import argparse
import sys

from .engine import Workflow


def main():
    parser = argparse.ArgumentParser(description="dlazy — minimal DFT workflow engine")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run a workflow")
    run.add_argument("param", help="param.json")
    run.add_argument("machine", help="machine.json")
    run.add_argument("--step", default=None, help="Only run a specific step by name")
    run.add_argument("--dry-run", action="store_true", help="Print tasks without submitting")

    collect = sub.add_parser("collect", help="Export SCF results to DeepH training format")
    collect.add_argument("param", help="param.json")
    collect.add_argument("machine", help="machine.json")
    collect.add_argument("--step", default=None, help="Only export one step")

    args = parser.parse_args()

    if args.command == "run":
        wf = Workflow(args.param, args.machine)
        wf.run(step_filter=args.step, dry_run=args.dry_run)
    elif args.command == "collect":
        wf = Workflow(args.param, args.machine)
        wf.collect_results(step_filter=args.step)


if __name__ == "__main__":
    main()

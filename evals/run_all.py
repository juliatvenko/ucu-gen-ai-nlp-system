"""Run component evals. Example: python -m evals.run_all --mode offline --split dev"""
import argparse
import json
import sys
import time

from trialmatch.llm import get_client

from . import eval_aggregate, eval_checker, eval_parsing, eval_patient_search, eval_profile, eval_retrieval, eval_safety, eval_trec
from .common import save

COMPONENTS = {
    "profile": eval_profile,
    "retrieval": eval_retrieval,
    "parsing": eval_parsing,
    "checker": eval_checker,
    "aggregate": eval_aggregate,
    "safety": eval_safety,
    "trec": eval_trec,
    "patient_search": eval_patient_search,
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["offline", "llm"], default="offline")
    ap.add_argument("--split", choices=["dev", "test"], default="dev")
    ap.add_argument("--only", nargs="*", choices=list(COMPONENTS))
    ap.add_argument("--limit", type=int, help="patients or topics; use it for LLM runs on a free tier")
    args = ap.parse_args()

    client = None
    if args.mode == "llm":
        client = get_client()
        if client is None:
            sys.exit("No LLM key found. Add one to .env, or use --mode offline.")

    for name in args.only or COMPONENTS:
        started = time.time()
        result = COMPONENTS[name].run(args.mode, args.split, args.limit, client)
        result.update(mode=args.mode, split=args.split, limit=args.limit, model=client.label if client else None,
                      seconds=round(time.time() - started, 1), date=time.strftime("%Y-%m-%d"))
        path = save(name, args.mode, args.split, result)
        print(f"\n## {name} ({args.mode}, {args.split}) -> {path.name}")
        print(json.dumps(result["metrics"], indent=1))
        print(f"errors recorded: {len(result['errors'])}")
        if name == "trec" and client is None:
            # The LLM run samples fewer trials per label, and nDCG depends on pool size, so also score that pool.
            same = eval_trec.run(args.mode, args.split, args.limit, None, per_label=2)
            save("trec_samepool", args.mode, args.split, same)


if __name__ == "__main__":
    main()

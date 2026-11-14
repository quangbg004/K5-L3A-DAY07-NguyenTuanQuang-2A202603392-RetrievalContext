"""Run and review the bonus benchmark independently of the basic lab."""
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import os
from pathlib import Path
from statistics import median
from time import perf_counter

from advanced_agent import ReportIndex, run_case
from advanced_claude import Claude, MODEL
from day7 import ROOT, read, write

BENCHMARK = ROOT / "data" / "advanced" / "benchmark.json"
CONFIGS = {
    "text": {"pages": 4, "images": 0},
    "vision": {"pages": 5, "images": 3},
}
RULE = "Highest dev pass count, then lowest reported API cost, then config order."


def summarize(cases, traces, reviews):
    by_id = {r["id"]: r for r in reviews}
    if set(by_id) != {c["id"] for c in cases} or len(by_id) != len(reviews):
        raise ValueError("A unique review is required for every case")
    counts = defaultdict(lambda: {"n": 0, "N": 0})
    for case, trace in zip(cases, traces, strict=True):
        review = by_id[case["id"]]
        if trace["id"] != case["id"] or type(review["pass"]) is not bool or not review["reason"].strip():
            raise ValueError("Trace or review does not match benchmark")
        if review["pass"] and (trace["status"] == "error" or
                               (trace["status"] == "abstain") != (case["group"] == "missing")):
            raise ValueError("Review pass contradicts agent status")
        for group in (case["group"], "overall"):
            counts[group]["n"] += review["pass"]
            counts[group]["N"] += 1
    return {
        "groups": {group: {**c, "rate": c["n"] / c["N"]} for group, c in counts.items()},
        "errors": sum(t["status"] == "error" for t in traces),
        "median_ms": median(t["elapsed_ms"] for t in traces),
        "usage": {key: sum(t["usage"][key] for t in traces) if all(t["usage"][key] is not None for t in traces)
                  else None for key in ("cost", "prompt_tokens", "completion_tokens")},
    }


def review(output, split, names, cases):
    summaries = {}
    for name in names:
        folder = output / split / name
        result = summarize(cases, read(folder / "traces.json"), read(folder / "reviews.json"))
        write(folder / "summary.json", result)
        summaries[name] = result
    return summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("dev", "select", "test", "review-test"))
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--index", type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "advanced-haiku")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--retry-errors", action="store_true",
                        help="Retry only system errors from the frozen test configuration")
    args = parser.parse_args()
    benchmark = BENCHMARK.read_bytes()
    cases = json.loads(benchmark)
    signature = {"benchmark_sha256": sha256(benchmark).hexdigest(), "configs": CONFIGS,
                 "model": MODEL, "selection_rule": RULE}
    lock = args.output / "selection.json"
    split = "dev" if args.action in ("dev", "select") else "test"
    cases = [c for c in cases if c["split"] == split]
    names = list(CONFIGS)
    if split == "test":
        selection = read(lock)
        if selection["signature"] != signature:
            raise ValueError("Benchmark, model or configs changed after selection")
        names = [selection["selected"]]
    elif lock.exists():
        raise ValueError("A dev configuration is frozen in this output directory")
    if args.action == "select":
        previous = read(args.output / split / "run.json")
        if previous["signature"] != signature:
            raise ValueError("Dev run signature mismatch")
        summaries = review(args.output, split, names, cases)
        selected = max(names, key=lambda name: (summaries[name]["groups"]["overall"]["n"],
                                                -summaries[name]["usage"]["cost"]))
        write(lock, {**previous, "selected": selected})
        print(f"Selected {selected}")
        return
    if args.action == "review-test":
        print(json.dumps(review(args.output, split, names, cases), indent=2))
        return
    if args.pdf is None or args.index is None:
        parser.error("--pdf and --index are required for dev and test")
    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file)
    start = perf_counter()
    index = ReportIndex(args.pdf, read(args.index))
    index_sha = sha256(args.index.read_bytes()).hexdigest()
    if split == "test" and index_sha != selection["index_sha256"]:
        raise ValueError("The index has changed since dev selection")
    if args.retry_errors:
        if args.action != "test":
            parser.error("--retry-errors requires test")
        previous = read(args.output / split / "run.json")
        if previous["signature"] != signature or previous["index_sha256"] != index_sha:
            raise ValueError("Prior test signature differs")
    write(args.output / split / "run.json", {"signature": signature, "index_sha256": index_sha,
           "pdf": index.manifest, "lexical_setup_seconds": perf_counter() - start})
    client = Claude(os.environ["ANTHROPIC_API_KEY"])
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for name in names:
            folder = args.output / split / name
            prior = {t["id"]: t for t in read(folder / "traces.json")} if args.retry_errors else {}
            jobs = {
                c["id"]: pool.submit(run_case, index, client, CONFIGS[name], c["question"])
                for c in cases if prior.get(c["id"], {}).get("status", "error") == "error"
            }
            traces = prior.copy()
            for case in cases:
                job = jobs.get(case["id"])
                if job is None:
                    continue
                trace = {"id": case["id"], **job.result()}
                previous = prior.get(case["id"])
                if previous:
                    history = previous.pop("prior_attempts", [])
                    trace["prior_attempts"] = [*history, previous]
                traces[case["id"]] = trace
                print(name, case["id"], trace["status"], flush=True)
                write(folder / "traces.json", [traces[c["id"]] for c in cases if c["id"] in traces])


if __name__ == "__main__":
    main()

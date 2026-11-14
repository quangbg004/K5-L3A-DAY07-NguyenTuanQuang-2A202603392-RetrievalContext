"""Run Day 7 experiments against the original Day 6 pgvector store."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
from statistics import mean, median
from time import perf_counter, sleep

from agent_metrics import aggregate
from baseline import hit, validate
from day7_agent import OpenRouter, run
from day7_retrieval import Day6Index, question_filter

ROOT = Path(__file__).resolve().parents[1]
MODEL = "openai/gpt-4.1-mini"
CONFIGS = {
    "dense": dict(method="dense", top_k=3, budget=2000, searches=1),
    "tfidf": dict(method="tfidf", top_k=3, budget=2000, searches=1),
    "hybrid": dict(method="hybrid", top_k=3, budget=2000, searches=1),
    "hybrid-wide": dict(method="hybrid", top_k=6, budget=3600, searches=2),
}
# Freeze before dev. Only reviewed full-credit answers count in the first criterion.
RULE = ("Highest fraction of fully grounded dev answers, then correct abstention, "
        "exact Context Evidence Rate, Evidence Hit@3, lowest API cost, then config order.")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for attempt in range(3):
        try:
            temp.replace(path)
            break
        except PermissionError:
            if attempt == 2:
                raise
            sleep(0.1 * (attempt + 1))


def execute(index, controller, config, case):
    start = perf_counter()
    question = case["question"]
    filters = question_filter(question)
    trace = {"query_id": case["id"], "question": question, "filter": filters, "events": [],
             "status": "error", "context": "", "context_ids": [], "citations": []}
    try:
        ranking = index.search(config["method"], question, max(3, config["top_k"]), filters)
    except Exception as exc:
        # Connection details in driver exceptions can contain credentials.
        trace["error"] = {"stage": "original_ranking", "type": type(exc).__name__}
    else:
        trace["original_retrieval_ms"] = (perf_counter() - start) * 1000
        trace["original_top3"] = ranking[:3]
        try:
            run(question, index, controller, config, filters, ranking, trace)
        except (RuntimeError, ValueError) as exc:
            trace["error"] = {"stage": "agent", "type": type(exc).__name__, "message": str(exc)}
        except Exception as exc:
            trace["error"] = {"stage": "agent", "type": type(exc).__name__}
    trace["elapsed_ms"] = (perf_counter() - start) * 1000
    calls = [event for event in trace["events"] if event["event"] == "model"]
    usages = [event["usage"] for event in calls]
    trace["usage"] = {
        key: sum(usage[key] for usage in usages) if all(usage.get(key) is not None for usage in usages) else None
        for key in ("prompt_tokens", "completion_tokens", "cost")
    }
    return trace


def scores(traces, cases, chunks):
    by_id = {case["id"]: case for case in cases}
    total = sum(case["answerable"] for case in cases)
    metrics = Counter()
    for trace in traces:
        case = by_id[trace["query_id"]]
        gold = case.get("gold", [])
        ranking = trace.get("original_top3", [])
        trace["hit1"] = any(hit(row, gold) for row in ranking[:1])
        trace["hit3"] = any(hit(row, gold) for row in ranking)
        trace["context_hit"] = any(hit(chunks[cid], gold) for cid in trace["context_ids"])
        for metric in ("hit1", "hit3", "context_hit"):
            metrics[metric] += trace[metric]
    return {
        **{metric: {"n": metrics[metric], "N": total, "rate": metrics[metric] / total}
           for metric in ("hit1", "hit3", "context_hit")},
        "errors": sum(t["status"] == "error" for t in traces),
        "tool_calls": dict(Counter(sum(e["event"] == "search" for e in t["events"]) for t in traces)),
        "median_original_ms": median(t["original_retrieval_ms"] for t in traces if "original_retrieval_ms" in t)
        if any("original_retrieval_ms" in t for t in traces) else None,
        "median_total_ms": median(t["elapsed_ms"] for t in traces),
        "avg_context_chars": mean(len(t["context"]) for t in traces),
        "usage": {
            key: sum(t["usage"][key] for t in traces) if all(t["usage"][key] is not None for t in traces) else None
            for key in ("prompt_tokens", "completion_tokens", "cost")
        },
    }


def review_split(output, split, names, cases):
    summaries = {}
    for name in names:
        directory = output / split / name
        traces = read(directory / "traces.json")
        reviews = read(directory / "reviews.json")
        summary = read(directory / "summary.json")
        summary["agent"] = aggregate(cases, traces, reviews)
        summary["context_grades"] = dict(Counter(r["context_grade"] for r in reviews if "context_grade" in r))
        write(directory / "summary.json", summary)
        summaries[name] = summary
    return summaries


def choose(summaries):
    if any(s["errors"] for s in summaries.values()):
        raise RuntimeError("Resolve provider or retrieval errors on dev before freezing the config.")

    def key(name):
        summary = summaries[name]
        agent = summary["agent"]
        return (
            agent["grounded_answer"]["2"] / agent["grounded_answer"]["N"],
            agent["abstention"]["n"] / agent["abstention"]["N"],
            summary["context_hit"]["rate"], summary["hit3"]["rate"],
            -summary["usage"]["cost"],
        )

    return max(CONFIGS, key=key)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("dev", "select", "test", "review-test"))
    parser.add_argument("--day6", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "results")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    path = ROOT / "data" / "questions.json"
    cases = read(path)
    signature = {"benchmark_sha256": sha256(path.read_bytes()).hexdigest(),
                 "model": MODEL, "configs": CONFIGS, "rule": RULE}
    lock = args.output / "selection.json"
    dev = [c for c in cases if c["split"] == "dev"]
    test = [c for c in cases if c["split"] == "test"]
    if args.action == "select":
        if lock.exists():
            raise RuntimeError("A config is already frozen in this output directory.")
        run_info = read(args.output / "dev" / "run.json")
        if run_info["signature"] != signature:
            raise RuntimeError("Dev run differs from the current benchmark or configs.")
        selection = choose(review_split(args.output, "dev", CONFIGS, dev))
        write(lock, {**run_info, "selected": selection})
        print(f"Selected on dev: {selection}", flush=True)
        return
    names = list(CONFIGS)
    split = args.action if args.action in ("dev", "test") else "test"
    selected_cases = dev if split == "dev" else test
    if split == "test":
        selection = read(lock)
        if selection["signature"] != signature:
            raise RuntimeError("Benchmark or configs changed after dev selection.")
        names = list(dict.fromkeys(("dense", selection["selected"])))
    if args.action == "review-test":
        review_split(args.output, "test", names, test)
        return
    if split == "dev" and lock.exists():
        raise RuntimeError("The dev run is frozen. Use a fresh output directory for a new experiment.")
    if not args.day6:
        parser.error("--day6 is required for dev and test")
    index = Day6Index(args.day6)
    validate(index.chunks, [c for c in selected_cases if c["answerable"]])
    run_info = {"signature": signature, "index": index.info}
    if split == "test":
        for field in ("embedding_fingerprint", "corpus_sha256"):
            if index.info[field] != selection["index"][field]:
                raise RuntimeError("Day 6 index changed after dev selection.")
    write(args.output / split / "run.json", run_info)
    controller = OpenRouter(index.env["OPENROUTER_API_KEY"], MODEL)
    chunks = {c["id"]: c for c in index.chunks}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for name in names:
            folder = args.output / split / name
            config = CONFIGS[name]
            jobs = [pool.submit(execute, index, controller, config, case) for case in selected_cases]
            traces = [job.result() for job in jobs]
            summary = scores(traces, selected_cases, chunks)
            write(folder / "traces.json", traces)
            write(folder / "summary.json", summary)
            print(name, json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()

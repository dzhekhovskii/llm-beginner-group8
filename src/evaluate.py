"""Measure the component on evals/test_cases.csv: scores, a judge with its controls, cost and latency.

    python -m src.evaluate run --strategy zero_shot      # the 30 cases through the component, then scored
    python -m src.evaluate run --strategy few_shot
    python -m src.evaluate run --strategy cot
    python -m src.evaluate swap --a zero_shot --b cot    # the judge compares two strategies, in BOTH orders
    python -m src.evaluate calibrate                     # our 10 hand scores (evals/calibration.csv) vs the judge
    python -m src.evaluate report                        # the table, the Pareto front, the failures to read

Scorers, from the cheapest and most trusted to the least:
  1. no model: exact match and token F1 on the short answer (SQuAD's normalisation, plus ours for prices),
     "evidence retrieved" (was the case's evidence sentence among the passages?), and for an unanswerable
     case, the rule "answerable is false";
  2. BLEU and ROUGE-L on the full answer, reported but never used to decide: they reward copying the
     reference's words (lesson 4: a wrong answer scored 79);
  3. a judge, from ANOTHER model than the component's (llm.JUDGE_MODEL), scoring the four criteria of
     evals/rubric.md from 1 to 5, as a record; a case is right when "correct" is 4 or 5. Comparisons of two
     answers are judged in both orders, and a preference counts only when it survives the swap.

Every API call goes through src/llm.py, which logs its tokens, cost and latency to runs/calls.csv.
"""

import argparse
import csv
import json
import re
import statistics
from collections import Counter
from datetime import date
from pathlib import Path

from src import llm
from src.retrieve import has_evidence
from src.schema import Choice, Verdict

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "evals" / "test_cases.csv"
CALIBRATION = ROOT / "evals" / "calibration.csv"
RUNS = ROOT / "runs"
EVAL_DOC = ROOT / "docs" / "evaluation.md"
PROMPTS = ROOT / "prompts"

CASE_COLUMNS = ["case_id", "input", "expected", "second_acceptable", "written_by", "checked_by"]


# ------------------------------------------------------------------ scorers that need no model

def normalise(text):
    """SQuAD's rule (lower case, no punctuation, no a/an/the, spaces collapsed) plus ours for prices:
    "4,90 €" -> "4.90", "12 %" -> "12%". Tested on known pairs in tests/test_evaluate.py."""
    s = (text or "").lower().replace("€", " ")
    s = re.sub(r"(\d),(\d)", r"\1.\2", s)           # a decimal comma BETWEEN two digits only
    s = re.sub(r"(\d)\s+%", r"\1%", s)
    s = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", s)        # a full stop, unless inside a number
    s = re.sub(r"[^\w.% ]", " ", s)
    return " ".join(w for w in s.split() if w not in ("a", "an", "the"))


def exact_match(prediction, gold):
    return normalise(prediction) == normalise(gold)


def token_f1(prediction, gold):
    p, g = normalise(prediction).split(), normalise(gold).split()
    if not p or not g:
        return float(p == g)
    common = sum((Counter(p) & Counter(g)).values())
    if common == 0:
        return 0.0
    precision, recall = common / len(p), common / len(g)
    return 2 * precision * recall / (precision + recall)


def bleu(candidate, reference):
    import sacrebleu
    return sacrebleu.sentence_bleu(candidate, [reference]).score


def rouge_l(candidate, reference):
    from rouge_score import rouge_scorer
    return rouge_scorer.RougeScorer(["rougeL"]).score(reference, candidate)["rougeL"].fmeasure * 100


# ------------------------------------------------------------------ the test cases

def load_cases(path=CASES, require_labels=True):
    """The test cases. A case is unanswerable when its column `answerable` is "no"."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    missing = [c for c in CASE_COLUMNS if c not in (rows[0] if rows else {})]
    if missing:
        raise ValueError(f"{path.name}: missing columns {missing}")
    if require_labels:
        unlabelled = [r["case_id"] for r in rows if r.get("answerable", "").strip().lower() not in ("yes", "no")
                      or (r["answerable"].strip().lower() == "yes" and not r["expected"].strip())]
        if unlabelled:
            raise ValueError(f"cases not labelled yet (expected / answerable): {unlabelled}")
        same = [r["case_id"] for r in rows if r["written_by"].strip().lower() == r["checked_by"].strip().lower()]
        if same:
            raise ValueError(f"cases checked by their own writer: {same}")
    return rows


def is_answerable(case):
    return case.get("answerable", "yes").strip().lower() != "no"


# ------------------------------------------------------------------ the judge

def _prompt(filename):
    blocks = re.findall(r"```text\n(.*?)\n```", (PROMPTS / filename).read_text(encoding="utf-8"), re.DOTALL)
    return blocks[0], blocks[1]


def judge(case, candidate, passages, model=llm.JUDGE_MODEL, tag=""):
    """One answer scored on the rubric's four criteria. Returns the llm.Result (record: a Verdict)."""
    system, user = _prompt("judge.md")
    user = (user.replace("{question}", case["input"]).replace("{reference}", case["expected"])
            .replace("{candidate}", candidate)
            .replace("{passages}", "\n\n".join(f"[{p['id']}] {p['text']}" for p in passages)))
    return llm.structured_call(model=model, system=system, user=user, schema=Verdict, tag=tag or "judge")


def judge_pair(case, a, b, model=llm.JUDGE_MODEL, tag=""):
    """Which of two answers is better, "A" or "B" (None if the judge call gave up)."""
    system, user = _prompt("judge_pair.md")
    user = (user.replace("{question}", case["input"]).replace("{reference}", case["expected"])
            .replace("{a}", a).replace("{b}", b))
    r = llm.structured_call(model=model, system=system, user=user, schema=Choice, tag=tag or "judge_pair")
    return r.record.better if r.ok else None


def swap(case, first, second, model=llm.JUDGE_MODEL, tag=""):
    """The pair judged twice, once in each order: "first" or "second" if the same answer won both times,
    "position" if the same LETTER won both times (the order decided, not the answers)."""
    once = judge_pair(case, first, second, model, tag + ":ab")
    twice = judge_pair(case, second, first, model, tag + ":ba")
    if once == "A" and twice == "B":
        return "first"
    if once == "B" and twice == "A":
        return "second"
    return "position" if once and twice else "failed"


# ------------------------------------------------------------------ one run of one strategy

RESULT_FIELDS = ["case_id", "kind", "input", "expected", "expected_short", "answerable_expected",
                 "sent", "short_answer", "answerable", "citations", "retrieved", "evidence_retrieved",
                 "calls", "reprompts", "gave_up", "blocked", "usd", "ms",
                 "em", "f1", "bleu", "rouge_l", "j_correct", "j_complete", "j_grounded", "j_clear", "j_reason",
                 "judge_usd", "right", "right_by"]


def results_path(strategy, model):
    return RUNS / f"results_{strategy}_{model}.csv"


def run(strategy, model=llm.COMPONENT_MODEL, judge_model=llm.JUDGE_MODEL, limit=None, cases_path=CASES):
    from src.assistant import answer   # imported here: it loads the embedding model
    if judge_model == model:
        raise ValueError("the judge must be a different model from the component's")
    cases = load_cases(cases_path)[:limit]
    rows = []
    for case in cases:
        reply = answer(case["input"], strategy, model, tag=f"{strategy}:{case['case_id']}")
        rec = reply.record
        short = rec.short_answer if rec else ""
        golds = [g for g in (case.get("expected_short", ""), case.get("second_acceptable", "")) if g.strip()]
        row = {
            "case_id": case["case_id"], "kind": case.get("kind", ""), "input": case["input"],
            "expected": case["expected"], "expected_short": case.get("expected_short", ""),
            "answerable_expected": is_answerable(case), "sent": reply.sent, "short_answer": short,
            "answerable": rec.answerable if rec else "", "citations": json.dumps(rec.citations if rec else []),
            "retrieved": json.dumps([p["id"] for p in reply.passages]),
            "evidence_retrieved": has_evidence(case.get("evidence", ""), reply.passages),
            "calls": len(reply.attempts), "reprompts": max(0, len(reply.attempts) - 1),
            "gave_up": reply.failure is not None, "blocked": json.dumps(reply.blocked),
            "usd": round(reply.cost_usd, 8), "ms": reply.ms,
            "em": any(exact_match(short, g) for g in golds) if golds else "",
            "f1": round(max((token_f1(short, g) for g in golds), default=0), 3) if golds else "",
            "bleu": round(bleu(reply.sent, case["expected"]), 1) if case["expected"] else "",
            "rouge_l": round(rouge_l(reply.sent, case["expected"]), 1) if case["expected"] else "",
            "judge_usd": 0.0,
        }
        if not is_answerable(case):
            # Rule, no model: right when the component said it could not answer, and sent no invented fact.
            row["right"] = bool(rec) and rec.answerable is False
            row["right_by"] = "rule:answerable=false"
        else:
            v = judge(case, reply.sent, reply.passages, judge_model, tag=f"judge:{strategy}:{case['case_id']}")
            row["judge_usd"] = round(v.cost_usd, 8)
            if v.ok:
                for k in ("correct", "complete", "grounded", "clear"):
                    row[f"j_{k}"] = getattr(v.record, k)
                row["j_reason"] = v.record.reason
                row["right"] = v.record.correct >= 4
                row["right_by"] = f"judge:{judge_model}"
            else:
                row["right"], row["right_by"] = "", f"judge failed: {v.failure}"
        rows.append(row)
        print(f"{case['case_id']:>4}  {'RIGHT' if row['right'] is True else 'wrong':5}  "
              f"{row['calls']} call(s)  ${row['usd']:.5f}  {row['ms']:>5} ms  {short[:50]}")
    path = results_path(strategy, model)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"-> {path.relative_to(ROOT)}: {sum(r['right'] is True for r in rows)}/{len(rows)} right")
    return rows


# ------------------------------------------------------------------ swap, calibration, report

def read_results(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def truthy(v):
    return str(v).strip().lower() == "true"


def run_swap(a, b, model=llm.COMPONENT_MODEL, judge_model=llm.JUDGE_MODEL):
    """Strategy a against strategy b on every answerable case, each pair judged in both orders."""
    cases = {c["case_id"]: c for c in load_cases()}
    ra = {r["case_id"]: r for r in read_results(results_path(a, model))}
    rb = {r["case_id"]: r for r in read_results(results_path(b, model))}
    out = []
    for cid, case in cases.items():
        if cid not in ra or cid not in rb or not is_answerable(case):
            continue
        out.append({"case_id": cid, "verdict": swap(case, ra[cid]["sent"], rb[cid]["sent"], judge_model,
                                                     tag=f"swap:{a}-vs-{b}:{cid}")})
    counts = Counter(r["verdict"] for r in out)
    path = RUNS / f"swap_{a}_vs_{b}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["case_id", "verdict"])
        w.writeheader()
        w.writerows(out)
    print(f"{a} better: {counts['first']} | {b} better: {counts['second']} | "
          f"order decided (position bias): {counts['position']} | failed: {counts['failed']}  -> {path.name}")
    return counts


def run_calibration(model=llm.COMPONENT_MODEL):
    """Our hand scores (evals/calibration.csv) against the judge's, on the same answers."""
    with open(CALIBRATION, newline="", encoding="utf-8") as f:
        human = [r for r in csv.DictReader(f) if r.get("correct", "").strip()]
    if not human:
        raise ValueError("evals/calibration.csv has no scores yet")
    agree, diffs, rows = 0, [], []
    for h in human:
        res = {r["case_id"]: r for r in read_results(results_path(h["strategy"], model))}[h["case_id"]]
        if not res["j_correct"]:
            continue
        human_right = int(h["correct"]) >= 4
        judge_right = int(res["j_correct"]) >= 4
        agree += human_right == judge_right
        diffs.append(abs(int(h["correct"]) - int(res["j_correct"])))
        rows.append(f"| {h['case_id']} | {h['strategy']} | {h['scored_by']} | {h['correct']} | {res['j_correct']} | "
                    f"{'yes' if human_right == judge_right else '**no**'} |")
    n = len(rows)
    table = ("| Case | Strategy | Scored by | Human 'correct' | Judge 'correct' | Same verdict |\n"
             "|---|---|---|---|---|---|\n" + "\n".join(rows) +
             f"\n\nAgreement on right/wrong: **{agree}/{n}**; mean gap on 'correct': "
             f"{statistics.mean(diffs):.2f} points.")
    (RUNS / "calibration_summary.md").write_text(table + "\n", encoding="utf-8")
    print(table)
    return agree, n


def pareto(summary):
    """The rows no other row beats on every axis: more right, cheaper, faster (median latency)."""
    def dominates(x, y):
        better_or_equal = x["right"] >= y["right"] and x["usd_1000"] <= y["usd_1000"] and x["p50"] <= y["p50"]
        strictly = x["right"] > y["right"] or x["usd_1000"] < y["usd_1000"] or x["p50"] < y["p50"]
        return better_or_equal and strictly
    return [s for s in summary if not any(dominates(o, s) for o in summary if o is not s)]


def percentile(values, q):
    v = sorted(values)
    return v[min(len(v) - 1, max(0, round(q * (len(v) - 1))))] if v else 0


def report():
    files = sorted(RUNS.glob("results_*.csv"))
    if not files:
        raise SystemExit("no runs/results_*.csv yet: run `python -m src.evaluate run --strategy ...` first")
    summary, failures = [], []
    for path in files:
        rows = read_results(path)
        strategy, model = path.stem.removeprefix("results_").rsplit("_claude", 1)
        model = "claude" + model
        ms = [int(r["ms"]) for r in rows]
        n = len(rows)
        s = {
            "strategy": strategy, "model": model, "n": n,
            "right": sum(truthy(r["right"]) for r in rows),
            "em": sum(truthy(r["em"]) for r in rows if r["em"] != ""),
            "em_n": sum(r["em"] != "" for r in rows),
            "evidence": sum(truthy(r["evidence_retrieved"]) for r in rows),
            "reprompts": sum(int(r["reprompts"]) for r in rows),
            "gave_up": sum(truthy(r["gave_up"]) for r in rows),
            "blocked": sum(r["blocked"] not in ("", "[]") for r in rows),
            "usd_1000": 1000 * sum(float(r["usd"]) for r in rows) / n,
            "judge_usd": sum(float(r["judge_usd"] or 0) for r in rows),
            "p50": statistics.median(ms), "p90": percentile(ms, 0.9),
        }
        summary.append(s)
        failures += [{"strategy": strategy, **{k: r[k] for k in ("case_id", "kind", "input", "expected", "sent",
                      "retrieved", "evidence_retrieved", "j_reason", "right_by")}, "cause": "", "read_by": "", "note": ""}
                     for r in rows if not truthy(r["right"])]
    front = pareto(summary)
    lines = ["| Strategy | Model | Right (judge / rule) | Exact match, short answer | Evidence retrieved | "
             "Re-prompts | Given up | Blocked by output check | Cost per 1,000 calls | Median latency | p90 latency | On the front |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in summary:
        lines.append(f"| {s['strategy']} | {s['model']} | {s['right']}/{s['n']} | {s['em']}/{s['em_n']} | "
                     f"{s['evidence']}/{s['n']} | {s['reprompts']} | {s['gave_up']} | {s['blocked']} | "
                     f"${s['usd_1000']:.2f} | {s['p50'] / 1000:.1f} s | {s['p90'] / 1000:.1f} s | "
                     f"{'**yes**' if s in front else 'no'} |")
    one_case = 100 / summary[0]["n"]
    table = "\n".join(lines) + (
        f"\n\nGenerated by `python -m src.evaluate report` on {date.today().isoformat()} from "
        f"{', '.join(f'`runs/{p.name}`' for p in files)}. Cost per 1,000 calls: the component's own calls only, "
        f"re-prompts included, from the measured tokens at each model's input and output prices "
        f"(`src/llm.py`, `PRICE`); the judge cost ${sum(s['judge_usd'] for s in summary):.3f} in all, on top. "
        f"One case is {one_case:.1f} points: a difference of one or two cases is within the noise of {summary[0]['n']} cases.")
    if EVAL_DOC.exists():
        doc = EVAL_DOC.read_text(encoding="utf-8")
        doc = re.sub(r"(<!-- TABLE:START -->).*?(<!-- TABLE:END -->)", lambda m: f"{m[1]}\n{table}\n{m[2]}", doc, flags=re.DOTALL)
        EVAL_DOC.write_text(doc, encoding="utf-8")
    with (RUNS / "failures.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(failures[0].keys()) if failures else ["strategy"])
        w.writeheader()
        w.writerows(failures)
    _plot(summary, front)
    print(table)
    print(f"\n{len(failures)} wrong answers to read -> runs/failures.csv (fill `cause`, `read_by`, `note`)")


def _plot(summary, front):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("(matplotlib not installed: no figure)")
        return
    fig, ax = plt.subplots(figsize=(7, 4.2))
    for s in summary:
        on = s in front
        ax.scatter(s["usd_1000"], s["right"], s=60 + s["p50"] / 20, color="#1f6feb" if on else "#9aa4b2",
                   edgecolor="black" if on else "none", zorder=3)
        ax.annotate(f"{s['strategy']}\n${s['usd_1000']:.2f} · {s['p50'] / 1000:.1f} s", (s["usd_1000"], s["right"]),
                    textcoords="offset points", xytext=(8, -4), fontsize=8)
    ax.set_xlabel("cost per 1,000 calls ($, measured)")
    ax.set_ylabel(f"right answers, of {summary[0]['n']}")
    ax.set_title("Quality, cost and latency (circle size: median latency). Blue: on the Pareto front", fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(ROOT / "docs" / "pareto.png", dpi=150)
    print("-> docs/pareto.png")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("--strategy", required=True, choices=["zero_shot", "few_shot", "cot"])
    p.add_argument("--model", default=llm.COMPONENT_MODEL)
    p.add_argument("--judge", default=llm.JUDGE_MODEL)
    p.add_argument("--limit", type=int)
    p = sub.add_parser("swap")
    p.add_argument("--a", required=True)
    p.add_argument("--b", required=True)
    p.add_argument("--model", default=llm.COMPONENT_MODEL)
    sub.add_parser("calibrate")
    sub.add_parser("report")
    a = ap.parse_args()
    if a.cmd == "run":
        run(a.strategy, a.model, a.judge, a.limit)
    elif a.cmd == "swap":
        run_swap(a.a, a.b, a.model)
    elif a.cmd == "calibrate":
        run_calibration()
    else:
        report()

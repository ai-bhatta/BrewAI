from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from customer_generation_service import CustomerGenerationService


async def evaluate(dataset_path: Path) -> dict:
    cases = json.loads(dataset_path.read_text(encoding="utf-8"))
    service = CustomerGenerationService()
    rows = []
    for case in cases:
        started = time.perf_counter()
        result = await service.generate({
            "canonical_recipe": case["canonical_recipe"],
            "persona": {"id": case["persona"]},
            "difficulty": case["difficulty"],
            "mode": "local_ai",
        })
        validation = result.get("validation", {})
        rows.append({
            "id": case["id"], "source": result["source"], "valid": validation.get("valid", False),
            "attribute_preservation": validation.get("attribute_preservation", False),
            "contradiction": validation.get("contradiction", False), "fallback_reason": result.get("fallback_reason"),
            "latency_ms": result.get("latency_ms", round((time.perf_counter() - started) * 1000, 2)),
            "request": result.get("request"),
        })
    latencies = [row["latency_ms"] for row in rows]
    total = len(rows) or 1
    return {
        "cases": rows,
        "summary": {
            "case_count": len(rows),
            "valid_rate": round(sum(row["valid"] for row in rows) / total, 3),
            "attribute_preservation_rate": round(sum(row["attribute_preservation"] for row in rows) / total, 3),
            "contradiction_rate": round(sum(row["contradiction"] for row in rows) / total, 3),
            "fallback_rate": round(sum(row["source"] != "local_ai" for row in rows) / total, 3),
            "mean_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0,
            "human_review_required": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate local customer dialogue against fixed canonical recipes.")
    parser.add_argument("--dataset", type=Path, default=ROOT / "data" / "customer_generation_eval.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = asyncio.run(evaluate(args.dataset))
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()

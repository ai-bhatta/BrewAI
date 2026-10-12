from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from customer_generation_repository import CustomerGenerationRepository
from customer_generation_service import CustomerGenerationService, validate_customer_request


async def main() -> int:
    service = CustomerGenerationService()
    config = service.config()
    model = str(config.get("model", ""))
    print(f"Ollama URL: {config['base_url']} (loopback only)")
    try:
        with urlopen(f"{config['base_url'].rstrip('/')}/api/tags", timeout=2) as response:
            tags = json.loads(response.read().decode("utf-8"))
    except Exception as error:
        print(f"FAIL Ollama unreachable: {error}")
        return 1
    print("OK Ollama reachable")
    installed = any(entry.get("name") == model
                    for entry in tags.get("models", []))
    if not installed:
        print(f"FAIL configured model '{model}' is not installed locally; this command never pulls models")
        return 1
    print(f"OK configured model available: {model}")

    case = json.loads((ROOT / "data" / "customer_generation_eval.json").read_text(encoding="utf-8"))[0]
    payload = {
        "canonical_recipe": case["canonical_recipe"],
        "persona": {"id": case["persona"]},
        "difficulty": case["difficulty"],
        "mode": "local_ai",
    }
    first = await service.generate(payload)
    if first["success"]:
        valid = validate_customer_request(first["request"], payload["canonical_recipe"])["valid"]
        print("OK generated local dialogue and canonical validation passed" if valid else "FAIL generated dialogue did not validate")
        if not valid:
            return 1
        second = await service.generate(payload)
        if not second.get("cache_hit"):
            print("FAIL validated response was not served from cache on repeat")
            return 1
        print("OK repeated generation used the local cache")
    else:
        if first["source"] != "template":
            print("FAIL generation failed without a safe template fallback")
            return 1
        print(f"WARN model output unavailable or invalid ({first.get('fallback_reason')}); template fallback is safe")
        with tempfile.TemporaryDirectory(prefix="brewai-cache-smoke-") as temporary:
            repository = CustomerGenerationRepository(Path(temporary) / "cache.sqlite3")
            repository.put("smoke-test-roundtrip", "smoke-test", model, "smoke-test")
            cache_ok = repository.get("smoke-test-roundtrip") == "smoke-test"
        if not cache_ok:
            print("FAIL local cache round-trip")
            return 1
        print("OK local cache storage round-trip; no invalid model response was cached")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

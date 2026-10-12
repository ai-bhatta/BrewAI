from __future__ import annotations

import importlib.util
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from customer_generation_service import CustomerGenerationService


def check(label: str, ok: bool, detail: str = "", warning: bool = False) -> bool:
    marker = "WARN" if warning else "OK" if ok else "FAIL"
    suffix = f" - {detail}" if detail else ""
    print(f"[{marker}] {label}{suffix}")
    return ok or warning


def main() -> int:
    failures = []
    version_ok = sys.version_info >= (3, 11)
    if not check("Python version", version_ok, sys.version.split()[0]):
        failures.append("python")

    modules = ("fastapi", "uvicorn", "sklearn", "joblib", "pydantic")
    dependencies_ok = all(importlib.util.find_spec(module) for module in modules)
    if not check("Backend dependencies", dependencies_ok, ", ".join(modules)):
        failures.append("dependencies")

    dataset_path = ROOT / "data" / "order_dataset.json"
    model_path = ROOT / "backend" / "model" / "order_parser.joblib"
    metadata_path = ROOT / "results" / "production_model_metadata.json"
    model_ok = model_path.is_file()
    if model_ok:
        try:
            import joblib
            bundle = joblib.load(model_path)
            model_metadata = bundle.get("training_metadata", {})
            dataset_digest = hashlib.sha256((ROOT / "data" / "order_dataset.json").read_bytes()).hexdigest()
            model_ok = (
                all(name in bundle.get("models", {}) for name in ("base", "milk", "sweetness", "topping", "vibe"))
                and model_metadata.get("dataset_sha256") == dataset_digest
            )
        except Exception:
            model_ok = False
    if not check("Production model", model_ok, str(model_path.relative_to(ROOT)), warning=not model_ok):
        failures.append("model")
    metadata_ok = metadata_path.is_file()
    if metadata_ok:
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            current_digest = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
            metadata_ok = bool(metadata.get("evaluation_method")) and metadata.get("dataset_sha256") == current_digest
        except (OSError, ValueError):
            metadata_ok = False
    if not check("Production model metadata", metadata_ok, str(metadata_path.relative_to(ROOT)), warning=not metadata_ok):
        failures.append("model_metadata")

    try:
        rows = json.loads(dataset_path.read_text(encoding="utf-8"))
        dataset_ok = bool(rows) and all(isinstance(row, dict) and "utterance" in row for row in rows)
        dataset_detail = f"{len(rows)} labeled examples"
    except (OSError, ValueError):
        dataset_ok, dataset_detail = False, str(dataset_path.relative_to(ROOT))
    if not check("Canonical dataset", dataset_ok, dataset_detail):
        failures.append("dataset")

    databases = {
        "Feedback DB": ROOT / "data" / "feedback.sqlite3",
        "Analytics DB": ROOT / "data" / "analytics.sqlite3",
        "Bandit DB": ROOT / "data" / "bandit.sqlite3",
        "Generation cache": ROOT / "data" / "customer_generation.sqlite3",
    }
    for label, path in databases.items():
        if not path.exists():
            check(label, True, "not initialized; created on demand", warning=True)
            continue
        try:
            with sqlite3.connect(path, timeout=2) as connection:
                db_ok = connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        except sqlite3.Error:
            db_ok = False
        if not check(label, db_ok, "SQLite quick_check" if db_ok else "database is unreadable"):
            failures.append(label)

    frontend_files = ("index.html", "style.css", "app.js", "analytics.js", "customer_generation.js")
    frontend_ok = all((ROOT / "frontend" / name).is_file() for name in frontend_files)
    if not check("Frontend files", frontend_ok, f"{len(frontend_files)} entry files"):
        failures.append("frontend")

    try:
        config = CustomerGenerationService().config()
        generation_ok = config.get("mode") in {"auto", "templates", "local_ai"}
        generation_detail = f"mode={config.get('mode')}, model={config.get('model')}"
    except (OSError, ValueError, KeyError, TypeError) as error:
        generation_ok, generation_detail = False, str(error)
    if not check("Customer-generation config", generation_ok, generation_detail):
        failures.append("generation_config")

    if generation_ok:
        try:
            with urlopen(f"{config['base_url'].rstrip('/')}/api/tags", timeout=1.0) as response:
                ollama = json.loads(response.read().decode("utf-8"))
            installed = any(item.get("name") == str(config.get("model", ""))
                            for item in ollama.get("models", []))
            check("Optional Ollama", installed, "configured model available" if installed else "model unavailable; templates will be used", warning=not installed)
        except Exception:
            check("Optional Ollama", True, "unavailable; templates will be used", warning=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

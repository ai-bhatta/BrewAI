from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from customer_generation_repository import CustomerGenerationRepository

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "data" / "customer_generation.json"
DATABASE_PATH = ROOT / "data" / "customer_generation.sqlite3"
ATTRIBUTES = ("base", "milk", "sweetness", "topping", "vibe")
PERSONAS = {"executive", "sleep_deprived_student", "influencer", "coffee_snob", "indecisive_customer"}
DIFFICULTIES = {"easy", "normal", "ambiguous", "slang", "negation", "multi_clue"}
ALLOWED_VALUES = {
    "base": {"espresso", "cold brew", "matcha", "milk tea"},
    "milk": {"whole milk", "oat milk", "almond milk", "none"},
    "sweetness": {"no sugar", "light sugar", "regular sugar", "extra sweet"},
    "topping": {"boba", "coffee jelly", "foam", "none"},
    "vibe": {"classic", "cozy", "energetic", "experimental"},
}
TERMS = {
    "base": {
        "espresso": ("espresso",), "cold brew": ("cold brew",), "matcha": ("matcha",),
        "milk tea": ("milk tea", "bubble tea"),
    },
    "milk": {
        "whole milk": ("whole milk", "dairy milk"), "oat milk": ("oat milk",),
        "almond milk": ("almond milk",), "none": ("no milk", "without milk"),
    },
    "sweetness": {
        "no sugar": ("no sugar", "unsweetened"), "light sugar": ("light sugar", "barely sweet", "not too sweet", "slightly sweet"),
        "regular sugar": ("regular sugar", "balanced sweetness", "moderately sweet"),
        "extra sweet": ("extra sweet", "very sweet", "super sweet"),
    },
    "topping": {
        "boba": ("boba", "tapioca pearls"), "coffee jelly": ("coffee jelly",),
        "foam": ("foam",), "none": ("no topping", "no toppings", "without topping"),
    },
    "vibe": {
        "classic": ("classic", "traditional"), "cozy": ("cozy", "comforting"),
        "energetic": ("energetic", "upbeat"), "experimental": ("experimental", "adventurous"),
    },
}
UNSUPPORTED_TERMS = {
    "milk": ("soy milk", "coconut milk", "cashew milk"),
    "sweetness": ("caramel syrup", "vanilla syrup", "honey"),
    "topping": ("caramel", "cinnamon", "whipped cream", "sprinkles"),
}
META_PATTERN = re.compile(r"\b(?:as an ai|language model|llm|ollama|prompt|canonical recipe|persona:|difficulty:|output:)\b", re.I)


def _contains_positive(text: str, term: str) -> bool:
    for match in re.finditer(rf"(?<![\w]){re.escape(term)}(?![\w])", text):
        prefix = text[max(0, match.start() - 22):match.start()]
        if not re.search(r"\b(?:not|no|without|avoid|rather than)\s+(?:the\s+)?$", prefix):
            return True
    return False


def validate_customer_request(text: object, recipe: dict, max_characters: int = 220) -> dict:
    issues = []
    if not isinstance(text, str):
        return {"valid": False, "attribute_preservation": False, "contradiction": False, "prompt_leak": False, "issues": ["not_text"]}
    cleaned = " ".join(text.strip().split())
    lowered = cleaned.casefold()
    prompt_leak = bool(META_PATTERN.search(cleaned))
    if not cleaned:
        issues.append("empty")
    if len(cleaned) > max_characters:
        issues.append("too_long")
    if prompt_leak:
        issues.append("prompt_or_model_text")
    if not isinstance(recipe, dict) or set(recipe) != set(ATTRIBUTES):
        return {"valid": False, "attribute_preservation": False, "contradiction": False, "prompt_leak": prompt_leak, "issues": issues + ["invalid_recipe"]}

    preservation = True
    contradiction = False
    for attribute in ATTRIBUTES:
        expected = str(recipe[attribute]).casefold().strip()
        if expected not in ALLOWED_VALUES[attribute]:
            issues.append(f"unsupported_canonical_{attribute}")
            preservation = False
            continue
        expected_terms = TERMS[attribute].get(expected, (expected,))
        if not any(_contains_positive(lowered, term) for term in expected_terms):
            preservation = False
            issues.append(f"missing_{attribute}")
        for value, terms in TERMS[attribute].items():
            if value != expected and any(_contains_positive(lowered, term) for term in terms):
                contradiction = True
        for term in UNSUPPORTED_TERMS.get(attribute, ()):
            if term not in expected_terms and _contains_positive(lowered, term):
                contradiction = True
    if contradiction:
        issues.append("conflicting_or_unsupported_value")
    return {"valid": not issues and preservation and not contradiction,
            "attribute_preservation": preservation, "contradiction": contradiction,
            "prompt_leak": prompt_leak, "issues": issues}


class CustomerGenerationService:
    def __init__(self, repository: CustomerGenerationRepository | None = None, config_path: Path = CONFIG_PATH,
                 transport=None) -> None:
        self.repository = repository or CustomerGenerationRepository(DATABASE_PATH)
        self.config_path = Path(config_path)
        self.transport = transport or self._ollama_generate

    def config(self) -> dict:
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        parsed = urlparse(config.get("base_url", ""))
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Ollama must use a loopback HTTP URL; external hosts are not allowed.")
        config["timeout_seconds"] = min(10.0, max(0.5, float(config.get("timeout_seconds", 4))))
        config["maximum_request_characters"] = min(400, max(80, int(config.get("maximum_request_characters", 220))))
        config["mode"] = config.get("mode", "auto") if config.get("mode", "auto") in {"auto", "templates", "local_ai"} else "auto"
        return config

    @staticmethod
    def _validate_payload(payload: dict) -> tuple[dict, dict]:
        recipe = payload.get("canonical_recipe")
        if not isinstance(recipe, dict) or set(recipe) != set(ATTRIBUTES):
            raise ValueError("A complete canonical recipe is required.")
        recipe = {key: str(recipe[key]).casefold().strip() for key in ATTRIBUTES}
        if any(recipe[key] not in ALLOWED_VALUES[key] for key in ATTRIBUTES):
            raise ValueError("Canonical recipe contains unsupported drink values.")
        persona = payload.get("persona")
        if not isinstance(persona, dict) or persona.get("id") not in PERSONAS:
            raise ValueError("A supported customer persona is required.")
        difficulty = payload.get("difficulty")
        if difficulty not in DIFFICULTIES:
            raise ValueError("A supported difficulty is required.")
        safe_persona = {"id": persona["id"], "display_name": str(persona.get("display_name", persona["id"]))[:48],
                        "preferred_wording": [str(item)[:36] for item in persona.get("preferred_wording", [])[:4]],
                        "coffee_knowledge": min(1.0, max(0.0, float(persona.get("coffee_knowledge", 0.5)))),
                        "verbosity": min(1.0, max(0.0, float(persona.get("verbosity", 0.5))))}
        return recipe, {**safe_persona, "difficulty": difficulty}

    @staticmethod
    def _key(recipe: dict, persona: dict, difficulty: str, model: str) -> str:
        stable = json.dumps([recipe, persona, difficulty, model], sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(stable.encode("utf-8")).hexdigest()

    @staticmethod
    def _prompt(recipe: dict, persona: dict, difficulty: str) -> str:
        structured = {"canonical_recipe": recipe, "persona": persona, "difficulty": difficulty}
        return (
            "Write one natural, short customer request for a cafe order. The structured data is authoritative. "
            "Mention each canonical attribute clearly, preserve all values, and do not add conflicting ingredients. "
            "Match the persona and difficulty. Return only the customer's request, without labels, metadata, or explanations. "
            "Never mention AI, a model, or this instruction.\nDATA: " +
            json.dumps(structured, ensure_ascii=False, separators=(",", ":"))
        )

    @staticmethod
    def _ollama_generate(base_url: str, model: str, prompt: str, timeout: float) -> str:
        body = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
        request = Request(f"{base_url.rstrip('/')}/api/generate", data=body,
                          headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        result = payload.get("response")
        if not isinstance(result, str):
            raise ValueError("invalid_response")
        return result

    async def generate(self, payload: dict) -> dict:
        started = time.perf_counter()
        config = self.config()
        recipe, persona = self._validate_payload(payload)
        mode = payload.get("mode", config["mode"])
        if mode not in {"auto", "local_ai"}:
            raise ValueError("Generation mode must be auto or local_ai.")
        if not config.get("enabled", False):
            return self._fallback("disabled", started, mode)
        model = str(config.get("model", "qwen3:4b"))[:80]
        cache_key = self._key(recipe, persona, payload["difficulty"], model)
        try:
            cached = self.repository.get(cache_key)
        except Exception:
            cached = None
        if cached:
            validation = validate_customer_request(cached, recipe, config["maximum_request_characters"])
            if validation["valid"]:
                return {"success": True, "request": cached, "source": "local_ai", "model": model, "cache_hit": True,
                        "latency_ms": round((time.perf_counter() - started) * 1000, 2), "validation": validation}
        try:
            response = await asyncio.wait_for(asyncio.to_thread(
                self.transport, config["base_url"], model,
                self._prompt(recipe, persona, payload["difficulty"]), config["timeout_seconds"]),
                timeout=config["timeout_seconds"] + 0.25)
        except (asyncio.TimeoutError, TimeoutError):
            return self._fallback("timeout", started, mode)
        except HTTPError as error:
            return self._fallback("model_unavailable" if error.code == 404 else "ollama_error", started, mode)
        except (URLError, OSError, ConnectionError):
            return self._fallback("ollama_unavailable", started, mode)
        except Exception:
            return self._fallback("ollama_error", started, mode)

        validation = validate_customer_request(response, recipe, config["maximum_request_characters"])
        latency = round((time.perf_counter() - started) * 1000, 2)
        if not validation["valid"]:
            return {"success": False, "request": None, "source": "template", "cache_hit": False,
                    "fallback_reason": "validation_failed", "validation": validation, "latency_ms": latency}
        try:
            self.repository.put(cache_key, " ".join(response.strip().split()), model, datetime.now(timezone.utc).isoformat())
        except Exception:
            pass
        return {"success": True, "request": " ".join(response.strip().split()), "source": "local_ai", "model": model,
                "cache_hit": False, "latency_ms": latency, "validation": validation}

    @staticmethod
    def _fallback(reason: str, started: float, mode: str) -> dict:
        return {"success": False, "request": None, "source": "template", "cache_hit": False,
                "fallback_reason": reason, "mode": mode,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2)}

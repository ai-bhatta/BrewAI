from __future__ import annotations


def parse_keyword_order(request: str) -> dict[str, str]:
    normalized = request.lower()
    recipe = {
        "base": "espresso",
        "milk": "whole milk",
        "sweetness": "regular sugar",
        "topping": "none",
        "vibe": "classic",
    }

    rules = [
        (["strong", "boldest", "coffee", "espresso"], {"base": "espresso"}),
        (["iced", "cold", "high-energy", "energy", "energetic"], {"base": "cold brew", "vibe": "energetic"}),
        (["tea", "afternoon", "calm"], {"base": "milk tea", "vibe": "cozy"}),
        (["matcha"], {"base": "matcha"}),
        (["creamy", "comforting", "cozy"], {"milk": "whole milk", "vibe": "cozy"}),
        (["no dairy", "dairy-free", "oat"], {"milk": "oat milk"}),
        (["no milk", "without milk"], {"milk": "none"}),
        (["almond"], {"milk": "almond milk"}),
        (["no sugar", "unsweetened"], {"sweetness": "no sugar"}),
        (["less sugar", "not too sweet", "light"], {"sweetness": "light sugar"}),
        (["extra sweet", "extra sweetness"], {"sweetness": "extra sweet"}),
        (["sweet", "playful"], {"sweetness": "regular sugar"}),
        (["boba", "chewy"], {"topping": "boba"}),
        (["jelly"], {"topping": "coffee jelly"}),
        (["futuristic", "experimental", "surprise", "unusual"], {"vibe": "experimental"}),
    ]

    for tokens, updates in rules:
        if any(token in normalized for token in tokens):
            recipe.update(updates)

    return recipe

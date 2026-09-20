"""Formulation classification (problem statement: the assistant "first helps
classify the formulation ... asks the minimum clarifying questions").

Two deliberate design choices.

**The decision tree is deterministic, not an LLM call.** The categories are
defined by regulatory tests with crisp answers ("is the formulation and method
drawn from a First-Schedule authoritative text?"), so a model adds latency and
non-determinism to a question that does not need judgement. It also keeps this
auditable: the same answers always produce the same category, and the path
taken can be shown to the user. Same reasoning as the rest of the pipeline
being a fixed sequence rather than an agent.

**Guidance is retrieved, never written here.** What each category *requires*
is a statement about law, so it has to come from the corpus with a citation or
not be made at all. `category_guidance` returns an abstention when nothing in
the corpus clears the confidence gate, and three of the six categories
currently land there — the Drugs and Cosmetics Act and its Rules could not be
sourced in an indexable form (see corpus/manifest.md), so "new drug",
"phytopharmaceutical" and "cosmetic" have no grounded definition available.
Saying so is the correct behaviour, not a placeholder.
"""
from confidence_gate import CONFIDENCE_THRESHOLD
from hybrid_retrieval import retrieve_hybrid

CLASSICAL = "classical"
PROPRIETARY = "patent_or_proprietary"
NEW_DRUG = "new_drug"
PHYTOPHARMACEUTICAL = "phytopharmaceutical"
AYURVEDA_AAHARA = "ayurveda_aahara"
COSMETIC = "cosmetic"

CATEGORY_LABELS = {
    CLASSICAL: "Classical / generic Ayurvedic medicine",
    PROPRIETARY: "Patent or proprietary Ayurvedic medicine",
    NEW_DRUG: "New / non-classical drug",
    PHYTOPHARMACEUTICAL: "Phytopharmaceutical",
    AYURVEDA_AAHARA: "Ayurveda-Aahara / nutraceutical",
    COSMETIC: "Cosmetic",
}

# The retrieval probe used to ground each category. Phrased as the regulatory
# question a user would ask, not as keywords, because the corpus is embedded
# for natural-language retrieval.
CATEGORY_PROBES = {
    CLASSICAL: "classical Ayurvedic medicine formulated per an authoritative First Schedule book",
    PROPRIETARY: "patent or proprietary Ayurvedic medicine definition and requirements",
    NEW_DRUG: "new drug requiring proof of safety and effectiveness before approval",
    PHYTOPHARMACEUTICAL: "phytopharmaceutical purified plant extract drug requirements",
    AYURVEDA_AAHARA: "Ayurveda Aahara food product standards and labelling",
    COSMETIC: "cosmetic product definition and regulatory requirements",
}

# The minimum questions needed to separate the six categories, in the order
# that eliminates the most at each step. Each `answers` key is one question.
QUESTIONS = [
    {
        "key": "intended_use",
        "question": "What is the product presented as?",
        "options": {
            "medicine": "A medicine — to treat, prevent or mitigate a disease or condition",
            "food": "A food, drink or nutraceutical taken for nourishment or wellbeing",
            "cosmetic": "A cosmetic — applied for cleansing, beautifying or appearance",
        },
    },
    {
        "key": "from_authoritative_text",
        "question": "Is both the formulation AND the manufacturing method drawn from a "
                    "text listed in the First Schedule to the Drugs and Cosmetics Act?",
        "options": {"yes": "Yes, both", "no": "No, one or both differ"},
        "asked_when": lambda a: a.get("intended_use") == "medicine",
    },
    {
        "key": "ingredients_only_from_texts",
        "question": "Are all ingredients and processes ones described in authoritative "
                    "Ayurvedic texts, even though the exact formulation is new?",
        "options": {"yes": "Yes", "no": "No — it goes beyond them"},
        "asked_when": lambda a: (a.get("intended_use") == "medicine"
                                 and a.get("from_authoritative_text") == "no"),
    },
    {
        "key": "purified_extract",
        "question": "Is it a purified or standardised plant extract with defined marker "
                    "constituents, rather than a whole-plant traditional preparation?",
        "options": {"yes": "Yes", "no": "No"},
        "asked_when": lambda a: (a.get("intended_use") == "medicine"
                                 and a.get("from_authoritative_text") == "no"
                                 and a.get("ingredients_only_from_texts") == "no"),
    },
]


def next_question(answers: dict) -> dict | None:
    """The next question worth asking, or None when the answers already decide.

    Questions whose `asked_when` is false for the answers so far are skipped
    entirely — that is what makes this the MINIMUM set rather than a fixed
    questionnaire. A cosmetic is classified after one question.
    """
    for q in QUESTIONS:
        gate = q.get("asked_when")
        if gate and not gate(answers):
            continue
        if q["key"] not in answers:
            return {k: v for k, v in q.items() if k != "asked_when"}
    return None


def classify(answers: dict) -> str | None:
    """Resolve answers to a category, or None if more answers are needed.

    Returning None rather than a best guess is the point: an under-specified
    product gets another question, never a category it might not be.
    """
    use = answers.get("intended_use")
    if use == "cosmetic":
        return COSMETIC
    if use == "food":
        return AYURVEDA_AAHARA
    if use != "medicine":
        return None

    if answers.get("from_authoritative_text") == "yes":
        return CLASSICAL
    if answers.get("from_authoritative_text") != "no":
        return None

    if answers.get("ingredients_only_from_texts") == "yes":
        return PROPRIETARY
    if answers.get("ingredients_only_from_texts") != "no":
        return None

    purified = answers.get("purified_extract")
    if purified == "yes":
        return PHYTOPHARMACEUTICAL
    if purified == "no":
        return NEW_DRUG
    return None


# Categories whose DEFINING instrument is absent from the corpus. These are
# not "no passage cleared the gate" — they are structurally unanswerable, and
# checking that before retrieval matters because a distance gate cannot tell
# a definition from a passing mention. Observed directly: the cosmetic probe
# retrieved the Biological Diversity Act at distance 0.831, comfortably inside
# the 0.90 gate, purely because that Act uses the word "cosmetic" in passing.
# Treating that as grounded would have produced a confident answer about
# cosmetics regulation sourced from a biodiversity statute — the exact
# right-source/wrong-support failure the whole project is built against.
#
# All three are defined by the Drugs and Cosmetics Act 1940 and its Rules,
# which could not be sourced in an indexable form (corpus/manifest.md: the
# available 635-page compilation interleaves Act, Rules and ~20 Schedules
# under three numbering systems). Remove a category from this set the moment
# that source is indexed — not before.
UNSOURCED_CATEGORIES = {
    NEW_DRUG: "Drugs and Cosmetics Act, 1940 and the Drugs and Cosmetics Rules, 1945 (Rule 122E)",
    PHYTOPHARMACEUTICAL: "Drugs and Cosmetics Rules, 1945 (phytopharmaceutical provisions)",
    COSMETIC: "Drugs and Cosmetics Act, 1940 (s.3(aaa))",
}


def category_guidance(category: str, top_k: int = 4) -> dict:
    """Grounded guidance for a category, or an honest abstention.

    Uses the same confidence gate as the main pipeline (Layer 1) rather than a
    threshold of its own, so "grounded" means the same thing here as it does
    for an ordinary question. A category whose best passage cannot clear that
    gate returns grounded=False with no guidance text — the corpus does not
    support a statement about it, and inventing one would be exactly the
    failure this project exists to prevent.
    """
    if category not in CATEGORY_PROBES:
        raise ValueError(f"unknown category: {category!r}")

    if category in UNSOURCED_CATEGORIES:
        return {
            "category": category,
            "label": CATEGORY_LABELS[category],
            "grounded": False,
            "best_distance": None,
            "threshold": CONFIDENCE_THRESHOLD,
            "passages": [],
            "abstention": (
                f"This tool cannot answer for {CATEGORY_LABELS[category].lower()}. "
                f"The instrument that defines it — {UNSOURCED_CATEGORIES[category]} — "
                f"is not in the corpus, so any statement here would be ungrounded. "
                f"Consult that instrument directly."
            ),
        }

    hits = retrieve_hybrid(CATEGORY_PROBES[category], top_k=top_k, jurisdiction="india")
    best = hits[0]["distance"] if hits else None
    grounded = best is not None and best <= CONFIDENCE_THRESHOLD

    return {
        "category": category,
        "label": CATEGORY_LABELS[category],
        "grounded": grounded,
        "best_distance": best,
        "threshold": CONFIDENCE_THRESHOLD,
        "passages": [
            {
                "chunk_id": h["chunk_id"],
                "doc_id": h["metadata"]["doc_id"],
                "text": h["text"],
                "distance": h["distance"],
            }
            for h in (hits if grounded else [])
        ],
        "abstention": None if grounded else (
            f"The corpus has no source that supports a statement about "
            f"{CATEGORY_LABELS[category].lower()}. The Drugs and Cosmetics Act and its "
            f"Rules, which define this category, could not be sourced in an indexable "
            f"form (see corpus/manifest.md). Consult those directly rather than relying "
            f"on this tool for this category."
        ),
    }

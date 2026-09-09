from itertools import cycle
from typing import Any

from pydantic import BaseModel

from app.ai.schemas import Diagnosis, LessonPlan, Recommendations, WorksheetOutput


class MockProvider:
    name = "mock"
    model = "mock-educator-v1"

    async def generate_structured(
        self, *, system_prompt: str, evidence: dict[str, Any],
        response_schema: type[BaseModel], feedback: str | None = None,
    ) -> dict[str, Any]:
        weak = evidence["weaknesses"] or evidence["concepts"][:1]
        strong = evidence["strengths"]
        weak_names = [item["name"] for item in weak]
        if response_schema is Diagnosis:
            return {
                "summary": (
                    f"This learner is ready to build confidence in {', '.join(weak_names)} "
                    "through focused, hands-on practice."
                ),
                "strengths": [
                    {"concept": item["name"], "evidence": f"Secure performance on {', '.join(item['question_ids'])}."}
                    for item in strong[:3]
                ],
                "learning_gaps": [
                    {
                        "concept": item["name"],
                        "severity": "high" if item["percentage"] < 50 else "medium",
                        "reasoning_type": item["reasoning_type"],
                        "evidence": f"Performance on {', '.join(item['question_ids'])} needs support.",
                        "explanation": f"Use concrete examples to revisit {item['name']}.",
                    }
                    for item in weak
                ],
                "encouragement": "You already have useful ideas to build on. Take one step at a time and explain what you notice.",
                "teacher_focus": [f"Model one example of {name}, then ask the learner to explain it." for name in weak_names],
            }
        if response_schema is Recommendations:
            return {"recommendations": [
                {
                    "concept": item["name"], "priority": "high" if index == 0 else "medium",
                    "why": f"This concept is supported by evidence from {', '.join(item['question_ids'])}.",
                    "teaching_approach": "Use a predict-observe-explain routine with a familiar object.",
                    "mini_activity": f"Ask the learner to draw a prediction about {item['name']}, test it, and explain the result.",
                    "misconception_to_watch": "Check whether the learner changes the explanation after observing evidence.",
                    "follow_up_check": "Give one new situation and ask for a prediction with a because statement.",
                }
                for index, item in enumerate(weak[:3])
            ]}
        if response_schema is LessonPlan:
            duration = evidence["options"]["duration_minutes"]
            warm_up = max(1, round(duration * 0.13))
            explicit = max(1, round(duration * 0.23))
            guided = max(1, round(duration * 0.23))
            independent = max(1, round(duration * 0.23))
            check = duration - warm_up - explicit - guided - independent
            return {
                "title": f"Build confidence with {', '.join(weak_names)}",
                "target_concepts": weak_names,
                "duration_minutes": duration,
                "objectives": [f"Explain {name} using evidence from an observation." for name in weak_names],
                "materials": ["paper", "pencil", "simple classroom objects"],
                "warm_up": {"minutes": warm_up, "activity": "Share one observation and one question."},
                "explicit_instruction": {"minutes": explicit, "activity": f"Model a clear example of {weak_names[0]}."},
                "guided_practice": {"minutes": guided, "activity": "Predict, observe, and explain with teacher prompts."},
                "independent_practice": {"minutes": independent, "activity": "Complete one new example and label the evidence."},
                "assessment_check": {"minutes": check, "activity": "Explain a new case in one sentence."},
                "teacher_notes": ["Praise evidence-based explanations.", "Do not introduce concepts outside this assessment."],
            }
        if response_schema is WorksheetOutput:
            count = evidence["options"]["question_count"]
            types = cycle(["multiple_choice", "fill_blank", "true_false", "short_answer", "structured_response", "scenario_application"])
            difficulty_counts = evidence["options"]["difficulty_counts"]
            difficulties = [level for level, amount in difficulty_counts.items() for _ in range(amount)]
            items = []
            for index in range(count):
                concept = weak_names[index % len(weak_names)]
                item_type = next(types)
                items.append({
                    "id": f"W{index + 1}", "type": item_type, "concept": concept,
                    "difficulty": difficulties[index],
                    "question": f"Show what you understand about {concept} in this new example.",
                    "options": ["First idea", "Second idea", "Third idea"] if item_type == "multiple_choice" else [],
                    "answer": f"A correct response explains {concept} using the blueprint keywords.",
                    "marking_notes": "Award credit for a clear idea supported by relevant evidence.",
                    "keywords": evidence["concept_keywords"].get(concept, [])[:4],
                })
            return {
                "title": f"My practice: {', '.join(weak_names)}",
                "student_name": evidence["student_ref"], "target_concepts": weak_names,
                "instructions": "Read each question carefully. Show your thinking and use scientific words where helpful.",
                "questions": items,
            }
        raise ValueError(f"Unsupported response schema: {response_schema.__name__}")

    async def extract_blueprint(
        self, *, system_prompt: str, paper_text: str,
        pdf_bytes: bytes | None, filename: str, feedback: str | None = None,
        required_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        raise RuntimeError(
            "PDF blueprint extraction needs a real AI provider; "
            "AI_PROVIDER=mock cannot read test papers."
        )

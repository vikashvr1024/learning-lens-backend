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
                    f"You are ready to build confidence in {', '.join(weak_names)}. "
                    "Use the guide one step at a time, practise, and check your own answers."
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
                        "explanation": (
                            f"You need more practice with {item['name']}. Start with one simple "
                            "example, explain the rule in your own words, and then try a new example."
                        ),
                    }
                    for item in weak
                ],
                "encouragement": "You already have useful ideas to build on. Take one step at a time and explain what you notice.",
                "teacher_focus": [
                    f"Read the notes for {name}, copy one worked example, then solve a similar example alone."
                    for name in weak_names
                ],
            }
        if response_schema is Recommendations:
            return {"recommendations": [
                {
                    "concept": item["name"], "priority": "high" if index == 0 else "medium",
                    "why": f"This concept is supported by evidence from {', '.join(item['question_ids'])}.",
                    "teaching_approach": (
                        "Study one worked example, explain each step, then try a similar example."
                    ),
                    "mini_activity": (
                        f"1. Write what you know about {item['name']}. 2. Practise one example. "
                        "3. Explain the method and check your work."
                    ),
                    "misconception_to_watch": "Check that the explanation uses the relevant rule, fact, or method.",
                    "follow_up_check": "Try one new example and explain why the answer or conclusion follows.",
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
                "objectives": [
                    f"Explain {name} using the relevant facts, steps, or evidence."
                    for name in weak_names
                ],
                "materials": ["paper", "pencil", "assessment revision notes"],
                "warm_up": {"minutes": warm_up, "activity": "Write one fact you remember and one question you still have."},
                "explicit_instruction": {"minutes": explicit, "activity": f"Read the explanation of {weak_names[0]}. Copy the main rule and say it aloud in your own words."},
                "guided_practice": {"minutes": guided, "activity": "Follow one worked example step by step. Cover it, then repeat the same method from memory."},
                "independent_practice": {"minutes": independent, "activity": "Complete one new example alone. Circle the keyword or evidence that supports your answer."},
                "assessment_check": {"minutes": check, "activity": "Answer one new case in a complete sentence, then compare every step with the solution."},
                "teacher_notes": ["Use evidence in every explanation.", "Revise only the concepts from this assessment."],
            }
        if response_schema is WorksheetOutput:
            count = evidence["options"]["question_count"]
            practice_names = (
                evidence.get("required_practice_concepts")
                or evidence["allowed_concepts"]
            )
            types = cycle(["multiple_choice", "fill_blank", "true_false", "short_answer", "structured_response", "scenario_application"])
            difficulty_counts = evidence["options"]["difficulty_counts"]
            difficulties = [level for level, amount in difficulty_counts.items() for _ in range(amount)]
            question_id_start = evidence["options"].get("question_id_start", 1)
            items = []
            for index in range(count):
                concept = practice_names[index % len(practice_names)]
                item_type = next(types)
                question_number = question_id_start + index
                items.append({
                    "id": f"W{question_number}", "type": item_type, "concept": concept,
                    "difficulty": difficulties[index],
                    "question": f"Practice example {question_number}: Show what you understand about {concept}.",
                    "options": ["First idea", "Second idea", "Third idea"] if item_type == "multiple_choice" else [],
                    "solution_steps": [
                        f"Identify what the question is asking about {concept}.",
                        "Recall the matching rule or keyword from your revision notes.",
                        "Apply the rule to the example and check that your explanation answers the question.",
                    ],
                    "answer": f"A correct response explains {concept} using the blueprint keywords.",
                "exam_tip": "Use the key subject word and explain how it supports your answer.",
                    "marking_notes": "Award credit for a clear idea supported by relevant evidence.",
                    "keywords": evidence["concept_keywords"].get(concept, [])[:4],
                })
            return {
                "title": f"My practice: {evidence['assessment']['subject']}",
                "student_name": evidence["student_ref"],
                "target_concepts": list(dict.fromkeys(practice_names)),
                "instructions": "Read each question carefully. Show your thinking and use the key subject words where helpful.",
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

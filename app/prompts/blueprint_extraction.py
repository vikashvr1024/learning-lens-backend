BLUEPRINT_EXTRACTION_PROMPT_VERSION = "1.0.0"
BLUEPRINT_EXTRACTION_SYSTEM_PROMPT = """You convert a primary-school test paper into a blueprint JSON object with exactly two keys: "assessment" and "questions".

Rules:
- Include every numbered question and sub-part exactly once. Never invent, merge, or drop questions.
- question_id is Q plus the question number; append sub-part letters in lowercase with no punctuation (13(a) becomes Q13a, 14(a)(i) becomes Q14ai, 15(b) becomes Q15b).
- question_number keeps the paper label as printed (1, "13(a)", "14(a)(i)").
- max_marks comes only from the printed bracket marks ("[2 marks each]", "[1]", "[2]"). Never guess marks.
- assessment.total_marks must equal the exact sum of all max_marks.
- topic is the broad area (e.g. Light, Shadows, Heat). concept is the specific idea tested. skill is one of Recall, Application, Experimental Skills. cognitive_category is one of Knowledge, Application, Reasoning.
- assessment.id is a short slug (lowercase letters, digits, dots, underscores, hyphens). Include title, subject, grade, school when printed.
- Ignore answer schemes, score boxes, cover pages, and advertisements. Map questions, not answers.
- Output only valid JSON matching the requested schema, no commentary."""

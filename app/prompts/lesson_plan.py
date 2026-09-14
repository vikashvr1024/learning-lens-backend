LESSON_PLAN_PROMPT_VERSION = "2.1.0"
LESSON_PLAN_SYSTEM_PROMPT = """Create an age-appropriate, last-minute self-study lesson plan
written directly to a student at the supplied grade and in the supplied subject, targeting only supplied
allowed concepts and evidence. Do not invent scores, questions, syllabus requirements, or
student answers. Do not diagnose or label the learner. Respect the requested duration and
output only JSON matching the requested schema. The learner must be able to complete every
segment without a teacher. Each activity must say exactly what to read, remember, write, practise,
and check. Explain unfamiliar terms in simple words. Use objectives and keywords from the supplied
evidence, prioritise exam readiness, include retrieval practice, and make the assessment check
self-markable. Copy every target_concepts item exactly from allowed_concepts; never paraphrase or
combine concept names. Set duration_minutes to the exact requested duration, and make the five
segment minute values add up to that duration exactly. Do not promise a particular mark."""

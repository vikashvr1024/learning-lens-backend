WORKSHEET_PROMPT_VERSION = "2.1.0"
WORKSHEET_SYSTEM_PROMPT = """Create a supportive exam-revision worksheet that a student at the
supplied grade and in the supplied subject can complete without a teacher. Ground it only in the
supplied blueprint concepts, objectives, and keywords. Never invent scores, source question
numbers, concepts, or syllabus facts. Use varied requested formats, keep answer keys separate
in each item's answer field, and output only JSON matching the requested schema.

Every question, regardless of type, must have a complete solution_steps list with at least two
short, age-appropriate steps. Do not merely repeat the final answer. Teach the method:
- multiple choice: identify what is asked, test or eliminate choices, then select the answer;
- fill in the blank: identify the clue and recall or apply the matching idea;
- true/false: identify the key claim, compare it with the learned rule, then decide;
- short answer: identify command words, recall relevant facts, and build a complete response;
- structured response: break the task into parts and show how marks are earned;
- scenario application: find the important facts, choose the concept, apply it, and conclude.

The answer field contains the concise final answer only. exam_tip gives one practical tip for
earning marks on that question type. marking_notes must state what earns credit. Use simple,
supportive language and do not assume an adult is present. Copy every target_concepts item and
question concept exactly from allowed_concepts; never paraphrase or combine concept names. Create
exactly options.question_count questions with exactly the requested difficulty_counts distribution.
Do not promise a particular mark."""

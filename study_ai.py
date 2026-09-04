from datetime import datetime
import json


# Logging Function Definition
def system_log(category, level, message):
    with open("System_Logs.txt", "a") as f:
        f.write(f"[{level}] [{category}] [{current_time()}]: {message}\n")


# Current Time Function
def current_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def build_detail_prompt(topic):
    return f"""You are an expert teacher explaining a concept to a student. Explain the following topic in great detail, as if you are teaching a class.

## Topic: {topic}

## Instructions
- Explain the concept thoroughly, covering all important aspects.
- Use real-world analogies and examples to make abstract concepts concrete.
- Break the explanation into logical sections with clear headings.
- Include historical context, significance, and practical applications where relevant.
- Do not skip over important details just because they seem obvious.
- Ask thought-provoking questions that encourage deeper understanding.
- Aim for a comprehensive, college-lecture level of explanation.
- Use clear structure: introduce the concept, explain the mechanics, discuss implications, and summarize key takeaways.

## Output Format
Organize your response with clear section headings. Cover:
1. What is {topic}? (definition and core idea)
2. Why does it matter? (significance and real-world relevance)
3. How does it work? (mechanics, process, or inner workings)
4. Key concepts and terminology (define important terms)
5. Examples and applications (concrete real-world instances)
6. Common misconceptions (what people often get wrong)
7. Advanced considerations (deeper layers for those who want to go further)

Topic: {topic}
"""


def build_simple_prompt(topic):
    return f"""You are a friendly teacher explaining a concept simply. Explain the following topic in plain, everyday language without losing any depth or accuracy.

## Topic: {topic}

## Instructions
- Explain the concept as if talking to a curious high school student.
- Use analogies from everyday life (cooking, sports, travel, music, etc.)
- Never use jargon without immediately defining it.
- If a technical term is necessary, explain it in the same sentence.
- Break complex ideas into small, easy-to-digest pieces.
- Use "imagine that..." or "think of it like..." analogies frequently.
- Maintain the same depth as a detailed explanation but with simpler words.
- Avoid: acronyms, technical terms, and abstract phrasing without simple equivalents.

## Output Format
Organize your response with clear sections. For each section:
- State the core idea in one simple sentence
- Explain it using everyday analogies
- Give one concrete example
- Summarize in a sentence

Topic: {topic}
"""


def build_quiz_prompt(topic):
    return f"""You are a quiz master creating educational questions. Generate exactly 10 high-quality multiple-choice questions about the following topic.

## Topic: {topic}

## Instructions
- Generate exactly 10 questions. No more, no less.
- Each question must have exactly 4 options: A, B, C, D.
- Include 3 easy questions, 4 medium questions, and 3 hard questions.
- Questions should test different aspects: definitions, applications, analysis, and synthesis.
- Make each question self-contained and unambiguous.
- Distractors (wrong options) should be plausible but clearly incorrect.
- After each question, provide the correct answer (A/B/C/D) and a brief explanation of why it is correct.

## Output Format
1. Question text
(A) Option (B) Option (C) Option (D)
Answer: A — Brief explanation of why A is correct

2. Question text
(A) Option (B) Option (C) Option (D)
Answer: B — Brief explanation of why B is correct

...continue through all 10 questions.

Topic: {topic}
"""


def build_timeline_prompt(topic):
    return f"""You are a historian organizing events chronologically. Present the key events related to the following topic in strict chronological order.

## Topic: {topic}

## Instructions
- List events in the order they occurred, from earliest to latest.
- For each event, include: the date or time period, the event name, and a brief description.
- Group events by era or phase when appropriate.
- Highlight cause-effect relationships between consecutive events.
- Include the significance of each event.
- If exact dates are unknown, use approximate dates or time periods.
- The timeline should tell a coherent story of how {topic} developed over time.

## Output Format
### Era/Period Name (Year)
- Event: Description (significance)
- Event: Description (significance)

Topic: {topic}
"""


def build_compare_prompt(topic):
    return f"""You are an analyst creating a side-by-side comparison. Compare the following subjects across multiple dimensions.

## Topic: {topic}

## Instructions
- The topic should contain two or more things to compare (separated by 'vs' or 'and' or similar).
- Identify the key dimensions of comparison (at least 5).
- Present the comparison in a structured table format.
- Each row should be a comparison dimension, each column should be one of the subjects.
- Include a summary row at the end with a brief verdict.
- Be objective — present facts, not opinions.
- Cover: definition, key features, strengths, weaknesses, best use cases, and overall comparison.

## Output Format
Use a table format like:
| Dimension | Subject1 | Subject2 |
|-----------|----------|----------|
| Feature 1 | ... | ... |
| Feature 2 | ... | ... |

End with a brief verdict: which is better and in what context.

Topic: {topic}
"""


def build_steps_prompt(topic):
    return f"""You are a guide breaking down a process into clear steps. Present the following topic as a sequential list of actionable steps.

## Topic: {topic}

## Instructions
- Break the topic into a logical sequence of steps (7-10 steps).
- Each step should be one clear, actionable instruction.
- Include a one-line explanation for why each step matters.
- Steps must be in logical order — each step builds on the previous one.
- Include prerequisites or requirements at the beginning if needed.
- Add a summary or conclusion at the end.
- Use action verbs to start each step (Do, Set up, Configure, Run, Verify, etc.)

## Output Format
Step 1: Action — Explanation
Step 2: Action — Explanation
Step 3: Action — Explanation
...

Topic: {topic}
"""


def study(topic, p_client, s_client, mode):
    system_log("AI", "INFO", f"Starting study request: mode={mode}, topic={topic}")

    with open("config.json", "r") as f:
        config_data = json.load(f)

    primary_model = config_data["specialist"]["study"]["primary"]["name"]
    primary_provider = config_data["specialist"]["study"]["primary"]["provider"]
    secondary_model = config_data["specialist"]["study"]["secondary"]["name"]
    secondary_provider = config_data["specialist"]["study"]["secondary"]["provider"]

    prompts = {
        "detail": build_detail_prompt(topic),
        "simple": build_simple_prompt(topic),
        "quiz": build_quiz_prompt(topic),
        "timeline": build_timeline_prompt(topic),
        "compare": build_compare_prompt(topic),
        "steps": build_steps_prompt(topic),
    }

    prompt = prompts.get(mode, build_detail_prompt(topic))

    def call(client, provider, model, label):
        if provider == "google":
            response = client.models.generate_content(model=model, contents=prompt)
            return response.text
        else:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content

    try:
        system_log("AI", "INFO", f"Primary model being used for study: {primary_model}. Provider: {primary_provider}")
        response = call(p_client, primary_provider, primary_model, "primary")
        return response
    except Exception as e:
        system_log("AI", "ERROR", f"Primary model failed for study. Error: {str(e)}. Switching to secondary model: {secondary_model}. Provider: {secondary_provider}")
        try:
            response = call(s_client, secondary_provider, secondary_model, "secondary")
            return response
        except Exception as e2:
            system_log("AI", "ERROR", f"Secondary model also failed for study. Error: {str(e2)}")
            return "Both models failed to generate a response for this study request."
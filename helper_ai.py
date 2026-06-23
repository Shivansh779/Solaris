import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
model = "nvidia/nemotron-3-super-120b-a12b:free"

client_or = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OR_ASSIST_API_KEY"),
)

def summarise_pref(user_preference):

    prompt = f"""
You are a preference extraction system.

Convert the user's message into short AI behavior instructions.

Rules:
- Each instruction must be concise.
- Use imperative style.
- Keep only stable preferences.
- Ignore temporary requests.
- Output only the instructions.
- One instruction per line.
- Do not explain your reasoning.
- Do not add headings or bullet points.

User message:
{user_preference}
"""

    response = client_or.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return response.choices[0].message.content
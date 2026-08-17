from datetime import datetime
import json
import helper_ai

# Logging Function Definition
def system_log(category, level, message):
    with open("System_Logs.txt", "a") as f:
        f.write(f"[{level}] [{category}] [{current_time()}]: {message}\n")

# Current Time Function
def current_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def coder (prompt, p_client, s_client):
    with open("config.json", "r") as f:
        config = json.load(f)
 
    primary_model = config["specialist"]["coding"]["primary"]["name"]
    primary_provider = config["specialist"]["coding"]["primary"]["provider"]

    secondary_model = config["specialist"]["coding"]["secondary"]["name"]
    secondary_provider = config["specialist"]["coding"]["secondary"]["provider"]

    try:
        system_log("AI", "INFO", f"Primary model being used for coding: {primary_model}. Provider: {primary_provider}")
        if primary_provider == "google":
            response = p_client.models.generate_content(
                model=primary_model,
                contents=helper_ai.build_coding_prompt(prompt)
            )
            return response.text
        else:
            response = p_client.chat.completions.create(
                model=primary_model,
                messages=[
                    {"role" : "user", "content" : helper_ai.build_coding_prompt(prompt)}
                ]
            )
            return response.choices[0].message.content
    except Exception as e:
        system_log("AI", "ERROR", f"Primary model failed for coding. Error: {str(e)}. Switching to secondary model: {secondary_model}. Provider: {secondary_provider}")
        try:
            if secondary_provider == "google":
                response = s_client.models.generate_content(
                    model=secondary_model,
                    contents=helper_ai.build_coding_prompt(prompt)
                )
                return response.text
            else:
                response = s_client.chat.completions.create(
                    model=secondary_model,
                    messages=[
                        {"role" : "user", "content" : helper_ai.build_coding_prompt(prompt)}
                    ]
                )
                return response.choices[0].message.content
        except Exception as e:
            system_log("AI", "ERROR", f"Secondary model also failed for coding. Error: {str(e)}")
            return "Both primary and secondary models failed to generate a response."

def writer (prompt, p_client, s_client):
    with open("config.json", "r") as f:
        config = json.load(f)
 
    primary_model = config["specialist"]["writing"]["primary"]["name"]
    primary_provider = config["specialist"]["writing"]["primary"]["provider"]

    secondary_model = config["specialist"]["writing"]["secondary"]["name"]
    secondary_provider = config["specialist"]["writing"]["secondary"]["provider"]

    try:
        system_log("AI", "INFO", f"Primary model being used for writing: {primary_model}. Provider: {primary_provider}")
        if primary_provider == "google":
            response = p_client.models.generate_content(
                model=primary_model,
                contents=helper_ai.build_writing_prompt(prompt)
            )
            return response.text
        else:
            response = p_client.chat.completions.create(
                model=primary_model,
                messages=[
                    {"role" : "user", "content" : helper_ai.build_writing_prompt(prompt)}
                ]
            )
            return response.choices[0].message.content
    except Exception as e:
        system_log("AI", "ERROR", f"Primary model failed for writing. Error: {str(e)}. Switching to secondary model: {secondary_model}. Provider: {secondary_provider}")
        try:
            if secondary_provider == "google":
                response = s_client.models.generate_content(
                    model=secondary_model,
                    contents=helper_ai.build_writing_prompt(prompt)
                )
                return response.text
            else:
                response = s_client.chat.completions.create(
                    model=secondary_model,
                    messages=[
                        {"role" : "user", "content" : helper_ai.build_writing_prompt(prompt)}
                    ]
                )
                return response.choices[0].message.content
        except Exception as e:
            system_log("AI", "ERROR", f"Secondary model also failed for writing. Error: {str(e)}")
            return "Both primary and secondary models failed to generate a response."

def questionaire (prompt, p_client, s_client):
    with open("config.json", "r") as f:
        config = json.load(f)

    primary_model = config["specialist"]["reasoning"]["primary"]["name"]
    primary_provider = config["specialist"]["reasoning"]["primary"]["provider"]

    secondary_model = config["specialist"]["reasoning"]["secondary"]["name"]
    secondary_provider = config["specialist"]["reasoning"]["secondary"]["provider"]

    try:
        system_log("AI", "INFO", f"Primary model being used for questions: {primary_model}. Provider: {primary_provider}")
        if primary_provider == "google":
            response = p_client.models.generate_content(
                model=primary_model,
                contents=helper_ai.questions(prompt)
            )
            return response.text
        else:
            response = p_client.chat.completions.create(
                model=primary_model,
                messages=[
                    {"role" : "user", "content" : helper_ai.questions(prompt)}
                ]
            )
            return response.choices[0].message.content
    except Exception as e:
        system_log("AI", "ERROR", f"Primary model failed for questions. Error: {str(e)}. Switching to secondary model: {secondary_model}. Provider: {secondary_provider}")
        try:
            if secondary_provider == "google":
                response = s_client.models.generate_content(
                    model=secondary_model,
                    contents=helper_ai.questions(prompt)
                )
                return response.text
            else:
                response = s_client.chat.completions.create(
                    model=secondary_model,
                    messages=[
                        {"role" : "user", "content" : helper_ai.questions(prompt)}
                    ]
                )
                return response.choices[0].message.content
        except Exception as e:
            system_log("AI", "ERROR", f"Secondary model also failed for questions. Error: {str(e)}")
            return "The question generation failed on both models."

def strategist (prompt, p_client, s_client, ai_questions, answers, previous_draft=None, force_secondary=False):
    with open("config.json", "r") as f:
        config = json.load(f)
 
    primary_model = config["specialist"]["reasoning"]["primary"]["name"]
    primary_provider = config["specialist"]["reasoning"]["primary"]["provider"]

    secondary_model = config["specialist"]["reasoning"]["secondary"]["name"]
    secondary_provider = config["specialist"]["reasoning"]["secondary"]["provider"]

    def call (client, provider, model, label):
        if provider == "google":
            response = client.models.generate_content(
                model=model,
                contents=helper_ai.build_strategist_prompt(prompt, answers, ai_questions, previous_draft)
            )
            return response.text
        else:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                     "role" : "user",
                     "content" : helper_ai.build_strategist_prompt(prompt, answers, ai_questions, previous_draft)
                    }
                ]
            )
            return response.choices[0].message.content

    # Comparison pass: user disliked the primary's draft, so use the secondary model explicitly.
    if force_secondary:
        system_log("AI", "INFO", f"Secondary model being used for strategist comparison: {secondary_model}. Provider: {secondary_provider}")
        try:
            return call(s_client, secondary_provider, secondary_model, "secondary")
        except Exception as e:
            system_log("AI", "ERROR", f"Secondary model failed for comparison. Error: {str(e)}. Falling back to primary: {primary_model}")
            try:
                return call(p_client, primary_provider, primary_model, "primary")
            except Exception as e2:
                system_log("AI", "ERROR", f"Primary model also failed for comparison. Error: {str(e2)}")
                return "Both models failed to generate a revised draft."

    try:
        system_log("AI", "INFO", f"Primary model being used for strategist: {primary_model}. Provider: {primary_provider}")
        return call(p_client, primary_provider, primary_model, "primary")
    except Exception as e:
        system_log("AI", "ERROR", f"Primary model failed for strategist. Error: {str(e)}. Switching to secondary model: {secondary_model}. Provider: {secondary_provider}")
        try:
            return call(s_client, secondary_provider, secondary_model, "secondary")
        except Exception as e:
            system_log("AI", "ERROR", f"Secondary model also failed for strategist. Error: {str(e)}")
            return "Both primary and secondary models failed to generate a response."
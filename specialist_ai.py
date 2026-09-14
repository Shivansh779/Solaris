import json
import helper_ai
from _log import system_log, current_time

def _call_model(client, provider, model, prompt):
    if provider == "google":
        response = client.models.generate_content(model=model, contents=prompt)
        return response.text
    else:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content

def _try_fallback(prompt_builder, primary_client, primary_provider, primary_model,
                  secondary_client, secondary_provider, secondary_model, task_name):
    try:
        system_log("AI", "INFO", f"Primary model being used for {task_name}: {primary_model}. Provider: {primary_provider}")
        return _call_model(primary_client, primary_provider, primary_model, prompt_builder())
    except Exception as e:
        system_log("AI", "ERROR", f"Primary model failed for {task_name}. Error: {str(e)}. Switching to secondary model: {secondary_model}. Provider: {secondary_provider}")
        try:
            return _call_model(secondary_client, secondary_provider, secondary_model, prompt_builder())
        except Exception as e:
            system_log("AI", "ERROR", f"Secondary model also failed for {task_name}. Error: {str(e)}")
            return f"Both primary and secondary models failed to generate a response for {task_name}."

def coder(prompt, p_client, s_client, attachment_context=""):
    with open("config.json", "r") as f:
        config = json.load(f)
    
    primary_model = config["specialist"]["coding"]["primary"]["name"]
    primary_provider = config["specialist"]["coding"]["primary"]["provider"]
    secondary_model = config["specialist"]["coding"]["secondary"]["name"]
    secondary_provider = config["specialist"]["coding"]["secondary"]["provider"]
    
    return _try_fallback(
        lambda: helper_ai.build_coding_prompt(prompt, attachment_context),
        p_client, primary_provider, primary_model,
        s_client, secondary_provider, secondary_model,
        "coding"
    )

def writer(prompt, p_client, s_client, attachment_context=""):
    with open("config.json", "r") as f:
        config = json.load(f)
    
    primary_model = config["specialist"]["writing"]["primary"]["name"]
    primary_provider = config["specialist"]["writing"]["primary"]["provider"]
    secondary_model = config["specialist"]["writing"]["secondary"]["name"]
    secondary_provider = config["specialist"]["writing"]["secondary"]["provider"]
    
    return _try_fallback(
        lambda: helper_ai.build_writing_prompt(prompt, attachment_context),
        p_client, primary_provider, primary_model,
        s_client, secondary_provider, secondary_model,
        "writing"
    )

def questionaire(prompt, p_client, s_client, attachment_context=""):
    with open("config.json", "r") as f:
        config = json.load(f)
    
    primary_model = config["specialist"]["reasoning"]["primary"]["name"]
    primary_provider = config["specialist"]["reasoning"]["primary"]["provider"]
    secondary_model = config["specialist"]["reasoning"]["secondary"]["name"]
    secondary_provider = config["specialist"]["reasoning"]["secondary"]["provider"]
    
    return _try_fallback(
        lambda: helper_ai.questions(prompt, attachment_context),
        p_client, primary_provider, primary_model,
        s_client, secondary_provider, secondary_model,
        "questions"
    )

def strategist(prompt, p_client, s_client, ai_questions, answers, previous_draft=None, force_secondary=False, attachment_context=""):
    with open("config.json", "r") as f:
        config = json.load(f)
    
    primary_model = config["specialist"]["reasoning"]["primary"]["name"]
    primary_provider = config["specialist"]["reasoning"]["primary"]["provider"]
    secondary_model = config["specialist"]["reasoning"]["secondary"]["name"]
    secondary_provider = config["specialist"]["reasoning"]["secondary"]["provider"]
    
    def build_prompt():
        return helper_ai.build_strategist_prompt(prompt, answers, ai_questions, previous_draft, attachment_context)
    
    if force_secondary:
        system_log("AI", "INFO", f"Secondary model being used for strategist comparison: {secondary_model}. Provider: {secondary_provider}")
        try:
            return _call_model(s_client, secondary_provider, secondary_model, build_prompt())
        except Exception as e:
            system_log("AI", "ERROR", f"Secondary model failed for comparison. Error: {str(e)}. Falling back to primary: {primary_model}")
            try:
                return _call_model(p_client, primary_provider, primary_model, build_prompt())
            except Exception as e2:
                system_log("AI", "ERROR", f"Primary model also failed for comparison. Error: {str(e2)}")
                return "Both models failed to generate a revised draft."
    
    return _try_fallback(
        build_prompt,
        p_client, primary_provider, primary_model,
        s_client, secondary_provider, secondary_model,
        "strategist"
    )
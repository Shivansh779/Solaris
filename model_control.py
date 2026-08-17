import json
from datetime import datetime

with open("config.json", "r") as f:
    config = json.load(f)

# Current Time Function
def current_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Logging Function
def system_log(category, level, message):
    with open("System_Logs.txt", "a") as file:
        file.write(f"[{level}] [{category}] [{current_time()}]: {message}\n")

def increment_used (role, hierarchy):
    config["specialist"][role][hierarchy]["times_used"] += 1
    with open("config.json", "w") as file:
        file.write(json.dumps(config, indent=4))

    system_log("MODEL_CONFIG", "INFO", "Number of times used increased.")

def increment_satisfied (role, hierarchy):
    config["specialist"][role][hierarchy]["times_satisfied"] += 1
    with open("config.json", "w") as file:
        file.write(json.dumps(config, indent=4))

    system_log("MODEL_CONFIG", "INFO", "Number of times satisfied increased.")

def switch_models (role):
    model1 = config['specialist'][role]['primary']
    model2 = config['specialist'][role]['secondary']

    temp = model1
    model1 = model2
    model2 = temp

    config['specialist'][role]['primary'] = model1
    config['specialist'][role]['secondary'] = model2

    with open("config.json", "w") as file:
        file.write(json.dumps(config, indent=4))

    system_log("MODEL_CONFIG", "INFO", f"Models for {role.title()} have been changed.")

def replace_model (specialist, role, hierarchy, model_name, provider):
    current_model = config['specialist'][specialist][hierarchy]

    current_model['name'] = model_name
    current_model['provider'] = provider
    current_model['role'] = role
    current_model['times_used'], current_model['times_satisfied'] = 0, 0

    config['specialist'][specialist][hierarchy] = current_model
    with open("config.json", "w") as file:
        file.write(json.dumps(config, indent=4))

    system_log(
        "MODEL_CONFIG", "INFO",
        f"The {hierarchy.title()} model for {role.title()} has been replaced with {model_name}."
    )


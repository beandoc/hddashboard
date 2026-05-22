import sys
from jinja2 import Environment, FileSystemLoader

env = Environment(loader=FileSystemLoader('templates'))
try:
    env.get_template('patient_profile.html')
    print("No Jinja2 syntax errors found in patient_profile.html.")
except Exception as e:
    print(f"Jinja2 Error: {e}")
    sys.exit(1)

with open('templates/patient_profile.html', 'r') as f:
    content = f.read()
import re
div_open = len(re.findall(r'<div', content))
div_close = len(re.findall(r'</div', content))
print(f"div open: {div_open}, div close: {div_close}")

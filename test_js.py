import re

with open('templates/patient_profile.html') as f:
    content = f.read()

scripts = re.findall(r'<script\b[^>]*>(.*?)</script>', content, re.DOTALL)
for i, script in enumerate(scripts):
    if not script.strip(): continue
    # Replace jinja tags {{ ... }} and {% ... %} with empty strings
    clean = re.sub(r'\{\{.*?\}\}', 'null', script)
    clean = re.sub(r'\{%.*?%\}', '', clean)
    with open(f'script_{i}.js', 'w') as out:
        out.write(clean)
print("Saved scripts.")

import re
with open('templates/patient_profile.html') as f:
    content = f.read()

scripts = re.findall(r'<script\b[^>]*>(.*?)</script>', content, re.DOTALL)
for i, script in enumerate(scripts):
    if not script.strip(): continue
    print(f"--- Script {i} ---")
    lines = script.split('\n')
    for j, line in enumerate(lines):
        print(f"{j+1:03d}: {line}")

import re
with open('templates/patient_profile.html') as f:
    html = f.read()
scripts = re.findall(r'<script>(.*?)</script>', html, re.DOTALL)
for i, script in enumerate(scripts):
    print(f"--- Script {i+1} ---")
    print("\n".join(script.splitlines()[:5]))
    print("...")

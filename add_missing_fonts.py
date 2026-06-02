import os
import glob
import re

html_files = glob.glob('templates/**/*.html', recursive=True)

links = """  <link rel="stylesheet" href="/static/vendor/fonts/fonts.css"/>
  <link rel="stylesheet" href="/static/vendor/fonts/material-icons.css"/>
"""

count = 0
for fpath in html_files:
    with open(fpath, 'r') as f:
        content = f.read()
    
    # Check if it has a <head> tag and does NOT have material-icons.css
    if '<head>' in content and 'material-icons.css' not in content:
        # Insert the links right after <head>
        new_content = content.replace('<head>', '<head>\n' + links, 1)
        with open(fpath, 'w') as f:
            f.write(new_content)
        count += 1
        print(f"Added fonts to {fpath}")

print(f"Added fonts to {count} files.")

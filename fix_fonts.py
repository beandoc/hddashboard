import os
import glob

html_files = glob.glob('templates/**/*.html', recursive=True)

old_fonts_preload = """    <link rel="preload" href="/static/vendor/fonts/fonts.css" as="style" onload="this.onload=null;this.rel='stylesheet'"/>
    <noscript><link rel="stylesheet" href="/static/vendor/fonts/fonts.css"/></noscript>"""

old_icons_preload = """    <link rel="preload" href="/static/vendor/fonts/material-icons.css" as="style" onload="this.onload=null;this.rel='stylesheet'"/>
    <noscript><link rel="stylesheet" href="/static/vendor/fonts/material-icons.css"/></noscript>"""

new_fonts = '    <link rel="stylesheet" href="/static/vendor/fonts/fonts.css"/>'
new_icons = '    <link rel="stylesheet" href="/static/vendor/fonts/material-icons.css"/>'

count = 0
for fpath in html_files:
    with open(fpath, 'r') as f:
        content = f.read()
    
    modified = False
    if old_fonts_preload in content:
        content = content.replace(old_fonts_preload, new_fonts)
        modified = True
    if old_icons_preload in content:
        content = content.replace(old_icons_preload, new_icons)
        modified = True
        
    if modified:
        with open(fpath, 'w') as f:
            f.write(content)
        count += 1

print(f"Modified {count} files.")

import os
import re

# get all json files in the current directory
json_files = [f for f in os.listdir('.') if os.path.isfile(f) and f.endswith('.json')]

# compile a regex pattern to match numbers with 11 or more digits
pattern = re.compile(r'\d{11,}')

for filename in json_files:
    print(f"Processing {filename}...")
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()

    # replace all numbers with 11 or more digits with 1145141919810
    new_content = pattern.sub('1145141919810', content)

    # write the new content to a new file with the same name but with '.example' appended
    new_filename = filename + '.example'
    with open(new_filename, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f"Created {new_filename}!")

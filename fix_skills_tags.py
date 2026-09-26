with open("src/open_skill_registry/server/routes/skills.py", "r") as f:
    code = f.read()

code = code.replace(
    '"tags": [tag.tag_name for tag in sv.tags]',
    '        "tags": await storage.get_version_tags(sv.id)'
)

with open("src/open_skill_registry/server/routes/skills.py", "w") as f:
    f.write(code)

with open("src/open_skill_registry/server/routes/skills.py", "r") as f:
    code = f.read()

code = code.replace(
    'if ".." in path or path.startswith("/"):',
    'if ".." in path or path.startswith("/") or "\\\\" in path:'
)

with open("src/open_skill_registry/server/routes/skills.py", "w") as f:
    f.write(code)

with open("src/open_skill_registry/registry/storage/sqlite.py", "r") as f:
    code = f.read()
code = code.replace("if query:\n                stmt = stmt.where(\n                    or_(", "if query and not query_vector:\n                stmt = stmt.where(\n                    or_(")
with open("src/open_skill_registry/registry/storage/sqlite.py", "w") as f:
    f.write(code)

with open("src/open_skill_registry/registry/storage/pgvector.py", "r") as f:
    code = f.read()
code = code.replace("if query:\n                stmt = stmt.where(\n                    or_(", "if query and not query_vector:\n                stmt = stmt.where(\n                    or_(")
with open("src/open_skill_registry/registry/storage/pgvector.py", "w") as f:
    f.write(code)

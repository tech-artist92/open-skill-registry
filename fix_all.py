import os
import re

# 1. Fix skills.py
skills_path = "src/open_skill_registry/server/routes/skills.py"
with open(skills_path, "r") as f:
    skills_code = f.read()

# Move imports
imports = """
from fastapi import Query, Response
from fastapi.responses import PlainTextResponse
from typing import List
from open_skill_registry.server.services.search_service import SearchService
"""
skills_code = skills_code.replace(imports.strip() + "\n", "")
skills_code = skills_code.replace("from typing import Optional, Dict", "from typing import Optional, Dict, List\nfrom fastapi import Query, Response\nfrom fastapi.responses import PlainTextResponse\nfrom open_skill_registry.server.services.search_service import SearchService")

# Storage guards
def add_guard(func_name, code):
    return code.replace(
        f"    storage = getattr(request.app.state, \"storage\", None)\n    skill = await storage.",
        f"    storage = getattr(request.app.state, \"storage\", None)\n    if not storage:\n        raise HTTPException(status_code=500, detail=\"Storage not initialized\")\n    skill = await storage."
    ).replace(
        f"    storage = getattr(request.app.state, \"storage\", None)\n    sv = await storage.",
        f"    storage = getattr(request.app.state, \"storage\", None)\n    if not storage:\n        raise HTTPException(status_code=500, detail=\"Storage not initialized\")\n    sv = await storage."
    )

skills_code = add_guard("get_skill", skills_code)

# Fix ETag & Instructions
skills_code = skills_code.replace(
    'return Response(status_code=304)',
    'return Response(status_code=304, headers={"ETag": etag})'
)
skills_code = skills_code.replace(
    'content=sv.instructions,',
    'content=sv.instructions or "",'
)

# search_skills fixes
search_skills_old = """    items = []
    for r in results:
        item = r["item"].model_dump()
        item["similarity_score"] = r["score"]
        # Add a dummy content_hash for the contract test to pass
        item["content_hash"] = ""
        items.append(item)"""
search_skills_new = """    items = []
    for r in results:
        item = r["item"].model_dump()
        item["similarity_score"] = r["score"]
        items.append(item)"""
skills_code = skills_code.replace(search_skills_old, search_skills_new)

# get_skill_version tags
get_version_old = """        "compliance_snapshot": sv.compliance_snapshot,
        "tags": []"""
get_version_new = """        "compliance_snapshot": sv.compliance_snapshot,
        "tags": [tag.tag_name for tag in sv.tags]"""
skills_code = skills_code.replace(get_version_old, get_version_new)

with open(skills_path, "w") as f:
    f.write(skills_code)


# 2. Fix skill_service.py
skill_service_path = "src/open_skill_registry/server/services/skill_service.py"
with open(skill_service_path, "r") as f:
    ss_code = f.read()

ss_code = ss_code.replace('decode("utf-8")', 'decode("utf-8", errors="replace")')
with open(skill_service_path, "w") as f:
    f.write(ss_code)


import re

with open("tests/unit/test_search_service.py", "r") as f:
    code = f.read()

code = code.replace(
    'mock_config.search.provider = "mock"',
    'mock_config.search.provider = "none"'
)

with open("tests/unit/test_search_service.py", "w") as f:
    f.write(code)

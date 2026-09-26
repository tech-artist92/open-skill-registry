with open("tests/unit/test_search_service.py", "r") as f:
    code = f.read()

code = code.replace(
    'config.search.provider = "mock"',
    'config.search.provider = "none"'
)

with open("tests/unit/test_search_service.py", "w") as f:
    f.write(code)

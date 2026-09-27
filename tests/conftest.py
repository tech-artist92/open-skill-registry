import os

# Configure in-memory database by default for all automated tests
os.environ["OSR_DATABASE__URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

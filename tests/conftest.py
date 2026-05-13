import os
import tempfile

# Isolate Chroma/SQLite per test run before `app` imports `settings`.
_test_data = tempfile.mkdtemp(prefix="legal_workflow_test_")
os.environ.setdefault("LEGAL_WORKFLOW_DATA_DIR", _test_data)
os.environ.setdefault("LEGAL_WORKFLOW_ENVIRONMENT", "development")
# Empty string = no API key required for tests (override host env if set).
os.environ.setdefault("LEGAL_WORKFLOW_API_KEY", "")
os.environ.setdefault("LEGAL_WORKFLOW_RATE_LIMIT_REQUESTS_PER_MINUTE", "0")

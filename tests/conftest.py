import os
import tempfile

# Isolate Chroma/SQLite per test run before `app` imports `settings`.
_test_data = tempfile.mkdtemp(prefix="legal_workflow_test_")
os.environ.setdefault("LEGAL_WORKFLOW_DATA_DIR", _test_data)

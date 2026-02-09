import pytest

from app.tools.contracts import ToolProvenance, ToolResponse
from app.tools.verifier import verify_response


def test_tool_envelope_provenance_required():
    response = ToolResponse.ok(
        correlation_id="corr",
        data={"revenue": 123.4},
        provenance=ToolProvenance(sources=[]),
    )
    verified = verify_response(response)

    assert verified.status == "error"
    assert verified.error is not None
    assert verified.error.code == "PROVENANCE_MISSING"

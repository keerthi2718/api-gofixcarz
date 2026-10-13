import io
import zipfile
from xml.etree import ElementTree
import pytest
from app.core.admin_totp import totp, new_secret, encrypt_secret, decrypt_secret, verify_totp
from app.services.admin_export_service import render_report, scalar


def test_rfc6238_sha1_six_digits_and_factor_encryption():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert totp(secret, 59//30) == "287082"
    fresh = new_secret()
    encrypted = encrypt_secret(fresh)
    assert encrypted != fresh and decrypt_secret(encrypted) == fresh
    counter = verify_totp(fresh, totp(fresh))
    assert counter is not None and verify_totp(fresh, totp(fresh), counter) is None


@pytest.mark.parametrize("value", ["=SUM(A1:A2)", "+command", "-command", "@SUM(A1)", "  =formula"])
def test_spreadsheet_injection(value):
    assert scalar(value).startswith("'")


def test_xlsx_is_valid_xml_and_csv_quotes_metadata():
    payload = {"rows": [{"name": "<&=unsafe", "count": 2}], "filters": {}, "generated_at": "fixture",
               "snapshot_id": "fixture", "row_count": 1, "source_totals": {"count": 2}, "metric_definitions": {}}
    output, mime = render_report(payload, "XLSX")
    assert mime.endswith("sheet")
    with zipfile.ZipFile(io.BytesIO(output)) as archive:
        for path in archive.namelist():
            ElementTree.fromstring(archive.read(path))
    csv, mime = render_report(payload, "CSV")
    assert mime == "text/csv" and b"source_totals" in csv

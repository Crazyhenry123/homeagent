"""Tests for health document upload/download/delete — mocked S3."""

from unittest.mock import MagicMock, patch


def _register_admin(client):
    resp = client.post(
        "/api/auth/register",
        json={
            "invite_code": "FAMILY",
            "device_name": "Admin Phone",
            "platform": "ios",
            "display_name": "Admin",
        },
    )
    data = resp.get_json()
    return data["user_id"], data["device_token"]


def _register_member(client, admin_token, name="Member"):
    resp = client.post(
        "/api/admin/invite-codes",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    code = resp.get_json()["code"]
    resp = client.post(
        "/api/auth/register",
        json={
            "invite_code": code,
            "device_name": "Phone",
            "platform": "android",
            "display_name": name,
        },
    )
    data = resp.get_json()
    return data["user_id"], data["device_token"]


def _with_s3_mock(app):
    """Set S3 config and return a mock S3 client."""
    app.config["S3_HEALTH_DOCUMENTS_BUCKET"] = "test-bucket"
    app.config["S3_ENDPOINT"] = "http://localhost:9000"
    mock_s3 = MagicMock()
    mock_s3.generate_presigned_url.return_value = "https://s3.example.com/presigned"
    return mock_s3


def test_upload_document(client, app):
    admin_id, admin_token = _register_admin(client)
    member_id, _ = _register_member(client, admin_token)
    mock_s3 = _with_s3_mock(app)

    with patch("app.services.health_documents._get_s3_client", return_value=mock_s3):
        resp = client.post(
            f"/api/admin/health-documents/{member_id}/upload",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "filename": "lab_results.pdf",
                "content_type": "application/pdf",
                "file_size": 1024,
                "description": "Blood work results",
            },
        )

    assert resp.status_code == 201
    data = resp.get_json()
    assert data["filename"] == "lab_results.pdf"
    assert data["content_type"] == "application/pdf"
    assert "upload_url" in data
    assert "document_id" in data
    assert data["uploaded_by"] == admin_id


def test_upload_invalid_content_type(client, app):
    _, admin_token = _register_admin(client)
    member_id, _ = _register_member(client, admin_token)
    _with_s3_mock(app)

    resp = client.post(
        f"/api/admin/health-documents/{member_id}/upload",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "filename": "doc.txt",
            "content_type": "text/plain",
            "file_size": 100,
        },
    )
    assert resp.status_code == 400
    assert "Invalid content type" in resp.get_json()["error"]


def test_upload_file_too_large(client, app):
    _, admin_token = _register_admin(client)
    member_id, _ = _register_member(client, admin_token)
    _with_s3_mock(app)

    resp = client.post(
        f"/api/admin/health-documents/{member_id}/upload",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "filename": "huge.pdf",
            "content_type": "application/pdf",
            "file_size": 20 * 1024 * 1024,  # 20 MB
        },
    )
    assert resp.status_code == 400
    assert "exceeds maximum" in resp.get_json()["error"]


def test_upload_missing_fields(client, app):
    _, admin_token = _register_admin(client)
    member_id, _ = _register_member(client, admin_token)

    resp = client.post(
        f"/api/admin/health-documents/{member_id}/upload",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"filename": "test.pdf"},
    )
    assert resp.status_code == 400
    assert "required" in resp.get_json()["error"]


def test_download_document(client, app):
    admin_id, admin_token = _register_admin(client)
    member_id, _ = _register_member(client, admin_token)
    mock_s3 = _with_s3_mock(app)

    with patch("app.services.health_documents._get_s3_client", return_value=mock_s3):
        upload_resp = client.post(
            f"/api/admin/health-documents/{member_id}/upload",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "filename": "photo.jpg",
                "content_type": "image/jpeg",
                "file_size": 2048,
            },
        )
        doc_id = upload_resp.get_json()["document_id"]

        resp = client.get(
            f"/api/admin/health-documents/{member_id}/{doc_id}/download",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert "download_url" in data
    assert data["filename"] == "photo.jpg"


def test_download_not_found(client, app):
    _, admin_token = _register_admin(client)
    member_id, _ = _register_member(client, admin_token)
    _with_s3_mock(app)

    resp = client.get(
        f"/api/admin/health-documents/{member_id}/nonexistent/download",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 404


def test_list_documents(client, app):
    _, admin_token = _register_admin(client)
    member_id, _ = _register_member(client, admin_token)
    mock_s3 = _with_s3_mock(app)

    with patch("app.services.health_documents._get_s3_client", return_value=mock_s3):
        for name in ["doc1.pdf", "doc2.pdf"]:
            client.post(
                f"/api/admin/health-documents/{member_id}/upload",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={
                    "filename": name,
                    "content_type": "application/pdf",
                    "file_size": 500,
                },
            )

    resp = client.get(
        f"/api/admin/health-documents/{member_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert len(resp.get_json()["documents"]) == 2


def test_delete_document(client, app):
    _, admin_token = _register_admin(client)
    member_id, _ = _register_member(client, admin_token)
    mock_s3 = _with_s3_mock(app)

    with patch("app.services.health_documents._get_s3_client", return_value=mock_s3):
        upload_resp = client.post(
            f"/api/admin/health-documents/{member_id}/upload",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "filename": "to_delete.pdf",
                "content_type": "application/pdf",
                "file_size": 100,
            },
        )
        doc_id = upload_resp.get_json()["document_id"]

        resp = client.delete(
            f"/api/admin/health-documents/{member_id}/{doc_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    # Verify S3 delete was called
    mock_s3.delete_object.assert_called_once()


def test_delete_document_not_found(client, app):
    _, admin_token = _register_admin(client)
    member_id, _ = _register_member(client, admin_token)
    mock_s3 = _with_s3_mock(app)

    with patch("app.services.health_documents._get_s3_client", return_value=mock_s3):
        resp = client.delete(
            f"/api/admin/health-documents/{member_id}/nonexistent",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 404


def test_documents_require_admin(client, app):
    _, admin_token = _register_admin(client)
    member_id, member_token = _register_member(client, admin_token)

    resp = client.get(
        f"/api/admin/health-documents/{member_id}",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp.status_code == 403

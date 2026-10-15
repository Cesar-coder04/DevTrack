import asyncio
from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from app.api.routes import (
    notifications,
    organization_invitations,
    user_preferences,
    work_item_attachments,
    work_item_comments,
    work_item_tags,
)
from app.core.security import hash_access_token
from app.models.notification import Notification
from app.models.organization import Organization
from app.models.organization_invitation import OrganizationInvitation
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.tag import Tag
from app.models.user import User
from app.models.user_preference import UserPreference
from app.models.work_item import WorkItem
from app.models.work_item_attachment import WorkItemAttachment
from app.models.work_item_comment import WorkItemComment
from app.models.work_item_tag import WorkItemTag
from app.schemas.notification import NotificationResponse
from app.schemas.organization_invitation import (
    OrganizationInvitationCreate,
    OrganizationInvitationResponse,
)
from app.schemas.user_preference import (
    UserPreferenceResponse,
    UserPreferenceUpdate,
)
from app.schemas.work_item_attachment import WorkItemAttachmentResponse
from app.schemas.work_item_comment import WorkItemCommentResponse
from app.schemas.work_item_tag import WorkItemTagResponse


NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)


def make_invitation(**overrides):
    values = {
        "id": 5,
        "organization_id": 7,
        "invited_by_id": 11,
        "email": "invitee@example.com",
        "role": "member",
        "token_hash": hash_access_token("opaque-token"),
        "expires_at": NOW + timedelta(days=3),
        "accepted_at": None,
        "revoked_at": None,
        "created_at": NOW,
    }
    values.update(overrides)
    return OrganizationInvitation(**values)


def make_user_preference(**overrides):
    values = {
        "user_id": 11,
        "email_notifications": True,
        "in_app_notifications": True,
        "preferences": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return UserPreference(**values)


def make_notification(**overrides):
    values = {
        "id": 3,
        "recipient_id": 11,
        "work_item_id": 17,
        "type": "task_assigned",
        "title": "Assigned",
        "message": "A task was assigned",
        "is_read": False,
        "read_at": None,
        "created_at": NOW,
    }
    values.update(overrides)
    return Notification(**values)


def test_invitation_creation_hashes_token_and_derives_pending_status(monkeypatch):
    monkeypatch.setattr(
        organization_invitations,
        "get_manageable_organization",
        lambda db, organization_id, user_id: Organization(
            id=organization_id, owner_id=user_id
        ),
    )
    monkeypatch.setattr(
        organization_invitations,
        "uuid4",
        lambda: SimpleNamespace(hex="raw-invitation-token"),
    )
    invited_user = SimpleNamespace(id=22, email="invitee@example.com", is_active=True)
    db = MagicMock()
    db.scalar.side_effect = [invited_user, None]
    db.get.return_value = None
    added = []
    def add_invitation(invitation):
        invitation.id = 5
        added.append(invitation)

    db.add.side_effect = add_invitation
    db.refresh.side_effect = lambda invitation: setattr(
        invitation, "created_at", NOW
    )

    invitation = organization_invitations.create_invitation(
        organization_id=7,
        data=OrganizationInvitationCreate(
            email="invitee@example.com",
            role="admin",
        ),
        db=db,
        current_user=SimpleNamespace(id=11),
    )

    assert added[0].invited_by_id == 11
    assert added[0].token_hash == hash_access_token("raw-invitation-token")
    assert not hasattr(added[0], "token")
    response = OrganizationInvitationResponse.model_validate(invitation)
    assert response.invited_by == 11
    assert response.status == "pending"


def test_invitation_schema_derives_all_persisted_states():
    assert (
        OrganizationInvitationResponse.model_validate(
            make_invitation(accepted_at=NOW)
        ).status
        == "accepted"
    )
    assert (
        OrganizationInvitationResponse.model_validate(
            make_invitation(revoked_at=NOW)
        ).status
        == "revoked"
    )
    assert (
        OrganizationInvitationResponse.model_validate(
            make_invitation(expires_at=NOW - timedelta(seconds=1))
        ).status
        == "expired"
    )
    with pytest.raises(ValidationError):
        OrganizationInvitationCreate(
            email="invitee@example.com",
            role="viewer",
        )


def test_invitation_lists_are_scoped_and_public_status_is_mapped(monkeypatch):
    invitation = make_invitation()
    monkeypatch.setattr(
        organization_invitations,
        "get_manageable_organization",
        lambda db, organization_id, user_id: Organization(id=organization_id),
    )
    db = MagicMock()
    db.scalars.return_value.all.return_value = [invitation]

    organization_result = organization_invitations.list_organization_invitations(
        organization_id=7,
        db=db,
        current_user=SimpleNamespace(id=11),
    )
    assert OrganizationInvitationResponse.model_validate(
        organization_result[0]
    ).status == "pending"
    organization_query = db.scalars.call_args.args[0]
    assert "organization_invitations.organization_id" in str(organization_query)
    assert 7 in organization_query.compile().params.values()

    organization_invitations.list_my_invitations(
        db=db,
        current_user=SimpleNamespace(id=22, email="invitee@example.com"),
    )
    my_query = str(db.scalars.call_args.args[0])
    assert "organization_invitations.email =" in my_query
    assert "organization_invitations.accepted_at IS NULL" in my_query
    assert "organization_invitations.revoked_at IS NULL" in my_query


def test_accept_invitation_creates_membership_and_marks_timestamp():
    invitation = make_invitation()
    db = MagicMock()
    db.scalar.return_value = invitation
    db.get.side_effect = [Organization(id=7), None]
    added = []
    db.add.side_effect = added.append

    result = organization_invitations.accept_invitation(
        invitation_id=5,
        db=db,
        current_user=SimpleNamespace(id=22, email="invitee@example.com"),
    )

    assert result["message"] == "Invitación aceptada correctamente."
    assert invitation.accepted_at is not None
    assert added[0].organization_id == 7
    assert added[0].user_id == 22
    assert added[0].role == "member"
    db.commit.assert_called_once()


def test_accept_invitation_rejects_expired_and_processed_invites():
    expired = make_invitation(expires_at=NOW - timedelta(seconds=1))
    db = MagicMock()
    db.scalar.return_value = expired
    db.get.return_value = Organization(id=7)

    with pytest.raises(HTTPException) as expired_error:
        organization_invitations.accept_invitation(
            invitation_id=5,
            db=db,
            current_user=SimpleNamespace(id=22, email="invitee@example.com"),
        )
    assert expired_error.value.status_code == 400
    db.commit.assert_not_called()


def test_comment_access_helper_rejects_nonmembers():
    item = WorkItem(id=17, project_id=7, created_by_id=11, title="Task")
    db = MagicMock()
    db.get.side_effect = [item, Project(id=7, deleted_at=None), None]

    with pytest.raises(HTTPException) as error:
        work_item_comments.get_accessible_work_item(
            db=db,
            work_item_id=17,
            user=SimpleNamespace(id=22),
        )
    assert error.value.status_code == 403

    db.reset_mock()
    db.scalar.return_value = make_invitation(accepted_at=NOW)
    with pytest.raises(HTTPException) as processed_error:
        organization_invitations.accept_invitation(
            invitation_id=5,
            db=db,
            current_user=SimpleNamespace(id=22, email="invitee@example.com"),
        )
    assert processed_error.value.status_code == 409
    db.commit.assert_not_called()


def test_invitee_rejection_and_manager_revocation_are_authorized(monkeypatch):
    invitation = make_invitation()
    db = MagicMock()
    db.scalar.return_value = invitation

    organization_invitations.reject_invitation(
        invitation_id=5,
        db=db,
        current_user=SimpleNamespace(id=22, email="invitee@example.com"),
    )
    assert invitation.revoked_at is not None
    db.commit.assert_called_once()

    pending = make_invitation()
    db.reset_mock()
    db.scalar.return_value = pending
    monkeypatch.setattr(
        organization_invitations,
        "get_manageable_organization",
        lambda db, organization_id, user_id: Organization(id=organization_id),
    )
    result = organization_invitations.revoke_invitation(
        organization_id=7,
        invitation_id=5,
        db=db,
        current_user=SimpleNamespace(id=11),
    )
    assert result["message"] == "Invitación revocada correctamente."
    assert pending.revoked_at is not None
    db.commit.assert_called_once()

    pending = make_invitation()
    db.reset_mock()
    db.scalar.return_value = pending
    db.commit.side_effect = RuntimeError("write failed")
    with pytest.raises(RuntimeError, match="write failed"):
        organization_invitations.revoke_invitation(
            organization_id=7,
            invitation_id=5,
            db=db,
            current_user=SimpleNamespace(id=11),
        )
    db.rollback.assert_called_once()
    assert pending.revoked_at is not None


def test_manager_cannot_revoke_invitation_from_another_organization(monkeypatch):
    monkeypatch.setattr(
        organization_invitations,
        "get_manageable_organization",
        lambda db, organization_id, user_id: Organization(id=organization_id),
    )
    db = MagicMock()
    db.scalar.return_value = None
    with pytest.raises(HTTPException) as error:
        organization_invitations.revoke_invitation(
            organization_id=7,
            invitation_id=99,
            db=db,
            current_user=SimpleNamespace(id=11),
        )
    assert error.value.status_code == 404
    db.commit.assert_not_called()


def test_organization_member_cannot_manage_invitations():
    db = MagicMock()
    db.get.side_effect = [
        Organization(id=7, deleted_at=None),
        SimpleNamespace(role="member"),
    ]

    with pytest.raises(HTTPException) as error:
        organization_invitations.get_manageable_organization(
            db=db,
            organization_id=7,
            user_id=22,
        )
    assert error.value.status_code == 403


def test_comment_create_list_edit_delete_use_author_id_and_public_alias(monkeypatch):
    item = WorkItem(id=17, project_id=7, created_by_id=11, title="Task")
    monkeypatch.setattr(
        work_item_comments,
        "get_accessible_work_item",
        lambda db, work_item_id, user: item,
    )
    db = MagicMock()
    created = []
    db.add.side_effect = created.append
    db.refresh.side_effect = lambda comment: (
        setattr(comment, "id", 4),
        setattr(comment, "created_at", NOW),
        setattr(comment, "updated_at", NOW),
    )

    comment = work_item_comments.create_comment(
        work_item_id=17,
        data=work_item_comments.WorkItemCommentCreate(content="Hello"),
        db=db,
        user=SimpleNamespace(id=11),
    )
    assert created[0].author_id == 11
    assert WorkItemCommentResponse.model_validate(comment).user_id == 11

    db.scalars.return_value.all.return_value = [comment]
    listed = work_item_comments.list_comments(
        work_item_id=17,
        db=db,
        user=SimpleNamespace(id=11),
    )
    assert WorkItemCommentResponse.model_validate(listed[0]).content == "Hello"

    db.get.return_value = comment
    comment.updated_at = NOW
    updated = work_item_comments.update_comment(
        work_item_id=17,
        comment_id=4,
        data=work_item_comments.WorkItemCommentUpdate(content="Updated"),
        db=db,
        user=SimpleNamespace(id=11),
    )
    assert updated.content == "Updated"

    work_item_comments.delete_comment(
        work_item_id=17,
        comment_id=4,
        db=db,
        user=SimpleNamespace(id=11),
    )
    db.delete.assert_called_once_with(comment)


def test_comment_edit_and_delete_reject_other_authors(monkeypatch):
    item = WorkItem(id=17, project_id=7, created_by_id=11, title="Task")
    comment = WorkItemComment(
        id=4, work_item_id=17, author_id=22, content="Private"
    )
    monkeypatch.setattr(
        work_item_comments,
        "get_accessible_work_item",
        lambda db, work_item_id, user: item,
    )
    db = MagicMock()
    db.get.return_value = comment

    with pytest.raises(HTTPException) as edit_error:
        work_item_comments.update_comment(
            work_item_id=17,
            comment_id=4,
            data=work_item_comments.WorkItemCommentUpdate(content="No"),
            db=db,
            user=SimpleNamespace(id=11),
        )
    assert edit_error.value.status_code == 403

    with pytest.raises(HTTPException) as delete_error:
        work_item_comments.delete_comment(
            work_item_id=17,
            comment_id=4,
            db=db,
            user=SimpleNamespace(id=11),
        )
    assert delete_error.value.status_code == 403
    db.commit.assert_not_called()


def test_attachment_upload_lists_downloads_and_deletes_with_orm_names(
    monkeypatch, tmp_path
):
    item = WorkItem(id=17, project_id=7, created_by_id=11, title="Task")
    monkeypatch.setattr(
        work_item_attachments,
        "get_accessible_work_item",
        lambda db, work_item_id, user_id: item,
    )
    monkeypatch.setattr(work_item_attachments, "UPLOAD_DIR", tmp_path)
    db = MagicMock()
    added = []
    db.add.side_effect = added.append
    db.refresh.side_effect = lambda attachment: (
        setattr(attachment, "id", 8),
        setattr(attachment, "uploaded_at", NOW),
    )
    upload = UploadFile(filename="report.txt", file=BytesIO(b"report"))

    attachment = asyncio.run(
        work_item_attachments.upload_attachment(
            work_item_id=17,
            file=upload,
            db=db,
            current_user=SimpleNamespace(id=11),
        )
    )
    assert added[0].uploaded_by_id == 11
    assert added[0].filename == "report.txt"
    assert (tmp_path / added[0].storage_key).read_bytes() == b"report"
    response = WorkItemAttachmentResponse.model_validate(attachment)
    assert response.uploaded_by == 11
    assert response.file_name == "report.txt"
    assert response.created_at == NOW
    assert "storage_key" not in response.model_dump()

    db.scalars.return_value.all.return_value = [attachment]
    listed = work_item_attachments.list_attachments(
        work_item_id=17,
        db=db,
        current_user=SimpleNamespace(id=11),
    )
    assert WorkItemAttachmentResponse.model_validate(listed[0]).file_name == (
        "report.txt"
    )
    assert "work_item_attachments.uploaded_at DESC" in str(
        db.scalars.call_args.args[0]
    )

    db.scalar.return_value = attachment
    download = work_item_attachments.download_attachment(
        work_item_id=17,
        attachment_id=8,
        db=db,
        current_user=SimpleNamespace(id=11),
    )
    assert Path(download.path) == tmp_path / attachment.storage_key
    assert download.filename == "report.txt"

    db.get.return_value = ProjectMember(
        project_id=7, user_id=11, role="member"
    )
    file_path = tmp_path / attachment.storage_key
    work_item_attachments.delete_attachment(
        work_item_id=17,
        attachment_id=8,
        db=db,
        current_user=SimpleNamespace(id=11),
    )
    assert not file_path.exists()
    db.delete.assert_called_once_with(attachment)


def test_failed_attachment_write_rolls_back_and_removes_file(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        work_item_attachments,
        "get_accessible_work_item",
        lambda db, work_item_id, user_id: WorkItem(
            id=17, project_id=7, created_by_id=11, title="Task"
        ),
    )
    monkeypatch.setattr(work_item_attachments, "UPLOAD_DIR", tmp_path)
    db = MagicMock()
    db.commit.side_effect = RuntimeError("database unavailable")
    upload = UploadFile(filename="failed.txt", file=BytesIO(b"contents"))

    with pytest.raises(RuntimeError, match="database unavailable"):
        asyncio.run(
            work_item_attachments.upload_attachment(
                work_item_id=17,
                file=upload,
                db=db,
                current_user=SimpleNamespace(id=11),
            )
        )

    db.rollback.assert_called_once()
    assert list(tmp_path.iterdir()) == []


def test_attachment_size_limit_returns_413_and_cleans_up(monkeypatch, tmp_path):
    monkeypatch.setattr(
        work_item_attachments,
        "get_accessible_work_item",
        lambda db, work_item_id, user_id: WorkItem(
            id=17, project_id=7, created_by_id=11, title="Task"
        ),
    )
    monkeypatch.setattr(work_item_attachments, "UPLOAD_DIR", tmp_path)
    db = MagicMock()
    upload = UploadFile(
        filename="large.bin",
        file=BytesIO(b"x" * (work_item_attachments.MAX_FILE_SIZE + 1)),
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            work_item_attachments.upload_attachment(
                work_item_id=17,
                file=upload,
                db=db,
                current_user=SimpleNamespace(id=11),
            )
        )

    assert error.value.status_code == 413
    db.rollback.assert_called_once()
    assert list(tmp_path.iterdir()) == []


def test_attachment_refresh_failure_keeps_file_after_commit(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        work_item_attachments,
        "get_accessible_work_item",
        lambda db, work_item_id, user_id: WorkItem(
            id=17, project_id=7, created_by_id=11, title="Task"
        ),
    )
    monkeypatch.setattr(work_item_attachments, "UPLOAD_DIR", tmp_path)
    db = MagicMock()
    db.refresh.side_effect = RuntimeError("refresh failed")
    upload = UploadFile(filename="saved.txt", file=BytesIO(b"saved"))

    with pytest.raises(RuntimeError, match="refresh failed"):
        asyncio.run(
            work_item_attachments.upload_attachment(
                work_item_id=17,
                file=upload,
                db=db,
                current_user=SimpleNamespace(id=11),
            )
        )

    db.commit.assert_called_once()
    db.rollback.assert_not_called()
    assert len(list(tmp_path.iterdir())) == 1


def test_attachment_delete_denies_non_owner_non_admin(monkeypatch):
    attachment = WorkItemAttachment(
        id=8,
        work_item_id=17,
        uploaded_by_id=22,
        filename="report.txt",
        storage_key="opaque",
        size_bytes=10,
    )
    monkeypatch.setattr(
        work_item_attachments,
        "get_accessible_work_item",
        lambda db, work_item_id, user_id: WorkItem(
            id=17, project_id=7, created_by_id=11, title="Task"
        ),
    )
    db = MagicMock()
    db.scalar.return_value = attachment
    db.get.return_value = ProjectMember(
        project_id=7, user_id=11, role="member"
    )

    with pytest.raises(HTTPException) as error:
        work_item_attachments.delete_attachment(
            work_item_id=17,
            attachment_id=8,
            db=db,
            current_user=SimpleNamespace(id=11),
        )
    assert error.value.status_code == 403
    db.delete.assert_not_called()


def test_attachment_access_helper_rejects_nonmembers():
    item = WorkItem(id=17, project_id=7, created_by_id=11, title="Task")
    db = MagicMock()
    db.get.side_effect = [item, Project(id=7), None]

    with pytest.raises(HTTPException) as error:
        work_item_attachments.get_accessible_work_item(
            db=db,
            work_item_id=17,
            user_id=22,
        )
    assert error.value.status_code == 403


def test_attachment_download_rejects_nonmembers_before_lookup(monkeypatch):
    def deny_access(db, work_item_id, user_id):
        raise HTTPException(status_code=403)

    monkeypatch.setattr(
        work_item_attachments,
        "get_accessible_work_item",
        deny_access,
    )
    db = MagicMock()

    with pytest.raises(HTTPException) as error:
        work_item_attachments.download_attachment(
            work_item_id=17,
            attachment_id=8,
            db=db,
            current_user=SimpleNamespace(id=22),
        )
    assert error.value.status_code == 403
    db.scalar.assert_not_called()


def test_notifications_list_count_mark_all_and_delete_are_recipient_scoped():
    notification = make_notification()
    db = MagicMock()
    db.scalars.return_value.all.return_value = [notification]

    rows = notifications.list_notifications(
        unread_only=True,
        db=db,
        current_user=SimpleNamespace(id=11),
    )
    assert NotificationResponse.model_validate(rows[0]).user_id == 11
    list_query = db.scalars.call_args.args[0]
    assert "notifications.recipient_id" in str(list_query)
    assert 11 in list_query.compile().params.values()

    db.scalar.return_value = 2
    assert notifications.get_unread_count(
        db=db,
        current_user=SimpleNamespace(id=11),
    ) == {"unread_count": 2}
    count_query = db.scalar.call_args.args[0]
    assert "notifications.recipient_id" in str(count_query)
    assert 11 in count_query.compile().params.values()

    db.scalar.return_value = notification
    updated = notifications.mark_notification_as_read(
        notification_id=3,
        db=db,
        current_user=SimpleNamespace(id=11),
    )
    assert updated.is_read is True
    assert updated.read_at is not None
    marked_query = db.scalar.call_args.args[0]
    assert "notifications.recipient_id" in str(marked_query)
    assert 11 in marked_query.compile().params.values()
    assert NotificationResponse.model_validate(updated).user_id == 11

    db.scalars.return_value.all.return_value = [notification]
    notifications.mark_all_notifications_as_read(
        db=db,
        current_user=SimpleNamespace(id=11),
    )
    assert notification.is_read is True
    assert notification.read_at is not None
    mass_query = db.scalars.call_args.args[0]
    assert "notifications.recipient_id" in str(mass_query)
    assert 11 in mass_query.compile().params.values()

    db.scalar.return_value = notification
    notifications.delete_notification(
        notification_id=3,
        db=db,
        current_user=SimpleNamespace(id=11),
    )
    db.delete.assert_called_once_with(notification)
    delete_query = db.scalar.call_args.args[0]
    assert "notifications.recipient_id" in str(delete_query)
    assert 11 in delete_query.compile().params.values()


def test_notification_operations_hide_other_users_records():
    db = MagicMock()
    db.scalar.return_value = None
    with pytest.raises(HTTPException) as error:
        notifications.mark_notification_as_read(
            notification_id=3,
            db=db,
            current_user=SimpleNamespace(id=11),
        )
    assert error.value.status_code == 404
    statement = db.scalar.call_args.args[0]
    assert "notifications.recipient_id" in str(statement)
    assert 11 in statement.compile().params.values()
    db.commit.assert_not_called()


def test_preferences_defaults_read_and_json_updates_preserve_other_keys():
    db = MagicMock()
    preference = make_user_preference(
        preferences={
            "theme": "dark",
            "language": "en",
            "push_notifications": True,
            "custom_setting": "keep",
        }
    )
    db.get.return_value = preference

    response = user_preferences.get_preferences(
        db=db,
        current_user=SimpleNamespace(id=11),
    )
    assert response == UserPreferenceResponse(
        user_id=11,
        theme="dark",
        language="en",
        email_notifications=True,
        push_notifications=True,
        updated_at=NOW,
    )

    updated = user_preferences.update_preferences(
        data=UserPreferenceUpdate(theme="light", email_notifications=False),
        db=db,
        current_user=SimpleNamespace(id=11),
    )
    assert preference.preferences == {
        "theme": "light",
        "language": "en",
        "push_notifications": True,
        "custom_setting": "keep",
    }
    assert preference.email_notifications is False
    assert preference.in_app_notifications is True
    assert updated.theme == "light"
    assert updated.push_notifications is True
    db.commit.assert_called_once()


def test_preferences_defaults_persisted_fields_and_validation():
    db = MagicMock()
    preference = make_user_preference()
    db.get.return_value = preference

    response = user_preferences.update_preferences(
        data=UserPreferenceUpdate(),
        db=db,
        current_user=SimpleNamespace(id=11),
    )
    assert response.theme == "system"
    assert response.language == "es"
    assert response.push_notifications is False
    assert response.email_notifications is True
    assert preference.preferences is None
    assert preference.in_app_notifications is True

    with pytest.raises(ValidationError):
        UserPreferenceUpdate(theme=None)
    with pytest.raises(ValidationError):
        UserPreferenceUpdate(push_notifications=None)
    with pytest.raises(ValidationError):
        UserPreferenceUpdate(theme="sepia")
    with pytest.raises(ValidationError):
        UserPreferenceUpdate(language="fr")


def test_work_item_tag_association_records_actor_and_duplicate_is_conflict(
    monkeypatch,
):
    item = WorkItem(id=17, project_id=7, created_by_id=11, title="Task")
    tag = Tag(id=9, project_id=7, name="backend", color="#123456")
    monkeypatch.setattr(
        work_item_tags,
        "get_accessible_item",
        lambda db, work_item_id, user: item,
    )
    db = MagicMock()
    db.get.side_effect = [tag, None]
    added = []
    db.add.side_effect = added.append

    result = work_item_tags.add_tag_to_work_item(
        work_item_id=17,
        data=work_item_tags.WorkItemTagCreate(tag_id=9),
        db=db,
        user=SimpleNamespace(id=11),
    )
    assert result == {"message": "Etiqueta asociada correctamente."}
    assert isinstance(added[0], WorkItemTag)
    assert added[0].work_item_id == 17
    assert added[0].tag_id == 9
    assert added[0].added_by_id == 11

    db.get.side_effect = [tag, WorkItemTag(work_item_id=17, tag_id=9, added_by_id=11)]
    with pytest.raises(HTTPException) as duplicate:
        work_item_tags.add_tag_to_work_item(
            work_item_id=17,
            data=work_item_tags.WorkItemTagCreate(tag_id=9),
            db=db,
            user=SimpleNamespace(id=11),
        )
    assert duplicate.value.status_code == 409
    assert db.commit.call_count == 1


def test_work_item_tag_duplicate_race_maps_integrity_error_to_conflict(
    monkeypatch,
):
    from sqlalchemy.exc import IntegrityError

    item = WorkItem(id=17, project_id=7, created_by_id=11, title="Task")
    tag = Tag(id=9, project_id=7, name="backend", color="#123456")
    monkeypatch.setattr(
        work_item_tags,
        "get_accessible_item",
        lambda db, work_item_id, user: item,
    )
    db = MagicMock()
    db.get.side_effect = [tag, None]
    db.commit.side_effect = IntegrityError("insert", {}, Exception("duplicate"))

    with pytest.raises(HTTPException) as error:
        work_item_tags.add_tag_to_work_item(
            work_item_id=17,
            data=work_item_tags.WorkItemTagCreate(tag_id=9),
            db=db,
            user=SimpleNamespace(id=11),
        )
    assert error.value.status_code == 409
    db.rollback.assert_called_once()


def test_work_item_tag_list_uses_tag_response_and_checks_access(monkeypatch):
    item = WorkItem(id=17, project_id=7, created_by_id=11, title="Task")
    monkeypatch.setattr(
        work_item_tags,
        "get_accessible_item",
        lambda db, work_item_id, user: item,
    )
    db = MagicMock()
    db.execute.return_value.all.return_value = [
        SimpleNamespace(id=9, name="backend", color="#123456")
    ]

    result = work_item_tags.list_work_item_tags(
        work_item_id=17,
        db=db,
        user=SimpleNamespace(id=11),
    )
    assert result == [
        WorkItemTagResponse(id=9, name="backend", color="#123456")
    ]


def test_work_item_tag_access_helper_rejects_nonmembers():
    item = WorkItem(id=17, project_id=7, created_by_id=11, title="Task")
    db = MagicMock()
    db.get.side_effect = [item, Project(id=7, deleted_at=None), None]

    with pytest.raises(HTTPException) as error:
        work_item_tags.get_accessible_item(
            db=db,
            work_item_id=17,
            user=SimpleNamespace(id=22),
        )
    assert error.value.status_code == 403

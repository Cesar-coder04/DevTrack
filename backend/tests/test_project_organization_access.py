import asyncio
import inspect
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app.api.routes import (
    organization_members,
    tags,
    work_item_attachments,
    work_item_comments,
    work_item_history,
    work_item_tags,
    work_items,
)
from app.db.base import Base
from app.models.organization import Organization
from app.models.organization_member import OrganizationMember
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.tag import Tag
from app.models.work_item import WorkItem
from app.models.work_item_attachment import WorkItemAttachment
from app.models.work_item_comment import WorkItemComment
from app.models.work_item_history import WorkItemHistory
from app.models.work_item_tag import WorkItemTag
from app.models.user import User
from app.schemas.tag import TagCreate
from app.schemas.work_item import WorkItemCreate
from app.schemas.work_item_comment import WorkItemCommentCreate
from app.schemas.work_item_tag import WorkItemTagCreate


USER_ID = 11
PROJECT_ID = 7
WORK_ITEM_ID = 17
ORGANIZATION_ID = 3


def make_database(
    *,
    organization_member_exists: bool = True,
    organization_role: str = "member",
    project_role: str = "member",
    organization_id: int | None = ORGANIZATION_ID,
):
    from unittest.mock import MagicMock

    database = MagicMock()
    project = Project(
        id=PROJECT_ID,
        organization_id=organization_id,
        owner_id=USER_ID,
        deleted_at=None,
        archived_at=None,
    )
    item = WorkItem(
        id=WORK_ITEM_ID,
        project_id=PROJECT_ID,
        created_by_id=USER_ID,
        title="Test task",
    )
    membership = ProjectMember(
        project_id=PROJECT_ID,
        user_id=USER_ID,
        role=project_role,
    )
    org_membership = OrganizationMember(
        organization_id=ORGANIZATION_ID,
        user_id=USER_ID,
        role=organization_role,
    )
    tag = Tag(
        id=9,
        project_id=PROJECT_ID,
        name="backend",
        color="#123456",
    )
    attachment = WorkItemAttachment(
        id=8,
        work_item_id=WORK_ITEM_ID,
        uploaded_by_id=USER_ID,
        filename="file.txt",
        storage_key="stored-file.txt",
        size_bytes=4,
    )
    comment = WorkItemComment(
        id=6,
        work_item_id=WORK_ITEM_ID,
        author_id=USER_ID,
        content="Comment",
    )
    database.resources = {
        Project: project,
        WorkItem: item,
        ProjectMember: membership,
        Tag: tag,
        WorkItemAttachment: attachment,
        WorkItemComment: comment,
    }
    if organization_member_exists:
        database.resources[OrganizationMember] = org_membership

    def get(model, key):
        if model is OrganizationMember:
            if organization_id is None:
                return None
            return database.resources.get(model)
        if model is ProjectMember:
            return database.resources[model]
        if model is Project:
            return database.resources[model]
        if model is WorkItemTag:
            return None
        return database.resources.get(model)

    database.get.side_effect = get
    database.scalars.return_value.all.return_value = []
    database.execute.return_value.all.return_value = []
    database.scalar.return_value = None
    database.refresh.side_effect = lambda instance: None
    database.flush.side_effect = lambda: [
        setattr(instance, "id", 99)
        for instance in getattr(database, "added", [])
        if isinstance(instance, WorkItem) and instance.id is None
    ]

    def add(instance):
        database.added.append(instance)

    database.added = []
    database.add.side_effect = add
    return database


def invoke(endpoint):
    result = endpoint()
    if inspect.isawaitable(result):
        return asyncio.run(result)
    return result


def revoked_access_endpoints(database, user):
    upload = UploadFile(filename="blocked.txt", file=BytesIO(b"data"))
    return [
        lambda: work_items.list_work_items(
            project_id=PROJECT_ID, db=database, current_user=user
        ),
        lambda: work_items.get_work_item(
            project_id=PROJECT_ID,
            work_item_id=WORK_ITEM_ID,
            db=database,
            current_user=user,
        ),
        lambda: work_items.create_work_item(
            project_id=PROJECT_ID,
            item_data=WorkItemCreate(title="Blocked"),
            db=database,
            current_user=user,
        ),
        lambda: work_items.update_work_item(
            project_id=PROJECT_ID,
            work_item_id=WORK_ITEM_ID,
            item_data=work_items.WorkItemUpdate(description="Blocked"),
            db=database,
            current_user=user,
        ),
        lambda: work_items.delete_work_item(
            project_id=PROJECT_ID,
            work_item_id=WORK_ITEM_ID,
            db=database,
            current_user=user,
        ),
        lambda: work_item_comments.list_comments(
            work_item_id=WORK_ITEM_ID, db=database, user=user
        ),
        lambda: work_item_comments.create_comment(
            work_item_id=WORK_ITEM_ID,
            data=WorkItemCommentCreate(content="Blocked"),
            db=database,
            user=user,
        ),
        lambda: work_item_comments.update_comment(
            work_item_id=WORK_ITEM_ID,
            comment_id=6,
            data=work_item_comments.WorkItemCommentUpdate(content="Blocked"),
            db=database,
            user=user,
        ),
        lambda: work_item_comments.delete_comment(
            work_item_id=WORK_ITEM_ID,
            comment_id=6,
            db=database,
            user=user,
        ),
        lambda: work_item_history.list_work_item_history(
            work_item_id=WORK_ITEM_ID, db=database, user=user
        ),
        lambda: tags.list_tags(
            project_id=PROJECT_ID, db=database, user=user
        ),
        lambda: tags.create_tag(
            project_id=PROJECT_ID,
            data=TagCreate(name="blocked"),
            db=database,
            user=user,
        ),
        lambda: tags.update_tag(
            project_id=PROJECT_ID,
            tag_id=9,
            data=tags.TagUpdate(color="#654321"),
            db=database,
            user=user,
        ),
        lambda: tags.delete_tag(
            project_id=PROJECT_ID, tag_id=9, db=database, user=user
        ),
        lambda: work_item_tags.list_work_item_tags(
            work_item_id=WORK_ITEM_ID, db=database, user=user
        ),
        lambda: work_item_tags.add_tag_to_work_item(
            work_item_id=WORK_ITEM_ID,
            data=WorkItemTagCreate(tag_id=9),
            db=database,
            user=user,
        ),
        lambda: work_item_tags.remove_tag_from_work_item(
            work_item_id=WORK_ITEM_ID, tag_id=9, db=database, user=user
        ),
        lambda: work_item_attachments.list_attachments(
            work_item_id=WORK_ITEM_ID,
            db=database,
            current_user=user,
        ),
        lambda: work_item_attachments.upload_attachment(
            work_item_id=WORK_ITEM_ID,
            file=upload,
            db=database,
            current_user=user,
        ),
        lambda: work_item_attachments.download_attachment(
            work_item_id=WORK_ITEM_ID,
            attachment_id=8,
            db=database,
            current_user=user,
        ),
        lambda: work_item_attachments.delete_attachment(
            work_item_id=WORK_ITEM_ID,
            attachment_id=8,
            db=database,
            current_user=user,
        ),
    ]


def test_removed_organization_member_cannot_use_project_resource_endpoints(
    tmp_path,
):
    database = make_database(organization_member_exists=False)
    user = SimpleNamespace(id=USER_ID)
    endpoints = revoked_access_endpoints(database, user)

    assert database.resources[ProjectMember].user_id == USER_ID
    for endpoint in endpoints:
        with pytest.raises(HTTPException) as error:
            invoke(endpoint)
        assert error.value.status_code == 403

    assert not any(
        call.args[0] is ProjectMember for call in database.get.call_args_list
    )
    database.add.assert_not_called()
    database.commit.assert_not_called()
    database.delete.assert_not_called()
    database.scalars.assert_not_called()
    database.scalar.assert_not_called()
    database.execute.assert_not_called()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("organization_role", "project_role"),
    [
        ("member", "member"),
        ("owner", "member"),
        ("admin", "member"),
        ("member", "owner"),
        ("member", "admin"),
        ("member", "viewer"),
    ],
)
def test_authorized_users_keep_project_resource_access(
    organization_role,
    project_role,
    tmp_path,
    monkeypatch,
):
    database = make_database(
        organization_role=organization_role,
        project_role=project_role,
    )
    user = SimpleNamespace(id=USER_ID)
    monkeypatch.setattr(work_item_attachments, "UPLOAD_DIR", tmp_path)

    assert work_items.list_work_items(
        project_id=PROJECT_ID, db=database, current_user=user
    ) == []
    work_items.create_work_item(
        project_id=PROJECT_ID,
        item_data=WorkItemCreate(title="Allowed"),
        db=database,
        current_user=user,
    )
    assert database.commit.call_count == 1

    assert work_item_comments.list_comments(
        work_item_id=WORK_ITEM_ID, db=database, user=user
    ) == []
    work_item_comments.create_comment(
        work_item_id=WORK_ITEM_ID,
        data=WorkItemCommentCreate(content="Allowed"),
        db=database,
        user=user,
    )
    assert database.commit.call_count == 2

    assert work_item_history.list_work_item_history(
        work_item_id=WORK_ITEM_ID, db=database, user=user
    ) == []

    assert tags.list_tags(project_id=PROJECT_ID, db=database, user=user) == []
    tags.create_tag(
        project_id=PROJECT_ID,
        data=TagCreate(name="allowed"),
        db=database,
        user=user,
    )
    assert database.commit.call_count == 3

    assert work_item_tags.list_work_item_tags(
        work_item_id=WORK_ITEM_ID, db=database, user=user
    ) == []
    work_item_tags.add_tag_to_work_item(
        work_item_id=WORK_ITEM_ID,
        data=WorkItemTagCreate(tag_id=9),
        db=database,
        user=user,
    )
    assert database.commit.call_count == 4

    assert work_item_attachments.list_attachments(
        work_item_id=WORK_ITEM_ID, db=database, current_user=user
    ) == []
    invoke(
        lambda: work_item_attachments.upload_attachment(
            work_item_id=WORK_ITEM_ID,
            file=UploadFile(filename="allowed.txt", file=BytesIO(b"data")),
            db=database,
            current_user=user,
        )
    )
    assert database.commit.call_count == 5
    assert len(list(tmp_path.iterdir())) == 1


@pytest.mark.parametrize("project_role", ["owner", "admin"])
def test_project_owners_and_admins_keep_delete_permissions(project_role):
    database = make_database(project_role=project_role)
    user = SimpleNamespace(id=USER_ID)

    work_items.delete_work_item(
        project_id=PROJECT_ID,
        work_item_id=WORK_ITEM_ID,
        db=database,
        current_user=user,
    )
    database.delete.assert_called_once_with(database.resources[WorkItem])
    database.commit.assert_called_once()
    tags.delete_tag(
        project_id=PROJECT_ID,
        tag_id=9,
        db=database,
        user=user,
    )
    database.delete.assert_called_with(database.resources[Tag])
    assert database.commit.call_count == 2


def test_project_organization_membership_guard_preserves_legacy_behavior():
    database = make_database(organization_id=None)
    user = SimpleNamespace(id=USER_ID)

    with pytest.raises(HTTPException) as task_access_error:
        work_items.get_project_access(PROJECT_ID, user, database)
    assert task_access_error.value.status_code == 403

    assert (
        work_item_comments.get_accessible_work_item(
            database, WORK_ITEM_ID, user
        )
        is database.resources[WorkItem]
    )
    assert (
        work_item_tags.get_accessible_item(
            database, WORK_ITEM_ID, user
        )
        is database.resources[WorkItem]
    )
    assert tags.get_project_for_member(database, PROJECT_ID, user) is database.resources[
        Project
    ]
    assert work_item_history.list_work_item_history(
        work_item_id=WORK_ITEM_ID, db=database, user=user
    ) == []
    assert (
        work_item_attachments.get_accessible_work_item(
            database, WORK_ITEM_ID, USER_ID
        )
        is database.resources[WorkItem]
    )
    assert database.resources[ProjectMember].user_id == USER_ID
    assert not any(
        call.args[0] is OrganizationMember for call in database.get.call_args_list
    )


def test_removing_organization_member_preserves_project_membership_and_revokes_access():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(
        engine,
        "connect",
        lambda connection, _: connection.create_function(
            "CHAR_LENGTH", 1, len
        ),
    )
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            Organization.__table__,
            OrganizationMember.__table__,
            Project.__table__,
            ProjectMember.__table__,
            WorkItem.__table__,
            WorkItemHistory.__table__,
        ],
    )

    try:
        with Session(engine) as database:
            manager = User(
                username="manager",
                email="manager@example.test",
                password_hash="unused",
                display_name="Manager",
            )
            expelled_user = User(
                username="expelled",
                email="expelled@example.test",
                password_hash="unused",
                display_name="Expelled",
            )
            database.add_all([manager, expelled_user])
            database.flush()

            organization = Organization(
                name="Test organization",
                slug="test-organization",
                owner_id=manager.id,
            )
            database.add(organization)
            database.flush()

            project = Project(
                name="Organizational project",
                organization_id=organization.id,
                owner_id=manager.id,
            )
            database.add(project)
            database.flush()
            work_item = WorkItem(
                project_id=project.id,
                created_by_id=manager.id,
                title="Protected task",
            )

            database.add_all(
                [
                    OrganizationMember(
                        organization_id=organization.id,
                        user_id=manager.id,
                        role="owner",
                    ),
                    OrganizationMember(
                        organization_id=organization.id,
                        user_id=expelled_user.id,
                        role="member",
                    ),
                    ProjectMember(
                        project_id=project.id,
                        user_id=expelled_user.id,
                        role="member",
                    ),
                    work_item,
                ]
            )
            database.commit()

            organization_members.remove_member(
                organization_id=organization.id,
                user_id=expelled_user.id,
                db=database,
                current_user=manager,
            )

            assert database.get(
                OrganizationMember, (organization.id, expelled_user.id)
            ) is None
            assert database.get(
                ProjectMember, (project.id, expelled_user.id)
            ) is not None

            resource_access_checks = [
                lambda: work_items.get_project_access(
                    project.id, expelled_user, database
                ),
                lambda: work_item_comments.get_accessible_work_item(
                    database, work_item.id, expelled_user
                ),
                lambda: work_item_history.list_work_item_history(
                    work_item_id=work_item.id,
                    db=database,
                    user=expelled_user,
                ),
                lambda: tags.get_project_for_member(
                    database, project.id, expelled_user
                ),
                lambda: work_item_tags.get_accessible_item(
                    database, work_item.id, expelled_user
                ),
                lambda: work_item_attachments.get_accessible_work_item(
                    database, work_item.id, expelled_user.id
                ),
            ]
            for check_access in resource_access_checks:
                with pytest.raises(HTTPException) as error:
                    check_access()
                assert error.value.status_code == 403
    finally:
        engine.dispose()

import asyncio
import inspect
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app.api.routes import (
    organization_projects,
    organization_members,
    tags,
    work_item_attachments,
    work_item_comments,
    work_item_history,
    work_item_tags,
    work_items,
    user_work_items,
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
from app.schemas.work_item import WorkItemCreate, WorkItemUpdate
from app.schemas.work_item_comment import WorkItemCommentCreate
from app.schemas.work_item_tag import WorkItemTagCreate


USER_ID = 11
PROJECT_ID = 7
WORK_ITEM_ID = 17
ORGANIZATION_ID = 3


@pytest.fixture
def access_database():
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
            Tag.__table__,
            WorkItem.__table__,
            WorkItemHistory.__table__,
            WorkItemComment.__table__,
            WorkItemAttachment.__table__,
            WorkItemTag.__table__,
        ],
    )
    try:
        with Session(engine) as database:
            yield database
    finally:
        engine.dispose()


@pytest.fixture
def foreign_key_access_database():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    def configure_sqlite(connection, _):
        connection.create_function("CHAR_LENGTH", 1, len)
        cursor = connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

    event.listen(engine, "connect", configure_sqlite)
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            Organization.__table__,
            OrganizationMember.__table__,
            Project.__table__,
            ProjectMember.__table__,
            Tag.__table__,
            WorkItem.__table__,
            WorkItemHistory.__table__,
            WorkItemComment.__table__,
            WorkItemAttachment.__table__,
            WorkItemTag.__table__,
        ],
    )
    try:
        with Session(engine) as database:
            yield database
    finally:
        engine.dispose()


def create_project_access_records(
    database,
    *,
    organization: bool,
    organization_member: bool = True,
    project_member: bool = True,
    project_role: str = "member",
):
    user = User(
        username="project-user",
        email="project-user@example.test",
        password_hash="unused",
        display_name="Project User",
    )
    database.add(user)
    database.flush()

    organization_record = None
    if organization:
        organization_record = Organization(
            name="Access test organization",
            slug="access-test-organization",
            owner_id=user.id,
        )
        database.add(organization_record)
        database.flush()
        if organization_member:
            database.add(
                OrganizationMember(
                    organization_id=organization_record.id,
                    user_id=user.id,
                    role="member",
                )
            )

    project = Project(
        name="Access test project",
        organization_id=(
            organization_record.id if organization_record is not None else None
        ),
        owner_id=user.id,
    )
    database.add(project)
    database.flush()

    if project_member:
        database.add(
            ProjectMember(
                project_id=project.id,
                user_id=user.id,
                role=project_role,
            )
        )

    item = WorkItem(
        project_id=project.id,
        created_by_id=user.id,
        title="Protected task",
    )
    database.add(item)
    database.commit()
    return user, project, item


def add_work_item_relations(database, user, project, work_item):
    tag = Tag(project_id=project.id, name="backend", color="#123456")
    database.add(tag)
    database.flush()
    database.add_all(
        [
            WorkItemComment(
                work_item_id=work_item.id,
                author_id=user.id,
                content="Keep this comment",
            ),
            WorkItemAttachment(
                work_item_id=work_item.id,
                uploaded_by_id=user.id,
                filename="spec.txt",
                storage_key="spec.txt",
                size_bytes=4,
            ),
            WorkItemTag(
                work_item_id=work_item.id,
                tag_id=tag.id,
                added_by_id=user.id,
            ),
        ]
    )
    database.commit()


def add_assigned_task(
    database,
    project,
    user,
    *,
    title="Assigned task",
    **overrides,
):
    values = {
        "project_id": project.id,
        "created_by_id": user.id,
        "assigned_to_id": user.id,
        "type": "task",
        "title": title,
        "status": "open",
        "priority": "medium",
    }
    values.update(overrides)
    item = WorkItem(**values)
    database.add(item)
    return item


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
    organization = Organization(
        id=ORGANIZATION_ID,
        name="Test organization",
        slug="test-organization",
        owner_id=USER_ID,
        deleted_at=None,
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
        Organization: organization,
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
        if model is Organization:
            return database.resources.get(model)
        if model is Project:
            return database.resources[model]
        if model is WorkItemTag:
            return None
        return database.resources.get(model)

    database.get.side_effect = get
    database.scalars.return_value.all.return_value = []
    database.execute.return_value.all.return_value = []
    database.execute.return_value.rowcount = 1
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
    delete_statement = database.execute.call_args.args[0]
    assert "work_items.deleted_at IS NULL" in str(delete_statement)
    database.delete.assert_not_called()
    deletion_history = database.add.call_args.args[0]
    assert isinstance(deletion_history, WorkItemHistory)
    assert deletion_history.changed_by_id == user.id
    assert deletion_history.field_name == "deleted"
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

    project, membership = work_items.get_project_access(
        PROJECT_ID, user, database
    )
    assert project is database.resources[Project]
    assert membership is database.resources[ProjectMember]

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


def test_personal_project_member_can_create_list_get_and_update_work_items(
    access_database,
):
    user, project, work_item = create_project_access_records(
        access_database,
        organization=False,
    )

    listed_work_items = work_items.list_work_items(
        project_id=project.id,
        db=access_database,
        current_user=user,
    )
    assert len(listed_work_items) == 1
    assert listed_work_items[0].id == work_item.id
    assert listed_work_items[0].assignee_id is None
    assert listed_work_items[0].assignee_display_name is None
    detail = work_items.get_work_item(
        project_id=project.id,
        work_item_id=work_item.id,
        db=access_database,
        current_user=user,
    )
    assert detail.id == work_item.id
    assert detail.project_name == project.name
    assert detail.assignee_id is None
    assert detail.assignee_display_name is None

    updated = work_items.update_work_item(
        project_id=project.id,
        work_item_id=work_item.id,
        item_data=WorkItemUpdate(description="Updated"),
        db=access_database,
        current_user=user,
    )
    assert updated.description == "Updated"

    created = work_items.create_work_item(
        project_id=project.id,
        item_data=WorkItemCreate(title="Created task"),
        db=access_database,
        current_user=user,
    )
    assert created.project_id == project.id
    assert access_database.get(WorkItem, created.id) is not None


def test_personal_project_user_without_project_membership_receives_403(
    access_database,
):
    user, project, _ = create_project_access_records(
        access_database,
        organization=False,
        project_member=False,
    )

    with pytest.raises(HTTPException) as error:
        work_items.list_work_items(
            project_id=project.id,
            db=access_database,
            current_user=user,
        )

    assert error.value.status_code == 403


def test_organization_project_member_keeps_work_item_access(access_database):
    user, project, work_item = create_project_access_records(
        access_database,
        organization=True,
    )

    accessible_project, membership = work_items.get_project_access(
        project.id, user, access_database
    )

    assert accessible_project is project
    assert membership.user_id == user.id

    work_item.assigned_to_id = user.id
    access_database.commit()
    listed_work_items = work_items.list_work_items(
        project_id=project.id,
        db=access_database,
        current_user=user,
    )
    assert len(listed_work_items) == 1
    assert listed_work_items[0].assignee_id == user.id
    assert listed_work_items[0].assignee_display_name == user.display_name


@pytest.mark.parametrize(
    ("organization_member", "project_member"),
    [(False, True), (True, False)],
)
def test_organization_project_access_still_requires_both_memberships(
    access_database,
    organization_member,
    project_member,
):
    user, project, _ = create_project_access_records(
        access_database,
        organization=True,
        organization_member=organization_member,
        project_member=project_member,
    )

    with pytest.raises(HTTPException) as error:
        work_items.list_work_items(
            project_id=project.id,
            db=access_database,
            current_user=user,
        )

    assert error.value.status_code == 403


def test_organization_project_listing_only_returns_projects_the_member_can_open(
    access_database,
):
    user, active_project, _ = create_project_access_records(
        access_database, organization=True
    )
    organization_id = active_project.organization_id
    no_project_membership = Project(
        name="Organization-only membership project",
        organization_id=organization_id,
        owner_id=user.id,
    )
    archived = Project(
        name="Archived organization project",
        organization_id=organization_id,
        owner_id=user.id,
        archived_at=datetime.now(timezone.utc),
    )
    deleted = Project(
        name="Deleted organization project",
        organization_id=organization_id,
        owner_id=user.id,
        deleted_at=datetime.now(timezone.utc),
    )
    access_database.add_all([no_project_membership, archived, deleted])
    access_database.flush()
    access_database.add_all(
        [
            ProjectMember(project_id=archived.id, user_id=user.id, role="member"),
            ProjectMember(project_id=deleted.id, user_id=user.id, role="member"),
        ]
    )
    outsider = User(
        username="organization-outsider",
        email="organization-outsider@example.test",
        password_hash="unused",
        display_name="Organization Outsider",
    )
    access_database.add(outsider)
    access_database.commit()

    result = organization_projects.list_projects(
        organization_id=organization_id,
        db=access_database,
        current_user=user,
    )

    assert [project.id for project in result] == [active_project.id]
    with pytest.raises(HTTPException) as error:
        organization_projects.list_projects(
            organization_id=organization_id,
            db=access_database,
            current_user=outsider,
        )
    assert error.value.status_code == 403

    organization = access_database.get(Organization, organization_id)
    organization.deleted_at = datetime.now(timezone.utc)
    access_database.commit()
    with pytest.raises(HTTPException) as deleted_error:
        organization_projects.list_projects(
            organization_id=organization_id,
            db=access_database,
            current_user=user,
        )
    assert deleted_error.value.status_code == 404
    assert access_database.get(Project, active_project.id) is not None
    assert access_database.get(Project, deleted.id) is not None


def test_deleted_organization_blocks_project_and_work_item_resources_without_deleting_data(
    foreign_key_access_database,
):
    database = foreign_key_access_database
    user, project, work_item = create_project_access_records(
        database,
        organization=True,
        project_role="owner",
    )
    organization = database.get(Organization, project.organization_id)
    work_item.assigned_to_id = user.id
    add_work_item_relations(database, user, project, work_item)
    database.add(
        WorkItemHistory(
            work_item_id=work_item.id,
            changed_by_id=user.id,
            field_name="title",
            old_value=None,
            new_value=work_item.title,
        )
    )
    organization.deleted_at = datetime.now(timezone.utc)
    database.commit()

    denied_access_checks = [
        lambda: work_items.get_project_access(project.id, user, database),
        lambda: work_items.list_work_items(
            project_id=project.id,
            db=database,
            current_user=user,
        ),
        lambda: work_item_comments.get_accessible_work_item(
            database, work_item.id, user
        ),
        lambda: work_item_attachments.get_accessible_work_item(
            database, work_item.id, user.id
        ),
        lambda: work_item_tags.get_accessible_item(
            database, work_item.id, user
        ),
        lambda: tags.get_project_for_member(database, project.id, user),
        lambda: work_item_history.list_work_item_history(
            work_item_id=work_item.id,
            db=database,
            user=user,
        ),
    ]
    for check_access in denied_access_checks:
        with pytest.raises(HTTPException) as error:
            check_access()
        assert error.value.status_code == 404

    assert database.get(Organization, organization.id).deleted_at is not None
    assert database.get(Project, project.id) is not None
    stored_work_item = database.get(WorkItem, work_item.id)
    assert stored_work_item is not None
    assert stored_work_item.deleted_at is None
    assert database.get(OrganizationMember, (organization.id, user.id)) is not None
    assert database.get(ProjectMember, (project.id, user.id)) is not None
    assert database.scalar(
        select(func.count())
        .select_from(WorkItemComment)
        .where(WorkItemComment.work_item_id == work_item.id)
    ) == 1
    assert database.scalar(
        select(func.count())
        .select_from(WorkItemAttachment)
        .where(WorkItemAttachment.work_item_id == work_item.id)
    ) == 1
    assert database.scalar(
        select(func.count())
        .select_from(WorkItemTag)
        .where(WorkItemTag.work_item_id == work_item.id)
    ) == 1
    assert database.scalar(
        select(func.count())
        .select_from(WorkItemHistory)
        .where(WorkItemHistory.work_item_id == work_item.id)
    ) == 1


def test_my_work_items_only_returns_assigned_active_tasks_in_accessible_projects(
    access_database,
):
    user, project, own_item = create_project_access_records(
        access_database,
        organization=False,
    )
    own_item.assigned_to_id = user.id
    other_user = User(
        username="other-user",
        email="other-user@example.test",
        password_hash="unused",
        display_name="Other User",
    )
    access_database.add(other_user)
    access_database.flush()

    issue = add_assigned_task(
        access_database, project, user, title="Issue", type="issue"
    )
    add_assigned_task(
        access_database,
        project,
        user,
        title="Assigned elsewhere",
        assigned_to_id=other_user.id,
    )

    inaccessible_project = Project(
        name="No project membership",
        owner_id=user.id,
    )
    archived_project = Project(
        name="Archived project",
        owner_id=user.id,
        archived_at=datetime.now(timezone.utc),
    )
    deleted_project = Project(
        name="Deleted project",
        owner_id=user.id,
        deleted_at=datetime.now(timezone.utc),
    )
    access_database.add_all(
        [inaccessible_project, archived_project, deleted_project]
    )
    access_database.flush()
    access_database.add_all(
        [
            ProjectMember(
                project_id=archived_project.id,
                user_id=user.id,
                role="member",
            ),
            ProjectMember(
                project_id=deleted_project.id,
                user_id=user.id,
                role="member",
            ),
        ]
    )
    inaccessible_item = add_assigned_task(
        access_database,
        inaccessible_project,
        user,
        title="No project access",
    )
    archived_item = add_assigned_task(
        access_database, archived_project, user, title="Archived task"
    )
    deleted_project_item = add_assigned_task(
        access_database, deleted_project, user, title="Deleted project task"
    )
    deleted_task = add_assigned_task(
        access_database,
        project,
        user,
        title="Deleted task",
        deleted_at=datetime.now(timezone.utc),
    )
    access_database.commit()

    result = user_work_items.list_my_work_items(
        db=access_database,
        current_user=user,
    )

    assert [item.id for item in result] == [own_item.id]
    assert result[0].type == "task"
    assert result[0].project_id == project.id
    assert result[0].project_name == project.name
    assert result[0].organization_id is None
    assert result[0].organization_name is None
    assert issue.id not in {item.id for item in result}
    assert inaccessible_item.id not in {item.id for item in result}
    assert archived_item.id not in {item.id for item in result}
    assert deleted_project_item.id not in {item.id for item in result}
    assert deleted_task.id not in {item.id for item in result}


def test_my_work_items_requires_project_and_organization_membership(
    access_database,
):
    user, _, _ = create_project_access_records(
        access_database,
        organization=False,
    )
    accessible_org = Organization(
        name="Accessible organization",
        slug="accessible-organization",
        owner_id=user.id,
    )
    organization_only = Organization(
        name="Organization only",
        slug="organization-only",
        owner_id=user.id,
    )
    project_only_org = Organization(
        name="Project membership only",
        slug="project-membership-only",
        owner_id=user.id,
    )
    access_database.add_all(
        [accessible_org, organization_only, project_only_org]
    )
    access_database.flush()
    access_database.add_all(
        [
            OrganizationMember(
                organization_id=accessible_org.id,
                user_id=user.id,
                role="member",
            ),
            OrganizationMember(
                organization_id=organization_only.id,
                user_id=user.id,
                role="member",
            ),
        ]
    )
    accessible_project = Project(
        name="Accessible organization project",
        organization_id=accessible_org.id,
        owner_id=user.id,
    )
    organization_only_project = Project(
        name="No project membership",
        organization_id=organization_only.id,
        owner_id=user.id,
    )
    project_only = Project(
        name="No organization membership",
        organization_id=project_only_org.id,
        owner_id=user.id,
    )
    access_database.add_all(
        [accessible_project, organization_only_project, project_only]
    )
    access_database.flush()
    access_database.add_all(
        [
            ProjectMember(
                project_id=accessible_project.id,
                user_id=user.id,
                role="member",
            ),
            ProjectMember(
                project_id=project_only.id,
                user_id=user.id,
                role="member",
            ),
        ]
    )
    accessible_item = add_assigned_task(
        access_database, accessible_project, user
    )
    organization_only_item = add_assigned_task(
        access_database, organization_only_project, user
    )
    project_only_item = add_assigned_task(
        access_database, project_only, user
    )
    access_database.commit()

    result = user_work_items.list_my_work_items(
        db=access_database,
        current_user=user,
    )

    assert [item.id for item in result] == [accessible_item.id]
    assert result[0].project_name == accessible_project.name
    assert result[0].organization_id == accessible_org.id
    assert result[0].organization_name == accessible_org.name
    assert organization_only_item.id not in {item.id for item in result}
    assert project_only_item.id not in {item.id for item in result}


def test_my_work_items_excludes_projects_in_deleted_organizations(access_database):
    user, project, _ = create_project_access_records(
        access_database,
        organization=True,
    )
    deleted_organization = access_database.get(
        Organization, project.organization_id
    )
    work_item = add_assigned_task(access_database, project, user)
    deleted_organization.deleted_at = datetime.now(timezone.utc)
    access_database.commit()

    result = user_work_items.list_my_work_items(
        db=access_database,
        current_user=user,
    )

    assert result == []
    assert access_database.get(WorkItem, work_item.id) is not None
    assert access_database.get(Project, project.id) is not None
    assert access_database.get(Organization, deleted_organization.id) is not None


def test_my_work_items_filters_dates_and_orders_by_urgency(access_database):
    user, personal_project, _ = create_project_access_records(
        access_database,
        organization=False,
    )
    today = datetime.now(timezone.utc).date()
    baseline = today + timedelta(days=10)
    personal_early = add_assigned_task(
        access_database,
        personal_project,
        user,
        title="Early",
        status="open",
        priority="high",
        due_date=baseline,
    )
    personal_late = add_assigned_task(
        access_database,
        personal_project,
        user,
        title="Later",
        status="in_progress",
        priority="medium",
        due_date=baseline + timedelta(days=1),
    )
    organization = Organization(
        name="Filter organization",
        slug="filter-organization",
        owner_id=user.id,
    )
    access_database.add(organization)
    access_database.flush()
    access_database.add(
        OrganizationMember(
            organization_id=organization.id,
            user_id=user.id,
            role="member",
        )
    )
    organization_project = Project(
        name="Organization project",
        organization_id=organization.id,
        owner_id=user.id,
    )
    access_database.add(organization_project)
    access_database.flush()
    access_database.add(
        ProjectMember(
            project_id=organization_project.id,
            user_id=user.id,
            role="member",
        )
    )
    organization_task = add_assigned_task(
        access_database,
        organization_project,
        user,
        title="Organization task",
        status="open",
        priority="high",
        due_date=baseline + timedelta(days=2),
    )
    access_database.commit()

    base_args = {"db": access_database, "current_user": user}
    assert {
        task.id
        for task in user_work_items.list_my_work_items(
            status_filter="open", **base_args
        )
    } == {personal_early.id, organization_task.id}
    assert [
        task.id
        for task in user_work_items.list_my_work_items(
            priority_filter="medium", **base_args
        )
    ] == [personal_late.id]
    assert [
        task.id
        for task in user_work_items.list_my_work_items(
            project_id=organization_project.id, **base_args
        )
    ] == [organization_task.id]
    assert [
        task.id
        for task in user_work_items.list_my_work_items(
            organization_id=organization.id, **base_args
        )
    ] == [organization_task.id]
    assert {
        task.id
        for task in user_work_items.list_my_work_items(
            due_date_to=(baseline + timedelta(days=1)).isoformat(),
            **base_args,
        )
    } == {personal_early.id, personal_late.id}
    assert {
        task.id
        for task in user_work_items.list_my_work_items(
            due_date_from=baseline.isoformat(), **base_args
        )
    } == {personal_early.id, personal_late.id, organization_task.id}
    assert [
        task.id
        for task in user_work_items.list_my_work_items(
            status_filter="open",
            priority_filter="high",
            project_id=organization_project.id,
            organization_id=organization.id,
            due_date_from=baseline.isoformat(),
            due_date_to=(baseline + timedelta(days=2)).isoformat(),
            **base_args,
        )
    ] == [organization_task.id]


def test_my_work_items_sorts_overdue_before_upcoming_and_undated(
    access_database,
):
    user, project, _ = create_project_access_records(
        access_database,
        organization=False,
    )
    today = datetime.now(timezone.utc).date()
    closest_overdue = add_assigned_task(
        access_database,
        project,
        user,
        title="Yesterday",
        due_date=today - timedelta(days=1),
    )
    older_overdue = add_assigned_task(
        access_database,
        project,
        user,
        title="Older overdue",
        due_date=today - timedelta(days=10),
    )
    upcoming = add_assigned_task(
        access_database,
        project,
        user,
        title="Tomorrow",
        due_date=today + timedelta(days=1),
    )
    undated = add_assigned_task(
        access_database,
        project,
        user,
        title="No due date",
        due_date=None,
    )
    completed_past_due = add_assigned_task(
        access_database,
        project,
        user,
        title="Completed",
        status="closed",
        due_date=today - timedelta(days=2),
    )
    resolved_past_due = add_assigned_task(
        access_database,
        project,
        user,
        title="Resolved",
        status="resolved",
        due_date=today - timedelta(days=3),
    )
    access_database.commit()

    result = user_work_items.list_my_work_items(
        db=access_database,
        current_user=user,
    )

    assert [task.id for task in result] == [
        closest_overdue.id,
        older_overdue.id,
        resolved_past_due.id,
        completed_past_due.id,
        upcoming.id,
        undated.id,
    ]


@pytest.mark.parametrize("organization", [False, True])
def test_project_member_cannot_delete_work_item_without_manager_role(
    access_database,
    organization,
):
    user, project, work_item = create_project_access_records(
        access_database,
        organization=organization,
        project_role="member",
    )

    with pytest.raises(HTTPException) as error:
        work_items.delete_work_item(
            project_id=project.id,
            work_item_id=work_item.id,
            db=access_database,
            current_user=user,
        )

    assert error.value.status_code == 403
    assert access_database.scalar(
        select(func.count())
        .select_from(WorkItem)
        .where(WorkItem.id == work_item.id)
    ) == 1


def test_logical_delete_preserves_work_item_relations_and_records_history(
    foreign_key_access_database,
):
    user, project, work_item = create_project_access_records(
        foreign_key_access_database,
        organization=False,
        project_role="owner",
    )
    add_work_item_relations(
        foreign_key_access_database, user, project, work_item
    )
    assert foreign_key_access_database.connection().exec_driver_sql(
        "PRAGMA foreign_keys"
    ).scalar_one() == 1

    work_items.delete_work_item(
        project_id=project.id,
        work_item_id=work_item.id,
        db=foreign_key_access_database,
        current_user=user,
    )

    stored_item = foreign_key_access_database.get(WorkItem, work_item.id)
    assert stored_item is not None
    assert stored_item.deleted_at is not None
    history = foreign_key_access_database.scalars(
        select(WorkItemHistory).where(
            WorkItemHistory.work_item_id == work_item.id
        )
    ).all()
    assert len(history) == 1
    assert history[0].changed_by_id == user.id
    assert history[0].field_name == "deleted"
    assert history[0].old_value is None
    recorded_deleted_at = datetime.fromisoformat(history[0].new_value)
    assert recorded_deleted_at.replace(tzinfo=None) == stored_item.deleted_at.replace(
        tzinfo=None
    )
    assert foreign_key_access_database.scalar(
        select(func.count())
        .select_from(WorkItemComment)
        .where(WorkItemComment.work_item_id == work_item.id)
    ) == 1
    assert foreign_key_access_database.scalar(
        select(func.count())
        .select_from(WorkItemAttachment)
        .where(WorkItemAttachment.work_item_id == work_item.id)
    ) == 1
    assert foreign_key_access_database.scalar(
        select(func.count())
        .select_from(WorkItemTag)
        .where(WorkItemTag.work_item_id == work_item.id)
    ) == 1


def test_logical_delete_rolls_back_when_history_insert_fails(
    foreign_key_access_database,
):
    database = foreign_key_access_database
    user, project, work_item = create_project_access_records(
        database,
        organization=False,
        project_role="owner",
    )
    add_work_item_relations(database, user, project, work_item)
    assert database.connection().exec_driver_sql(
        "PRAGMA foreign_keys"
    ).scalar_one() == 1

    def invalidate_history_actor(session, _flush_context, _instances):
        history_events = [
            value
            for value in session.new
            if isinstance(value, WorkItemHistory)
        ]
        for history_event in history_events:
            history_event.changed_by_id = -1

    event.listen(database, "before_flush", invalidate_history_actor)
    try:
        with pytest.raises(IntegrityError) as error:
            work_items.delete_work_item(
                project_id=project.id,
                work_item_id=work_item.id,
                db=database,
                current_user=user,
            )
    finally:
        event.remove(database, "before_flush", invalidate_history_actor)

    assert "INSERT INTO work_item_history" in error.value.statement
    assert "FOREIGN KEY constraint failed" in str(error.value.orig)
    assert database.is_active
    database.expire_all()
    stored_item = database.get(WorkItem, work_item.id)
    assert stored_item is not None
    assert stored_item.deleted_at is None
    assert database.scalar(
        select(func.count())
        .select_from(WorkItemHistory)
        .where(WorkItemHistory.work_item_id == work_item.id)
    ) == 0
    assert database.scalar(
        select(func.count())
        .select_from(WorkItemComment)
        .where(WorkItemComment.work_item_id == work_item.id)
    ) == 1
    assert database.scalar(
        select(func.count())
        .select_from(WorkItemAttachment)
        .where(WorkItemAttachment.work_item_id == work_item.id)
    ) == 1
    assert database.scalar(
        select(func.count())
        .select_from(WorkItemTag)
        .where(WorkItemTag.work_item_id == work_item.id)
    ) == 1


def test_logical_delete_rolls_back_when_commit_fails(access_database):
    user, project, work_item = create_project_access_records(
        access_database,
        organization=False,
        project_role="owner",
    )

    def fail_commit(_session):
        raise RuntimeError("commit failed")

    event.listen(access_database, "before_commit", fail_commit)
    try:
        with pytest.raises(RuntimeError, match="commit failed"):
            work_items.delete_work_item(
                project_id=project.id,
                work_item_id=work_item.id,
                db=access_database,
                current_user=user,
            )
    finally:
        event.remove(access_database, "before_commit", fail_commit)

    access_database.expire_all()
    assert access_database.get(WorkItem, work_item.id).deleted_at is None
    assert access_database.scalar(
        select(func.count())
        .select_from(WorkItemHistory)
        .where(WorkItemHistory.work_item_id == work_item.id)
    ) == 0


def test_repeated_logical_delete_returns_404_without_duplicate_history(
    access_database,
):
    user, project, work_item = create_project_access_records(
        access_database,
        organization=False,
        project_role="owner",
    )
    work_items.delete_work_item(
        project_id=project.id,
        work_item_id=work_item.id,
        db=access_database,
        current_user=user,
    )

    with pytest.raises(HTTPException) as error:
        work_items.delete_work_item(
            project_id=project.id,
            work_item_id=work_item.id,
            db=access_database,
            current_user=user,
        )

    assert error.value.status_code == 404
    assert access_database.scalar(
        select(func.count())
        .select_from(WorkItemHistory)
        .where(WorkItemHistory.work_item_id == work_item.id)
    ) == 1


def test_delete_with_lost_active_row_race_returns_404_without_history():
    database = make_database(project_role="owner")
    database.execute.return_value.rowcount = 0
    user = SimpleNamespace(id=USER_ID)

    with pytest.raises(HTTPException) as error:
        work_items.delete_work_item(
            project_id=PROJECT_ID,
            work_item_id=WORK_ITEM_ID,
            db=database,
            current_user=user,
        )

    assert error.value.status_code == 404
    database.add.assert_not_called()
    database.commit.assert_not_called()
    database.rollback.assert_called_once()


def test_deleted_work_items_are_hidden_from_list_and_rejected_by_id(
    access_database,
):
    user, project, deleted_item = create_project_access_records(
        access_database,
        organization=False,
        project_role="owner",
    )
    active_item = WorkItem(
        project_id=project.id,
        created_by_id=user.id,
        title="Still active",
    )
    access_database.add(active_item)
    access_database.commit()
    work_items.delete_work_item(
        project_id=project.id,
        work_item_id=deleted_item.id,
        db=access_database,
        current_user=user,
    )

    listed = work_items.list_work_items(
        project_id=project.id,
        db=access_database,
        current_user=user,
    )
    assert [item.id for item in listed] == [active_item.id]

    with pytest.raises(HTTPException) as get_error:
        work_items.get_work_item(
            project_id=project.id,
            work_item_id=deleted_item.id,
            db=access_database,
            current_user=user,
        )
    assert get_error.value.status_code == 404

    with pytest.raises(HTTPException) as update_error:
        work_items.update_work_item(
            project_id=project.id,
            work_item_id=deleted_item.id,
            item_data=WorkItemUpdate(description="Should not update"),
            db=access_database,
            current_user=user,
        )
    assert update_error.value.status_code == 404


def test_deleted_work_item_blocks_related_resource_operations(access_database):
    user, project, work_item = create_project_access_records(
        access_database,
        organization=False,
        project_role="owner",
    )
    work_items.delete_work_item(
        project_id=project.id,
        work_item_id=work_item.id,
        db=access_database,
        current_user=user,
    )

    operations = [
        lambda: work_item_comments.create_comment(
            work_item_id=work_item.id,
            data=WorkItemCommentCreate(content="blocked"),
            db=access_database,
            user=user,
        ),
        lambda: work_item_comments.list_comments(
            work_item_id=work_item.id, db=access_database, user=user
        ),
        lambda: work_item_comments.update_comment(
            work_item_id=work_item.id,
            comment_id=1,
            data=work_item_comments.WorkItemCommentUpdate(content="blocked"),
            db=access_database,
            user=user,
        ),
        lambda: work_item_comments.delete_comment(
            work_item_id=work_item.id,
            comment_id=1,
            db=access_database,
            user=user,
        ),
        lambda: work_item_attachments.list_attachments(
            work_item_id=work_item.id,
            db=access_database,
            current_user=user,
        ),
        lambda: work_item_attachments.upload_attachment(
            work_item_id=work_item.id,
            file=UploadFile(filename="blocked.txt", file=BytesIO(b"data")),
            db=access_database,
            current_user=user,
        ),
        lambda: work_item_attachments.download_attachment(
            work_item_id=work_item.id,
            attachment_id=1,
            db=access_database,
            current_user=user,
        ),
        lambda: work_item_attachments.delete_attachment(
            work_item_id=work_item.id,
            attachment_id=1,
            db=access_database,
            current_user=user,
        ),
        lambda: work_item_tags.list_work_item_tags(
            work_item_id=work_item.id, db=access_database, user=user
        ),
        lambda: work_item_tags.add_tag_to_work_item(
            work_item_id=work_item.id,
            data=WorkItemTagCreate(tag_id=1),
            db=access_database,
            user=user,
        ),
        lambda: work_item_tags.remove_tag_from_work_item(
            work_item_id=work_item.id,
            tag_id=1,
            db=access_database,
            user=user,
        ),
    ]

    for operation in operations:
        with pytest.raises(HTTPException) as error:
            invoke(operation)
        assert error.value.status_code == 404


@pytest.mark.parametrize("organization", [False, True])
@pytest.mark.parametrize("role", ["owner", "admin"])
def test_logical_delete_preserves_personal_and_organization_permissions(
    access_database,
    organization,
    role,
):
    user, project, work_item = create_project_access_records(
        access_database,
        organization=organization,
        project_role=role,
    )

    work_items.delete_work_item(
        project_id=project.id,
        work_item_id=work_item.id,
        db=access_database,
        current_user=user,
    )

    assert access_database.get(WorkItem, work_item.id).deleted_at is not None


@pytest.mark.parametrize("organization", [False, True])
def test_deleted_work_item_history_remains_readable_to_project_members(
    access_database,
    organization,
):
    user, project, work_item = create_project_access_records(
        access_database,
        organization=organization,
        project_role="owner",
    )
    work_items.delete_work_item(
        project_id=project.id,
        work_item_id=work_item.id,
        db=access_database,
        current_user=user,
    )

    history = work_item_history.list_work_item_history(
        work_item_id=work_item.id,
        db=access_database,
        user=user,
    )
    assert len(history) == 1
    assert history[0].field_name == "deleted"

    other_user = User(
        username="outsider",
        email="outsider@example.test",
        password_hash="unused",
        display_name="Outsider",
    )
    access_database.add(other_user)
    access_database.commit()
    with pytest.raises(HTTPException) as item_error:
        work_items.get_work_item(
            project_id=project.id,
            work_item_id=work_item.id,
            db=access_database,
            current_user=other_user,
        )
    assert item_error.value.status_code == 403

    with pytest.raises(HTTPException) as error:
        work_item_history.list_work_item_history(
            work_item_id=work_item.id,
            db=access_database,
            user=other_user,
        )
    assert error.value.status_code == 403


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


def test_my_issues_returns_assignee_name_and_keeps_unassigned_issues(access_database):
    user, project, _ = create_project_access_records(
        access_database,
        organization=False,
    )
    assigned = add_assigned_task(
        access_database,
        project,
        user,
        title="Assigned issue",
        type="issue",
        description="Issue details",
        priority="urgent",
    )
    unassigned = add_assigned_task(
        access_database,
        project,
        user,
        title="Unassigned issue",
        type="issue",
        assigned_to_id=None,
    )
    access_database.commit()

    result = user_work_items.list_my_issues(
        db=access_database,
        current_user=user,
        assignee_id=None,
        unassigned=False,
    )
    by_id = {issue.id: issue for issue in result}

    assert set(by_id) == {assigned.id, unassigned.id}
    assert by_id[assigned.id].assignee_id == user.id
    assert by_id[assigned.id].assignee_display_name == user.display_name
    assert by_id[unassigned.id].assignee_id is None
    assert by_id[unassigned.id].assignee_display_name is None
    assert by_id[assigned.id].type == "issue"
    assert by_id[assigned.id].project_name == project.name
    assert "email" not in by_id[assigned.id].model_dump()
    assert "bio" not in by_id[assigned.id].model_dump()


@pytest.mark.parametrize("organization", [False, True])
def test_my_issues_allows_members_of_personal_and_organization_projects(
    access_database,
    organization,
):
    user, project, _ = create_project_access_records(
        access_database,
        organization=organization,
    )
    issue = add_assigned_task(
        access_database, project, user, type="issue", title="Visible issue"
    )
    access_database.commit()

    result = user_work_items.list_my_issues(
        db=access_database,
        current_user=user,
        assignee_id=None,
        unassigned=False,
    )

    assert [item.id for item in result] == [issue.id]
    assert result[0].organization_id == (
        project.organization_id if organization else None
    )


def test_my_issues_requires_both_organization_and_project_membership(
    access_database,
):
    user, _, _ = create_project_access_records(
        access_database,
        organization=False,
    )
    project_only_organization = Organization(
        name="Project only organization",
        slug="project-only-organization",
        owner_id=user.id,
    )
    organization_only = Organization(
        name="Organization only",
        slug="organization-only",
        owner_id=user.id,
    )
    access_database.add_all([project_only_organization, organization_only])
    access_database.flush()
    project_only = Project(
        name="Project membership only",
        organization_id=project_only_organization.id,
        owner_id=user.id,
    )
    organization_only_project = Project(
        name="Organization membership only",
        organization_id=organization_only.id,
        owner_id=user.id,
    )
    access_database.add_all([project_only, organization_only_project])
    access_database.flush()
    access_database.add_all(
        [
            ProjectMember(
                project_id=project_only.id, user_id=user.id, role="member"
            ),
            OrganizationMember(
                organization_id=organization_only.id,
                user_id=user.id,
                role="member",
            ),
        ]
    )
    project_only_issue = add_assigned_task(
        access_database, project_only, user, type="issue"
    )
    organization_only_issue = add_assigned_task(
        access_database, organization_only_project, user, type="issue"
    )
    access_database.commit()

    result = user_work_items.list_my_issues(
        db=access_database,
        current_user=user,
        assignee_id=None,
        unassigned=False,
    )

    assert result == []
    assert access_database.get(WorkItem, project_only_issue.id) is not None
    assert access_database.get(WorkItem, organization_only_issue.id) is not None


def test_my_issues_excludes_archived_deleted_projects_and_deleted_organizations(
    access_database,
):
    user, _, _ = create_project_access_records(
        access_database, organization=False
    )
    organization = Organization(
        name="Deleted issue organization",
        slug="deleted-issue-organization",
        owner_id=user.id,
        deleted_at=datetime.now(timezone.utc),
    )
    access_database.add(organization)
    access_database.flush()
    deleted_org_project = Project(
        name="Deleted organization project",
        organization_id=organization.id,
        owner_id=user.id,
    )
    archived_project = Project(
        name="Archived issue project",
        owner_id=user.id,
        archived_at=datetime.now(timezone.utc),
    )
    deleted_project = Project(
        name="Deleted issue project",
        owner_id=user.id,
        deleted_at=datetime.now(timezone.utc),
    )
    access_database.add_all(
        [deleted_org_project, archived_project, deleted_project]
    )
    access_database.flush()
    access_database.add_all(
        [
            ProjectMember(
                project_id=deleted_org_project.id,
                user_id=user.id,
                role="member",
            ),
            ProjectMember(
                project_id=archived_project.id,
                user_id=user.id,
                role="member",
            ),
            ProjectMember(
                project_id=deleted_project.id,
                user_id=user.id,
                role="member",
            ),
            OrganizationMember(
                organization_id=organization.id,
                user_id=user.id,
                role="member",
            ),
        ]
    )
    issues = [
        add_assigned_task(
            access_database, project, user, title=project.name, type="issue"
        )
        for project in [deleted_org_project, archived_project, deleted_project]
    ]
    access_database.commit()

    result = user_work_items.list_my_issues(
        db=access_database,
        current_user=user,
        assignee_id=None,
        unassigned=False,
    )

    assert result == []
    assert all(access_database.get(WorkItem, issue.id) is not None for issue in issues)


def test_my_issues_uses_one_query_for_project_assignee_and_organization_data(
    access_database,
):
    user, project, _ = create_project_access_records(
        access_database, organization=False
    )
    add_assigned_task(
        access_database, project, user, type="issue", title="Issue"
    )
    access_database.commit()
    access_database.refresh(user)
    statements = []

    def count_query(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    engine = access_database.get_bind()
    event.listen(engine, "before_cursor_execute", count_query)
    try:
        result = user_work_items.list_my_issues(
            db=access_database,
            current_user=user,
            assignee_id=None,
            unassigned=False,
        )
    finally:
        event.remove(engine, "before_cursor_execute", count_query)

    assert len(result) == 1
    assert len(statements) == 1


def test_my_issues_filters_and_sorts_with_stable_id_tiebreak(access_database):
    user, project, _ = create_project_access_records(
        access_database,
        organization=False,
    )
    low = add_assigned_task(
        access_database,
        project,
        user,
        title="Low",
        type="issue",
        priority="low",
        status="open",
    )
    urgent_one = add_assigned_task(
        access_database,
        project,
        user,
        title="Urgent one",
        type="issue",
        priority="urgent",
        status="open",
    )
    urgent_two = add_assigned_task(
        access_database,
        project,
        user,
        title="Urgent two",
        type="issue",
        priority="urgent",
        status="closed",
    )
    unassigned = add_assigned_task(
        access_database,
        project,
        user,
        title="Unassigned",
        type="issue",
        assigned_to_id=None,
        priority="high",
        status="open",
    )
    task = add_assigned_task(
        access_database, project, user, title="Task excluded", type="task"
    )
    deleted = add_assigned_task(
        access_database,
        project,
        user,
        title="Deleted issue",
        type="issue",
        deleted_at=datetime.now(timezone.utc),
    )
    access_database.commit()
    arguments = {
        "db": access_database,
        "current_user": user,
        "assignee_id": None,
        "unassigned": False,
    }

    default_order = user_work_items.list_my_issues(**arguments)
    assert [item.id for item in default_order] == [
        urgent_one.id,
        urgent_two.id,
        unassigned.id,
        low.id,
    ]
    assert [item.id for item in user_work_items.list_my_issues(
        status_filter="open",
        priority_filter="urgent",
        assignee_id=user.id,
        **{key: value for key, value in arguments.items() if key != "assignee_id"},
    )] == [urgent_one.id]
    assert [item.id for item in user_work_items.list_my_issues(
        unassigned=True,
        **{key: value for key, value in arguments.items() if key != "unassigned"},
    )] == [unassigned.id]
    assert [item.id for item in user_work_items.list_my_issues(
        sort_by="priority",
        sort_order="asc",
        **arguments,
    )] == [low.id, unassigned.id, urgent_one.id, urgent_two.id]
    assert task.id not in {item.id for item in default_order}
    assert deleted.id not in {item.id for item in default_order}


def test_my_issues_can_sort_by_creation_and_update_dates(access_database):
    user, project, _ = create_project_access_records(
        access_database, organization=False
    )
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    older = add_assigned_task(
        access_database,
        project,
        user,
        title="Older issue",
        type="issue",
        created_at=base,
        updated_at=base + timedelta(days=3),
    )
    newer = add_assigned_task(
        access_database,
        project,
        user,
        title="Newer issue",
        type="issue",
        created_at=base + timedelta(days=1),
        updated_at=base + timedelta(days=2),
    )
    access_database.commit()
    common = {
        "db": access_database,
        "current_user": user,
        "assignee_id": None,
        "unassigned": False,
    }

    assert [
        issue.id
        for issue in user_work_items.list_my_issues(
            sort_by="created_at", sort_order="asc", **common
        )
    ] == [older.id, newer.id]
    assert [
        issue.id
        for issue in user_work_items.list_my_issues(
            sort_by="updated_at", sort_order="desc", **common
        )
    ] == [older.id, newer.id]

import asyncio
import inspect
from datetime import datetime
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import IntegrityError
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
    assert (
        work_items.get_work_item(
            project_id=project.id,
            work_item_id=work_item.id,
            db=access_database,
            current_user=user,
        )
        is work_item
    )

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

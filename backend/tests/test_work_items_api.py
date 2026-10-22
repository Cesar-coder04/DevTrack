from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.api.routes import work_item_history, work_items
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.work_item import WorkItem
from app.models.work_item_history import WorkItemHistory
from app.schemas.work_item import (
    WorkItemCreate,
    WorkItemDetailResponse,
    WorkItemListResponse,
    WorkItemResponse,
    WorkItemUpdate,
)
from app.schemas.work_item_history import WorkItemHistoryResponse


def make_work_item(**overrides) -> WorkItem:
    values = {
        "id": 3,
        "project_id": 7,
        "type": "task",
        "created_by_id": 11,
        "assigned_to_id": 13,
        "title": "Task",
        "description": "Description",
        "status": "open",
        "priority": "medium",
        "due_date": date(2026, 10, 15),
        "created_at": datetime(2026, 10, 15, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 10, 15, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return WorkItem(**values)


def test_create_work_item_uses_mapped_fields_and_returns_public_aliases(
    monkeypatch,
):
    monkeypatch.setattr(
        work_items,
        "get_project_access",
        lambda project_id, current_user, db: (Project(id=project_id), None),
    )
    db = MagicMock()
    added = []

    def add(instance):
        added.append(instance)
        if isinstance(instance, WorkItem):
            instance.id = 21

    db.add.side_effect = add
    db.refresh.side_effect = lambda instance: (
        setattr(instance, "created_at", datetime(2026, 10, 15, tzinfo=timezone.utc)),
        setattr(instance, "updated_at", datetime(2026, 10, 15, tzinfo=timezone.utc)),
    )

    item = work_items.create_work_item(
        project_id=7,
        item_data=WorkItemCreate(
            title="New task",
            due_date=datetime(2026, 10, 16, 9, tzinfo=timezone.utc),
        ),
        db=db,
        current_user=SimpleNamespace(id=11),
    )

    assert item.created_by_id == 11
    assert item.assigned_to_id is None
    assert item.due_date == date(2026, 10, 16)
    assert isinstance(added[1], WorkItemHistory)
    assert added[1].changed_by_id == 11

    response = WorkItemResponse.model_validate(item)
    assert response.reporter_id == 11
    assert response.assignee_id is None
    assert response.type == "task"
    assert response.model_dump()["reporter_id"] == 11
    assert "created_by_id" not in response.model_dump()
    assert "assignee_display_name" not in response.model_dump()


def test_list_work_items_filters_by_mapped_assignee_field(monkeypatch):
    monkeypatch.setattr(
        work_items,
        "get_project_access",
        lambda project_id, current_user, db: (Project(id=project_id), None),
    )
    item = make_work_item()
    db = MagicMock()
    db.execute.return_value.all.return_value = [(item, "Visible Assignee")]

    result = work_items.list_work_items(
        project_id=7,
        status_filter="resolved",
        priority_filter="high",
        assignee_id=13,
        db=db,
        current_user=SimpleNamespace(id=11),
    )

    statement = str(db.execute.call_args.args[0])
    assert "work_items.assigned_to_id" in statement
    assert "LEFT OUTER JOIN users" in statement
    assert "users.display_name" in statement
    assert "work_items.status" in statement
    assert "work_items.priority" in statement
    assert "work_items.created_at DESC" in statement
    assert [response.assignee_id for response in result] == [13]
    assert [response.assignee_display_name for response in result] == [
        "Visible Assignee"
    ]
    assert isinstance(result[0], WorkItemListResponse)
    assert result[0].model_dump()["assignee_display_name"] == "Visible Assignee"
    assert "email" not in result[0].model_dump()
    assert "bio" not in result[0].model_dump()
    assert "password_hash" not in result[0].model_dump()


def test_list_work_items_returns_null_assignee_fields_for_unassigned_items(
    monkeypatch,
):
    monkeypatch.setattr(
        work_items,
        "get_project_access",
        lambda project_id, current_user, db: (Project(id=project_id), None),
    )
    assigned_item = make_work_item()
    unassigned_item = make_work_item(
        id=4,
        assigned_to_id=None,
        title="Unassigned task",
    )
    db = MagicMock()
    db.execute.return_value.all.return_value = [
        (assigned_item, "Visible Assignee"),
        (unassigned_item, None),
    ]

    result = work_items.list_work_items(
        project_id=7,
        db=db,
        current_user=SimpleNamespace(id=11),
    )

    assert len(result) == 2
    assert [(item.assignee_id, item.assignee_display_name) for item in result] == [
        (13, "Visible Assignee"),
        (None, None),
    ]


def test_project_work_item_type_filter_is_optional_and_additive(monkeypatch):
    monkeypatch.setattr(
        work_items,
        "get_project_access",
        lambda project_id, current_user, db: (Project(id=project_id), None),
    )
    task = make_work_item(type="task")
    issue = make_work_item(id=4, type="issue", title="Issue")
    db = MagicMock()
    db.execute.return_value.all.return_value = [
        (task, "Assignee"),
        (issue, "Assignee"),
    ]

    unfiltered = work_items.list_work_items(
        project_id=7,
        db=db,
        current_user=SimpleNamespace(id=11),
    )
    assert [item.type for item in unfiltered] == ["task", "issue"]
    assert "work_items.type =" not in str(db.execute.call_args.args[0])

    db.execute.return_value.all.return_value = [(task, "Assignee")]
    tasks_only = work_items.list_work_items(
        project_id=7,
        type_filter="task",
        db=db,
        current_user=SimpleNamespace(id=11),
    )
    assert "work_items.type =" in str(db.execute.call_args.args[0])
    assert [item.type for item in tasks_only] == ["task"]


def test_update_work_item_supports_partial_updates_and_public_assignee_field(
    monkeypatch,
):
    monkeypatch.setattr(
        work_items,
        "get_project_access",
        lambda project_id, current_user, db: (Project(id=project_id), None),
    )
    checked_assignees = []
    monkeypatch.setattr(
        work_items,
        "check_assignee",
        lambda project_id, assignee_id, project, db: checked_assignees.append(
            assignee_id
        ),
    )

    item = make_work_item()
    db = MagicMock()
    db.get.return_value = item

    updated = work_items.update_work_item(
        project_id=7,
        work_item_id=3,
        item_data=WorkItemUpdate(description="Changed"),
        db=db,
        current_user=SimpleNamespace(id=11),
    )

    assert updated.description == "Changed"
    assert updated.title == "Task"
    assert updated.assigned_to_id == 13
    assert checked_assignees == [13]

    assigned = work_items.update_work_item(
        project_id=7,
        work_item_id=3,
        item_data=WorkItemUpdate(assignee_id=17),
        db=db,
        current_user=SimpleNamespace(id=11),
    )

    assert checked_assignees[-1] == 17
    assert assigned.assigned_to_id == 17
    assert "assignee_display_name" not in WorkItemResponse.model_validate(
        assigned
    ).model_dump()
    assert isinstance(db.add.call_args.args[0], WorkItemHistory)
    assert db.add.call_args.args[0].changed_by_id == 11

    due_date_updated = work_items.update_work_item(
        project_id=7,
        work_item_id=3,
        item_data=WorkItemUpdate(
            due_date=datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
        ),
        db=db,
        current_user=SimpleNamespace(id=11),
    )

    assert due_date_updated.due_date == date(2026, 10, 20)


def test_get_work_item_detail_includes_only_visible_project_and_assignee_names(
    monkeypatch,
):
    monkeypatch.setattr(
        work_items,
        "get_project_access",
        lambda project_id, current_user, db: (Project(id=project_id), None),
    )
    item = make_work_item()
    db = MagicMock()
    db.execute.return_value.one_or_none.return_value = (
        item,
        "Visible Assignee",
        "Project name",
        None,
        None,
    )

    result = work_items.get_work_item(
        project_id=7,
        work_item_id=item.id,
        db=db,
        current_user=SimpleNamespace(id=11),
    )

    response = WorkItemDetailResponse.model_validate(result)
    assert response.assignee_display_name == "Visible Assignee"
    assert response.project_name == "Project name"
    assert response.organization_name is None
    assert "email" not in response.model_dump()
    assert "bio" not in response.model_dump()
    assert "password_hash" not in response.model_dump()


def test_non_list_work_item_endpoints_keep_the_base_response_schema():
    response_models = {
        route.endpoint: route.response_model
        for route in work_items.router.routes
    }

    assert response_models[work_items.create_work_item] is WorkItemResponse
    assert response_models[work_items.update_work_item] is WorkItemResponse
    assert response_models[work_items.get_work_item] is WorkItemDetailResponse
    assert response_models[work_items.list_work_items] == list[WorkItemListResponse]


@pytest.mark.parametrize(
    "status",
    ["open", "in_progress", "resolved", "closed"],
)
def test_work_item_schemas_accept_valid_statuses(status):
    assert WorkItemCreate(title="Task", status=status).status == status
    assert WorkItemUpdate(status=status).status == status


@pytest.mark.parametrize(
    "status",
    ["todo", "in_review", "done", "cancelled", "unknown"],
)
def test_work_item_schemas_reject_invalid_statuses(status):
    with pytest.raises(ValidationError):
        WorkItemCreate(title="Task", status=status)

    with pytest.raises(ValidationError):
        WorkItemUpdate(status=status)


def test_work_item_create_defaults_to_open_and_update_rejects_null_required_fields():
    assert WorkItemCreate(title="Task").status == "open"
    assert WorkItemUpdate(description="Optional update").description == (
        "Optional update"
    )
    assert WorkItemUpdate(description=None).description is None
    assert WorkItemUpdate(assignee_id=None).assignee_id is None
    assert WorkItemUpdate(due_date=None).due_date is None

    for field in ("title", "status", "priority"):
        with pytest.raises(ValidationError):
            WorkItemUpdate(**{field: None})


def test_list_work_item_history_orders_by_changed_at_and_maps_response():
    item = make_work_item()
    history = WorkItemHistory(
        id=9,
        work_item_id=item.id,
        changed_by_id=11,
        field_name="status",
        old_value="open",
        new_value="resolved",
        changed_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
    )
    db = MagicMock()
    db.get.side_effect = lambda model, key: {
        WorkItem: item,
        Project: Project(id=item.project_id),
        ProjectMember: ProjectMember(project_id=item.project_id, user_id=11),
    }[model]
    db.scalars.return_value.all.return_value = [history]

    result = work_item_history.list_work_item_history(
        work_item_id=item.id,
        db=db,
        user=SimpleNamespace(id=11),
    )

    statement = str(db.scalars.call_args.args[0])
    assert "work_item_history.changed_at DESC" in statement
    response = WorkItemHistoryResponse.model_validate(result[0])
    assert response.user_id == 11
    assert response.created_at == history.changed_at
    assert response.model_dump()["user_id"] == 11
    assert "changed_by_id" not in response.model_dump()

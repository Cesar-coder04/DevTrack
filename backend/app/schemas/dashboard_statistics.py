from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


Coverage = Literal["reliable", "partial", "unavailable"]


class StatisticsCoverage(BaseModel):
    state_and_cycles: Coverage
    assignments: Coverage
    completions: Coverage
    due_date_snapshots: Coverage


class StatisticsWarning(BaseModel):
    code: str
    message: str


class QuarterlyLoad(BaseModel):
    carried_in: int | None
    new_cycles: int | None


class WeeklyStatisticsPoint(BaseModel):
    week_start: date
    week_end: date
    completed_cumulative: int | None
    pending_at_cut: int | None
    required_cumulative: float | None
    required_per_week: float | None
    coverage: Coverage


class QuarterlyStatisticsResponse(BaseModel):
    year: int
    quarter: int
    timezone: str
    period_start: date
    period_end_exclusive: date
    as_of: datetime
    period_complete: bool
    scope: str
    organization_id: int | None = None
    project_id: int | None = None
    total_cycles: int | None
    completed_cycles: int | None
    pending_at_close: int | None
    completed_on_time_percent: float | None
    punctuality_comparable_count: int | None
    completed_with_known_assignee: int | None
    completed_unassigned: int | None
    completed_assignee_unknown: int | None
    pending_with_known_assignee: int | None
    pending_unassigned: int | None
    pending_assignee_unknown: int | None
    load: QuarterlyLoad
    coverage: StatisticsCoverage
    warnings: list[StatisticsWarning]
    weekly: list[WeeklyStatisticsPoint]

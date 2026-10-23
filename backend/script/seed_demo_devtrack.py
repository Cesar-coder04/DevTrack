"""
Carga de datos ficticios para DevTrack.
Uso desde backend:
    python scripts/seed_demo.py                 # simulación, sin escrituras
    python scripts/seed_demo.py --apply         # inserta los datos de demostración

La carga solo inserta filas. Si ya existe la organización demo, no hace nada.
Si encuentra usuarios demo sueltos sin la organización, aborta para evitar conflictos.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import sys

# Permite ejecutar el script desde backend/scripts o desde backend.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import User
from app.models.organization import Organization
from app.models.organization_member import OrganizationMember
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.work_item import WorkItem
from app.models.work_item_history import WorkItemHistory
from app.models.work_item_assignment_baseline import WorkItemAssignmentBaseline
from app.models.work_item_completion_coverage import WorkItemCompletionCoverage
from app.models.work_item_completion import WorkItemCompletion


ORG_NAME = "NovaTech Solutions (Demo)"
ORG_SLUG = "novatech-solutions-demo-2026"
DEMO_PASSWORD = "Demo2026!DevTrack"

USER_SPECS = [
    ("demo_nova_owner", "nova.owner@example.test", "Alex Moreno", "owner"),
    ("demo_nova_admin", "nova.admin@example.test", "Lucía Martín", "admin"),
    ("demo_nova_dev1", "nova.dev1@example.test", "Daniel Ruiz", "member"),
    ("demo_nova_dev2", "nova.dev2@example.test", "Marta Sánchez", "member"),
    ("demo_nova_qa", "nova.qa@example.test", "Pablo Torres", "member"),
    ("demo_nova_pm", "nova.pm@example.test", "Elena García", "member"),
]

PROJECT_SPECS = [
    ("Portal de clientes", "Portal web y área privada de clientes."),
    ("Aplicación móvil", "Aplicación móvil para clientes y operaciones."),
    ("Plataforma interna", "Herramientas internas y automatización."),
    ("Infraestructura y calidad", "Despliegues, observabilidad y control de calidad."),
]

TASK_TITLES = [
    "Definir requisitos funcionales", "Preparar entorno de desarrollo",
    "Diseñar esquema de base de datos", "Implementar autenticación",
    "Crear pantalla de inicio", "Añadir validación de formularios",
    "Preparar pruebas unitarias", "Revisar accesibilidad",
    "Optimizar consultas SQL", "Documentar API",
    "Configurar integración continua", "Corregir errores de navegación",
    "Implementar gestión de perfiles", "Añadir registro de actividad",
    "Revisar permisos por rol", "Mejorar mensajes de error",
    "Preparar despliegue de pruebas", "Actualizar dependencias",
    "Validar flujo de recuperación", "Revisar rendimiento",
]
ISSUE_TITLES = [
    "El formulario pierde los datos al volver atrás",
    "La sesión caduca antes de tiempo",
    "La tabla no se adapta a pantallas pequeñas",
    "El filtro devuelve resultados duplicados",
    "El aviso de error no se muestra correctamente",
    "La carga de archivos falla con nombres largos",
    "La búsqueda tarda demasiado con muchos registros",
    "El botón de guardar permite doble envío",
    "El informe exportado tiene fechas incorrectas",
    "La vista móvil corta el menú lateral",
    "La notificación aparece dos veces",
    "El estado no se actualiza tras reabrir un elemento",
]
PRIORITIES = ("low", "medium", "high", "urgent")
INITIAL_STATUSES = ("open", "in_progress")
FINAL_STATUSES = ("resolved", "closed")


def utc_at(day: date, hour: int = 10, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=timezone.utc)


def planned_task(index: int) -> dict:
    # Reparto determinista entre enero y octubre de 2026.
    created_day = date(2026, 1, 8) + timedelta(days=round(index * 4.55))
    created_at = utc_at(created_day, 9 + index % 7, (index * 7) % 60)
    initial_status = INITIAL_STATUSES[index % len(INITIAL_STATUSES)]
    initial_assignee_slot = None if index % 6 == 0 else (index % 5) + 1
    project_slot = index % len(PROJECT_SPECS)
    priority = PRIORITIES[(index * 3) % len(PRIORITIES)]
    due_date = created_day + timedelta(days=14 + (index % 24))
    completion_events = []
    assignment_events = []

    # La mayoría termina en algún momento; el resto sigue pendiente.
    completes = index % 5 != 0
    first_completion = created_day + timedelta(days=8 + (index % 18))
    if first_completion > date(2026, 10, 20):
        completes = False

    current_assignee = initial_assignee_slot
    if index % 7 == 2:
        change_at = created_at + timedelta(days=2, hours=1)
        new_assignee = ((index + 2) % 5) + 1
        if new_assignee == current_assignee:
            new_assignee = (new_assignee % 5) + 1
        assignment_events.append((change_at, current_assignee, new_assignee))
        current_assignee = new_assignee

    status_events = []
    if completes:
        first_at = utc_at(first_completion, 13, (index * 11) % 60)
        first_status = FINAL_STATUSES[index % 2]
        status_events.append((first_at, initial_status, first_status))
        completion_events.append((first_at, first_status, current_assignee, due_date))

        # Algunos ciclos se reabren: una parte vuelve a completarse y otra
        # permanece pendiente al corte actual.
        if index % 11 == 0 and first_completion <= date(2026, 9, 25):
            reopen_day = first_completion + timedelta(days=5)
            reopen_at = utc_at(reopen_day, 11, (index * 5) % 60)
            status_events.append((reopen_at, first_status, "in_progress"))
            if index % 22 == 0:
                second_day = reopen_day + timedelta(days=7)
                second_at = utc_at(second_day, 15, (index * 3) % 60)
                second_status = "closed" if first_status == "resolved" else "resolved"
                status_events.append((second_at, "in_progress", second_status))
                completion_events.append((second_at, second_status, current_assignee, due_date))
        elif index % 13 == 0 and first_completion <= date(2026, 9, 25):
            reopen_day = first_completion + timedelta(days=5)
            reopen_at = utc_at(reopen_day, 11, (index * 5) % 60)
            status_events.append((reopen_at, first_status, "in_progress"))

    final_status = status_events[-1][2] if status_events else initial_status
    final_assignee = assignment_events[-1][2] if assignment_events else initial_assignee_slot
    return {
        "index": index,
        "title": f"{TASK_TITLES[index % len(TASK_TITLES)]} #{index + 1:02d}",
        "description": "Elemento ficticio generado para validar el panel y las estadísticas trimestrales.",
        "created_at": created_at,
        "initial_status": initial_status,
        "initial_assignee_slot": initial_assignee_slot,
        "project_slot": project_slot,
        "priority": priority,
        "due_date": due_date,
        "assignment_events": assignment_events,
        "status_events": status_events,
        "completion_events": completion_events,
        "final_status": final_status,
        "final_assignee_slot": final_assignee,
    }


def planned_issue(index: int) -> dict:
    created_day = date(2026, 2, 3) + timedelta(days=index * 17)
    created_at = utc_at(created_day, 12, (index * 9) % 60)
    statuses = ("open", "in_progress", "resolved", "closed")
    return {
        "title": ISSUE_TITLES[index],
        "created_at": created_at,
        "status": statuses[index % len(statuses)],
        "priority": PRIORITIES[(index + 1) % len(PRIORITIES)],
        "project_slot": index % len(PROJECT_SPECS),
        "assignee_slot": None if index % 4 == 0 else ((index + 2) % 5) + 1,
        "due_date": created_day + timedelta(days=10 + index % 15),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Cargar datos ficticios de DevTrack.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Inserta los datos. Sin esta opción solo realiza una simulación.",
    )
    args = parser.parse_args()

    tasks_plan = [planned_task(i) for i in range(60)]
    issues_plan = [planned_issue(i) for i in range(len(ISSUE_TITLES))]

    print("=" * 68)
    print("DEVTRACK · CARGA DE DEMOSTRACIÓN")
    print(f"Modo: {'APLICAR CAMBIOS' if args.apply else 'SIMULACIÓN SIN ESCRITURAS'}")
    print(f"Organización: {ORG_NAME} ({ORG_SLUG})")
    print(f"Usuarios nuevos previstos: {len(USER_SPECS)}")
    print(f"Proyectos nuevos previstos: {len(PROJECT_SPECS)}")
    print(f"Tareas nuevas previstas: {len(tasks_plan)}")
    print(f"Incidencias nuevas previstas: {len(issues_plan)}")
    print(f"Contraseña común de demostración: {DEMO_PASSWORD}")
    print("=" * 68)

    with SessionLocal() as db:
        existing_org = db.scalar(
            select(Organization).where(Organization.slug == ORG_SLUG)
        )
        if existing_org is not None:
            print(
                f"ABORTADO: ya existe la organización demo (id={existing_org.id}). "
                "No se ha modificado ni insertado nada."
            )
            return 0

        usernames = [spec[0] for spec in USER_SPECS]
        emails = [spec[1] for spec in USER_SPECS]
        collisions = list(
            db.scalars(
                select(User).where(
                    (User.username.in_(usernames)) | (User.email.in_(emails))
                )
            ).all()
        )
        if collisions:
            print("ABORTADO: hay usuarios demo preexistentes; no se ha escrito nada:")
            for user in collisions:
                print(f"  - id={user.id}, username={user.username}, email={user.email}")
            return 2

        if not args.apply:
            print("\nSIMULACIÓN COMPLETADA: no se ha insertado ni modificado ningún registro.")
            print("La carga real solo se ejecutará si se vuelve a lanzar con --apply.")
            print("Fechas de tareas previstas: 2026-01-08 a 2026-10-03.")
            print("Incluye tareas pendientes, finalizaciones, reaperturas y cambios de responsable.")
            print("La simulación no reserva IDs ni garantiza que la inserción vaya a completarse.")
            return 0

        # Las consultas de comprobación han abierto una transacción de lectura.
        # La cerramos antes de iniciar la transacción atómica de inserción.
        db.rollback()
        try:
            with db.begin():
                users = []
                for username, email, display_name, _role in USER_SPECS:
                    user = User(
                        username=username,
                        email=email,
                        display_name=display_name,
                        password_hash=hash_password(DEMO_PASSWORD),
                        is_active=True,
                        email_verified_at=datetime.now(timezone.utc),
                    )
                    db.add(user)
                    users.append(user)
                db.flush()

                owner = users[0]
                org = Organization(
                    name=ORG_NAME,
                    slug=ORG_SLUG,
                    description="Organización ficticia para probar DevTrack.",
                    owner_id=owner.id,
                    status="active",
                )
                db.add(org)
                db.flush()

                for user, spec in zip(users, USER_SPECS):
                    role = spec[3]
                    db.add(
                        OrganizationMember(
                            organization_id=org.id,
                            user_id=user.id,
                            role=role,
                        )
                    )

                projects = []
                for name, description in PROJECT_SPECS:
                    project = Project(
                        name=name,
                        description=description,
                        status="active",
                        organization_id=org.id,
                        owner_id=owner.id,
                        visibility="private",
                    )
                    db.add(project)
                    projects.append(project)
                db.flush()

                for project in projects:
                    for user_index, user in enumerate(users):
                        role = "owner" if user_index == 0 else (
                            "admin" if user_index == 1 else "member"
                        )
                        db.add(
                            ProjectMember(
                                project_id=project.id,
                                user_id=user.id,
                                role=role,
                            )
                        )

                db.flush()
                task_count = 0
                completion_count = 0
                history_count = 0
                for item in tasks_plan:
                    creator = users[item["index"] % len(users)]
                    initial_assignee = (
                        users[item["initial_assignee_slot"]].id
                        if item["initial_assignee_slot"] is not None
                        else None
                    )
                    current_assignee_id = initial_assignee
                    project = projects[item["project_slot"]]
                    task = WorkItem(
                        project_id=project.id,
                        created_by_id=creator.id,
                        assigned_to_id=initial_assignee,
                        type="task",
                        title=item["title"],
                        description=item["description"],
                        status=item["initial_status"],
                        priority=item["priority"],
                        due_date=item["due_date"],
                        created_at=item["created_at"],
                        updated_at=item["created_at"],
                    )
                    db.add(task)
                    db.flush()
                    task_count += 1

                    db.add(
                        WorkItemAssignmentBaseline(
                            work_item_id=task.id,
                            assignee_id=initial_assignee,
                            baseline_at=item["created_at"],
                            baseline_kind="creation",
                        )
                    )
                    open_cycle = (
                        item["created_at"]
                        if item["initial_status"] in ("open", "in_progress")
                        else None
                    )
                    db.add(
                        WorkItemCompletionCoverage(
                            work_item_id=task.id,
                            tracking_started_at=item["created_at"],
                            tracking_state_at=item["created_at"],
                            tracking_state_status=item["initial_status"],
                            tracking_state_assignee_id=initial_assignee,
                            tracking_state_assignee_known=True,
                            tracking_open_cycle_started_at=open_cycle,
                            coverage_origin="creation",
                            captured_since_creation=True,
                            legacy_status_event_count=0,
                            legacy_completion_candidate_count=0,
                            legacy_completion_imported_count=0,
                            legacy_completion_omitted_count=0,
                            legacy_status_timestamps_ambiguous=False,
                            legacy_status_timeline_inconsistent=False,
                            legacy_assignment_history_partial=False,
                            legacy_assignment_timestamps_ambiguous=False,
                            legacy_assignment_timeline_inconsistent=False,
                            assignment_event_count=len(item["assignment_events"]),
                            assignment_sequence_reconstructible=True,
                            assignment_timestamps_ambiguous=False,
                            assignment_timeline_inconsistent=False,
                        )
                    )

                    created_history = WorkItemHistory(
                        work_item_id=task.id,
                        changed_by_id=creator.id,
                        field_name="created",
                        old_value=None,
                        new_value=task.title,
                        changed_at=item["created_at"],
                    )
                    status_init = WorkItemHistory(
                        work_item_id=task.id,
                        changed_by_id=creator.id,
                        field_name="status_initialized",
                        old_value=None,
                        new_value=item["initial_status"],
                        changed_at=item["created_at"],
                    )
                    due_init = WorkItemHistory(
                        work_item_id=task.id,
                        changed_by_id=creator.id,
                        field_name="due_date_initialized",
                        old_value=None,
                        new_value=str(item["due_date"]),
                        changed_at=item["created_at"],
                    )
                    db.add_all([created_history, status_init, due_init])
                    history_count += 3
                    db.flush()

                    timeline = []
                    for change_at, old_assignee_slot, new_assignee_slot in item["assignment_events"]:
                        old_id = (
                            users[old_assignee_slot].id
                            if old_assignee_slot is not None
                            else None
                        )
                        new_id = users[new_assignee_slot].id
                        timeline.append(
                            (change_at, 0, "assignee_id", old_id, new_id)
                        )
                    for change_at, old_status, new_status in item["status_events"]:
                        timeline.append(
                            (change_at, 1, "status", old_status, new_status)
                        )
                    timeline.sort(key=lambda event: (event[0], event[1]))

                    completion_by_time = {
                        event[0]: event for event in item["completion_events"]
                    }
                    for event_at, _sort_order, field_name, old_value, new_value in timeline:
                        if field_name == "assignee_id":
                            old_text = str(old_value) if old_value is not None else None
                            new_text = str(new_value) if new_value is not None else None
                            current_assignee_id = new_value
                            changed_by = creator.id
                        else:
                            old_text = old_value
                            new_text = new_value
                            changed_by = creator.id
                        history = WorkItemHistory(
                            work_item_id=task.id,
                            changed_by_id=changed_by,
                            field_name=field_name,
                            old_value=old_text,
                            new_value=new_text,
                            changed_at=event_at,
                        )
                        db.add(history)
                        db.flush()
                        history_count += 1

                        if field_name == "status" and event_at in completion_by_time:
                            _, final_status, _assignee_slot, completion_due = completion_by_time[event_at]
                            # Snapshot the assignee in force at this completion.
                            assignee_at_completion = current_assignee_id
                            completion = WorkItemCompletion(
                                work_item_id=task.id,
                                source_history_id=history.id,
                                project_id_at_completion=project.id,
                                assignee_id_at_completion=assignee_at_completion,
                                completed_at=event_at,
                                status=final_status,
                                due_date_at_completion=completion_due,
                                due_date_known=True,
                                assignee_known=True,
                                completed_at_is_utc=True,
                            )
                            db.add(completion)
                            completion_count += 1

                    task.status = item["final_status"]
                    final_slot = item["final_assignee_slot"]
                    task.assigned_to_id = (
                        users[final_slot].id if final_slot is not None else None
                    )
                    task.updated_at = max(
                        [item["created_at"]] + [event[0] for event in item["status_events"]]
                        + [event[0] for event in item["assignment_events"]]
                    )

                for index, issue_spec in enumerate(issues_plan):
                    creator = users[(index + 1) % len(users)]
                    assignee = (
                        users[issue_spec["assignee_slot"]].id
                        if issue_spec["assignee_slot"] is not None
                        else None
                    )
                    issue = WorkItem(
                        project_id=projects[issue_spec["project_slot"]].id,
                        created_by_id=creator.id,
                        assigned_to_id=assignee,
                        type="issue",
                        title=issue_spec["title"],
                        description="Incidencia ficticia para comprobar el listado y los filtros.",
                        status=issue_spec["status"],
                        priority=issue_spec["priority"],
                        due_date=issue_spec["due_date"],
                        created_at=issue_spec["created_at"],
                        updated_at=issue_spec["created_at"],
                    )
                    db.add(issue)
                    db.flush()
                    db.add_all([
                        WorkItemHistory(
                            work_item_id=issue.id,
                            changed_by_id=creator.id,
                            field_name="created",
                            old_value=None,
                            new_value=issue.title,
                            changed_at=issue_spec["created_at"],
                        ),
                        WorkItemHistory(
                            work_item_id=issue.id,
                            changed_by_id=creator.id,
                            field_name="status_initialized",
                            old_value=None,
                            new_value=issue_spec["status"],
                            changed_at=issue_spec["created_at"],
                        ),
                        WorkItemHistory(
                            work_item_id=issue.id,
                            changed_by_id=creator.id,
                            field_name="due_date_initialized",
                            old_value=None,
                            new_value=str(issue_spec["due_date"]),
                            changed_at=issue_spec["created_at"],
                        ),
                    ])
                    history_count += 3

            print("\nCARGA COMPLETADA.")
            print(f"Organización creada: id={org.id}, slug={org.slug}")
            print(f"Usuarios creados: {len(users)}")
            print(f"Proyectos creados: {len(projects)}")
            print(f"Tareas creadas: {task_count}")
            print(f"Incidencias creadas: {len(issues_plan)}")
            print(f"Registros de historial creados: {history_count}")
            print(f"Registros de finalización creados: {completion_count}")
            print("\nTodos los cambios se han confirmado en una sola transacción.")
            print("No se han actualizado ni borrado registros preexistentes.")
            return 0
        except Exception:
            db.rollback()
            raise


if __name__ == "__main__":
    raise SystemExit(main())

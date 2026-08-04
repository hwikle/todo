"""Local Flask adapter for the browser checklist."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, cast

from flask import Flask, Response, jsonify, render_template, request

from todo_model import DeadlineKind, DueDate, Priority
from todo_repository import configured_daily_categories
from todo_schema import CanonicalSchemaBundle
from todo_web_application import (
    RevisionConflict,
    TaskRequiredError,
    TodoWebApplication,
    WebEditError,
    snapshot_payload,
)


ROOT = Path(__file__).resolve().parent.parent


def create_app(path: Path, bundle: CanonicalSchemaBundle) -> Flask:
    app = Flask(
        __name__,
        template_folder=str(ROOT / "templates"),
        static_folder=str(ROOT / "static"),
    )
    categories = configured_daily_categories(ROOT / "config" / "task-types.conf")
    service = TodoWebApplication(path, bundle, categories)
    if service.exists():
        service.load()

    def response_for(snapshot: Any) -> Response:
        payload = snapshot_payload(snapshot)
        payload["exists"] = True
        payload["priorities"] = list(bundle.priority_policy.order)
        return jsonify(payload)

    @app.errorhandler(RevisionConflict)
    def revision_conflict(error: RevisionConflict) -> tuple[Response, int]:
        return jsonify(error=str(error), code="revision_conflict"), 409

    @app.errorhandler(TaskRequiredError)
    def task_required(error: TaskRequiredError) -> tuple[Response, int]:
        return jsonify(
            error=str(error), code="task_required", blockers=error.blockers
        ), 409

    @app.errorhandler(WebEditError)
    @app.errorhandler(ValueError)
    @app.errorhandler(OSError)
    def invalid_edit(error: Exception) -> tuple[Response, int]:
        return jsonify(error=str(error), code="invalid_edit"), 400

    @app.get("/")
    def index() -> str:
        return render_template("todo.html")

    @app.get("/api/todo")
    def get_todo() -> Response:
        if not service.exists():
            payload = service.creation_state()
            payload["priorities"] = list(bundle.priority_policy.order)
            return jsonify(payload)
        return response_for(service.load())

    @app.post("/api/todo")
    def create_todo() -> Response:
        data = _object_payload()
        return response_for(service.create(_text(data, "date")))

    @app.post("/api/tasks")
    def add_task() -> Response:
        data = _object_payload()
        result = service.add_task(
            _text(data, "revision"),
            name=_text(data, "name"),
            categories=tuple(_text_list(data, "categories")),
            priority=cast(Optional[Priority], data.get("priority")),
            parent_id=_optional_text(data, "parent_id"),
            after_id=_optional_text(data, "after_id"),
            context_category=_optional_text(data, "context_category"),
        )
        payload = snapshot_payload(result.snapshot)
        payload["exists"] = True
        payload["priorities"] = list(bundle.priority_policy.order)
        payload["created_id"] = result.task_id
        return jsonify(payload)

    @app.patch("/api/tasks/<task_id>")
    def edit_task(task_id: str) -> Response:
        data = _object_payload()
        if "completed" in data:
            completed = data["completed"]
            if not isinstance(completed, bool):
                raise WebEditError("completed must be a boolean")
            snapshot = service.set_completed(_text(data, "revision"), task_id, completed)
        else:
            categories = tuple(_text_list(data, "categories")) if "categories" in data else None
            due_value = data.get("due")
            if due_value is not None and not isinstance(due_value, dict):
                raise WebEditError("due must be an object or null")
            snapshot = service.edit_task(
                _text(data, "revision"),
                task_id,
                name=_optional_text(data, "name") if "name" in data else None,
                description_supplied="description" in data,
                description=_nullable_text(data, "description"),
                priority_supplied="priority" in data,
                priority=cast(Optional[Priority], data.get("priority")),
                categories=categories,
                due_supplied="due" in data,
                due=cast(Optional[DueDate], due_value),
                deadline_kind=cast(Optional[DeadlineKind], data.get("deadline_kind")),
            )
        return response_for(snapshot)

    @app.post("/api/tasks/<task_id>/move")
    def move_task(task_id: str) -> Response:
        data = _object_payload()
        snapshot = service.move_task(
            _text(data, "revision"),
            task_id,
            old_parent_id=_optional_text(data, "old_parent_id"),
            new_parent_id=_optional_text(data, "new_parent_id"),
            after_id=_optional_text(data, "after_id"),
            context_category=_optional_text(data, "context_category"),
        )
        return response_for(snapshot)

    @app.delete("/api/tasks/<task_id>")
    def remove_task(task_id: str) -> Response:
        data = _object_payload()
        snapshot = service.remove_task(_text(data, "revision"), task_id)
        return response_for(snapshot)

    return app


def _object_payload() -> dict[str, Any]:
    value = request.get_json(silent=False)
    if not isinstance(value, dict):
        raise WebEditError("request body must be a JSON object")
    return value


def _text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise WebEditError(f"{key} must be a non-empty string")
    return value


def _optional_text(data: dict[str, Any], key: str) -> Optional[str]:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise WebEditError(f"{key} must be a non-empty string or null")
    return value


def _nullable_text(data: dict[str, Any], key: str) -> Optional[str]:
    value = data.get(key)
    if value is not None and not isinstance(value, str):
        raise WebEditError(f"{key} must be a string or null")
    return value


def _text_list(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise WebEditError(f"{key} must be a list of non-empty strings")
    return cast(list[str], value)

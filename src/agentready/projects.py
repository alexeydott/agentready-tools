"""Durable local project/run relationships over the canonical SiteStore."""
from __future__ import annotations

import logging
from dataclasses import asdict
from urllib.parse import urlsplit

from .audit_core.store import ProjectRecord, ProjectRunRecord, SiteStore

logger = logging.getLogger(__name__)


class ProjectService:
    """Compose project metadata and run history without owning a database."""

    def __init__(self, store: SiteStore) -> None:
        self.store = store

    def create(self, project: ProjectRecord) -> ProjectRecord:
        _validate_target(project.target)
        if project.default_profile not in {"quick", "standard", "deep", "custom"}:
            raise ValueError("unsupported project profile")
        return self.store.put_project(project)

    def get(self, project_id: str) -> ProjectRecord:
        return self.store.get_project(project_id)

    def list(self) -> tuple[ProjectRecord, ...]:
        return tuple(self.store.iter_projects())

    def update(self, project_id: str, *, name: str | None = None, default_profile: str | None = None, default_ruleset: str | None = None, retention_policy: str | None = None) -> ProjectRecord:
        current = self.get(project_id)
        profile = default_profile or current.default_profile
        if profile not in {"quick", "standard", "deep", "custom"}:
            raise ValueError("unsupported project profile")
        updated = ProjectRecord(project_id, name or current.name, current.target, profile, default_ruleset if default_ruleset is not None else current.default_ruleset, current.created_at, retention_policy or current.retention_policy)
        return self.store.put_project(updated)

    def attach_run(
        self,
        project_id: str,
        run_id: str,
        *,
        target: str,
        parent_run_id: str | None = None,
        baseline_run_id: str | None = None,
        trigger: str = "manual",
    ) -> ProjectRunRecord:
        project = self.get(project_id)
        _validate_target(target)
        if _origin(project.target) != _origin(target):
            raise ValueError("run target origin does not match project origin")
        relation = ProjectRunRecord(project_id, run_id, parent_run_id, baseline_run_id, trigger)
        result = self.store.put_project_run(relation)
        logger.info("project run attached project_id=%s run_id=%s trigger=%s", project_id, run_id, trigger)
        return result

    def history(self, project_id: str, *, limit: int = 100) -> tuple[ProjectRunRecord, ...]:
        if limit <= 0 or limit > 1000:
            raise ValueError("project history limit must be between 1 and 1000")
        self.get(project_id)
        return tuple(item for index, item in enumerate(self.store.iter_project_runs(project_id)) if index < limit)

    def set_baseline(self, project_id: str, run_id: str) -> ProjectRunRecord:
        self.get(project_id)
        for relation in self.store.iter_project_runs(project_id):
            if relation.run_id == run_id:
                return self.store.update_project_run(ProjectRunRecord(relation.project_id, relation.run_id, relation.parent_run_id, run_id, relation.trigger, relation.created_at))
        raise KeyError("project run not found")

    def delete_metadata(self, project_id: str) -> None:
        """Delete project metadata and memberships; immutable runs remain."""
        self.store.delete_project(project_id)
        logger.info("project metadata deleted project_id=%s runs_retained=true", project_id)


def _validate_target(target: str) -> None:
    parts = urlsplit(target)
    if parts.scheme not in {"http", "https"} or not parts.netloc or parts.username or parts.password:
        raise ValueError("project target must be an HTTP(S) URL without credentials")


def _origin(target: str) -> str:
    parts = urlsplit(target)
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}"


def project_to_dict(project: ProjectRecord) -> dict[str, object]:
    return asdict(project)


def project_run_to_dict(relation: ProjectRunRecord) -> dict[str, object]:
    return asdict(relation)

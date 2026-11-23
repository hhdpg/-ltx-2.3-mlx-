"""项目与版本的仓储层。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import GenerationProject, GenerationSegment, utcnow


class ProjectRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ---- 写入 ----
    def add(self, project: GenerationProject) -> GenerationProject:
        self.session.add(project)
        self.session.flush()
        return project

    def save(self, project: GenerationProject) -> GenerationProject:
        project.updated_at = utcnow()
        self.session.add(project)
        self.session.flush()
        return project

    def delete(self, project: GenerationProject) -> None:
        self.session.delete(project)

    # ---- 查询 ----
    def get(self, project_id: str) -> GenerationProject | None:
        return self.session.get(GenerationProject, project_id)

    def list_all(self) -> list[GenerationProject]:
        stmt = select(GenerationProject).order_by(GenerationProject.updated_at.desc())
        return list(self.session.execute(stmt).scalars().all())

    def count(self) -> int:
        return int(
            self.session.execute(
                select(func.count(GenerationProject.id))
            ).scalar_one()
        )


class SegmentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ---- 写入 ----
    def add(self, segment: GenerationSegment) -> GenerationSegment:
        self.session.add(segment)
        self.session.flush()
        return segment

    def save(self, segment: GenerationSegment) -> GenerationSegment:
        self.session.add(segment)
        self.session.flush()
        return segment

    def delete(self, segment: GenerationSegment) -> None:
        self.session.delete(segment)

    # ---- 查询 ----
    def get(self, segment_id: str) -> GenerationSegment | None:
        return self.session.get(GenerationSegment, segment_id)

    def get_by_task(self, task_id: str) -> GenerationSegment | None:
        stmt = select(GenerationSegment).where(GenerationSegment.task_id == task_id)
        return self.session.execute(stmt).scalars().first()

    def list_by_project(self, project_id: str) -> list[GenerationSegment]:
        stmt = (
            select(GenerationSegment)
            .where(GenerationSegment.project_id == project_id)
            .order_by(GenerationSegment.created_at.asc())
        )
        return list(self.session.execute(stmt).scalars().all())

    def children_of(self, segment_id: str) -> list[GenerationSegment]:
        stmt = select(GenerationSegment).where(
            GenerationSegment.parent_segment_id == segment_id
        )
        return list(self.session.execute(stmt).scalars().all())

    def count_by_project(self, project_id: str) -> int:
        return int(
            self.session.execute(
                select(func.count(GenerationSegment.id)).where(
                    GenerationSegment.project_id == project_id
                )
            ).scalar_one()
        )

    def next_index(self, project_id: str) -> int:
        current = self.session.execute(
            select(func.max(GenerationSegment.segment_index)).where(
                GenerationSegment.project_id == project_id
            )
        ).scalar_one()
        return int(current or 0) + 1

    def referenced_video_paths(self) -> set[str]:
        """所有被 Segment 引用的视频路径。"""
        stmt = select(GenerationSegment.video_path)
        return {row for row in self.session.execute(stmt).scalars().all() if row}

    def is_video_referenced(self, video_path: str | None) -> bool:
        """指定视频是否被任何 Segment 引用。"""
        if not video_path:
            return False
        stmt = select(GenerationSegment.id).where(
            GenerationSegment.video_path == video_path
        )
        return self.session.execute(stmt).first() is not None

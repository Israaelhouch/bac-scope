"""Pydantic response schemas."""
from __future__ import annotations

from pydantic import BaseModel


class Student(BaseModel):
    registration_number: int
    name: str
    institution: str | None = None
    stream: str
    result_raw: str | None = None
    passed: bool
    mention: str | None = None
    total: float | None = None
    moyenne: float | None = None


class Grade(BaseModel):
    subject: str
    score: float | None = None


class StudentDetail(Student):
    grades: list[Grade] = []


class StudentList(BaseModel):
    count: int          # number of rows returned
    total: int          # total matching the filters (ignoring limit/offset)
    limit: int
    offset: int
    items: list[Student]


class Institution(BaseModel):
    institution: str
    count: int
    passed: int
    pass_rate: float          # 0..1
    avg_moyenne: float | None = None


class StreamSummary(BaseModel):
    stream: str
    count: int
    passed: int
    pass_rate: float
    avg_moyenne: float | None = None

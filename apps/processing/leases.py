"""Database leases: at most one worker executes a given job/file stage at a time.

A lease is acquired with a single conditional UPDATE, which is atomic on every
supported database. A crashed worker's lease simply expires and recovery can
re-enqueue the work.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import timedelta

from django.db.models import Model, Q
from django.utils import timezone

from apps.core.config import get_config


def _ttl() -> timedelta:
    return timedelta(seconds=int(get_config().app["processing"]["lease_seconds"]))


def acquire(model: type[Model], pk, owner: str | None = None) -> str | None:
    owner = owner or uuid.uuid4().hex
    now = timezone.now()
    updated = (
        model.objects.filter(pk=pk)
        .filter(Q(lease_until__isnull=True) | Q(lease_until__lt=now) | Q(lease_owner=owner))
        .update(lease_owner=owner, lease_until=now + _ttl())
    )
    return owner if updated else None


def renew(model: type[Model], pk, owner: str) -> bool:
    return bool(model.objects.filter(pk=pk, lease_owner=owner).update(lease_until=timezone.now() + _ttl()))


def release(model: type[Model], pk, owner: str) -> None:
    model.objects.filter(pk=pk, lease_owner=owner).update(lease_owner="", lease_until=None)


@contextmanager
def leased(model: type[Model], pk):
    """Yield the owner id when the lease was acquired, else None (someone else is working)."""
    owner = acquire(model, pk)
    try:
        yield owner
    finally:
        if owner:
            release(model, pk, owner)

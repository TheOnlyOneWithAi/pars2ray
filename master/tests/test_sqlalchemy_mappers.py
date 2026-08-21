from sqlalchemy import inspect
from sqlalchemy.orm import configure_mappers

from app.models.entities import Permission, Role, User


def test_all_sqlalchemy_mappers_configure_cleanly():
    """Catch broken back_populates pairs before Uvicorn starts."""
    configure_mappers()

    role = inspect(Role)
    permission = inspect(Permission)
    user = inspect(User)

    assert "users" in role.relationships
    assert "permissions" in role.relationships
    assert "roles" in permission.relationships
    assert "roles" in user.relationships

    assert role.relationships["users"].back_populates == "roles"
    assert role.relationships["permissions"].back_populates == "roles"
    assert permission.relationships["roles"].back_populates == "permissions"
    assert user.relationships["roles"].back_populates == "users"

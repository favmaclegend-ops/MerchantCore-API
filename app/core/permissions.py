"""Role-based permission checks for organisation members.

The backend enforces the same hierarchy the frontend UI defines so a member
can never perform an action the UI would hide:

- ``super-admin``      : everything
- ``admin``            : everything except transferring ownership
- ``manager``          : operations on people (employees/customers/suppliers)
                         and operational data, but no billing / plan changes
- ``staff``            : read access + point-of-sale transactions
- ``external``         : read-only access

The department-manager variants (``hrm-manager``, ``finance-manager``,
``logistics-manager``) stored by the frontend are treated as ``manager`` here.
"""

from fastapi import HTTPException, status

from app.models.organisation import OrgMember

MANAGER_VARIANTS = {"hrm-manager", "finance-manager", "logistics-manager"}
MANAGED_ROLES = {"super-admin", "admin", "manager"} | MANAGER_VARIANTS
OPERATIONAL_ROLES = MANAGED_ROLES | {"staff"}

OWNER_ROLE = "super-admin"


def require_role(member: OrgMember, *allowed: str) -> None:
    if member.role not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions for this action")


def require_manager(member: OrgMember) -> None:
    require_role(member, *MANAGED_ROLES)


def require_owner(member: OrgMember) -> None:
    require_role(member, OWNER_ROLE)


def require_staff(member: OrgMember) -> None:
    require_role(member, *OPERATIONAL_ROLES)

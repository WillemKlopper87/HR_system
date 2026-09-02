"""core_hr's models, split by aggregate/workflow (HR_Code_report.md M5:
this package was previously an 852-line models.py). Every class below is
re-exported here so `from core_hr.models import X` (used throughout the
codebase, including this app's own admin.py and every migration's
historical-model bookkeeping) keeps working unchanged regardless of
which submodule actually defines X -- Django resolves a model's app_label
from its containing package (`core_hr`), not from this file, so the
split has no effect on migrations or the app registry.

Import order matters here (though not inside Django itself): each
submodule below imports its own dependencies directly from the sibling
submodule that defines them (e.g. `probation.py` does
`from .core import Employee`), so this file just needs to import them in
an order where each submodule's own imports already resolve -- which is
simply reference_data -> core -> everything else, since only
reference_data and core are depended on by more than one sibling."""
from .core import (  # noqa: F401
    ContractRenewalDecision,
    Employee,
    EmployeeManager,
    EmployeeVersion,
    EmployeeVersionQuerySet,
    EmploymentEvent,
    VERSION_CARRY_FIELDS,
)
from .data_quality import DataQualityException  # noqa: F401
from .dependants import Dependant, EmergencyContact  # noqa: F401
from .employment_changes import EmploymentChange  # noqa: F401
from .exit_interviews import ExitInterview  # noqa: F401
from .probation import ProbationPeriod, ProbationReview  # noqa: F401
from .reference_data import Department, JobGrade, Location, OccupationalLevel  # noqa: F401

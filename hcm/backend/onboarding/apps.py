from django.apps import AppConfig


class OnboardingConfig(AppConfig):
    """Onboarding *and* offboarding checklists (C1 part 3 slice 3) -- one app
    covering both directions, see the design spec section 2.1-2.2 for why.
    The name is the brief's own suggested one; this docstring is the
    reminder to a future reader that "onboarding" isn't the whole story."""

    name = "onboarding"
    verbose_name = "Onboarding / offboarding checklists (C1 part 3)"

    def ready(self):
        from core_hr import lifecycle_hooks

        from . import services

        lifecycle_hooks.register_hire_handler(
            "onboarding.ChecklistInstance", services.create_onboarding_checklist_on_hire
        )
        lifecycle_hooks.register_exit_completion_handler(
            "onboarding.ChecklistInstance", services.create_offboarding_checklist_on_exit
        )

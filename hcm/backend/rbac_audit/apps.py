from django.apps import AppConfig


class RbacAuditConfig(AppConfig):
    name = 'rbac_audit'

    def ready(self):
        # Retention handlers for this app's own models. Other apps register
        # theirs from their own AppConfig.ready() — see rbac_audit/retention.py.
        from .retention import register_builtin_handlers

        register_builtin_handlers()

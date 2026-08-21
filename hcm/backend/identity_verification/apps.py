from django.apps import AppConfig


class IdentityVerificationConfig(AppConfig):
    name = 'identity_verification'

    def ready(self):
        # Access-cascade handlers for the employment exit state machine
        # (C1 part 3) -- registered with the shared registry in core_hr,
        # which never imports a peer app. See identity_verification/exit_handlers.py.
        from core_hr.access_cascade import register_exit_handler, register_restore_handler

        from .exit_handlers import restore_biometric_enrollment, suspend_biometric_enrollment

        register_exit_handler("identity_verification.BiometricEnrollment", suspend_biometric_enrollment)
        register_restore_handler("identity_verification.BiometricEnrollment", restore_biometric_enrollment)

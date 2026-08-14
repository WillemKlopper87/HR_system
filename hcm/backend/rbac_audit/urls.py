from django.urls import path

from . import views

urlpatterns = [
    path("csrf/", views.csrf, name="auth-csrf"),
    path("login/", views.login_view, name="auth-login"),
    path("logout/", views.logout_view, name="auth-logout"),
    path("me/", views.me_view, name="auth-me"),
    path("totp/enroll/", views.totp_enroll, name="totp-enroll"),
    path("totp/confirm/", views.totp_confirm, name="totp-confirm"),
    path("totp/status/", views.totp_status, name="totp-status"),
    path("step-up/", views.step_up_request_view, name="step-up-request"),
    path("step-up/status/", views.step_up_status_view, name="step-up-status"),
]

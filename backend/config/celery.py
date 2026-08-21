"""Celery-приложение проекта."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("lms")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
# чтобы celery.current_app указывал на наше приложение, а не на дефолтное
app.set_default()

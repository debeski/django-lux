"""``django.tasks`` functions the task-runner tests enqueue through the dlux backend (Django 6.0+)."""

from django.tasks import task


@task
def add(a, b):
    return a + b


@task(takes_context=True)
def attempt_number(context):
    return context.attempt

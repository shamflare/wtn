"""تشغيل خدمة جلسة ZNET (متصفّح خفيّ). تعمل في حاوية مستقلّة."""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "تشغيل خدمة جلسة ZNET (Playwright) على KONTOR_SESSION_PORT"

    def handle(self, *args, **o):
        from kontor.session_service import serve
        self.stdout.write(self.style.SUCCESS("kontor session service: starting…"))
        serve()

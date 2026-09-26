"""`provision_instance` — تجهيز نسخة عميل: مرّةً واحدة، وبلا كلمات سرٍّ معروفة."""
from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase

from core.models import Tenant, User


class ProvisionInstanceTest(TestCase):

    def run_cmd(self, **kw):
        out = StringIO()
        call_command("provision_instance", store="أهلا كارد", admin_login="5551234567",
                     stdout=out, **kw)
        return out.getvalue()

    def test_creates_one_store_its_owner_and_the_platform_owner(self):
        out = self.run_cmd()
        tenant = Tenant.objects.get()
        admin = User.objects.get(login_id="5551234567")
        self.assertEqual(admin.tenant, tenant)
        self.assertEqual(admin.role, User.Role.TENANT_ADMIN)
        owner = User.objects.get(role=User.Role.PLATFORM_OWNER)
        self.assertIsNone(owner.tenant)
        # الكلمات العشوائية تُطبع مرّةً — وتعمل فعلاً
        admin_pw = out.split("5551234567  /  ")[1].split()[0]
        self.assertTrue(admin.check_password(admin_pw))
        self.assertFalse(admin.check_password("admin123"))

    def test_refuses_a_second_run(self):
        self.run_cmd()
        with self.assertRaises(CommandError):
            self.run_cmd()
        self.assertEqual(Tenant.objects.count(), 1)

    def test_the_login_page_wears_the_single_store(self):
        """نسخة العميل: الباب العام هو باب متجره، فتلبس صفحة الدخول اسمه."""
        self.run_cmd()
        store = self.client.get("/api/storefront/").json()["store"]
        self.assertEqual(store["name"], "أهلا كارد")

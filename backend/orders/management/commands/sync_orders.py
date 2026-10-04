"""
متابعة الطلبات «قيد التنفيذ» لكل المتاجر — تشغّلها مهمّةٌ مجدولة كل دقيقة.

**أقدم دَين في المشروع.** كانت المتابعة يحرّكها **متصفّح الأدمن المفتوح** وحده
(نبضة كل ٦ ثوانٍ)، فمتى أُغلقت اللوحة تجمّد كل طلبٍ أكّد المزوّد استلامه —
ووكيله ينتظر ومالُه محجوز إلى الأبد. وصار الأمر أثقل بعد التوجيه الداخلي:
موافقة المورّد اليدوية لا تصل إلى المتجر المشتري إلا بنبضة، وهو متجرٌ آخر قد
لا تكون لوحته مفتوحة أصلاً.

    python manage.py sync_orders

**قفل الملفّ** يمنع تشغيلين متوازيين: النبضة كل دقيقة والمتابعة قد تطول، فلو
تراكبتا لسأل مزوّدٌ عن الطلب مرّتين معاً — وحسمُه مرّتين يعني استرجاعين لمبلغ
واحد. ولا نستعمل قفلاً في القاعدة كي يبقى الأمر يعمل ولو انقطعت.
"""
import os
import time

from django.core.management.base import BaseCommand

from core.models import Tenant
from orders.models import Order
from orders.services import sync_pending

LOCK_PATH = "/tmp/wtn_sync_orders.lock"
# قفلٌ أقدم من هذا يعني تشغيلاً مات دون أن ينظّف — لا تشغيلاً حيّاً
STALE_AFTER = 15 * 60


class Command(BaseCommand):
    help = "متابعة الطلبات قيد التنفيذ لكل المتاجر (تُجدوَل كل دقيقة)"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50,
                            help="أقصى عدد طلبات لكل متجر في النبضة الواحدة")
        parser.add_argument("--quiet", action="store_true",
                            help="لا تطبع شيئاً ما لم يتغيّر شيء — لسجلّ cron نظيف")

    def handle(self, *args, **options):
        if not self._take_lock():
            if not options["quiet"]:
                self.stdout.write("نبضةٌ سابقة ما زالت تعمل — تُخُطّيت هذه")
            return
        try:
            self._run(options)
            try:
                from kontor.execution import poll_all_processing
                n = poll_all_processing()
                if n and not options["quiet"]:
                    self.stdout.write(f"خطوط: حُدّث {n} طلب")
            except Exception as e:  # noqa: BLE001 — متابعة الخطوط لا تُسقط مزامنة الألعاب
                if not options["quiet"]:
                    self.stdout.write(f"تعذّرت متابعة الخطوط: {e}")
        finally:
            try:
                os.unlink(LOCK_PATH)
            except FileNotFoundError:
                pass

    def _take_lock(self) -> bool:
        try:
            fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(LOCK_PATH) > STALE_AFTER:
                    os.unlink(LOCK_PATH)      # قفلٌ يتيم — نكسره ونمضي
                    return self._take_lock()
            except FileNotFoundError:
                return self._take_lock()
            return False

    def _run(self, options):
        # المتاجر التي لها طلبٌ ينتظر فعلاً — لا نمرّ على متجرٍ لا شيء فيه
        tenant_ids = (
            Order.objects.filter(status=Order.Status.PROCESSING)
            .values_list("tenant_id", flat=True).distinct()
        )
        tenants = Tenant.objects.filter(id__in=list(tenant_ids))
        if not tenants:
            if not options["quiet"]:
                self.stdout.write("لا طلبات قيد التنفيذ")
            return

        changed = checked = 0
        for tenant in tenants:
            try:
                results = sync_pending(tenant, limit=options["limit"])
            except Exception as e:
                # متجرٌ متعثّر لا يوقف البقيّة — والمجدول يعيد المحاولة بعد دقيقة
                self.stderr.write(f"{tenant.subdomain}: {e}")
                continue
            checked += len(results)
            changed += sum(1 for r in results if r.get("changed"))

        if changed or not options["quiet"]:
            self.stdout.write(
                f"تُوبع {checked} طلباً في {len(tenants)} متجراً · تغيّر {changed}"
            )

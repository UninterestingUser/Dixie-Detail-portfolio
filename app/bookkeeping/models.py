"""GnuCash exports (bookkeeping-gnucash.md, decision 0035)."""

from django.conf import settings
from django.db import models


class ExportBatch(models.Model):
    """One GnuCash export file. Payments, refunds and helper payouts point to
    the batch that exported them, so nothing is exported twice. Payments with
    no GnuCash account (bitcoin, trades) are listed for manual entry instead."""

    date_from = models.DateField()
    date_to = models.DateField()
    file_name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "export batches"

    def __str__(self):
        return f"GnuCash export {self.date_from} to {self.date_to}"

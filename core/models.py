from django.db import models
from django.contrib.auth.models import User


class Bank(models.Model):
    bank_name = models.CharField(max_length=255, unique=True)
    food_cashback = models.FloatField(default=0.0)        # % кешбэка на еду
    transport_cashback = models.FloatField(default=0.0)   # % кешбэка на транспорт
    clothes_cashback = models.FloatField(default=0.0)     # % кешбэка на одежду
    percent_on_balance = models.FloatField(default=0.0)  # % на остаток
    deposit_percent = models.FloatField(default=0.0)     # % на вклад

    def __str__(self):
        return self.bank_name


class Statement(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="statements")
    bank = models.ForeignKey(Bank, on_delete=models.CASCADE, related_name="statements")
    file = models.FileField(upload_to="statements/")
    pars = models.TextField(blank=True, null=True)
    advice = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Statement of {self.user.username} - {self.bank.bank_name}"
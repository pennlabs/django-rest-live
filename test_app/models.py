from django.contrib import admin
from django.db import models


class List(models.Model):
    name = models.CharField(max_length=64)


class Todo(models.Model):
    text = models.CharField(max_length=140)
    done = models.BooleanField(default=False)
    list = models.ForeignKey("List", on_delete=models.CASCADE)
    another_field = models.BooleanField(default=True)


admin.site.register(List)
admin.site.register(Todo)

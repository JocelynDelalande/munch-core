# -*- coding: utf-8 -*-
# Generated by Django 1.10.1 on 2016-09-23 13:19
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('abuse', '0003_set_default_for_comments'),
    ]

    operations = [
        migrations.AlterField(
            model_name='abusenotification',
            name='comments',
            field=models.TextField(verbose_name='comments'),
        ),
    ]

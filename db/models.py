from django.db import models


class Record(models.Model):
    qname      = models.CharField(db_index=True, max_length=256)
    rtype      = models.CharField(max_length=16)
    ad         = models.BooleanField(null=True)
    preference = models.IntegerField(null=True)
    value      = models.CharField(max_length=256)
    error      = models.CharField(max_length=256)
    nxdomain   = models.BooleanField()


class MtaStsPolicy(models.Model):
    domain  = models.CharField(max_length=256, primary_key=True)
    mode    = models.CharField(max_length=16)
    max_age = models.IntegerField(null=True)
    error   = models.CharField(max_length=256)


class MtaStsMx(models.Model):
    domain  = models.CharField(max_length=256, primary_key=True)
    name     = models.CharField(max_length=256)
    wildcard = models.BooleanField()


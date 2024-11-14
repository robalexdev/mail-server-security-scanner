#!/usr/bin/env python

import base64
import click
import django
import dns.flags
import dns.rdatatype
import dns.resolver
import json
import os
import psl
import re
import sys

from urllib.request import urlopen
from django.conf import settings
from url_normalize import url_normalize
from urllib.parse import urlparse


TIMEOUT_SECONDS = 20
url_re = re.compile("[._a-z0-9]+")

dns_resolver = dns.resolver.Resolver()
dns_resolver.nameservers = ['127.0.0.1']
dns_resolver.port = 8053
dns_resolver.search = []
# Ask for DNSSEC validation
dns_resolver.edns = 0
dns_resolver.ednsflags |= dns.flags.DO


def get_owning_domain(mailhost):
    # Some providers have public suffixes that obscure the domain
    if mailhost.endswith(".amazonaws.com"):
        return "amazonaws.com"
    elif mailhost.endswith(".cloudflare.net"):
        return "cloudflare.net"
    elif mailhost.endswith(".invalid"):
        # Merge everything in the invalid TLD
        return "invalid"
    return psl.domain_suffixes(mailhost).private


def mailhost_tlsa_qname(mailhost):
    return f"_25._tcp.{mailhost}"


def normalize_domain(domain):
    try:
        if domain:
            return urlparse(url_normalize(domain)).hostname
    except UnicodeError:
        return None


class DnsLookup:
    def __init__(self, qname, rtype, rdatatype):
        self.qname = normalize_domain(qname)
        self.rtype = rtype
        self.rdatatype = rdatatype
        self.ad = None

    def save_record(self, value, preference=None):
        Record(
            qname=self.qname,
            rtype=self.rtype,
            ad=self.ad,
            preference=preference,
            value=value,
            nxdomain=False,
        ).save()

    def save_exception(self, e):
        Record(
            qname=self.qname,
            rtype=self.rtype,
            error=str(e),
            nxdomain=False,
        ).save()

    def get_cache(self):
        records = []
        for record in Record.objects.filter(qname=self.qname, rtype=self.rtype).all():
            records.append(record)
        return records

    def get_cache_or_fetch(self):
        records = self.get_cache()
        if not records:
            self.lookup()
            records = self.get_cache()
        return records

    def lookup(self):
        try:
            answer = dns_resolver.resolve(self.qname, self.rdatatype)
            self.ad = bool(answer.response.flags.value & dns.flags.AD)
            for rdata in answer:
                self._handle_answer(rdata)
        except dns.resolver.NXDOMAIN as e:
            Record(
                qname=self.qname,
                rtype=self.rtype,
                value="",
                nxdomain=True,
            ).save()
        except dns.exception.DNSException as e:
            self.save_exception(e)


class MxLookup(DnsLookup):
    def __init__(self, qname):
        super().__init__(qname, "MX", dns.rdatatype.MX)
        self.results = set([])

    def _handle_answer(self, rdata):
        rdata_host = normalize_domain(rdata.exchange.to_text())
        if rdata_host is not None:
            self.results.add(rdata_host)
            self.save_record(rdata_host, preference=rdata.preference)

    def get_results(self):
        return self.results


class ALookup(DnsLookup):
    def __init__(self, qname):
        super().__init__(qname, "A", dns.rdatatype.A)
        self.results = set([])

    def _handle_answer(self, rdata):
        self.results.add(rdata.address)
        self.save_record(rdata.address)

    def get_results(self):
        return self.results

class MtaStsLookup(DnsLookup):
    def __init__(self, qname):
        super().__init__(f"_mta-sts.{qname}", "TXT", dns.rdatatype.TXT)
        self.results = set([])

    def _handle_answer(self, rdata):
        for string in rdata.strings:
            if string.startswith(b"v=STSv1;"):
                self.results.add(string)
                self.save_record(string)

    def get_results(self):
        return self.results

class MtaStsLookupCname(DnsLookup):
    def __init__(self, qname):
        super().__init__(f"_mta-sts.{qname}", "CNAME", dns.rdatatype.CNAME)
        self.results = set([])

    def _handle_answer(self, rdata):
        self.results.add(rdata.to_text())
        self.save_record(rdata.to_text())

    def get_results(self):
        return self.results


class MailHostTlsaLookup(DnsLookup):
    def __init__(self, mailhost):
        super().__init__(
                mailhost_tlsa_qname(mailhost),
                "TLSA",
                dns.rdatatype.TLSA,
        )
        self.results = set([])

    def _handle_answer(self, rdata):
        if rdata.usage is not None:
            d = {
                "usage": rdata.usage,
                "selector": rdata.selector,
                "mtype": rdata.mtype,
                "cert": base64.b64encode(rdata.cert).decode('ascii'),
            }
            self.results.add(rdata.usage)
            self.save_record(json.dumps(d))

    def get_results(self):
        return self.results


def fetch_mtasts_policy(domain):
    if MtaStsPolicy.objects.filter(domain=domain, error="").count() > 0:
        return

    try:
        with urlopen(f"https://mta-sts.{domain}/.well-known/mta-sts.txt", timeout=TIMEOUT_SECONDS) as u:
            body = u.read(10240).decode("UTF-8")
    except Exception as e:
        MtaStsPolicy(
            domain=domain,
            error=str(e),
        ).save()
        return

    mxes = set([])
    mode = ""
    max_age = None
    for line in body.splitlines():
        line_parts = line.split(":", 1)
        if len(line_parts) != 2:
            continue
        k, v = line_parts
        k = k.strip()
        v = v.strip()
        if k == "mode":
            mode = v
        elif k == "max_age":
            try:
                max_age = int(v)
            except ValueError:
                MtaStsPolicy(
                    domain=domain,
                    error=f"Invalid max_age: {v}",
                ).save()
                return
        elif k == "mx":
            v = normalize_domain(v)
            if v is not None:
                mxes.add(v)

    if mode not in ["none", "testing", "enforce"]:
        MtaStsPolicy(
            domain=domain,
            error=f"Invalid mode: {mode}",
        ).save()
        return
    if max_age < 0 or max_age > 31557600:
        MtaStsPolicy(
            domain=domain,
            error=f"Invalid max_age: {max_age}",
        ).save()
        return

    MtaStsPolicy(
        domain=domain,
        mode=mode,
        max_age=max_age,
    ).save()

    for mx in mxes:
        is_wildcard = mx.startswith("*.")
        if is_wildcard:
            mx = mx[2:]
        MtaStsMx(
            domain=domain,
            name=mx,
            wildcard=is_wildcard,
        ).save()
    return


def scan(domains_list):
    domains = []
    for line in domains_list.readlines():
        normalized = normalize_domain(line.strip())
        if normalized is not None:
            domains.append(normalized)

    for domain in domains:
        print(f"Checking {domain}")
        mtasts_records = MtaStsLookup(domain).get_cache_or_fetch()
        if any([bool(r.value) for r in mtasts_records]):
            fetch_mtasts_policy(domain)
        mtasts_cname_records = MtaStsLookupCname(domain).get_cache_or_fetch()
        if mtasts_cname_records:
            for mtasts_cname_record in mtasts_cname_records:
                MtaStsLookup(mtasts_cname_record).get_cache_or_fetch()
            fetch_mtasts_policy(domain)
        for mx in MxLookup(domain).get_cache_or_fetch():
            if not mx.value:
                continue
            print(f"  checking mx {mx.value}")
            ALookup(mx.value).get_cache_or_fetch()
            MailHostTlsaLookup(mx.value).get_cache_or_fetch()


def report():
    domain_count = Record.objects.filter(
            rtype="MX",
            nxdomain=False,
        ).values(
            "qname",
        ).distinct().count()

    domain_count_ad = Record.objects.filter(
            rtype="MX",
            ad=True,
        ).values(
            "qname",
        ).distinct().count()

    domain_count_error = Record.objects.filter(
            rtype="MX",
        ).exclude(
            error="",
        ).exclude(
            error__contains="DNS response does not contain an answer",
        ).values(
            "qname",
        ).distinct().count()

    domain_with_mx_count = Record.objects.filter(
            rtype="MX",
            nxdomain=False,
            error="",
        ).exclude(
            value="",
        ).values(
            "qname",
        ).distinct().count()

    domain_with_mx_and_ad = Record.objects.filter(
            rtype="MX",
            nxdomain=False,
            error__exact="",
            ad=True,
        ).exclude(
            value="",
        ).values(
            "qname",
        ).distinct().count()


    mtasts_domain_count = MtaStsPolicy.objects.exclude(
        mode="",
    ).count()
    mtasts_domain_enforce_count = MtaStsPolicy.objects.filter(
        mode="enforce",
    ).count()

    # Checking DANE support:
    # Domain must support DNSSEC
    # MX must support DNSSEC
    # MX must have TLSA record
    possible_dane_domains = Record.objects.filter(
            rtype="MX",
            nxdomain=False,
            error="",
            ad=True,
        ).exclude(
            value="",
        ).all()
    dane_domains = set([])
    for domain_obj in possible_dane_domains:
        domain = domain_obj.qname
        mx = domain_obj.value
        tlsa_count = Record.objects.filter(
            qname=mailhost_tlsa_qname(mx),
            rtype="TLSA",
            nxdomain=False,
            error="",
            ad=True,
        ).exclude(
            value="",
        ).count()
        if tlsa_count > 0:
            dane_domains.add(domain)
    dane_domains_count = len(dane_domains)

    top_mail_hosting = {}
    mx_records = Record.objects.filter(
            rtype="MX",
            nxdomain=False,
            error="",
        ).exclude(
            value="",
        ).all()
    for record in mx_records:
        provider = get_owning_domain(record.value)
        if provider not in top_mail_hosting:
            top_mail_hosting[provider] = set([])
        top_mail_hosting[provider].add(record.qname)
    provider_counts = []
    for provider, domain_set in top_mail_hosting.items():
        provider_counts.append((len(domain_set), provider))
    provider_counts = sorted(provider_counts, key=lambda x : x[0], reverse=True)[:100]
    for item in provider_counts:
        print(f"{item[0]}\t{item[1]}")



    print(f"{domain_count} domains scanned")
    print("\tof which:")
    print(f"\t{int(domain_with_mx_count * 100 / domain_count)}%\thave a mail server ({domain_with_mx_count} domains)")
    print(f"\t{int(domain_count_ad * 100 / domain_count)}%\tuse DNSSEC ({domain_count_ad} domains)")
    print(f"\t{int(domain_count_error * 100 / domain_count)}%\tthrew an error ({domain_count_error} domains)")
    print()
    print("Of the domains with a mail server:")
    print(f"\t{int(domain_with_mx_and_ad * 100 / domain_with_mx_count)}%\tusing DNSSEC ({domain_with_mx_and_ad})")
    print(f"\t{int(mtasts_domain_count * 100 / domain_with_mx_count)}%\tuse MTA-STS ({mtasts_domain_count} domains)")
    print(f"\t{int(mtasts_domain_enforce_count * 100 / domain_with_mx_count)}%\tuse MTA-STS in enforce mode ({mtasts_domain_enforce_count} domains)")
    print(f"\t{int(dane_domains_count * 100 / domain_with_mx_count)}%\tuse DANE ({dane_domains_count} domains)")


@click.command()
@click.argument("domains_list", required=False, type=click.File('r'))
def main(domains_list):
    if domains_list:
        scan(domains_list)
    else:
        report()


if __name__ == "__main__":
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
    django.setup()
    from db.models import *
    main()


import argparse
import os

import pyotp
import requests
from playwright.sync_api import sync_playwright

# https://letsencrypt.org/docs/challenge-types/#dns-01-challenge


def get_result(response) -> dict:
    response.raise_for_status()
    result = response.json()

    if result["Error"]:
        raise Exception(result["Msg"])

    return result


class NamecheapClient:
    api_base_url = "https://ap.www.namecheap.com"
    auth_cookie_name = ".ncauth"
    csrf_token_name = "_NcCompliance"

    def __init__(self, auth_token: str = None, csrf_token: str = None):
        self.auth_token = auth_token
        self.csrf_token = csrf_token

    @property
    def auth_headers(self):
        return {self.csrf_token_name: self.csrf_token}

    @property
    def auth_cookies(self):
        return {
            self.auth_cookie_name: self.auth_token,
            self.csrf_token_name: self.csrf_token,
        }

    def login(
        self,
        username: str,
        password: str,
        get_totp: callable,
        headless: bool = True,
    ) -> (str, str):
        with sync_playwright() as pw:
            browser = pw.firefox.launch(headless=headless)
            context = browser.new_context()

            page = context.new_page()
            page.goto("https://www.namecheap.com/myaccount/login/")

            username_input = page.wait_for_selector(
                "input.nc_username", state="visible"
            )
            username_input.fill(username)

            password_input = page.wait_for_selector(
                "input.nc_password", state="visible"
            )
            password_input.fill(password)
            password_input.press("Enter")

            otp_input = page.wait_for_selector(
                "input[data-ncid='verification-otp']", state="visible"
            )
            otp_input.fill(get_totp())
            otp_input.press("Enter")

            page.wait_for_url(self.api_base_url)
            cookies = context.cookies()
            cookies = {c["name"]: c for c in cookies}

            context.close()

            try:
                self.auth_token = cookies[self.auth_cookie_name]["value"]
                self.csrf_token = cookies[self.csrf_token_name]["value"]
            except KeyError:
                raise Exception("Authentication cookies not found")

            return self.auth_token, self.csrf_token

    def get_dns_info(self, domain: str) -> dict:
        url = f"{self.api_base_url}/Domains/dns/GetAdvancedDnsInfo"
        params = {"domainName": domain}  # , "fillTransferInfo": "false"

        response = requests.get(
            url,
            params=params,
            headers=self.auth_headers,
            cookies=self.auth_cookies,
        )
        result = get_result(response)

        return result

    def add_or_update_record(self, domain: str, record: dict) -> dict:
        url = f"{self.api_base_url}/Domains/dns/AddOrUpdateHostRecord"
        data = {"domainName": domain, "model": record}

        response = requests.post(
            url,
            json=data,
            headers=self.auth_headers,
            cookies=self.auth_cookies,
        )
        result = get_result(response)

        return result["Result"][0]

    def remove_record(self, domain: str, record: dict) -> dict:
        url = f"{self.api_base_url}/Domains/dns/RemoveDomainDnsRecord"
        data = {
            "domainName": domain,
            "hostId": record["HostId"],
            "recordType": record["RecordType"],
        }

        response = requests.post(
            url,
            json=data,
            headers=self.auth_headers,
            cookies=self.auth_cookies,
        )
        result = get_result(response)

        return result

    def add_acme_record(self, domain: str, value: str) -> dict:
        record = {
            "Data": value,
            "Host": "_acme-challenge",
            "HostId": -1,
            "RecordType": 5,  # TXT
            "Ttl": 60,  # 1 min
        }

        return self.add_or_update_record(domain, record)


def login(args):
    if args.username is None:
        raise Exception("Missing username")
    if args.password is None:
        raise Exception("Missing password")

    client = NamecheapClient()

    totp = pyotp.TOTP(args.totp_secret)
    client.login(args.username, args.password, lambda: totp.now())

    print(f"NAMECHEAP_AUTH_TOKEN={client.auth_token}")
    print(f"NAMECHEAP_CSRF_TOKEN={client.csrf_token}")


def require_txt_args(args):
    if args.domain is None:
        raise Exception("Missing domain name")
    if args.validation is None:
        raise Exception("Missing TXT record value")


def create_client(args) -> NamecheapClient:
    if args.auth_token is None:
        raise Exception("Missing auth token")
    if args.csrf_token is None:
        raise Exception("Missing CSRF token")

    client = NamecheapClient(
        auth_token=args.auth_token,
        csrf_token=args.csrf_token,
    )

    return client


def auth_hook(args):
    require_txt_args(args)
    client = create_client(args)
    client.add_acme_record(args.domain, args.validation)


def cleanup_hook(args):
    require_txt_args(args)
    client = create_client(args)

    dns_info = client.get_dns_info(args.domain)
    records = dns_info["Result"]["CustomHostRecords"]["Records"]

    acme_record = next(
        record
        for record in records
        if record["RecordType"] == 5  # TXT
        and record["Host"] == "_acme-challenge"
        and record["Data"] == args.validation
    )

    client.remove_record(args.domain, acme_record)


def main():
    parser = argparse.ArgumentParser(
        prog="hook",
        description="Certbot DNS-01 challenge hook for Namecheap",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # login subcommand
    login_parser = subparsers.add_parser(
        "login",
        help="Login to Namecheap",
    )
    login_parser.add_argument(
        "--username",
        default=os.getenv("NAMECHEAP_USERNAME"),
        help="Namecheap username",
    )
    login_parser.add_argument(
        "--password",
        default=os.getenv("NAMECHEAP_PASSWORD"),
        help="Namecheap password",
    )
    login_parser.add_argument(
        "--totp-secret",
        default=os.getenv("NAMECHEAP_TOTP_SECRET"),
        help="TOTP secret for 2FA",
    )
    login_parser.set_defaults(func=login)

    # add shared arguments for auth/cleanup parsers
    def add_txt_parser_args(parser):
        parser.add_argument(
            "--domain",
            default=os.getenv("CERTBOT_DOMAIN"),
            help="Domain name",
        )
        parser.add_argument(
            "--validation",
            default=os.getenv("CERTBOT_VALIDATION"),
            help="TXT record value for validation",
        )
        parser.add_argument(
            "--auth-token",
            default=os.getenv("NAMECHEAP_AUTH_TOKEN"),
            help="Namecheap authentication token",
        )
        parser.add_argument(
            "--csrf-token",
            default=os.getenv("NAMECHEAP_CSRF_TOKEN"),
            help="Namecheap CSRF token",
        )

    # auth subcommand
    auth_parser = subparsers.add_parser(
        "auth",
        help="Add DNS TXT record",
    )
    add_txt_parser_args(auth_parser)
    auth_parser.set_defaults(func=auth_hook)

    # cleanup subcommand
    cleanup_parser = subparsers.add_parser(
        "cleanup",
        help="Remove DNS TXT record",
    )
    add_txt_parser_args(cleanup_parser)
    cleanup_parser.set_defaults(func=cleanup_hook)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

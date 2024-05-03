from pathlib import Path

import arrow
import humps
import yaml
from helloasso_api import HaApiV5

CONFIG_FILE = Path("config.yml")

with CONFIG_FILE.open() as f:
    config = yaml.safe_load(f)


def debug(o):
    with open("debug.json", "w") as f:
        f.write(o.text)


class HelloAssoAPI(HaApiV5):
    def __init__(self, client_id, client_secret, organization_slug, **_kwargs):
        super().__init__(
            api_base="api.helloasso.com",
            client_id=client_id,
            client_secret=client_secret,
        )
        self.organization_slug = organization_slug
        self.base_url = "/v5"

    def call(self, url, *args, method="GET", **kwargs):
        url = self.base_url + url
        kwargs = {
            "method": method,
            "params": humps.camelize(kwargs),
        }
        response = super().call(url, *args, **kwargs)
        response.raise_for_status()
        return response

    def get_organizations(self):
        return self.call("/users/me/organizations")

    def get_forms(self):
        return self.call(f"/organizations/{self.organization_slug}/forms")

    def get_form(self, form_slug):
        result = []
        token = None
        while True:
            response = self.call(
                f"/organizations/{self.organization_slug}/forms/Membership/{form_slug}/orders",
                with_details=True,
                continuation_token=token,
            )
            debug(response)
            result.extend(response.json()["data"])
            pagination = response.json()["pagination"]
            if pagination["pageIndex"] == pagination["totalPages"]:
                break
            token = pagination["continuationToken"]
            print("continuation token:", token)
        return result


api = HelloAssoAPI(**config)

response = api.get_form(config["form_slug"])


def dict_by_key(iterable, key):
    return {x[key]: x for x in iterable}


for result in response:
    id = result["id"]
    date = arrow.get(result["date"])
    field_name = config["form_field_name"]
    items = dict_by_key(result["items"], "type")
    custom_fields = items["Membership"].get("customFields")
    custom_fields = dict_by_key(custom_fields, "name") if custom_fields else {}
    expiry = date.shift(years=1)
    if field_name in custom_fields:
        print(
            id,
            date,
            custom_fields[field_name]["answer"],
            "Expiration:",
            expiry.humanize(),
        )

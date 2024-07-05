import functools
from dataclasses import dataclass

import arrow
import humps
from arrow import Arrow
from helloasso_api import HaApiV5

from config import config


def debug(o):
    with open("debug.json", "w") as f:
        f.write(o.text)


def dict_by_key(iterable, key):
    return {x[key]: x for x in iterable}


@dataclass
class Membership:
    email: str
    date: Arrow
    custom_fields: dict

    @classmethod
    def from_helloasso_api(cls, d: dict):
        items = dict_by_key(d["items"], "type")
        custom_fields = items["Membership"].get("customFields")
        custom_fields = (
            dict_by_key(custom_fields, "name") if custom_fields else {}
        )
        for key in custom_fields:
            custom_fields[key] = custom_fields[key]["answer"]
        return cls(
            email=d["payer"]["email"],
            date=arrow.get(d["date"]),
            custom_fields=custom_fields,
        )


@functools.cache
def _get_client():
    return HelloAssoAPI(
        client_id=config["helloasso"]["client_id"],
        client_secret=config["helloasso"]["client_secret"],
        organization_slug=config["helloasso"]["organization_slug"],
    )


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

    def get_form_answers(self, form_slug):
        result = []
        token = None
        while True:
            response = self.call(
                f"/organizations/{self.organization_slug}/forms/Membership/{form_slug}/orders",
                with_details=True,
                continuation_token=token,
            )
            debug(response)
            data = response.json()
            pagination = data["pagination"]
            current_page = data["data"]
            page_index = pagination["pageIndex"]
            pages_total = pagination["totalPages"]
            print(
                f"Got {len(current_page)} results on page {page_index}/{pages_total}"
            )
            result.extend(current_page)
            if page_index == pages_total:
                break
            token = pagination["continuationToken"]
            print("continuation token:", token)

        print("Total results:", len(result))
        return result


@functools.cache
def get_memberships(slug=None) -> list[Membership]:
    slug = slug or config["helloasso"]["form_slug"]
    client = _get_client()
    return [
        Membership.from_helloasso_api(x) for x in client.get_form_answers(slug)
    ]


@functools.cache
def get_memberships_by_email(slug=None) -> dict[str, Membership]:
    result = {}
    for membership in get_memberships(slug):
        if (
            membership.email in result
            and membership.date < result[membership.email].date
        ):
            continue
        result[membership.email] = membership
    return result

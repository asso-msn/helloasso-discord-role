import humps
from helloasso_api import HaApiV5


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

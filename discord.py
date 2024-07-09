import dataclasses
import functools
import sys
from dataclasses import dataclass

import requests

from config import config


def dry(func):
    def wrapper(*args, **kwargs):
        if config["discord"]["dry"]:
            print(
                f"DRY RUN: {func.__name__}({args=}, {kwargs=})", file=sys.stderr
            )
            return
        return func(*args, **kwargs)

    return wrapper


@dry
def send_webhook(webhook_url, content=None, embeds=None):
    data = {"content": content}
    if embeds:
        data["embeds"] = embeds
    response = requests.post(webhook_url, json=data)
    response.raise_for_status()


@dry
def send_webhook_embed(webhook_url, title, content):
    send_webhook(webhook_url, embeds=[{"title": title, "description": content}])


class DiscordAPI:
    BASE_URL = "https://discord.com/api/v10"

    @classmethod
    def call(cls, url, *args, method="GET", ignore_errors=False, **kwargs):
        url = cls.BASE_URL + url
        response = requests.request(
            method,
            url,
            *args,
            json=kwargs.pop("json", None),
            params=kwargs,
            headers={"Authorization": f"Bot {config['discord']['bot_token']}"},
        )
        if not ignore_errors:
            response.raise_for_status()
        return response


@dataclass
class User:
    id: int
    username: str
    roles: list[int] = dataclasses.field(default_factory=list)

    def __str__(self):
        return f"@{self.username}"

    @classmethod
    def from_api(cls, d: dict):
        return cls(
            id=int(d["user"]["id"]),
            username=d["user"]["username"],
            roles=[int(x) for x in d["roles"]],
        )

    @dry
    def add_role(self, role: int):
        DiscordAPI.call(
            f"/guilds/{config['discord']['server_id']}/members/{self.id}/roles/{role}",
            method="PUT",
        )

    @dry
    def remove_role(self, role: int):
        DiscordAPI.call(
            f"/guilds/{config['discord']['server_id']}/members/{self.id}/roles/{role}",
            method="DELETE",
        )

    def has_role(self, role: int) -> bool:
        return role in self.roles

    @dry
    def send_dm(self, content):
        response = DiscordAPI.call(
            "/users/@me/channels",
            method="POST",
            json={"recipient_id": self.id},
            ignore_errors=True,
        )
        if not response.ok:
            print(f"Failed to create DM channel with {self.username}")
            return
        channel_id = response.json()["id"]
        response = DiscordAPI.call(
            f"/channels/{channel_id}/messages",
            method="POST",
            json={"content": content},
            ignore_errors=True,
        )
        if not response.ok:
            print(f"Failed to send DM to {self.username}")
            return


def get_user_by_username(username) -> User:
    """Case insensitive"""

    username = username.lower()
    for member in get_members():
        if member.username.lower() == username:
            return member


def get_user_by_id(user_id) -> User:
    for member in get_members():
        if member.id == user_id:
            return member


@functools.cache
def get_members(guild_id=None) -> list[User]:
    guild_id = guild_id or config["discord"]["server_id"]
    result = []
    limit = 1000
    while True:
        response = DiscordAPI.call(
            f"/guilds/{guild_id}/members", limit=limit
        ).json()
        result.extend(response)
        if len(response) < limit:
            break
    return [User.from_api(x) for x in result if not x["user"].get("bot")]


if __name__ == "__main__":
    obj = get_user_by_username("tina.moe")
    obj.add_role(config["discord"]["role_id"])

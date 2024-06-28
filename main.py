import json
from dataclasses import dataclass
from pathlib import Path

import arrow
import discord
import yaml
from arrow import Arrow

from helloasso import HelloAssoAPI

CONFIG_FILE = Path("config.yml")
SAVE_FILE = Path("save.json")

with CONFIG_FILE.open() as f:
    config = yaml.safe_load(f)


def dict_by_key(iterable, key):
    return {x[key]: x for x in iterable}


@dataclass
class AssoMember:
    date: Arrow
    email: str
    discord_role = False
    discord: str = None
    discord_id: int = None

    def __post_init__(self):
        self.date = arrow.get(self.date)

    @classmethod
    def from_api(cls, d: dict):
        discord_field_name = config["helloasso"]["form_field_name"]
        email = d["payer"]["email"]
        items = dict_by_key(d["items"], "type")
        custom_fields = items["Membership"].get("customFields")
        custom_fields = (
            dict_by_key(custom_fields, "name") if custom_fields else {}
        )
        if discord_field_name not in custom_fields:
            discord = None
        else:
            discord = custom_fields[discord_field_name]["answer"]
        return cls(
            email=email,
            date=d["date"],
            discord=discord,
        )

    @classmethod
    def from_dict(cls, d: dict):
        date = arrow.get(d["timestamp"])
        return cls(
            email=d["email"],
            date=date,
            discord=d["discord_username"],
            discord_id=d["discord_id"],
        )

    @property
    def timestamp(self):
        return self.date.timestamp()

    @property
    def expiration_date(self):
        return self.date.shift(years=1)

    @property
    def is_expired(self):
        return self.expiration_date < arrow.now()


def get_members():
    helloasso_api = HelloAssoAPI(**config["helloasso"])
    members_form_entries = helloasso_api.get_form(
        config["helloasso"]["form_slug"]
    )
    return [AssoMember.from_api(entry) for entry in members_form_entries]


class DiscordBot(discord.Client):
    data = {}
    task = None

    async def task_get_users(self):
        self.data["discord_users_by_username"] = {}
        for user in self.get_guild(config["discord"]["server"]).members:
            self.data["discord_users_by_username"][user.name] = user

    async def on_ready(self):
        print("Logged in as", self.user)
        await getattr(self, f"task_{self.task}")()
        await self.close()

    def run(self):
        return super().run(config["discord"]["token"])


def main():
    intents = discord.Intents.default()
    intents.members = True
    discord_bot = DiscordBot(intents=intents)

    discord_bot.task = "get_users"
    discord_bot.run()
    discord_users_by_username = discord_bot.data["discord_users_by_username"]

    helloasso_members = get_members()
    for member in helloasso_members:
        print(member, member.expiration_date.humanize())

    if not SAVE_FILE.exists():
        saved_members_by_email = {}
    else:
        with SAVE_FILE.open() as f:
            saved_members_by_email = {
                key: AssoMember.from_dict(dict(email=key, **value))
                for key, value in json.load(f).items()
            }
    for member in helloasso_members:
        if (
            member.email in saved_members_by_email
            and member.timestamp
            > saved_members_by_email[member.email].timestamp
        ):
            saved_members_by_email[member.email] = member
        saved_members_by_email[member.email] = member

    for member in saved_members_by_email.values():
        print(member, member.expiration_date.humanize())
        if not member.discord:
            continue
        discord_user = discord_users_by_username.get(member.discord)
        if not discord_user:
            print("User not found", member.discord)
            continue
        member.discord_id = discord_user.id
        for role in discord_user.roles:
            if role.id == config["discord"]["role"]:
                member.discord_role = True
                break
        if member.is_expired and member.discord_role:
            discord_bot.task = "remove_role"
            discord_bot.data["discord_user"] = discord_user
            # discord_bot.run()

    with SAVE_FILE.open("w") as f:
        json.dump(
            {
                member.email: {
                    "timestamp": member.timestamp,
                    "discord_username": member.discord,
                    "expired": member.is_expired,
                    "discord_id": member.discord_id,
                    "role": member.discord_role,
                }
                for member in helloasso_members
            },
            f,
            indent=2,
        )


if __name__ == "__main__":
    main()

import json
from dataclasses import dataclass

import arrow
from arrow import Arrow

import discord
import helloasso
from config import SAVE_FILE, config


@dataclass
class AssoMember:
    date: Arrow
    email: str
    discord_role: bool = False
    discord_username: str = None
    discord_id: int = None
    discord: "discord.User" = None

    def __str__(self):
        result = self.email
        if self.discord_username:
            result += f" ({self.discord_username})"
        return result

    def __post_init__(self):
        self.date = arrow.get(self.date)
        self.update_discord()

    def update_discord(self):
        if self.discord_id:
            self.discord_id = int(self.discord_id)
            self.discord = discord.get_user_by_id(self.discord_id)
        elif self.discord_username:
            username = self.discord_username
            if username.startswith("@"):
                username = username[1:]
            if "#" in username:
                username, _discriminator = username.split("#")
            self.discord = discord.get_user_by_username(username)

        if self.discord:
            if self.discord_id != self.discord.id:
                print(
                    f"Fixed Discord ID {self.discord_id} -> {self.discord.id} for {self})"
                )
                self.discord_id = self.discord.id
            if self.discord.username != self.discord_username:
                print(
                    f"Fixed Discord username {self.discord_username} -> {self.discord.username} for {self}"
                )
                self.discord_username = self.discord.username

            self.discord_role = self.discord.has_role(
                config["discord"]["role_id"]
            )

    @staticmethod
    def get_discord_from_helloasso(m: helloasso.Membership):
        return m.custom_fields.get(config["helloasso"]["form_field_name"])

    @classmethod
    def from_helloasso_api(cls, membership: helloasso.Membership):
        return cls(
            date=membership.date,
            email=membership.email,
            discord_username=cls.get_discord_from_helloasso(membership),
        )

    @classmethod
    def from_save(cls, d: dict):
        date = arrow.get(d["membership_latest"])
        return cls(
            date=date,
            email=d["email"],
            discord_role=d["discord_role"],
            discord_username=d["discord_username"],
            discord_id=d["discord_id"],
        )

    def update_from_helloasso_api(self, membership: helloasso.Membership):
        self.date = membership.date
        discord_username = self.get_discord_from_helloasso(membership)
        if discord_username != self.discord_username:
            print(
                f"Updated Discord username {self.discord_username} -> {discord_username} for {self}"
            )
            self.discord_username = discord_username
            self.discord_id = None
            self.update_discord()

    def to_save(self) -> dict:
        return {
            # We exclude email since it's the map key
            # "email": self.email,
            "membership_latest": self.timestamp,
            "discord_username": self.discord_username,
            "discord_id": self.discord_id,
            # only for debugging, fetched on the fly from API
            "discord_role": self.discord_role,
            # only for debugging, calculated on the fly from timestamp
            "membership_expired": self.is_expired,
        }

    @property
    def timestamp(self):
        return self.date.timestamp()

    @property
    def expiration_date(self):
        return self.date.shift(years=config["membership_duration_years"])

    @property
    def is_expired(self):
        return self.expiration_date < arrow.now()


def get_saved_members() -> dict[str, AssoMember]:
    """Return a dict of saved members by email."""

    if not SAVE_FILE.exists():
        return {}

    with SAVE_FILE.open() as f:
        return {
            email: AssoMember.from_save({"email": email, **props})
            for email, props in json.load(f).items()
        }


def save_members(members: dict[str, AssoMember]):
    with SAVE_FILE.open("w") as f:
        json.dump(
            {email: member.to_save() for email, member in members.items()},
            f,
            indent=2,
        )


def refresh_users():
    helloasso_members = helloasso.get_memberships_by_email()
    discord_members = discord.get_members()
    membership_role = config["discord"]["role_id"]
    members = get_saved_members()

    for membership in helloasso_members.values():
        if membership.email not in members:
            members[membership.email] = AssoMember.from_helloasso_api(
                membership
            )
        elif membership.date > members[membership.email].date:
            members[membership.email].update_from_helloasso_api(membership)

    for member in members.values():
        if member.email not in helloasso_members:
            print(f"{member} in save file but not found in HelloAsso!!")

    members_by_discord_id = {
        member.discord_id: member
        for member in members.values()
        if member.discord_id
    }

    for member in discord_members:
        # Discord users with the role but no membership found
        # it probably means their Discord ID is unknown
        if member.id not in members_by_discord_id:
            if member.has_role(membership_role):
                print(
                    f"Discord member {member} not found in HelloAsso but has role!!",
                    "Please update the save file with the Discord ID",
                )

    for member in members.values():
        if member.discord_username and not member.discord:
            print(
                f"Discord member {member} not found in Discord but has username!!",
                "Please update the save file with the Discord ID",
            )

    save_members(members)


def update_discord_roles():
    membership_role = config["discord"]["role_id"]

    for member in get_saved_members().values():
        if not member.discord:
            continue

        if not member.is_expired and not member.discord_role:
            print(f"Adding Discord role to {member}")
            member.discord.add_role(membership_role)
            member.discord_role = True
            member.discord.send_dm(config["discord"]["welcome_message"])

        if member.is_expired and member.discord_role:
            print(f"Removing Discord role from {member}")
            member.discord.remove_role(membership_role)
            member.discord_role = False
            if member.date > arrow.now().shift(
                days=-config["discord"]["delay_days"]
            ):
                message = config["discord"]["removal_message"]
            else:
                message = config["discord"]["removal_message_delayed"].format(
                    delay=member.expiration_date.humanize(locale="fr")
                )
            try:
                member.discord.send_dm(message)
            except Exception as e:
                print(f"Failed to send DM to {member}: {e}")


def print_report():
    members = get_saved_members().values()
    members_active = []
    members_expired = []
    members_with_discord = []
    members_without_discord = []
    members_sub_range = {
        "9 months +": 0,
        "6 to 9 months": 0,
        "3 to 6 months": 0,
        "1 to 3 month": 0,
        "< 1 month": 0,
    }
    members_expired_range = {
        "1 year +": 0,
        "6 to 12 months": 0,
        "3 to 6 months": 0,
        "1 to 3 month": 0,
        "< 1 month": 0,
    }
    short_months = config["membership_expiration_delay_months_short"]
    members_expired_short = []
    members_expired_short_without_discord = []

    for member in members:
        if not member.is_expired:
            members_active.append(member)
            if member.date <= arrow.now().shift(months=-9):
                members_sub_range["9 months +"] += 1
            elif member.date <= arrow.now().shift(months=-6):
                members_sub_range["6 to 9 months"] += 1
            elif member.date <= arrow.now().shift(months=-3):
                members_sub_range["3 to 6 months"] += 1
            elif member.date <= arrow.now().shift(months=-1):
                members_sub_range["1 to 3 month"] += 1
            else:
                members_sub_range["< 1 month"] += 1

            if member.discord:
                members_with_discord.append(member)
            else:
                members_without_discord.append(member)
            continue

        members_expired.append(member)

        if member.expiration_date <= arrow.now().shift(years=-1):
            members_expired_range["1 year +"] += 1
        elif member.expiration_date <= arrow.now().shift(months=-6):
            members_expired_range["6 to 12 months"] += 1
        elif member.expiration_date <= arrow.now().shift(months=-3):
            members_expired_range["3 to 6 months"] += 1
        elif member.expiration_date <= arrow.now().shift(months=-1):
            members_expired_range["1 to 3 month"] += 1
        else:
            members_expired_range["< 1 month"] += 1

        if member.expiration_date >= arrow.now().shift(months=-short_months):
            members_expired_short.append(member)
            if not member.discord:
                members_expired_short_without_discord.append(member)

    print("Unique members:", len(members))
    print("Active members:", len(members_active))
    print("Expired members:", len(members_expired))
    print("Subscription date range:", members_sub_range)
    print("Expiration time range:", members_expired_range)
    print("Active members with Discord:", len(members_with_discord))
    print("Active members without Discord:", len(members_without_discord))
    print(
        f"Members expired in the last {short_months} months",
        f"({len(members_expired_short)}):",
    )
    for member in members_expired_short:
        print(f"- {member} expired {member.expiration_date.humanize()}")
    print(
        f"Members expired in the last {short_months} months without Discord",
        f"({len(members_expired_short_without_discord)}):",
    )
    for member in members_expired_short_without_discord:
        print(f"- {member} expired {member.expiration_date.humanize()}")


def main():
    refresh_users()
    update_discord_roles()
    print_report()


if __name__ == "__main__":
    main()

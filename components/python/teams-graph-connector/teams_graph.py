"""Microsoft Teams through Graph and the Bot Framework connector: the gates (transitive group membership), the
war-room channel (create, add members), posting and pinning (proactive delivery), and the app token.

Channel messages from the bot go through the Bot Framework connector (`serviceUrl`) when a conversation
reference exists, otherwise through Graph with the application's resource-specific consent (RSC) permissions.
Every proactive delivery returns an id or raises; nothing fails silently.
"""
from __future__ import annotations
import itertools, time, urllib.parse


class UpstreamError(Exception):
    pass

GRAPH = "https://graph.microsoft.com/v1.0"
MAX_MESSAGE = 4000


def chunk(text: str, limit: int = MAX_MESSAGE) -> list[str]:
    """Split on paragraph boundaries, then lines, then hard, and mark the parts (n/m)."""
    if len(text) <= limit:
        return [text]
    parts, cur = [], ""
    for para in text.split("\n\n"):
        cand = (cur + "\n\n" + para) if cur else para
        if len(cand) <= limit - 12:
            cur = cand; continue
        if cur: parts.append(cur); cur = ""
        while len(para) > limit - 12:
            cut = para.rfind("\n", 0, limit - 12)
            cut = cut if cut > 0 else limit - 12
            parts.append(para[:cut]); para = para[cut:].lstrip("\n")
        cur = para
    if cur: parts.append(cur)
    m = len(parts)
    return [f"({i}/{m}) {p}" for i, p in enumerate(parts, 1)]


class AppToken:
    """Client-credentials token for the bot's Entra application, cached until shortly before expiry."""

    def __init__(self, http, secrets, tenant_id: str, app_id: str, secret_name: str, scope: str = "https://graph.microsoft.com/.default"):
        self.http, self.secrets, self.tenant, self.app_id, self.secret_name, self.scope = http, secrets, tenant_id, app_id, secret_name, scope
        self._tok, self._exp = None, 0.0

    def get(self) -> str:
        if self._tok and time.time() < self._exp - 60:
            return self._tok
        r = self.http.form(f"https://login.microsoftonline.com/{self.tenant}/oauth2/v2.0/token",
                           {"grant_type": "client_credentials", "client_id": self.app_id, "client_secret": self.secrets.get(self.secret_name), "scope": self.scope})
        self._tok, self._exp = r["access_token"], time.time() + int(r.get("expires_in", 3600))
        return self._tok


class GraphClient:
    def __init__(self, http, token: AppToken, bot_token: AppToken | None = None):
        self.http, self.token, self.bot_token = http, token, bot_token

    def _h(self): return {"Authorization": "Bearer " + self.token.get()}

    # ---- gates ----
    def check_member_groups(self, user_id: str, group_ids: list) -> list:
        """Transitive membership (checkMemberGroups): the ids in `group_ids` the user belongs to."""
        r = self.http.json("POST", f"{GRAPH}/users/{urllib.parse.quote(user_id)}/checkMemberGroups", self._h(), {"groupIds": list(group_ids)[:20]})
        return list(r.get("value", []))

    # ---- war room ----
    def create_channel(self, team_id: str, name: str, description: str) -> dict:
        r = self.http.json("POST", f"{GRAPH}/teams/{team_id}/channels", self._h(), {"displayName": name[:50], "description": description[:1024], "membershipType": "standard"})
        return {"channel_id": r["id"], "url": r.get("webUrl"), "team_id": team_id}

    def post_message(self, team_id: str, channel_id: str, html: str, mentions: list | None = None) -> dict:
        body = {"body": {"contentType": "html", "content": html}}
        if mentions:
            body["mentions"] = [{"id": i, "mentionText": m["name"], "mentioned": {"user": {"id": m["id"], "displayName": m["name"], "userIdentityType": "aadUser"}}} for i, m in enumerate(mentions)]
        r = self.http.json("POST", f"{GRAPH}/teams/{team_id}/channels/{channel_id}/messages", self._h(), body)
        return {"message_id": r["id"]}

    def post_card(self, team_id: str, channel_id: str, card: dict, text: str = "") -> dict:
        att_id = "card1"
        body = {"body": {"contentType": "html", "content": (text or "") + f'<attachment id="{att_id}"></attachment>'},
                "attachments": [{"id": att_id, "contentType": "application/vnd.microsoft.card.adaptive", "content": __import__("json").dumps(card)}]}
        r = self.http.json("POST", f"{GRAPH}/teams/{team_id}/channels/{channel_id}/messages", self._h(), body)
        return {"message_id": r["id"]}

    def pin_message(self, team_id: str, channel_id: str, message_id: str) -> dict:
        r = self.http.json("POST", f"{GRAPH}/teams/{team_id}/channels/{channel_id}/pinnedMessages", self._h(), {"message@odata.bind": f"{GRAPH}/teams/{team_id}/channels/{channel_id}/messages/{message_id}"})
        return {"pinned_id": r.get("id")}

    def archive_channel(self, team_id: str, channel_id: str) -> dict:
        self.http.json("POST", f"{GRAPH}/teams/{team_id}/channels/{channel_id}/archive", self._h(), {}, expect=(204, 200, 202))
        return {"archived": channel_id}

    def add_member(self, team_id: str, channel_id: str, user_id: str) -> dict:
        r = self.http.json("POST", f"{GRAPH}/teams/{team_id}/channels/{channel_id}/members", self._h(),
                           {"@odata.type": "#microsoft.graph.aadUserConversationMember", "roles": [], "user@odata.bind": f"{GRAPH}/users('{user_id}')"})
        return {"member_id": r.get("id")}

    def reply_via_connector(self, service_url: str, conversation_id: str, activity: dict) -> dict:
        """Bot Framework connector: reply into an existing conversation (the on-call channel thread)."""
        if not self.bot_token:
            raise UpstreamError("teams: no bot token for the connector")
        r = self.http.json("POST", f"{service_url.rstrip('/')}/v3/conversations/{urllib.parse.quote(conversation_id)}/activities", {"Authorization": "Bearer " + self.bot_token.get()}, activity)
        return {"message_id": r.get("id")}

    # ---- change-notification subscriptions (basic notifications: ids only, no encryption certificate) ----
    def create_subscription(self, notification_url: str, lifecycle_url: str, resource: str, expiration_iso: str, client_state: str, change_type: str = "created") -> dict:
        body = {"changeType": change_type, "notificationUrl": notification_url, "lifecycleNotificationUrl": lifecycle_url,
                "resource": resource, "expirationDateTime": expiration_iso, "clientState": client_state}
        r = self.http.json("POST", f"{GRAPH}/subscriptions", self._h(), body)
        return {"id": r["id"], "expirationDateTime": r.get("expirationDateTime")}

    def renew_subscription(self, sub_id: str, expiration_iso: str) -> dict:
        r = self.http.json("PATCH", f"{GRAPH}/subscriptions/{urllib.parse.quote(sub_id)}", self._h(), {"expirationDateTime": expiration_iso})
        return {"id": sub_id, "expirationDateTime": r.get("expirationDateTime")}

    def delete_subscription(self, sub_id: str) -> dict:
        self.http.json("DELETE", f"{GRAPH}/subscriptions/{urllib.parse.quote(sub_id)}", self._h(), None, expect=(204, 200, 202, 404))
        return {"deleted": sub_id}

    def list_subscriptions(self) -> list:
        return self.http.json("GET", f"{GRAPH}/subscriptions", self._h()).get("value", [])

    def get_message(self, team_id: str, channel_id: str, message_id: str) -> dict:
        return self.http.json("GET", f"{GRAPH}/teams/{team_id}/channels/{channel_id}/messages/{urllib.parse.quote(message_id)}", self._h())

    def list_messages(self, team_id: str, channel_id: str, top: int = 50) -> list:
        return self.http.json("GET", f"{GRAPH}/teams/{team_id}/channels/{channel_id}/messages?$top={int(top)}", self._h()).get("value", [])


class FakeTeams:
    """In-memory Teams: users with group memberships, teams, channels, posted messages and cards, pins."""

    def __init__(self):
        self.groups: dict[str, set] = {}          # user_id -> {group ids}
        self.channels: dict[str, dict] = {}; self.messages: list = []; self.pins: list = []; self.members: dict[str, set] = {}
        self.subscriptions: dict[str, dict] = {}; self.channel_msgs: dict[str, list] = {}   # ambient: subscriptions + incoming human messages (Graph chatMessage shape)
        self._n = itertools.count(1); self._subn = itertools.count(1); self.down = False; self.fail_next = 0

    def add_user(self, user_id: str, groups: list): self.groups[user_id] = set(groups)

    def _up(self):
        if self.down: raise UpstreamError("teams: unavailable")
        if self.fail_next > 0:
            self.fail_next -= 1; raise UpstreamError("teams: transient 503")

    def check_member_groups(self, user_id, group_ids): self._up(); return [g for g in group_ids if g in self.groups.get(user_id, set())]
    def create_channel(self, team_id, name, description):
        self._up(); cid = f"19:chan{next(self._n)}@thread.tacv2"; self.channels[cid] = {"team_id": team_id, "name": name, "description": description, "archived": False}
        return {"channel_id": cid, "url": f"https://teams.example/l/channel/{cid}", "team_id": team_id}
    def post_message(self, team_id, channel_id, html, mentions=None):
        self._up(); mid = str(next(self._n)); self.messages.append({"id": mid, "channel": channel_id, "html": html, "mentions": [m["id"] for m in (mentions or [])], "kind": "message"}); return {"message_id": mid}
    def post_card(self, team_id, channel_id, card, text=""):
        self._up(); mid = str(next(self._n)); self.messages.append({"id": mid, "channel": channel_id, "card": card, "text": text, "kind": "card"}); return {"message_id": mid}
    def pin_message(self, team_id, channel_id, message_id): self._up(); self.pins.append((channel_id, message_id)); return {"pinned_id": f"pin{message_id}"}
    def archive_channel(self, team_id, channel_id): self._up(); self.channels[channel_id]["archived"] = True; return {"archived": channel_id}
    def add_member(self, team_id, channel_id, user_id): self._up(); self.members.setdefault(channel_id, set()).add(user_id); return {"member_id": f"m-{user_id}"}
    def reply_via_connector(self, service_url, conversation_id, activity):
        self._up(); mid = str(next(self._n)); self.messages.append({"id": mid, "channel": conversation_id, "html": activity.get("text", ""), "card": (activity.get("attachments") or [{}])[0].get("content"), "kind": "reply"}); return {"message_id": mid}

    def in_channel(self, channel_id): return [m for m in self.messages if m["channel"] == channel_id]

    # ---- subscriptions and incoming channel messages (Graph chatMessage shape) ----
    def create_subscription(self, notification_url, lifecycle_url, resource, expiration_iso, client_state, change_type="created"):
        self._up(); sid = f"sub-{next(self._subn)}"
        self.subscriptions[sid] = {"id": sid, "resource": resource, "expirationDateTime": expiration_iso, "notificationUrl": notification_url, "lifecycleNotificationUrl": lifecycle_url, "changeType": change_type}
        return {"id": sid, "expirationDateTime": expiration_iso}
    def renew_subscription(self, sub_id, expiration_iso):
        self._up()
        if sub_id not in self.subscriptions: raise UpstreamError("graph: 404 subscription")
        self.subscriptions[sub_id]["expirationDateTime"] = expiration_iso; return {"id": sub_id, "expirationDateTime": expiration_iso}
    def delete_subscription(self, sub_id): self._up(); self.subscriptions.pop(sub_id, None); return {"deleted": sub_id}
    def list_subscriptions(self): self._up(); return list(self.subscriptions.values())
    def add_channel_message(self, channel_id, message): self.channel_msgs.setdefault(channel_id, []).append(message)   # test/live-mirror helper
    def get_message(self, team_id, channel_id, message_id):
        self._up()
        for m in self.channel_msgs.get(channel_id, []):
            if str(m.get("id")) == str(message_id): return m
        raise UpstreamError("graph: 404 message")
    def list_messages(self, team_id, channel_id, top=50): self._up(); return list(self.channel_msgs.get(channel_id, []))[-int(top):]

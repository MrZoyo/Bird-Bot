import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace

from bot.cogs.tickets import cog as tickets_cog
from bot.cogs.tickets import modals as tickets_modals
from bot.cogs.tickets import views as tickets_views
from bot.cogs.tickets.cog import TicketsCog
from bot.cogs.tickets.modals import CloseTicketModal, TicketConfirmModal
from bot.cogs.tickets.views import TicketThreadView


TICKET_TEXT = {
    "tickets.messages.ticket_modal_confirm_title": "Confirm {type_name}",
    "tickets.messages.ticket_modal_confirm_label": "Type yes for {type_name}",
    "tickets.messages.ticket_modal_confirm_placeholder": "yes",
    "tickets.messages.ticket_confirmation_failed": "confirmation failed",
    "tickets.messages.old_system_no_new_channel": "no ticket channel",
    "tickets.messages.ticket_thread_not_found": "ticket channel not found",
    "tickets.messages.ticket_create_db_error": "ticket db error",
    "tickets.messages.ticket_created_title": "Ticket #{number} {type_name}",
    "tickets.messages.ticket_created_creator": "Creator",
    "tickets.messages.ticket_created_time": "Created",
    "tickets.messages.ticket_instructions_title": "Instructions",
    "tickets.messages.ticket_instructions": "Please wait",
    "tickets.messages.ticket_create_success": "created {thread}",
    "tickets.messages.ticket_created_dm_title": "Ticket created",
    "tickets.messages.ticket_created_dm_content": "Ticket #{number} {type_name}",
    "tickets.messages.ticket_jump_button": "Open ticket",
    "tickets.messages.ticket_thread_create_error": "ticket create error",
    "tickets.messages.ticket_accept_button": "Accept",
    "tickets.messages.ticket_accept_button_disabled": "Accepted",
    "tickets.messages.ticket_add_user_button": "Add user",
    "tickets.messages.ticket_close_button": "Close",
    "tickets.messages.ticket_admin_only": "admin only",
    "tickets.messages.ticket_already_accepted": "already accepted",
    "tickets.messages.ticket_accepted_title": "Accepted",
    "tickets.messages.ticket_accepted_content": "accepted by {user}",
    "tickets.messages.ticket_accepted_dm_title": "Accepted DM",
    "tickets.messages.ticket_accepted_dm_content": "accepted by {user}",
    "tickets.messages.ticket_accept_get_info_error": "accept error",
    "tickets.messages.close_modal_title": "Close ticket",
    "tickets.messages.close_modal_label": "Reason",
    "tickets.messages.close_modal_placeholder": "reason",
    "tickets.messages.ticket_already_closed": "already closed",
    "tickets.messages.ticket_close_stats_error": "close failed",
    "tickets.messages.close_dm_title": "Closed",
    "tickets.messages.close_dm_content": "closed by {closer}; reason={reason}",
    "tickets.messages.ticket_close_error": "close error",
}


class FakeResponse:
    def __init__(self, events):
        self.events = events
        self.messages = []
        self.modals = []
        self.edited_messages = []
        self.deferred = []
        self._done = False

    async def send_message(self, content=None, *, embed=None, ephemeral=False, **kwargs):
        self._done = True
        self.events.append(("response", content or (embed.title if embed else None)))
        self.messages.append({
            "content": content,
            "embed": embed,
            "ephemeral": ephemeral,
            **kwargs,
        })

    async def send_modal(self, modal):
        self._done = True
        self.events.append(("modal", type(modal).__name__))
        self.modals.append(modal)

    async def defer(self, *, ephemeral=False, **kwargs):
        self._done = True
        self.events.append(("defer", ephemeral))
        self.deferred.append({"ephemeral": ephemeral, **kwargs})

    async def edit_message(self, *, view=None, **kwargs):
        self._done = True
        self.events.append(("edit_message", type(view).__name__))
        self.edited_messages.append({"view": view, **kwargs})

    def is_done(self):
        return self._done


class FakeFollowup:
    def __init__(self, events):
        self.events = events
        self.messages = []

    async def send(self, content=None, *, embed=None, ephemeral=False, **kwargs):
        self.events.append(("followup", content or (embed.title if embed else None)))
        self.messages.append({
            "content": content,
            "embed": embed,
            "ephemeral": ephemeral,
            **kwargs,
        })


class FakeInteraction:
    def __init__(self, user, guild, events):
        self.user = user
        self.guild = guild
        self.response = FakeResponse(events)
        self.followup = FakeFollowup(events)


@dataclass
class FakeUser:
    id: int
    display_name: str
    name: str
    mention: str
    bot: bool = False
    guild_permissions: object = field(default_factory=lambda: SimpleNamespace(manage_channels=False))
    dms: list = field(default_factory=list)

    def get_role(self, role_id):
        return None

    async def send(self, *, embed=None, view=None, **kwargs):
        self.dms.append({"embed": embed, "view": view, **kwargs})


class FakeMessage:
    def __init__(self, message_id, events):
        self.id = message_id
        self.events = events
        self.edits = []

    async def edit(self, *, view=None, **kwargs):
        self.events.append(("control_edit", type(view).__name__))
        self.edits.append({"view": view, **kwargs})


class FakeThread:
    def __init__(self, thread_id, guild, events):
        self.id = thread_id
        self.guild = guild
        self.events = events
        self.mention = f"<#{thread_id}>"
        self.archived = False
        self.sent_messages = []
        self.added_users = []
        self.deleted = False
        self.edits = []

    async def add_user(self, user):
        self.events.append(("thread_add_user", user.id))
        self.added_users.append(user)

    async def send(self, *, embeds=None, view=None, **kwargs):
        self.events.append(("thread_send", type(view).__name__))
        message = FakeMessage(888, self.events)
        self.sent_messages.append({"embeds": embeds, "view": view, **kwargs})
        return message

    async def fetch_message(self, message_id):
        self.events.append(("thread_fetch_message", message_id))
        return FakeMessage(message_id, self.events)

    async def delete(self):
        self.events.append(("thread_delete", self.id))
        self.deleted = True

    async def edit(self, *, locked=False, archived=False, **kwargs):
        self.events.append(("thread_edit", locked, archived))
        self.archived = archived
        self.edits.append({"locked": locked, "archived": archived, **kwargs})


class FakeTicketChannel:
    def __init__(self, channel_id, guild, events):
        self.id = channel_id
        self.guild = guild
        self.events = events
        self.created_threads = []

    async def create_thread(self, *, name, **kwargs):
        self.events.append(("create_thread", name))
        thread = FakeThread(700, self.guild, self.events)
        self.guild.threads[thread.id] = thread
        self.created_threads.append(thread)
        return thread


class FakeGuild:
    def __init__(self, guild_id=1):
        self.id = guild_id
        self.channels = {}
        self.threads = {}
        self.members = {}

    def get_channel(self, channel_id):
        return self.channels.get(channel_id)

    def get_thread(self, thread_id):
        return self.threads.get(thread_id)

    def get_member(self, user_id):
        return self.members.get(user_id)

    def get_role(self, role_id):
        return None


class FakeBot:
    def __init__(self, events):
        self.events = events
        self.user = SimpleNamespace(id=999, avatar=None)
        self.views = []
        self.channels = {}

    def add_view(self, view):
        self.events.append(("bot_add_view", type(view).__name__))
        self.views.append(view)

    def get_channel(self, channel_id):
        return self.channels.get(channel_id)


class FakeTicketsDB:
    def __init__(self, events, *, create_success=True, accept_success=True, close_success=True):
        self.events = events
        self.create_success = create_success
        self.accept_success = accept_success
        self.close_success = close_success
        self.config = {
            "ticket_channel_id": 10,
            "info_channel_id": 20,
            "main_message_id": 30,
        }
        self.ticket_data = {
            "thread_id": 700,
            "message_id": 888,
            "creator_id": 123,
            "ticket_number": 7,
            "is_accepted": 1,
        }

    async def get_config(self):
        self.events.append(("db_get_config",))
        return self.config

    async def get_ticket_number(self):
        self.events.append(("db_ticket_number",))
        return 7

    async def create_ticket(self, thread_id, message_id, creator_id, type_name, ticket_channel_id, ticket_number):
        self.events.append(("db_create_ticket", thread_id, message_id, creator_id, type_name, ticket_number))
        return self.create_success

    async def update_ticket_message_id(self, thread_id, message_id):
        self.events.append(("db_update_message_id", thread_id, message_id))
        self.ticket_data["message_id"] = message_id
        return True

    async def accept_ticket(self, thread_id, accepted_by):
        self.events.append(("db_accept_ticket", thread_id, accepted_by))
        return self.accept_success

    async def fetch_ticket(self, thread_id):
        self.events.append(("db_fetch_ticket", thread_id))
        return self.ticket_data

    async def close_ticket(self, thread_id, closed_by, reason):
        self.events.append(("db_close_ticket", thread_id, closed_by, reason))
        return self.close_success


def _install_translations(monkeypatch):
    translator = lambda key, **kwargs: TICKET_TEXT[key]
    monkeypatch.setattr(tickets_cog, "t", translator)
    monkeypatch.setattr(tickets_views, "t", translator)
    monkeypatch.setattr(tickets_modals, "t", translator)


def _build_cog(events, db):
    cog = object.__new__(TicketsCog)
    cog.bot = FakeBot(events)
    cog.db_manager = db
    cog.conf = {"admin_roles": [], "admin_users": [], "max_admins_per_ticket": 50}
    cog.ticket_types = {
        "support": {
            "description": "Support",
            "guide": "Describe the issue",
            "button_color": "b",
            "admin_roles": [],
            "admin_users": [],
        }
    }

    async def add_admins_to_ticket(thread, type_name, creator, ticket_number):
        events.append(("add_admins", thread.id, type_name, creator.id, ticket_number))

    async def log_ticket_action(action, thread_id, user, **kwargs):
        events.append(("log", action, thread_id, user.id))

    async def is_admin_for_type(user, ticket_type=None):
        events.append(("is_admin", user.id, ticket_type))
        return getattr(user, "is_ticket_admin", False)

    cog.add_admins_to_ticket = add_admins_to_ticket
    cog.log_ticket_action = log_ticket_action
    cog.is_admin_for_type = is_admin_for_type
    return cog


def test_ticket_confirmation_modal_defers_then_creates_ticket(monkeypatch):
    async def scenario():
        _install_translations(monkeypatch)
        events = []

        class FakeCog:
            async def create_ticket_thread(self, interaction, type_name, type_data):
                events.append(("create_ticket_thread", type_name, type_data["guide"]))

        user = FakeUser(123, "Creator", "creator", "<@123>")
        interaction = FakeInteraction(user, FakeGuild(), events)
        modal = TicketConfirmModal(
            FakeCog(),
            "support",
            {"guide": "Describe the issue"},
        )
        modal.confirm_input._value = "yes"

        await modal.on_submit(interaction)

        assert events == [
            ("defer", True),
            ("create_ticket_thread", "support", "Describe the issue"),
        ]

    asyncio.run(scenario())


def test_create_ticket_thread_success_responds_before_admin_log_and_dm(monkeypatch):
    async def scenario():
        _install_translations(monkeypatch)
        events = []
        db = FakeTicketsDB(events)
        cog = _build_cog(events, db)
        guild = FakeGuild()
        channel = FakeTicketChannel(10, guild, events)
        guild.channels[channel.id] = channel
        user = FakeUser(123, "Creator", "creator", "<@123>")
        guild.members[user.id] = user
        interaction = FakeInteraction(user, guild, events)

        await cog.create_ticket_thread(
            interaction,
            "support",
            cog.ticket_types["support"],
        )

        event_names = [event[0] for event in events]
        assert event_names == [
            "db_get_config",
            "db_ticket_number",
            "create_thread",
            "thread_add_user",
            "db_create_ticket",
            "bot_add_view",
            "thread_send",
            "db_update_message_id",
            "followup",
            "add_admins",
            "log",
        ]
        assert user.dms[0]["embed"].title == "Ticket created"
        assert interaction.followup.messages[0]["content"] == "created <#700>"
        assert channel.created_threads[0].sent_messages[0]["view"].thread_id == 700

    asyncio.run(scenario())


def test_create_ticket_thread_deletes_thread_when_db_create_fails(monkeypatch):
    async def scenario():
        _install_translations(monkeypatch)
        events = []
        db = FakeTicketsDB(events, create_success=False)
        cog = _build_cog(events, db)
        guild = FakeGuild()
        channel = FakeTicketChannel(10, guild, events)
        guild.channels[channel.id] = channel
        user = FakeUser(123, "Creator", "creator", "<@123>")
        interaction = FakeInteraction(user, guild, events)

        await cog.create_ticket_thread(
            interaction,
            "support",
            cog.ticket_types["support"],
        )

        event_names = [event[0] for event in events]
        assert event_names == [
            "db_get_config",
            "db_ticket_number",
            "create_thread",
            "thread_add_user",
            "db_create_ticket",
            "thread_delete",
            "followup",
        ]
        assert interaction.followup.messages[0]["content"] == "ticket db error"
        assert cog.bot.views == []
        assert channel.created_threads[0].sent_messages == []

    asyncio.run(scenario())


def test_accept_callback_rejects_non_admin_without_db_write(monkeypatch):
    async def scenario():
        _install_translations(monkeypatch)
        events = []
        db = FakeTicketsDB(events)
        cog = _build_cog(events, db)
        user = FakeUser(456, "User", "user", "<@456>")
        interaction = FakeInteraction(user, FakeGuild(), events)
        view = TicketThreadView(cog, thread_id=700, type_name="support")

        await view.accept_callback(interaction)

        assert events == [
            ("is_admin", 456, "support"),
            ("response", "admin only"),
        ]
        assert interaction.response.messages[0]["ephemeral"] is True

    asyncio.run(scenario())


def test_accept_callback_updates_view_before_followup_and_dms_creator(monkeypatch):
    async def scenario():
        _install_translations(monkeypatch)
        events = []
        db = FakeTicketsDB(events)
        cog = _build_cog(events, db)
        guild = FakeGuild()
        creator = FakeUser(123, "Creator", "creator", "<@123>")
        guild.members[creator.id] = creator
        admin = FakeUser(456, "Admin", "admin", "<@456>")
        admin.is_ticket_admin = True
        interaction = FakeInteraction(admin, guild, events)
        view = TicketThreadView(cog, thread_id=700, type_name="support")

        await view.accept_callback(interaction)

        event_names = [event[0] for event in events]
        assert event_names == [
            "is_admin",
            "db_accept_ticket",
            "bot_add_view",
            "edit_message",
            "followup",
            "log",
            "db_fetch_ticket",
        ]
        assert interaction.response.edited_messages[0]["view"].children[0].disabled is True
        assert interaction.followup.messages[0]["embed"].title == "Accepted"
        assert creator.dms[0]["embed"].title == "Accepted DM"

    asyncio.run(scenario())


def test_close_ticket_modal_closes_db_before_response_and_archives_thread(monkeypatch):
    async def scenario():
        _install_translations(monkeypatch)
        events = []
        db = FakeTicketsDB(events)
        cog = _build_cog(events, db)
        guild = FakeGuild()
        thread = FakeThread(700, guild, events)
        guild.threads[thread.id] = thread
        creator = FakeUser(123, "Creator", "creator", "<@123>")
        guild.members[creator.id] = creator
        admin = FakeUser(456, "Admin", "admin", "<@456>")
        interaction = FakeInteraction(admin, guild, events)
        modal = CloseTicketModal(cog, thread_id=700)
        modal.reason_input._value = "done"

        await modal.on_submit(interaction)

        event_names = [event[0] for event in events]
        assert event_names == [
            "db_close_ticket",
            "response",
            "db_fetch_ticket",
            "thread_fetch_message",
            "db_fetch_ticket",
            "control_edit",
            "log",
            "thread_edit",
            "db_fetch_ticket",
        ]
        assert interaction.response.messages[0]["embed"].title == "Closed"
        assert thread.edits == [{"locked": True, "archived": True}]
        assert creator.dms[0]["embed"].title == "Closed"

    asyncio.run(scenario())

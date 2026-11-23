"""Tests that answers meant to be ephemeral become regular replies where the bot cannot send
ephemeral messages.

Telegram delivers ephemeral messages only from a bot that administers the chat, and refuses the
rest with BOT_NOT_ADMIN.
"""

import pytest
from pyrogram.errors import BadRequest
from pyrogram.types import Message

from spb.classes.handler import Handler
from spb.objects.admin_info import AdminInfo
from spb.objects.context.handler_context import HandlerContext
from tests.support import contexts, updates
from tests.support.recording_client import RecordingClient

pytestmark = pytest.mark.anyio

CHAT = -1001234567890
BOT_ADMINISTRATOR = AdminInfo(contexts.BOT.id, False, False, False, False)


def group_command() -> Message:
    update = updates.group_message(5, "/help")
    assert update.message is not None
    return update.message


async def test_an_answer_in_a_group_the_bot_administers_is_ephemeral(
    context: HandlerContext, client: RecordingClient
) -> None:
    context.chat_admins.put(CHAT, [BOT_ADMINISTRATOR])

    await Handler.send_html(context, group_command(), "answer")

    (sent,) = client.named("send_message")
    assert sent.kwargs["ephemeral_message_parameters"].receiver_user_id == updates.TESTER.id
    assert sent.kwargs.get("reply_parameters") is None


async def test_an_answer_in_a_group_the_bot_does_not_administer_replies_to_the_command(
    context: HandlerContext, client: RecordingClient
) -> None:
    client.respond("get_chat_members", [])

    await Handler.send_html(context, group_command(), "answer")

    (sent,) = client.named("send_message")
    assert sent.kwargs["ephemeral_message_parameters"] is None
    assert sent.kwargs["reply_parameters"].message_id == 5


async def test_an_answer_refused_as_ephemeral_is_sent_again_as_a_reply(
    context: HandlerContext, client: RecordingClient
) -> None:
    context.chat_admins.put(CHAT, [BOT_ADMINISTRATOR])
    client.fail("send_message", BadRequest("[400 BOT_NOT_ADMIN]"))

    await Handler.send_ephemeral(context, group_command(), "answer")

    refused, sent = client.named("send_message")
    assert refused.kwargs["ephemeral_message_parameters"] is not None
    assert sent.kwargs["ephemeral_message_parameters"] is None
    assert sent.kwargs["reply_parameters"].message_id == 5
    # The cached administrator list was stale, so the next answer loads it again.
    assert context.chat_admins.get_if_present(CHAT) is None


async def test_other_failures_of_an_ephemeral_answer_are_raised(
    context: HandlerContext, client: RecordingClient
) -> None:
    context.chat_admins.put(CHAT, [BOT_ADMINISTRATOR])
    client.fail("send_message", BadRequest("[400 MESSAGE_TOO_LONG]"))

    with pytest.raises(BadRequest):
        await Handler.send_html(context, group_command(), "answer")

    assert len(client.named("send_message")) == 1


async def test_a_private_answer_never_looks_up_administrators(
    context: HandlerContext, client: RecordingClient
) -> None:
    update = updates.private_message(5, "/help")
    assert update.message is not None

    await Handler.send_html(context, update.message, "answer", ephemeral=True)

    assert client.named("get_chat_members") == []
    (sent,) = client.named("send_message")
    assert sent.kwargs["ephemeral_message_parameters"].receiver_user_id == updates.TESTER.id

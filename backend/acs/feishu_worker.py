"""Single official SDK long-connection worker. No public HTTP callback required."""
import asyncio
import json
import logging
import sys

from .db import connect
from .feishu_channel import configuration, decrypt_secret, process_message, record_message, runtime


def sdk_message(data, app_id):
    event = data.event
    message, sender = event.message, event.sender
    if sender.sender_type != "user" or message.chat_type != "p2p" or message.message_type != "text":
        return  # Group messages and attachments are deliberately not admitted.
    content = json.loads(message.content)
    record_message(app_id, sender.sender_id.open_id, message.chat_id, message.message_id, content.get("text", ""))


def main():
    # SDK creates its own module-level asyncio loop; import only in this process.
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

    revision = int(sys.argv[1])
    config = configuration()
    if not config or not config["enabled"] or config["version"] != revision:
        return
    client = lark.Client.builder().app_id(config["app_id"]).app_secret(decrypt_secret(config["secret_cipher"])).timeout(12).log_level(lark.LogLevel.ERROR).build()

    def send_to(chat_id, key, text):
        request = (CreateMessageRequest.builder().receive_id_type("chat_id")
                   .request_body(CreateMessageRequestBody.builder().receive_id(chat_id)
                                 .msg_type("text").content(json.dumps({"text": text}, ensure_ascii=False))
                                 .uuid(key).build()).build())
        response = client.im.v1.message.create(request)
        if not response.success():
            raise RuntimeError("Feishu send rejected")

    def on_message(data):
        sdk_message(data, config["app_id"])

    def drain():
        with connect() as conn:
            rows = conn.execute("""SELECT m.*,c.chat_id,c.scope_key FROM feishu_messages m
                JOIN feishu_conversations c ON c.id=m.conversation_id
                WHERE c.app_id=%s AND m.delivery IN ('received','pending','failed') AND m.attempts<5
                AND m.retry_at<=now() ORDER BY m.id LIMIT 20""", (config["app_id"],)).fetchall()
        for row in rows:
            process_message(row, row["scope_key"], lambda key, text: send_to(row["chat_id"], key, text))

    async def retry_outbox():
        while True:
            try:
                await asyncio.to_thread(drain)
            except Exception:
                pass  # Retained inbox rows are retried; never log private payloads.
            await asyncio.sleep(2)

    handler = lark.EventDispatcherHandler.builder("", "").register_p2_im_message_receive_v1(on_message).build()
    connection = lark.ws.Client(config["app_id"], decrypt_secret(config["secret_cipher"]),
                                event_handler=handler, log_level=lark.LogLevel.ERROR)
    logging.disable(logging.CRITICAL)  # Never log SDK payloads or credential-bearing URLs.
    # Actual connection status is intentionally not inferred from process startup.
    runtime("waiting_event", version=revision)
    asyncio.get_event_loop().create_task(retry_outbox())
    try:
        connection.start()
    except Exception:
        runtime("error", "飞书连接失败，请检查应用凭证、长连接配置及服务器网络", revision)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()

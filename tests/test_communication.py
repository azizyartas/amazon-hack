"""Agent İletişim Protokolü unit testleri."""

import uuid
from src.agents.communication import AgentMessage, MessageBus, MessageType, ResourceLock


class TestMessageBus:
    """Gereksinim 5.1, 5.2: Agent mesajlaşma."""

    def test_send_and_receive_message(self):
        """Özellik 12: Agent veri talep edebilmeli ve yanıt alabilmeli."""
        bus = MessageBus()

        def handler(msg: AgentMessage) -> AgentMessage:
            return AgentMessage(
                message_id=str(uuid.uuid4()),
                sender="AgentB",
                receiver="AgentA",
                message_type=MessageType.DATA_RESPONSE,
                payload={"stock": 100},
            )

        bus.register_handler("AgentB", handler)
        response = bus.request_data("AgentA", "AgentB", "stock_level", {"sku": "SKU001"})
        assert response is not None
        assert response.payload["stock"] == 100

    def test_no_handler_returns_none(self):
        bus = MessageBus()
        response = bus.request_data("AgentA", "AgentB", "stock_level", {})
        assert response is None

    def test_broadcast_alert(self):
        bus = MessageBus()
        responses = []

        def handler_b(msg: AgentMessage) -> AgentMessage:
            return AgentMessage(
                message_id=str(uuid.uuid4()),
                sender="AgentB",
                receiver=msg.sender,
                message_type=MessageType.STATUS_UPDATE,
                payload={"ack": True},
            )

        def handler_c(msg: AgentMessage) -> AgentMessage:
            return AgentMessage(
                message_id=str(uuid.uuid4()),
                sender="AgentC",
                receiver=msg.sender,
                message_type=MessageType.STATUS_UPDATE,
                payload={"ack": True},
            )

        bus.register_handler("AgentB", handler_b)
        bus.register_handler("AgentC", handler_c)

        responses = bus.broadcast_alert("AgentA", {"type": "low_stock"})
        assert len(responses) == 2

    def test_message_logging(self):
        """Özellik 14: İletişimler loglanmalı."""
        bus = MessageBus()
        bus.register_handler("AgentB", lambda msg: None)
        bus.request_data("AgentA", "AgentB", "test", {})
        log = bus.get_message_log()
        assert len(log) >= 1

    def test_error_notification(self):
        """Özellik 15: Hata durumunda diğer agentlar bilgilendirilmeli."""
        bus = MessageBus()
        error_received = []

        def error_handler(msg: AgentMessage) -> AgentMessage:
            if msg.message_type == MessageType.ERROR:
                error_received.append(msg)
            return AgentMessage(
                message_id=str(uuid.uuid4()),
                sender="AgentC",
                receiver=msg.sender,
                message_type=MessageType.STATUS_UPDATE,
                payload={"ack": True},
            )

        def failing_handler(msg: AgentMessage) -> AgentMessage:
            raise RuntimeError("Agent hatası")

        bus.register_handler("AgentB", failing_handler)
        bus.register_handler("AgentC", error_handler)

        response = bus.request_data("AgentA", "AgentB", "test", {})
        assert response is not None
        assert response.message_type == MessageType.ERROR


class TestResourceLock:
    """Gereksinim 5.3: Eşzamanlı kaynak erişim kontrolü."""

    def test_acquire_and_release(self):
        """Özellik 13: Kaynak erişim çakışmaları önlenmeli."""
        lock = ResourceLock()
        assert lock.acquire("WH001:SKU001", "AgentA") is True
        assert lock.is_locked("WH001:SKU001") is True
        assert lock.release("WH001:SKU001", "AgentA") is True
        assert lock.is_locked("WH001:SKU001") is False

    def test_wrong_owner_cannot_release(self):
        lock = ResourceLock()
        lock.acquire("WH001:SKU001", "AgentA")
        assert lock.release("WH001:SKU001", "AgentB") is False

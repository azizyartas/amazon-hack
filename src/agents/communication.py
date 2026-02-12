"""Agent İletişim Protokolü - Agentlar arası mesajlaşma ve koordinasyon.

Gereksinim 5: Agent İşbirliği ve Koordinasyon
- Agentlar arası standart mesajlaşma protokolü
- Veri paylaşım mekanizması
- Eşzamanlı kaynak erişim kontrolü
- Hata bildirimi
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    DATA_REQUEST = "data_request"
    DATA_RESPONSE = "data_response"
    ALERT = "alert"
    TRANSFER_REQUEST = "transfer_request"
    TRANSFER_RESPONSE = "transfer_response"
    ERROR = "error"
    STATUS_UPDATE = "status_update"


@dataclass
class AgentMessage:
    message_id: str
    sender: str
    receiver: str
    message_type: MessageType
    payload: dict
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    correlation_id: Optional[str] = None


class ResourceLock:
    """Eşzamanlı kaynak erişim kontrolü (Gereksinim 5.3)."""

    def __init__(self) -> None:
        self._locks: dict[str, threading.Lock] = {}
        self._lock_owners: dict[str, str] = {}
        self._master_lock = threading.Lock()

    def acquire(self, resource_key: str, agent_name: str, timeout: float = 10.0) -> bool:
        """Bir kaynak için kilit alır."""
        with self._master_lock:
            if resource_key not in self._locks:
                self._locks[resource_key] = threading.Lock()

        acquired = self._locks[resource_key].acquire(timeout=timeout)
        if acquired:
            self._lock_owners[resource_key] = agent_name
            logger.debug("Kilit alındı: %s -> %s", agent_name, resource_key)
        else:
            logger.warning("Kilit alınamadı: %s -> %s (timeout)", agent_name, resource_key)
        return acquired

    def release(self, resource_key: str, agent_name: str) -> bool:
        """Bir kaynak kilidini serbest bırakır."""
        if resource_key not in self._locks:
            return False

        owner = self._lock_owners.get(resource_key)
        if owner != agent_name:
            logger.warning("Kilit sahibi uyuşmazlığı: %s != %s", agent_name, owner)
            return False

        try:
            self._locks[resource_key].release()
            del self._lock_owners[resource_key]
            return True
        except RuntimeError:
            return False

    def is_locked(self, resource_key: str) -> bool:
        """Kaynağın kilitli olup olmadığını kontrol eder."""
        if resource_key not in self._locks:
            return False
        return self._locks[resource_key].locked()


class MessageBus:
    """Agent mesajlaşma sistemi (Gereksinim 5.1, 5.2)."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable]] = {}
        self._message_log: list[AgentMessage] = []
        self._resource_lock = ResourceLock()

    def register_handler(
        self, agent_name: str, handler: Callable[[AgentMessage], Optional[AgentMessage]]
    ) -> None:
        """Bir agent için mesaj handler'ı kaydeder."""
        if agent_name not in self._handlers:
            self._handlers[agent_name] = []
        self._handlers[agent_name].append(handler)

    def send_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        """Bir agent'a mesaj gönderir ve yanıt döndürür."""
        self._message_log.append(message)
        logger.info(
            "Mesaj gönderildi: %s -> %s [%s]",
            message.sender,
            message.receiver,
            message.message_type.value,
        )

        handlers = self._handlers.get(message.receiver, [])
        if not handlers:
            logger.warning("Handler bulunamadı: %s", message.receiver)
            return None

        for handler in handlers:
            try:
                response = handler(message)
                if response:
                    response.correlation_id = message.message_id
                    self._message_log.append(response)
                    return response
            except Exception as e:
                error_msg = AgentMessage(
                    message_id=str(uuid.uuid4()),
                    sender=message.receiver,
                    receiver=message.sender,
                    message_type=MessageType.ERROR,
                    payload={"error": str(e), "original_message_id": message.message_id},
                    correlation_id=message.message_id,
                )
                self._message_log.append(error_msg)
                self._notify_error(message.receiver, e)
                return error_msg

        return None

    def request_data(
        self, requester: str, provider: str, data_type: str, params: dict
    ) -> Optional[AgentMessage]:
        """Bir agent'tan veri talep eder (Gereksinim 5.1)."""
        message = AgentMessage(
            message_id=str(uuid.uuid4()),
            sender=requester,
            receiver=provider,
            message_type=MessageType.DATA_REQUEST,
            payload={"data_type": data_type, "params": params},
        )
        return self.send_message(message)

    def broadcast_alert(self, sender: str, alert_data: dict) -> list[AgentMessage]:
        """Tüm agentlara uyarı gönderir."""
        responses = []
        for agent_name in self._handlers:
            if agent_name == sender:
                continue
            message = AgentMessage(
                message_id=str(uuid.uuid4()),
                sender=sender,
                receiver=agent_name,
                message_type=MessageType.ALERT,
                payload=alert_data,
            )
            resp = self.send_message(message)
            if resp:
                responses.append(resp)
        return responses

    # --- Gereksinim 5.6: Hata bildirimi ---

    def _notify_error(self, failed_agent: str, error: Exception) -> None:
        """Bir agent hata ile karşılaştığında diğer agentları bilgilendirir."""
        for agent_name in self._handlers:
            if agent_name == failed_agent:
                continue
            error_notification = AgentMessage(
                message_id=str(uuid.uuid4()),
                sender="system",
                receiver=agent_name,
                message_type=MessageType.ERROR,
                payload={
                    "failed_agent": failed_agent,
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                },
            )
            self.send_message(error_notification)

    def notify_agents_of_error(
        self, failed_agent: str, error: Exception, exclude: Optional[list[str]] = None
    ) -> list[AgentMessage]:
        """Belirli agentları hariç tutarak hata bildirimi yapar."""
        exclude = exclude or []
        notifications = []
        for agent_name in self._handlers:
            if agent_name == failed_agent or agent_name in exclude:
                continue
            msg = AgentMessage(
                message_id=str(uuid.uuid4()),
                sender="system",
                receiver=agent_name,
                message_type=MessageType.ERROR,
                payload={
                    "failed_agent": failed_agent,
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                },
            )
            resp = self.send_message(msg)
            if resp:
                notifications.append(resp)
        return notifications

    # --- Gereksinim 5.3: Eşzamanlı kaynak erişim kontrolü ---

    def acquire_resource(self, resource_key: str, agent_name: str) -> bool:
        """Bir kaynak için kilit alır."""
        return self._resource_lock.acquire(resource_key, agent_name)

    def release_resource(self, resource_key: str, agent_name: str) -> bool:
        """Bir kaynak kilidini serbest bırakır."""
        return self._resource_lock.release(resource_key, agent_name)

    # --- Gereksinim 5.4: Karar ve iletişim loglama ---

    def get_message_log(self) -> list[AgentMessage]:
        """Tüm mesaj logunu döndürür."""
        return list(self._message_log)

    def get_agent_messages(self, agent_name: str) -> list[AgentMessage]:
        """Belirli bir agent'ın gönderdiği/aldığı mesajları döndürür."""
        return [
            m for m in self._message_log
            if m.sender == agent_name or m.receiver == agent_name
        ]

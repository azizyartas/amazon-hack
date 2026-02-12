"""Transfer Coordinator Agent - Depolar arası transfer koordinasyonu.

Gereksinim 2: Depolar Arası Otomatik Transfer
Gereksinim 10: İnsan Müdahalesi ve Onay Mekanizması

- Transfer ihtiyacını tespit eder
- Kaynak ve hedef depo seçer
- Transfer miktarını hesaplar
- Atomik transfer işlemi gerçekleştirir
- İnsan onayı mekanizmasını yönetir
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from src.agents.base_agent import BaseAgent
from src.models.warehouse import (
    ApprovalConfig,
    InventoryItem,
    OperationMode,
    SalesPrediction,
    TransferRequest,
    TransferStatus,
)

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Transfer validasyon hatası."""
    pass


class InsufficientStockError(ValidationError):
    """Yetersiz stok hatası."""
    pass


class TransferCoordinatorAgent(BaseAgent):
    """Depolar arası transfer işlemlerini koordine eden agent."""

    def __init__(self, region_name: str = "us-east-1", **kwargs: Any):
        super().__init__(
            agent_name="TransferCoordinatorAgent",
            model_id="us.amazon.nova-pro-v1:0",
            region_name=region_name,
            **kwargs,
        )
        # Stok verileri: {(warehouse_id, sku): quantity}
        self._stock: dict[tuple[str, str], int] = {}
        # Transfer geçmişi
        self._transfers: list[TransferRequest] = []
        # Onay kuyruğu
        self._approval_queue: list[TransferRequest] = []
        # Onay konfigürasyonu
        self._approval_config = ApprovalConfig()
        # Ürün fiyatları: {sku: price}
        self._product_prices: dict[str, float] = {}

    def set_stock(self, warehouse_id: str, sku: str, quantity: int) -> None:
        """Stok seviyesini ayarlar."""
        self._stock[(warehouse_id, sku)] = quantity

    def get_stock(self, warehouse_id: str, sku: str) -> int:
        """Stok seviyesini döndürür."""
        return self._stock.get((warehouse_id, sku), 0)

    def set_product_price(self, sku: str, price: float) -> None:
        """Ürün fiyatını ayarlar."""
        self._product_prices[sku] = price

    def set_approval_config(self, config: ApprovalConfig) -> None:
        """Onay konfigürasyonunu ayarlar."""
        self._approval_config = config

    # --- Gereksinim 2.1: Transfer ihtiyacı tespiti ---

    def evaluate_transfer_need(
        self,
        warehouse_id: str,
        sku: str,
        threshold: int,
        aging_priority: float = 0.0,
        sales_potential: float = 0.0,
    ) -> Optional[dict]:
        """Bir depo-SKU çifti için transfer ihtiyacını değerlendirir.

        Returns:
            Transfer ihtiyacı varsa detay dict, yoksa None.
        """
        current_stock = self.get_stock(warehouse_id, sku)

        if current_stock >= threshold:
            return None

        deficit = threshold - current_stock
        priority = 1.0
        if aging_priority > 0:
            priority += aging_priority
        if sales_potential > 0:
            priority += sales_potential / 100.0

        result = {
            "warehouse_id": warehouse_id,
            "sku": sku,
            "current_stock": current_stock,
            "threshold": threshold,
            "deficit": deficit,
            "priority_score": round(priority, 3),
            "should_transfer": True,
        }

        self.log_decision(
            decision_type="transfer_need_evaluation",
            input_data={"warehouse_id": warehouse_id, "sku": sku, "current_stock": current_stock},
            output_data=result,
            reasoning=f"Stok ({current_stock}) eşiğin ({threshold}) altında. Açık: {deficit}",
        )

        return result

    # --- Gereksinim 2.2: Kaynak depo seçimi ---

    def select_source_warehouse(
        self, sku: str, target_warehouse_id: str, required_quantity: int,
        safety_threshold: int = 0, sales_scores: Optional[dict[str, float]] = None
    ) -> Optional[str]:
        """Transfer için en uygun kaynak depoyu seçer.

        Seçim kriterleri:
        1. Hedef depo olmamalı
        2. Yeterli stok olmalı (transfer sonrası safety_threshold altına düşmemeli)
        3. sales_scores verilmişse: düşük satış potansiyeli olan depo tercih edilir
           (ürünün az satıldığı depodan, çok satıldığı depoya gönderilmeli)
        4. sales_scores yoksa: en fazla stok fazlası olan depo tercih edilir

        safety_threshold: Kaynak depoda transfer sonrası kalması gereken minimum stok.
        sales_scores: {warehouse_id: sales_potential_score} - düşük skor = düşük satış = öncelikli kaynak
        """
        candidates: list[tuple[str, int, float]] = []

        for (wh_id, s), qty in self._stock.items():
            if s != sku or wh_id == target_warehouse_id:
                continue
            safe_available = qty - safety_threshold
            if safe_available >= required_quantity:
                score = sales_scores.get(wh_id, 0.0) if sales_scores else 0.0
                candidates.append((wh_id, qty, score))

        if not candidates:
            return None

        if sales_scores:
            # Düşük satış potansiyeli olan depoyu tercih et (az satan depodan gönder)
            # Eşit satış skorunda fazla stok olan tercih edilir
            candidates.sort(key=lambda x: (x[2], -x[1]))
        else:
            # Satış verisi yoksa en fazla stok olan depoyu seç
            candidates.sort(key=lambda x: x[1], reverse=True)

        return candidates[0][0]

    def get_safe_transfer_amount(
        self, source_warehouse_id: str, sku: str, requested_quantity: int,
        safety_threshold: int = 0
    ) -> int:
        """Kaynak depoyu güvenli seviyede tutarak transfer edilebilecek max miktarı döndürür."""
        available = self.get_stock(source_warehouse_id, sku)
        safe_available = max(0, available - safety_threshold)
        return min(requested_quantity, safe_available)

    # --- Gereksinim 3.2, 3.5: Hedef depo seçimi (satış potansiyeli entegrasyonu) ---

    def select_target_warehouse(
        self,
        sku: str,
        source_warehouse_id: str,
        candidate_predictions: list[SalesPrediction],
    ) -> Optional[str]:
        """Satış potansiyeline göre en uygun hedef depoyu seçer.

        Birden fazla uygun hedef depo olduğunda en yüksek satış potansiyeline
        sahip olanı seçer (Gereksinim 3.5).
        """
        valid = [
            p for p in candidate_predictions
            if p.warehouse_id != source_warehouse_id
        ]

        if not valid:
            return None

        # En yüksek satış potansiyeline göre sırala
        valid.sort(key=lambda p: p.sales_potential_score, reverse=True)
        best = valid[0]

        self.log_decision(
            decision_type="target_warehouse_selection",
            input_data={
                "sku": sku,
                "candidates": [p.warehouse_id for p in valid],
            },
            output_data={
                "selected": best.warehouse_id,
                "score": best.sales_potential_score,
            },
            reasoning=f"En yüksek satış potansiyeli: {best.warehouse_id} (skor: {best.sales_potential_score})",
        )

        return best.warehouse_id

    # --- Gereksinim 2.3: Transfer miktarı hesaplama ---

    def calculate_transfer_quantity(
        self, source_warehouse_id: str, target_warehouse_id: str, sku: str, deficit: int
    ) -> int:
        """Transfer miktarını hesaplar.

        Özellik 4: Transfer miktarı kaynak deponun mevcut stok miktarını aşmamalıdır.
        """
        source_stock = self.get_stock(source_warehouse_id, sku)

        if source_stock <= 0:
            return 0

        # Kaynak depoda minimum bir miktar bırak (stok seviyesinin %20'si)
        max_transferable = max(0, source_stock - int(source_stock * 0.2))
        transfer_qty = min(deficit, max_transferable)

        return max(0, transfer_qty)

    # --- Gereksinim 2.4: Transfer öncesi stok tutarlılığı doğrulama ---

    def validate_transfer(
        self, source_warehouse_id: str, target_warehouse_id: str, sku: str, quantity: int
    ) -> bool:
        """Transfer başlatılmadan önce stok tutarlılığını doğrular.

        Kontroller:
        - Kaynak depoda yeterli stok var mı
        - Transfer miktarı pozitif mi
        - Kaynak ve hedef farklı mı
        """
        if quantity <= 0:
            raise ValidationError("Transfer miktarı pozitif olmalıdır")

        if source_warehouse_id == target_warehouse_id:
            raise ValidationError("Kaynak ve hedef depo aynı olamaz")

        source_stock = self.get_stock(source_warehouse_id, sku)
        if source_stock < quantity:
            raise InsufficientStockError(
                f"Yetersiz stok: {source_warehouse_id}/{sku} "
                f"mevcut={source_stock}, istenen={quantity}"
            )

        return True

    # --- Gereksinim 10.1: Yüksek değerli transfer onayı ---

    def requires_approval(self, sku: str, quantity: int) -> bool:
        """Transfer için insan onayı gerekip gerekmediğini kontrol eder."""
        if self._approval_config.mode == OperationMode.AUTONOMOUS:
            return False

        price = self._product_prices.get(sku, 0.0)
        total_value = price * quantity

        if total_value >= self._approval_config.high_value_threshold:
            return True
        if quantity >= self._approval_config.high_quantity_threshold:
            return True

        return False

    # --- Gereksinim 2.5, 6.1: Atomik transfer işlemi ---

    def execute_transfer(
        self,
        source_warehouse_id: str,
        target_warehouse_id: str,
        sku: str,
        quantity: int,
        reason: str = "",
        aging_priority: float = 0.0,
        sales_potential: float = 0.0,
    ) -> TransferRequest:
        """Transfer işlemini gerçekleştirir.

        Özellik 6: Transfer öncesi ve sonrası toplam stok korunmalıdır.
        Özellik 16: Atomik transfer - ya her iki depo güncellenir ya da hiçbiri.
        Özellik 17: Negatif stok yasağı.
        """
        # Validasyon
        self.validate_transfer(source_warehouse_id, target_warehouse_id, sku, quantity)

        transfer = TransferRequest(
            transfer_id=str(uuid.uuid4()),
            source_warehouse_id=source_warehouse_id,
            target_warehouse_id=target_warehouse_id,
            sku=sku,
            quantity=quantity,
            reason=reason,
            priority_score=aging_priority + (sales_potential / 100.0),
        )

        # Onay kontrolü
        if self.requires_approval(sku, quantity):
            transfer.status = TransferStatus.AWAITING_APPROVAL
            transfer.requires_approval = True
            self._approval_queue.append(transfer)
            self._transfers.append(transfer)

            self.log_decision(
                decision_type="transfer_awaiting_approval",
                input_data={"transfer_id": transfer.transfer_id, "quantity": quantity, "sku": sku},
                output_data={"status": transfer.status.value},
                reasoning="Yüksek değerli transfer - insan onayı bekleniyor.",
            )
            return transfer

        # Atomik transfer: toplam stok korunumu
        return self._execute_atomic_transfer(transfer)

    def _execute_atomic_transfer(self, transfer: TransferRequest) -> TransferRequest:
        """Atomik transfer işlemini gerçekleştirir.

        Stok korunumu garantisi: kaynak - miktar, hedef + miktar.
        Hata durumunda rollback yapılır.
        """
        src_key = (transfer.source_warehouse_id, transfer.sku)
        tgt_key = (transfer.target_warehouse_id, transfer.sku)

        source_stock = self._stock.get(src_key, 0)
        target_stock = self._stock.get(tgt_key, 0)

        # Son kontrol: negatif stok yasağı
        if source_stock < transfer.quantity:
            transfer.status = TransferStatus.FAILED
            self._transfers.append(transfer)
            raise InsufficientStockError(
                f"Atomik transfer başarısız: yetersiz stok {src_key}"
            )

        # Atomik güncelleme
        try:
            self._stock[src_key] = source_stock - transfer.quantity
            self._stock[tgt_key] = target_stock + transfer.quantity

            # Negatif stok kontrolü (invariant)
            if self._stock[src_key] < 0:
                # Rollback
                self._stock[src_key] = source_stock
                self._stock[tgt_key] = target_stock
                transfer.status = TransferStatus.ROLLED_BACK
                self._transfers.append(transfer)
                raise ValidationError("Negatif stok tespit edildi, rollback yapıldı")

            transfer.status = TransferStatus.COMPLETED
            transfer.completed_at = datetime.utcnow().isoformat()
            self._transfers.append(transfer)

            self.log_decision(
                decision_type="transfer_completed",
                input_data={
                    "transfer_id": transfer.transfer_id,
                    "source": transfer.source_warehouse_id,
                    "target": transfer.target_warehouse_id,
                    "sku": transfer.sku,
                    "quantity": transfer.quantity,
                },
                output_data={
                    "source_stock_after": self._stock[src_key],
                    "target_stock_after": self._stock[tgt_key],
                    "status": transfer.status.value,
                },
                reasoning=(
                    f"Transfer tamamlandı: {transfer.source_warehouse_id} -> "
                    f"{transfer.target_warehouse_id}, {transfer.sku} x{transfer.quantity}"
                ),
            )

            return transfer

        except Exception as e:
            # Rollback
            self._stock[src_key] = source_stock
            self._stock[tgt_key] = target_stock
            transfer.status = TransferStatus.ROLLED_BACK
            if transfer not in self._transfers:
                self._transfers.append(transfer)
            logger.error("Transfer rollback: %s", e)
            raise

    # --- Gereksinim 10.2: Onay kuyruğu yönetimi ---

    def get_pending_approvals(self) -> list[TransferRequest]:
        """Onay bekleyen transferleri döndürür."""
        return [
            t for t in self._approval_queue
            if t.status == TransferStatus.AWAITING_APPROVAL
        ]

    # --- Gereksinim 10.3: Onay sonrası transfer devamı ---

    def approve_transfer(self, transfer_id: str) -> TransferRequest:
        """Bir transferi onaylar ve işlemi tamamlar."""
        transfer = self._find_transfer(transfer_id)
        if not transfer:
            raise ValidationError(f"Transfer bulunamadı: {transfer_id}")

        if transfer.status != TransferStatus.AWAITING_APPROVAL:
            raise ValidationError(
                f"Transfer onay bekliyor durumunda değil: {transfer.status.value}"
            )

        transfer.status = TransferStatus.APPROVED
        return self._execute_atomic_transfer(transfer)

    # --- Gereksinim 10.4: Red sonrası alternatif öneriler ---

    def reject_transfer(self, transfer_id: str) -> list[dict]:
        """Bir transferi reddeder ve alternatif çözümler önerir."""
        transfer = self._find_transfer(transfer_id)
        if not transfer:
            raise ValidationError(f"Transfer bulunamadı: {transfer_id}")

        transfer.status = TransferStatus.REJECTED

        # Alternatif öneriler oluştur
        alternatives = []

        # 1. Daha küçük miktarla transfer
        half_qty = transfer.quantity // 2
        if half_qty > 0:
            alternatives.append({
                "type": "reduced_quantity",
                "description": f"Daha küçük miktar ile transfer: {half_qty} adet",
                "source": transfer.source_warehouse_id,
                "target": transfer.target_warehouse_id,
                "sku": transfer.sku,
                "quantity": half_qty,
            })

        # 2. Farklı kaynak depo
        alt_source = self.select_source_warehouse(
            transfer.sku, transfer.target_warehouse_id, transfer.quantity
        )
        if alt_source and alt_source != transfer.source_warehouse_id:
            alternatives.append({
                "type": "alternative_source",
                "description": f"Farklı kaynak depo: {alt_source}",
                "source": alt_source,
                "target": transfer.target_warehouse_id,
                "sku": transfer.sku,
                "quantity": transfer.quantity,
            })

        self.log_decision(
            decision_type="transfer_rejected_alternatives",
            input_data={"transfer_id": transfer_id},
            output_data={"alternatives_count": len(alternatives), "alternatives": alternatives},
            reasoning="Transfer reddedildi, alternatif çözümler önerildi.",
        )

        return alternatives

    def _find_transfer(self, transfer_id: str) -> Optional[TransferRequest]:
        """Transfer ID'ye göre transfer bulur."""
        for t in self._transfers:
            if t.transfer_id == transfer_id:
                return t
        for t in self._approval_queue:
            if t.transfer_id == transfer_id:
                return t
        return None

    # --- Gereksinim 10.5: Yapılandırılabilir onay eşikleri ---

    def get_approval_config(self) -> ApprovalConfig:
        """Mevcut onay konfigürasyonunu döndürür."""
        return self._approval_config

    # --- Gereksinim 10.6: Çift mod çalışma ---

    def set_operation_mode(self, mode: OperationMode) -> None:
        """Sistem çalışma modunu ayarlar."""
        self._approval_config.mode = mode
        self.log_decision(
            decision_type="mode_change",
            input_data={"new_mode": mode.value},
            output_data={"mode": mode.value},
            reasoning=f"Çalışma modu değiştirildi: {mode.value}",
        )

    # --- Gereksinim 4.4: Yaşlı stokları önceliklendirme ---

    def prioritize_transfer_with_aging(
        self,
        transfer_needs: list[dict],
        aging_data: list[dict],
    ) -> list[dict]:
        """Transfer ihtiyaçlarını yaşlandırma verileriyle birleştirip önceliklendirir.

        Yaşlı stoklar daha yeni stoklardan önce transfer edilir.
        """
        # Yaşlandırma verilerini index'le
        aging_map: dict[tuple[str, str], dict] = {}
        for a in aging_data:
            aging_map[(a["warehouse_id"], a["sku"])] = a

        # Her transfer ihtiyacına yaşlandırma önceliği ekle
        for need in transfer_needs:
            key = (need["warehouse_id"], need["sku"])
            aging = aging_map.get(key)
            if aging:
                need["aging_priority"] = aging.get("priority_score", 0.0)
                need["is_aging_critical"] = aging.get("is_critical", False)
            else:
                need["aging_priority"] = 0.0
                need["is_aging_critical"] = False

        # Yaşlı stokları önce, sonra normal öncelik
        transfer_needs.sort(
            key=lambda x: (x.get("is_aging_critical", False), x.get("aging_priority", 0.0)),
            reverse=True,
        )

        return transfer_needs

    # --- Görev 7.8: Nova model ile optimal transfer kararı ---

    def decide_with_model(
        self,
        warehouse_id: str,
        sku: str,
        current_stock: int,
        threshold: int,
        available_sources: list[dict],
    ) -> dict:
        """Nova model kullanarak optimal transfer kararı alır."""
        sources_text = "\n".join(
            f"  - {s['warehouse_id']}: stok={s['quantity']}"
            for s in available_sources
        )

        prompt = (
            f"Transfer kararı al:\n"
            f"- Hedef depo: {warehouse_id}\n"
            f"- SKU: {sku}\n"
            f"- Mevcut stok: {current_stock}, Eşik: {threshold}\n"
            f"- Açık: {threshold - current_stock}\n"
            f"- Uygun kaynak depolar:\n{sources_text}\n\n"
            f"En uygun kaynak depoyu ve transfer miktarını belirle. "
            f'JSON formatında yanıt ver: {{"source_warehouse": "...", "quantity": N, "reasoning": "..."}}'
        )

        try:
            response_text = self.invoke_model(prompt, max_tokens=500, temperature=0.3)
            return {"decision": response_text}
        except Exception as e:
            logger.error("Model karar hatası: %s", e)
            return {"error": str(e)}

    # --- Stok tutarlılığı yardımcıları ---

    def get_total_stock(self, sku: str) -> int:
        """Bir SKU'nun tüm depolardaki toplam stok miktarını döndürür."""
        return sum(
            qty for (_, s), qty in self._stock.items() if s == sku
        )

    def get_all_transfers(self) -> list[TransferRequest]:
        """Tüm transfer geçmişini döndürür."""
        return list(self._transfers)

    def process(self, warehouse_id: str, sku: str, threshold: int) -> dict:
        """Ana işlem: transfer ihtiyacını değerlendir ve gerekirse transfer başlat."""
        need = self.evaluate_transfer_need(warehouse_id, sku, threshold)
        if not need:
            return {"action": "none", "reason": "Stok seviyesi yeterli"}

        source = self.select_source_warehouse(sku, warehouse_id, need["deficit"])
        if not source:
            return {"action": "no_source", "reason": "Uygun kaynak depo bulunamadı"}

        qty = self.calculate_transfer_quantity(source, warehouse_id, sku, need["deficit"])
        if qty <= 0:
            return {"action": "insufficient", "reason": "Transfer edilecek yeterli miktar yok"}

        transfer = self.execute_transfer(source, warehouse_id, sku, qty, reason="auto_transfer")
        return {
            "action": "transferred",
            "transfer_id": transfer.transfer_id,
            "status": transfer.status.value,
            "quantity": qty,
        }

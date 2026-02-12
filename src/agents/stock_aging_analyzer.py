"""Stock Aging Analyzer Agent - Ürün yaşlandırma analizi.

Gereksinim 4: Ürün Yaşlandırma Yönetimi
- Her SKU için yaşlandırma süresini takip eder
- Kritik yaşlandırma eşiğini aşan ürünler için öncelikli transfer önerisi oluşturur
- Kategori bazlı farklı yaşlandırma eşikleri uygular
- Günlük yaşlandırma analizi gerçekleştirir
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from src.agents.base_agent import BaseAgent
from src.models.warehouse import AgingInfo

logger = logging.getLogger(__name__)

# Kategori bazlı yaşlandırma eşikleri (gün)
DEFAULT_AGING_THRESHOLDS: dict[str, int] = {
    "Elektronik": 90,
    "Giyim": 180,
    "Gıda": 30,
    "Mobilya": 365,
    "Kitap": 730,
    "Oyuncak": 180,
    "Spor Malzemeleri": 365,
    "Ev Aletleri": 180,
    "Kozmetik": 365,
    "Otomotiv": 730,
}


class StockAgingAnalyzerAgent(BaseAgent):
    """Ürün yaşlandırmasını analiz eden agent."""

    def __init__(self, region_name: str = "us-east-1", **kwargs: Any):
        super().__init__(
            agent_name="StockAgingAnalyzerAgent",
            model_id="us.amazon.nova-lite-v1:0",
            region_name=region_name,
            **kwargs,
        )
        # Ürün giriş tarihleri: {(warehouse_id, sku): entry_date_iso}
        self._entry_dates: dict[tuple[str, str], str] = {}
        # Ürün kategorileri: {sku: category}
        self._product_categories: dict[str, str] = {}
        # Özel yaşlandırma eşikleri (kategori bazlı override)
        self._custom_thresholds: dict[str, int] = {}

    def set_entry_date(self, warehouse_id: str, sku: str, entry_date: str) -> None:
        """Ürünün depoya giriş tarihini ayarlar (ISO 8601 formatı)."""
        self._entry_dates[(warehouse_id, sku)] = entry_date

    def set_product_category(self, sku: str, category: str) -> None:
        """Ürün kategorisini ayarlar."""
        self._product_categories[sku] = category

    def set_custom_threshold(self, category: str, threshold_days: int) -> None:
        """Kategori için özel yaşlandırma eşiği ayarlar."""
        if threshold_days < 0:
            raise ValueError("Yaşlandırma eşiği negatif olamaz")
        self._custom_thresholds[category] = threshold_days

    # --- Gereksinim 4.3: Kategori bazlı eşik yönetimi ---

    def get_aging_threshold(self, sku: str) -> int:
        """Bir SKU'nun kategorisine göre yaşlandırma eşiğini döndürür."""
        category = self._product_categories.get(sku, "")
        # Önce özel eşik, sonra varsayılan
        if category in self._custom_thresholds:
            return self._custom_thresholds[category]
        return DEFAULT_AGING_THRESHOLDS.get(category, 180)  # varsayılan 180 gün

    # --- Gereksinim 4.1: Yaşlandırma süresi hesaplama ---

    def calculate_aging(
        self, warehouse_id: str, sku: str, reference_date: Optional[str] = None
    ) -> AgingInfo:
        """Bir ürünün depoda kalma süresini hesaplar."""
        entry_date_str = self._entry_dates.get((warehouse_id, sku))
        if not entry_date_str:
            raise ValueError(
                f"Giriş tarihi bulunamadı: {warehouse_id}/{sku}"
            )

        entry_date = datetime.fromisoformat(entry_date_str)
        ref_date = (
            datetime.fromisoformat(reference_date)
            if reference_date
            else datetime.utcnow()
        )

        days = (ref_date - entry_date).days
        if days < 0:
            days = 0

        threshold = self.get_aging_threshold(sku)
        category = self._product_categories.get(sku, "Bilinmiyor")

        return AgingInfo(
            warehouse_id=warehouse_id,
            sku=sku,
            entry_date=entry_date_str,
            days_in_warehouse=days,
            aging_threshold_days=threshold,
            is_critical=days >= threshold,
            category=category,
        )

    # --- Gereksinim 4.2: Kritik yaşlandırma tespiti ---

    def detect_critical_aging(
        self, reference_date: Optional[str] = None
    ) -> list[AgingInfo]:
        """Kritik yaşlandırma eşiğini aşan tüm ürünleri tespit eder."""
        critical_items: list[AgingInfo] = []

        for (warehouse_id, sku) in self._entry_dates:
            aging = self.calculate_aging(warehouse_id, sku, reference_date)
            if aging.is_critical:
                critical_items.append(aging)

        if critical_items:
            self.log_decision(
                decision_type="critical_aging_detection",
                input_data={"total_tracked": len(self._entry_dates)},
                output_data={
                    "critical_count": len(critical_items),
                    "items": [
                        {"warehouse_id": a.warehouse_id, "sku": a.sku, "days": a.days_in_warehouse}
                        for a in critical_items
                    ],
                },
                reasoning=f"{len(critical_items)} ürün kritik yaşlandırma eşiğini aştı.",
            )

        return critical_items

    # --- Gereksinim 4.4, 4.5: Yaşlı stok önceliklendirme ---

    def prioritize_aging_transfers(
        self, reference_date: Optional[str] = None
    ) -> list[dict]:
        """Yaşlı stokları öncelik sırasına göre transfer önerisi olarak döndürür.

        Öncelik skoru = days_in_warehouse / aging_threshold_days
        Skor ne kadar yüksekse, transfer o kadar acil.
        """
        all_aging: list[AgingInfo] = []

        for (warehouse_id, sku) in self._entry_dates:
            aging = self.calculate_aging(warehouse_id, sku, reference_date)
            all_aging.append(aging)

        # Öncelik skoruna göre sırala (yüksekten düşüğe)
        all_aging.sort(
            key=lambda a: a.days_in_warehouse / max(a.aging_threshold_days, 1),
            reverse=True,
        )

        recommendations = []
        for aging in all_aging:
            priority_score = aging.days_in_warehouse / max(aging.aging_threshold_days, 1)
            recommendations.append(
                {
                    "warehouse_id": aging.warehouse_id,
                    "sku": aging.sku,
                    "days_in_warehouse": aging.days_in_warehouse,
                    "aging_threshold_days": aging.aging_threshold_days,
                    "is_critical": aging.is_critical,
                    "priority_score": round(priority_score, 3),
                    "category": aging.category,
                    "recommendation": (
                        "urgent_transfer" if aging.is_critical else "monitor"
                    ),
                }
            )

        if recommendations:
            self.log_decision(
                decision_type="aging_transfer_prioritization",
                input_data={"total_items": len(all_aging)},
                output_data={
                    "critical_count": sum(1 for r in recommendations if r["is_critical"]),
                    "top_priority": recommendations[0] if recommendations else None,
                },
                reasoning="Yaşlandırma bazlı transfer önceliklendirmesi yapıldı.",
            )

        return recommendations

    def get_daily_aging_report(self, reference_date: Optional[str] = None) -> dict:
        """Günlük yaşlandırma raporu oluşturur."""
        critical = self.detect_critical_aging(reference_date)
        all_recommendations = self.prioritize_aging_transfers(reference_date)

        categories_summary: dict[str, int] = {}
        for item in critical:
            categories_summary[item.category] = categories_summary.get(item.category, 0) + 1

        return {
            "report_date": reference_date or datetime.utcnow().isoformat(),
            "total_tracked_items": len(self._entry_dates),
            "critical_items_count": len(critical),
            "categories_affected": categories_summary,
            "urgent_transfers_needed": [
                r for r in all_recommendations if r["recommendation"] == "urgent_transfer"
            ],
        }

    def process(self, reference_date: Optional[str] = None) -> dict:
        """Ana işlem: günlük yaşlandırma analizi."""
        return self.get_daily_aging_report(reference_date)

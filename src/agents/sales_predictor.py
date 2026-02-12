"""Sales Predictor Agent - Satış tahminleri ve potansiyel hesaplama.

Gereksinim 3: Satış Potansiyeline Göre Ürün Yönlendirme
- Her depo için SKU bazında satış potansiyeli hesaplar
- Geçmiş satış verilerini analiz eder
- Mevsimsel trendleri ve bölgesel faktörleri hesaba katar
- Nova model ile satış tahminleri yapar
"""

from __future__ import annotations

import logging
import math
from datetime import datetime
from typing import Any, Optional

from src.agents.base_agent import BaseAgent
from src.models.warehouse import SalesPrediction

logger = logging.getLogger(__name__)

# Mevsimsel çarpanlar (design dokümanından)
SEASONAL_MULTIPLIERS: dict[str, dict] = {
    "Elektronik": {"high_season": [11, 12, 1], "multiplier": 2.5},
    "Giyim": {"high_season": [9, 10, 11], "multiplier": 2.0},
    "Gıda": {"high_season": [6, 7, 8], "multiplier": 1.5},
    "Mobilya": {"high_season": [3, 4, 5], "multiplier": 1.3},
    "Kitap": {"high_season": [9, 10], "multiplier": 1.4},
    "Oyuncak": {"high_season": [11, 12], "multiplier": 3.0},
    "Spor Malzemeleri": {"high_season": [5, 6, 7], "multiplier": 2.0},
    "Ev Aletleri": {"high_season": [1, 2, 3], "multiplier": 1.5},
    "Kozmetik": {"high_season": [2, 3, 11, 12], "multiplier": 1.8},
    "Otomotiv": {"high_season": [4, 5, 6], "multiplier": 1.3},
}

# Bölgesel çarpanlar
REGIONAL_MULTIPLIERS: dict[str, float] = {
    "Marmara": 1.5,
    "İç Anadolu": 1.2,
    "Ege": 1.3,
    "Akdeniz": 1.1,
    "Karadeniz": 1.0,
}


class SalesPredictorAgent(BaseAgent):
    """Satış tahminleri yapan ve satış potansiyeli hesaplayan agent."""

    def __init__(self, region_name: str = "us-east-1", **kwargs: Any):
        super().__init__(
            agent_name="SalesPredictorAgent",
            model_id="us.amazon.nova-pro-v1:0",
            region_name=region_name,
            **kwargs,
        )
        # Geçmiş satış verileri: {(warehouse_id, sku): [monthly_sales]}
        self._sales_history: dict[tuple[str, str], list[float]] = {}
        # Depo bölge bilgileri: {warehouse_id: region}
        self._warehouse_regions: dict[str, str] = {}
        # Ürün kategori bilgileri: {sku: category}
        self._product_categories: dict[str, str] = {}

    def set_sales_history(
        self, warehouse_id: str, sku: str, monthly_sales: list[float]
    ) -> None:
        """Bir depo-SKU çifti için geçmiş satış verilerini ayarlar."""
        self._sales_history[(warehouse_id, sku)] = monthly_sales

    def set_warehouse_region(self, warehouse_id: str, region: str) -> None:
        """Depo bölge bilgisini ayarlar."""
        self._warehouse_regions[warehouse_id] = region

    def set_product_category(self, sku: str, category: str) -> None:
        """Ürün kategori bilgisini ayarlar."""
        self._product_categories[sku] = category

    # --- Gereksinim 3.3: Geçmiş satış verisi analizi ---

    def analyze_sales_history(
        self, warehouse_id: str, sku: str
    ) -> dict:
        """Geçmiş satış verilerini analiz eder."""
        history = self._sales_history.get((warehouse_id, sku), [])
        if not history:
            return {
                "warehouse_id": warehouse_id,
                "sku": sku,
                "avg_monthly_sales": 0.0,
                "trend": "unknown",
                "total_sales": 0.0,
                "months_of_data": 0,
            }

        avg = sum(history) / len(history)
        total = sum(history)

        # Basit trend hesaplama: son 3 ay vs ilk 3 ay
        if len(history) >= 6:
            recent = sum(history[-3:]) / 3
            earlier = sum(history[:3]) / 3
            if earlier > 0:
                trend_ratio = recent / earlier
                if trend_ratio > 1.1:
                    trend = "increasing"
                elif trend_ratio < 0.9:
                    trend = "decreasing"
                else:
                    trend = "stable"
            else:
                trend = "increasing" if recent > 0 else "stable"
        else:
            trend = "insufficient_data"

        return {
            "warehouse_id": warehouse_id,
            "sku": sku,
            "avg_monthly_sales": round(avg, 2),
            "trend": trend,
            "total_sales": round(total, 2),
            "months_of_data": len(history),
        }

    # --- Gereksinim 3.4: Mevsimsel trend tespiti ---

    def calculate_seasonal_factor(
        self, sku: str, month: Optional[int] = None
    ) -> float:
        """Ürün kategorisine göre mevsimsel çarpanı hesaplar."""
        if month is None:
            month = datetime.utcnow().month

        category = self._product_categories.get(sku, "")
        seasonal_info = SEASONAL_MULTIPLIERS.get(category)

        if seasonal_info and month in seasonal_info["high_season"]:
            return seasonal_info["multiplier"]
        return 1.0

    # --- Gereksinim 3.5: Bölgesel faktör hesaplama ---

    def calculate_regional_factor(self, warehouse_id: str) -> float:
        """Depo bölgesine göre bölgesel çarpanı hesaplar."""
        region = self._warehouse_regions.get(warehouse_id, "")
        return REGIONAL_MULTIPLIERS.get(region, 1.0)

    # --- Gereksinim 3.1: Satış potansiyeli hesaplama ---

    def calculate_sales_potential(
        self, warehouse_id: str, sku: str, month: Optional[int] = None
    ) -> SalesPrediction:
        """Bir depo-SKU çifti için satış potansiyeli skoru hesaplar.

        Skor = ortalama_günlük_satış × mevsimsel_çarpan × bölgesel_çarpan
        Normalize edilmiş skor 0-100 arasında döndürülür.
        """
        analysis = self.analyze_sales_history(warehouse_id, sku)
        avg_monthly = analysis["avg_monthly_sales"]
        avg_daily = avg_monthly / 30.0 if avg_monthly > 0 else 0.0

        seasonal = self.calculate_seasonal_factor(sku, month)
        regional = self.calculate_regional_factor(warehouse_id)

        predicted_daily = avg_daily * seasonal * regional

        # Normalize: 0-100 arası skor (max günlük satış 50 varsayımı)
        raw_score = predicted_daily * seasonal * regional
        score = min(100.0, (raw_score / 50.0) * 100.0) if raw_score > 0 else 0.0

        # Confidence: veri miktarına göre
        months = analysis["months_of_data"]
        confidence = min(1.0, months / 12.0)

        prediction = SalesPrediction(
            warehouse_id=warehouse_id,
            sku=sku,
            predicted_daily_sales=round(predicted_daily, 2),
            sales_potential_score=round(score, 2),
            seasonal_factor=seasonal,
            regional_factor=regional,
            confidence=round(confidence, 2),
        )

        self.log_decision(
            decision_type="sales_potential_calculation",
            input_data={
                "warehouse_id": warehouse_id,
                "sku": sku,
                "avg_daily_sales": avg_daily,
            },
            output_data={
                "predicted_daily_sales": prediction.predicted_daily_sales,
                "sales_potential_score": prediction.sales_potential_score,
            },
            reasoning=(
                f"Satış potansiyeli hesaplandı: günlük={predicted_daily:.2f}, "
                f"mevsimsel={seasonal}, bölgesel={regional}, skor={score:.2f}"
            ),
        )

        return prediction

    # --- Gereksinim 3.2, 3.5: En yüksek potansiyelli depo seçimi ---

    def rank_warehouses_by_potential(
        self, sku: str, warehouse_ids: list[str], month: Optional[int] = None
    ) -> list[SalesPrediction]:
        """Verilen depoları satış potansiyeline göre sıralar (yüksekten düşüğe)."""
        predictions = [
            self.calculate_sales_potential(wh_id, sku, month)
            for wh_id in warehouse_ids
        ]
        predictions.sort(key=lambda p: p.sales_potential_score, reverse=True)
        return predictions

    def get_best_warehouse(
        self, sku: str, warehouse_ids: list[str], month: Optional[int] = None
    ) -> Optional[SalesPrediction]:
        """Bir SKU için en yüksek satış potansiyeline sahip depoyu döndürür."""
        ranked = self.rank_warehouses_by_potential(sku, warehouse_ids, month)
        return ranked[0] if ranked else None

    # --- Görev 5.6: Nova model ile satış tahmin prompt'ları ---

    def predict_with_model(self, warehouse_id: str, sku: str) -> dict:
        """Nova model kullanarak detaylı satış tahmini yapar."""
        analysis = self.analyze_sales_history(warehouse_id, sku)
        category = self._product_categories.get(sku, "Bilinmiyor")
        region = self._warehouse_regions.get(warehouse_id, "Bilinmiyor")

        prompt = (
            f"Satış tahmini yap:\n"
            f"- Depo: {warehouse_id} (Bölge: {region})\n"
            f"- SKU: {sku} (Kategori: {category})\n"
            f"- Ortalama aylık satış: {analysis['avg_monthly_sales']}\n"
            f"- Trend: {analysis['trend']}\n"
            f"- Mevcut ay: {datetime.utcnow().month}\n\n"
            f"Önümüzdeki 3 ay için günlük satış tahmini yap. "
            f'JSON formatında yanıt ver: {{"next_3_months": [daily1, daily2, daily3], "confidence": 0.0-1.0}}'
        )

        try:
            response_text = self.invoke_model(prompt, max_tokens=500, temperature=0.5)
            return {"warehouse_id": warehouse_id, "sku": sku, "prediction": response_text}
        except Exception as e:
            logger.error("Model tahmin hatası: %s", e)
            return {"error": str(e)}

    def process(self, warehouse_id: str, sku: str) -> SalesPrediction:
        """Ana işlem: satış potansiyeli hesapla."""
        return self.calculate_sales_potential(warehouse_id, sku)

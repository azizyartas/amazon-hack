"""Tüm agentlar için temel sınıf - Bedrock Agent Core entegrasyonu."""

from __future__ import annotations

import json
import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional

import boto3
from botocore.exceptions import ClientError

from src.models.warehouse import AgentDecision

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """AWS Bedrock tabanlı agent temel sınıfı."""

    def __init__(
        self,
        agent_name: str,
        model_id: str,
        region_name: str = "us-east-1",
        bedrock_runtime_client: Optional[Any] = None,
        dynamodb_resource: Optional[Any] = None,
        s3_client: Optional[Any] = None,
    ):
        self.agent_name = agent_name
        self.model_id = model_id
        self.region_name = region_name

        # AWS istemcileri - dependency injection destekli
        self.bedrock_runtime = bedrock_runtime_client or boto3.client(
            "bedrock-runtime", region_name=region_name
        )
        self.dynamodb = dynamodb_resource or boto3.resource(
            "dynamodb", region_name=region_name
        )
        self.s3 = s3_client or boto3.client("s3", region_name=region_name)

        # Tablo referansları
        self.inventory_table = self.dynamodb.Table("Inventory")
        self.warehouses_table = self.dynamodb.Table("Warehouses")
        self.products_table = self.dynamodb.Table("Products")
        self.transfers_table = self.dynamodb.Table("Transfers")
        self.decisions_table = self.dynamodb.Table("AgentDecisions")

        self._decisions: list[AgentDecision] = []

        logger.info("Agent başlatıldı: %s (model: %s)", agent_name, model_id)

    def invoke_model(self, prompt: str, max_tokens: int = 1000, temperature: float = 0.7) -> str:
        """Bedrock Nova modelini çağırır (inference profile kullanarak)."""
        try:
            response = self.bedrock_runtime.invoke_model(
                modelId=self.model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(
                    {
                        "messages": [{"role": "user", "content": [{"text": prompt}]}],
                        "inferenceConfig": {
                            "max_new_tokens": max_tokens,
                            "temperature": temperature,
                        },
                    }
                ),
            )
            result = json.loads(response["body"].read())
            return result.get("output", {}).get("message", {}).get("content", [{}])[0].get("text", "")
        except ClientError as e:
            logger.error("Bedrock API hatası [%s]: %s", self.agent_name, e)
            raise

    def log_decision(
        self,
        decision_type: str,
        input_data: dict,
        output_data: dict,
        reasoning: str,
    ) -> AgentDecision:
        """Agent kararını loglar ve DynamoDB'ye kaydeder."""
        decision = AgentDecision(
            decision_id=str(uuid.uuid4()),
            agent_name=self.agent_name,
            decision_type=decision_type,
            input_data=input_data,
            output_data=output_data,
            reasoning=reasoning,
        )
        self._decisions.append(decision)

        try:
            self.decisions_table.put_item(
                Item={
                    "decision_id": decision.decision_id,
                    "agent_name": decision.agent_name,
                    "decision_type": decision.decision_type,
                    "input_data": json.dumps(input_data),
                    "output_data": json.dumps(output_data),
                    "reasoning": reasoning,
                    "timestamp": decision.timestamp,
                }
            )
        except ClientError as e:
            logger.warning("Karar loglama hatası: %s", e)

        # S3'e de logla
        try:
            self.log_to_s3({
                "decision_id": decision.decision_id,
                "agent_name": decision.agent_name,
                "decision_type": decision_type,
                "input_data": input_data,
                "output_data": output_data,
                "reasoning": reasoning,
                "timestamp": decision.timestamp,
            }, prefix=f"{decision_type}-")
        except Exception as e:
            logger.warning("S3 karar log hatası: %s", e)

        return decision

    def log_to_s3(self, log_data: dict, prefix: str = "") -> None:
        """Agent logunu S3'e kaydeder."""
        timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S")
        key = f"agent-logs/{self.agent_name.lower().replace(' ', '-')}/{prefix}{timestamp}.json"
        try:
            # Bucket adini dinamik al
            if not hasattr(self, '_s3_bucket_name') or not self._s3_bucket_name:
                sts = boto3.client("sts", region_name=self.region_name, verify=False)
                account_id = sts.get_caller_identity()["Account"]
                self._s3_bucket_name = f"warehouse-stock-mgmt-{account_id}"
            self.s3.put_object(
                Bucket=self._s3_bucket_name,
                Key=key,
                Body=json.dumps(log_data, default=str),
            )
        except ClientError as e:
            logger.warning("S3 log hatası: %s", e)

    @abstractmethod
    def process(self, *args: Any, **kwargs: Any) -> Any:
        """Her agent kendi iş mantığını implement eder."""
        ...

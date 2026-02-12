"""
Deploy edilen AgentCore agent'i programatik olarak cagirmak icin script.

Kullanim:
    python infra/invoke_agent.py "kritik stoklari goster"
    python infra/invoke_agent.py "WH001 icin stok durumu nedir?"
    python infra/invoke_agent.py "SKU001 icin transfer oner"

Not: .bedrock_agentcore.yaml dosyasindan ARN otomatik okunur.
     Yoksa AGENT_ARN env var kullanilir.
"""

import json
import sys
import uuid
import os

import boto3
import yaml


def get_agent_arn() -> str:
    """ARN'i config dosyasindan veya env var'dan al."""
    # Once env var
    arn = os.environ.get("AGENT_ARN")
    if arn:
        return arn

    # .bedrock_agentcore.yaml'dan oku
    config_path = ".bedrock_agentcore.yaml"
    if os.path.exists(config_path):
        with open(config_path) as f:
            config = yaml.safe_load(f)
        arn = config.get("bedrock_agentcore", {}).get("agent_runtime_arn")
        if arn:
            return arn

    print("HATA: Agent ARN bulunamadi.")
    print("  Ya AGENT_ARN env var ayarlayin ya da agentcore deploy yapin.")
    sys.exit(1)


def invoke(prompt: str, session_id: str = None):
    agent_arn = get_agent_arn()
    session_id = session_id or str(uuid.uuid4())

    client = boto3.client("bedrock-agentcore")
    payload = json.dumps({"prompt": prompt, "session_id": session_id}).encode()

    print(f"Agent ARN: {agent_arn}")
    print(f"Session: {session_id}")
    print(f"Prompt: {prompt}")
    print("-" * 50)

    response = client.invoke_agent_runtime(
        agentRuntimeArn=agent_arn,
        runtimeSessionId=session_id,
        payload=payload,
        qualifier="DEFAULT",
    )

    content = []
    for chunk in response.get("response", []):
        content.append(chunk.decode("utf-8"))

    result = json.loads("".join(content))
    print(result.get("result", result))
    return result


if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Merhaba, sistem durumunu ozetle"
    invoke(prompt)

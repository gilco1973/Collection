# Walkthrough: bedrock-converse-adapter

## 1. Run the live example

```
cd components/python/bedrock-converse-adapter && python3 example.py
```

The Converse request exactly as Bedrock receives it (URL with the inference profile ARN, SigV4 header, system and user blocks, the guardrail), and the text and token counts parsed back.

## 2. Copy the two files

```
cp bedrock.py sigv4.py /path/to/your-service/
```

## 3. Configure names, never keys

The model id is an application inference profile ARN from configuration; the region and an optional private endpoint likewise. The task role signs. There is no API key anywhere.

## 4. Put it behind the gateway

```python
gateway = ModelGateway(BedrockConverseAdapter(http, region), profiles, allowlist, prompts, telemetry)
```

The gateway enforces the allowlist, loads the prompt by reference with its hash, charges tokens to the session's budget and stamps the model context on the record. Your engine calls the gateway, never the adapter.

## 5. Handle refusal

An answer without a usable message raises `BedrockConverseError`; turn it into the typed stop `vendor.refusal` and keep the record intact. Never guess an answer.

## 6. Prove it

```
python3 -m unittest discover -s tests -t . -v
```

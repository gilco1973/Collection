# Walkthrough: aws-sigv4

## 1. Run the live example

```
cd components/python/aws-sigv4 && python3 example.py
```

A Secrets Manager call signed with fixed credentials: the date, the payload hash and the Authorization header, then the call through a fake HTTP double.

## 2. Copy the file next to the HTTP client

```
cp sigv4.py /path/to/your-service/
```

It needs an object with `request(method, url, headers, body)`; `stdlib-http-client` is one.

## 3. Let the task role be the credential

`AwsJson(http, region)` loads credentials from the ECS container endpoint, then the instance role, then the environment. In production there is no key to configure and nothing to rotate.

## 4. Call a JSON-protocol service

```python
aws.call("secretsmanager", "secretsmanager", "secretsmanager.GetSecretValue", {"SecretId": "app/pagerduty-api"})
aws.call("ecs", "ecs", "AmazonEC2ContainerServiceV20141113.DescribeServices", {...})
```

For the query protocol (CloudWatch metrics), `aws.query(service, prefix, params)` returns the XML bytes.

## 5. Prove it

```
python3 -m unittest discover -s tests -t . -v
```

The first test is the documented key-derivation vector from AWS.

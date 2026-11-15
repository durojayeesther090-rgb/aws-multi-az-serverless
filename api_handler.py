"""HTTP API handler: POST /items, GET /items, GET /items/{id} backed by DynamoDB."""
import json
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3

table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])


def _default(o):
    if isinstance(o, Decimal):
        return int(o) if o % 1 == 0 else float(o)
    raise TypeError


def _response(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=_default),
    }


def handler(event, context):
    route = event.get("routeKey")

    if route == "POST /items":
        try:
            payload = json.loads(event.get("body") or "{}")
        except json.JSONDecodeError:
            return _response(400, {"error": "Body must be valid JSON"})
        if not isinstance(payload, dict) or not payload.get("name"):
            return _response(400, {"error": "'name' is required"})
        item = {
            "id": str(uuid.uuid4()),
            "source": "api",
            "name": str(payload["name"]),
            "description": str(payload.get("description", "")),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        table.put_item(Item=item)
        return _response(201, item)

    if route == "GET /items":
        result = table.scan(Limit=50)
        return _response(200, {"items": result.get("Items", [])})

    if route == "GET /items/{id}":
        item_id = event["pathParameters"]["id"]
        result = table.get_item(Key={"id": item_id})
        if "Item" not in result:
            return _response(404, {"error": "Item not found"})
        return _response(200, result["Item"])

    return _response(404, {"error": "Route not found"})

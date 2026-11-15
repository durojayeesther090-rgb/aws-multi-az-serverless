"""S3 event handler: stores metadata for every uploaded object in DynamoDB."""
import os
from datetime import datetime, timezone
from urllib.parse import unquote_plus

import boto3

s3 = boto3.client("s3")
table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])


def handler(event, context):
    processed = 0
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])

        head = s3.head_object(Bucket=bucket, Key=key)
        table.put_item(
            Item={
                "id": f"file#{key}",
                "source": "s3-upload",
                "name": key,
                "bucket": bucket,
                "size_bytes": head["ContentLength"],
                "content_type": head.get("ContentType", "unknown"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        processed += 1
        print(f"Recorded s3://{bucket}/{key}")

    return {"processed": processed}

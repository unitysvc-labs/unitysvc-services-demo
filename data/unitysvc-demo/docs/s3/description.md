## S3 Content via UnitySVC Storage Gateway

Access S3-compatible content through UnitySVC's storage gateway using any
S3 client (boto3, aws-cli, rclone, cyberduck) authenticated with your
UnitySVC API key.

```python
import boto3

s3 = boto3.client('s3',
    endpoint_url='{{ S3_GATEWAY_PUBLIC_URL }}',
    aws_access_key_id='{{ API_KEY }}',
    aws_secret_access_key='not-used',
)

# Browse available files
s3.list_objects_v2(Bucket='{{ SERVICE_NAME }}', MaxKeys=10)
```

The gateway authenticates you against your UnitySVC API key, resolves the
upstream bucket from the service configuration, and proxies the request.

import logging
import sys

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

qualifier = sys.argv[1]
stack_name = sys.argv[2]
# Set default values
account = None
region = None
# Check if region argument is provided
if len(sys.argv) > 4:
    account = sys.argv[3] if sys.argv[3] != "" else None
    region = sys.argv[4] if sys.argv[4] != "" else None

s3 = boto3.resource("s3", region_name=region)
cloudformation = boto3.resource("cloudformation", region_name=region)

account = account if account else boto3.client("sts").get_caller_identity()["Account"]
region = region if region else boto3.session.Session().region_name

try:
    logger.info(f"Deleting stack {stack_name} in account {account} and region {region}")
    stack = cloudformation.Stack(stack_name)
    stack.delete()
    logger.info(f"Deleting S3 bucket cdk-{qualifier}-assets-{account}-{region}")
    bucket = s3.Bucket(f"cdk-{qualifier}-assets-{account}-{region}")
    bucket.objects.delete()
    bucket.object_versions.delete()
    bucket.delete()
    logger.info(f"Stack {stack_name} deleted successfully")
except s3.meta.client.exceptions.NoSuchBucket:
    pass

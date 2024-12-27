# s3_bucket.py

from aws_cdk import RemovalPolicy
from aws_cdk import aws_s3 as s3
from constructs import Construct


class L3S3Bucket(Construct):
    def __init__(
        self, scope: Construct, id: str, *, bucket_name: str, log_bucket_name: str, **kwargs
    ) -> None:
        super().__init__(scope, id, **kwargs)

        # Create a log bucket for server access logging
        self.log_bucket = s3.Bucket(
            self,
            log_bucket_name,
            versioned=True,
            removal_policy=RemovalPolicy.DESTROY,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            public_read_access=False,
        )

        # Create the main S3 bucket
        self.bucket = s3.Bucket(
            self,
            bucket_name,
            versioned=True,
            public_read_access=False,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            lifecycle_rules=kwargs.get("lifecycle_rules", []),
            server_access_logs_bucket=self.log_bucket,
            server_access_logs_prefix="access-logs/",
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
        )

    def get_bucket(self) -> s3.IBucket:
        """Return the bucket instance"""
        return self.bucket

    def get_log_bucket(self) -> s3.IBucket:
        """Return the log bucket instance"""
        return self.log_bucket

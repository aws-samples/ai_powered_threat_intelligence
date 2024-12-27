from typing import List, Mapping, Optional

from aws_cdk import Duration
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_lambda as lambda_
from constructs import Construct


class L3Lambda(lambda_.Function):
    def __init__(
        self,
        scope: Construct,
        id: str,
        handler: str,
        code_path: Optional[str] = None,
        code: Optional[lambda_.Code] = None,
        runtime: Optional[lambda_.Runtime] = None,
        role: Optional[iam.Role] = None,
        vpc: Optional[str] = None,
        memory_size: int = 128,
        timeout: Duration = Duration.seconds(60),
        description: Optional[str] = None,
        layers: Optional[List[lambda_.LayerVersion]] = None,
        environment: Optional[Mapping] = None,
        environment_encryption: Optional[kms.Key] = None,
        security_groups: Optional[List[ec2.SecurityGroup]] = None,
    ):
        super(L3Lambda, self).__init__(
            scope=scope,
            id=id,
            runtime=runtime,
            code=code or lambda_.Code.from_asset(code_path),
            handler=handler,
            role=role,
            vpc=vpc,
            memory_size=memory_size or 128,
            timeout=timeout,
            description=description,
            layers=layers,
            environment=environment,
            environment_encryption=environment_encryption,
            security_groups=security_groups,
        )

        if environment_encryption:
            environment_encryption.grant_encrypt_decrypt(self)

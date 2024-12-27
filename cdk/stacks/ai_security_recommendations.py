import os

import cdk_nag
import constants
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_sns as sns
from constructs import Construct
from l3constructs.helpers.base_stack import BaseStack
from l3constructs.lambda_functions.L3LambdaPython import L3LambdaPython
from l3constructs.s3.l3_bucket import L3S3Bucket


class AISecurityRecommendations(BaseStack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Instantiate the L3 S3 bucket with loggin enabled
        bucket_construct = L3S3Bucket(
            self,
            "AiReportsBucketConstruct",
            bucket_name="AiReportsBucket",
            log_bucket_name="AiReportsLogBucket",
        )

        # Access the bucket and log bucket if needed
        self.reports_bucket = bucket_construct.get_bucket()
        self.log_bucket = bucket_construct.get_log_bucket()

        # create the SNS topic for the notifications
        # Create a KMS key for encryption
        self.topic_encryption_key = kms.Key(
            self, f"{id}Key", enable_key_rotation=True  # Enable key rotation for added security
        )
        self.topic = sns.Topic(
            self,
            "AiSecurityRecommendationsTopic",
            topic_name="AiSecurityRecommendationsTopic",
            display_name="AI Security Recommendations Topic",
            enforce_ssl=True,
            master_key=self.topic_encryption_key,
        )

        # event bridge rule to trigger the lambda based on guardduty event
        self.rule = events.Rule(
            self,
            "AiSecurityRecommendationsRule",
            event_pattern=events.EventPattern(
                source=["aws.guardduty"], detail_type=["GuardDuty Finding"]
            ),
        )

        # Create a custom IAM role for the Lambda function
        self.lambda_role = iam.Role(
            self, "LambdaExecutionRole", assumed_by=iam.ServicePrincipal("lambda.amazonaws.com")
        )

        # Create the Lambda function using the L3 construct
        self.lambda_function = L3LambdaPython(
            self,
            "L3LambdaPython",
            code=os.path.join(
                os.path.dirname(__file__), "..", "..", "app", "ai_generator"
            ),  # Path to Lambda code
            handler="index.lambda_handler",  # Lambda entry point
            role=self.lambda_role,  # Set the custom role
            # layers=[constants.LAMBDA_PILLOW_LAYER],
            environment={
                "AI_REPORTS_BUCKET_NAME": self.reports_bucket.bucket_name,
                "AI_REPORTS_TOPIC_ARN": self.topic.topic_arn,
                "BEDROCK_MODEL_ID": constants.BEDROCK_MODEL_ID,
                "body_args_anthropic_version": constants.ANTROPIC_VERSION,
            },
        )

        # # Grant write access to the Lambda function for the S3 bucket
        self.reports_bucket.grant_write(self.lambda_function.role)
        self.lambda_function.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaBasicExecutionRole"
            )
        )

        # add cdk_nag exclusion for lambda role resource
        # Suppress the AWS managed policy warning
        cdk_nag.NagSuppressions.add_resource_suppressions(
            self.lambda_role,
            [
                cdk_nag.NagPackSuppression(
                    id="AwsSolutions-IAM4",
                    reason="Managed Policies are for service account roles only",
                )
            ],
            apply_to_children=True,
        )

        cdk_nag.NagSuppressions.add_resource_suppressions(
            self.lambda_role,
            [
                cdk_nag.NagPackSuppression(
                    id="AwsSolutions-IAM5",
                    reason="Managed Policies are for service account roles only",
                )
            ],
            apply_to_children=True,
        )

        # Grant write, read access to the bucket to store the pdf and generate the pre-signed link
        self.lambda_function.role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["s3:PutObject", "s3:GetObject", "s3:ListBucket"],
                resources=[self.reports_bucket.bucket_arn, self.reports_bucket.bucket_arn + "/*"],
            )
        )

        # Grant publish access to the SNS topic
        # self.topic.grant_publish(self.lambda_function.role) permissions are to wide for this
        self.topic.add_to_resource_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                principals=[iam.ServicePrincipal("lambda.amazonaws.com")],
                actions=["sns:Publish"],
                resources=[self.topic.topic_arn],
                conditions={"ArnEquals": {"aws:SourceArn": self.lambda_function.function_arn}},
            )
        )
        self.topic_encryption_key.grant_encrypt_decrypt(self.lambda_function.role)

        # Grant sns Publish access to the lambda function role
        self.lambda_function.role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW, actions=["sns:Publish"], resources=[self.topic.topic_arn]
            )
        )

        # Grant Guardduty access to the lambda function role
        self.lambda_function.role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "guardduty:GetFindings",
                    "guardduty:ListDetectors",
                    "guardduty:ListFindings",
                ],
                resources=["arn:aws:guardduty:*:*:detector/*"],
            )
        )
        # Grant Permissions to query detective
        self.lambda_function.role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "detective:ListGraphs",
                    "detective:GetMembers",
                    "detective:ListDatasourcePackages",
                    "detective:ListActivities",
                    "detective:ListMembers",
                ],
                resources=["*"],
            )
        )
        # lets grant permission to invoke the bedrock model
        self.lambda_function.role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["bedrock:InvokeModel"],
                resources=[
                    f"arn:aws:bedrock:{self.region}::model/{constants.BEDROCK_MODEL_ID}",
                    f"arn:aws:bedrock:{self.region}::foundation-model/{constants.BEDROCK_MODEL_ID}",
                ],
            )
        )
        # grant permissions to reschedule an event in case of throttling
        self.lambda_function.role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "events:PutRule",
                    "events:PutTargets",
                    "events:DeleteRule",
                    "events:RemoveTargets",
                ],
                resources=[
                    f"arn:aws:events:{self.region}:{self.account}:rule/RetryLambdaInvocation-*"
                ],
            )
        )
        # grant invoke to sns event to trigger lambda function from resource arn:aws:events:*:{self.account}:rule/RetryLambdaInvocation-*
        # Add permission for the Event Rule to invoke the Lambda function
        self.lambda_function.add_permission(
            "RetryEventsPermissions",
            principal=iam.ServicePrincipal("events.amazonaws.com"),
            action="lambda:InvokeFunction",
            source_arn=f"arn:aws:events:{self.region}:{self.account}:rule/RetryLambdaInvocation-*",
        )
        # lets connect event bridge rule to the lambda function
        self.rule.add_target(targets.LambdaFunction(self.lambda_function))

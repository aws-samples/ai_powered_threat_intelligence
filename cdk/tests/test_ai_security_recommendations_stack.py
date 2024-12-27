import pytest
from aws_cdk import App, assertions
from l3constructs.helpers.helper import Helper
from stacks.ai_security_recommendations import AISecurityRecommendations


@pytest.fixture(scope="module")
def load_stack():
    app = App()
    Helper(tags={}, prefix="")
    stack = AISecurityRecommendations(app, "AISecurityRecommendations", env={"region": "us-east-1"})
    return assertions.Template.from_stack(stack)


# Test to check if the S3 bucket is created
def test_s3_bucket_created(load_stack):
    load_stack.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "BucketEncryption": assertions.Match.any_value(),
            "LoggingConfiguration": assertions.Match.object_like(
                {"DestinationBucketName": assertions.Match.any_value()}
            ),
            "PublicAccessBlockConfiguration": assertions.Match.any_value(),
            "VersioningConfiguration": assertions.Match.any_value(),
        },
    )


# Test to verify if SNS Topic is created with encryption enabled
def test_sns_topic_created_with_encryption(load_stack):
    load_stack.has_resource_properties(
        "AWS::SNS::Topic",
        {
            "TopicName": "AiSecurityRecommendationsTopic",
            "KmsMasterKeyId": assertions.Match.any_value(),
        },
    )


# Test to check if the EventBridge Rule is created for GuardDuty events
def test_event_rule_created(load_stack):
    load_stack.has_resource_properties(
        "AWS::Events::Rule",
        {"EventPattern": {"source": ["aws.guardduty"], "detail-type": ["GuardDuty Finding"]}},
    )


# Test to check if Lambda function is created with correct environment variables
def test_lambda_function_created(load_stack):
    load_stack.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Handler": "index.lambda_handler",
            "Environment": {
                "Variables": {
                    "AI_REPORTS_BUCKET_NAME": assertions.Match.any_value(),
                    "AI_REPORTS_TOPIC_ARN": assertions.Match.any_value(),
                    "BEDROCK_MODEL_ID": assertions.Match.any_value(),
                }
            },
        },
    )


# Test to check if Lambda function has S3, SNS, and GuardDuty permissions
def test_lambda_has_required_permissions(load_stack):
    expected_policy = {
        "Statement": [
            {
                "Action": [
                    "s3:DeleteObject*",
                    "s3:PutObject",
                    "s3:PutObjectLegalHold",
                    "s3:PutObjectRetention",
                    "s3:PutObjectTagging",
                    "s3:PutObjectVersionTagging",
                    "s3:Abort*",
                ],
                "Effect": "Allow",
                "Resource": assertions.Match.any_value(),
            },
            {
                "Action": ["s3:PutObject", "s3:GetObject", "s3:ListBucket"],
                "Effect": "Allow",
                "Resource": assertions.Match.any_value(),
            },
            {
                "Action": ["kms:Decrypt", "kms:Encrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*"],
                "Effect": "Allow",
                "Resource": assertions.Match.any_value(),
            },
            {"Action": "sns:Publish", "Effect": "Allow", "Resource": assertions.Match.any_value()},
            {
                "Action": [
                    "guardduty:GetFindings",
                    "guardduty:ListDetectors",
                    "guardduty:ListFindings",
                ],
                "Effect": "Allow",
                "Resource": "arn:aws:guardduty:*:*:detector/*",
            },
            {
                "Action": [
                    "detective:ListGraphs",
                    "detective:GetMembers",
                    "detective:ListDatasourcePackages",
                    "detective:ListActivities",
                    "detective:ListMembers",
                ],
                "Effect": "Allow",
                "Resource": "*",
            },
            {
                "Action": "bedrock:InvokeModel",
                "Effect": "Allow",
                "Resource": assertions.Match.any_value(),
            },
            {
                "Action": [
                    "events:PutRule",
                    "events:PutTargets",
                    "events:DeleteRule",
                    "events:RemoveTargets",
                ],
                "Effect": "Allow",
                "Resource": assertions.Match.any_value(),
            },
        ],
        "Version": "2012-10-17",
    }

    load_stack.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": expected_policy,
            "PolicyName": "LambdaExecutionRoleDefaultPolicy6D69732F",
            "Roles": [{"Ref": "LambdaExecutionRoleD5C26073"}],
        },
    )


# Test for EventBridge rescheduling permissions in Lambda IAM policy
def test_lambda_rescheduling_permissions(load_stack):
    load_stack.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": {
                "Statement": assertions.Match.array_with(
                    [
                        assertions.Match.object_like(
                            {
                                "Action": [
                                    "events:PutRule",
                                    "events:PutTargets",
                                    "events:DeleteRule",
                                    "events:RemoveTargets",
                                ],
                                "Effect": "Allow",
                                "Resource": assertions.Match.any_value(),
                            }
                        )
                    ]
                )
            }
        },
    )


# Test if KMS key is created with key rotation enabled
def test_kms_key_with_rotation(load_stack):
    load_stack.has_resource_properties("AWS::KMS::Key", {"EnableKeyRotation": True})

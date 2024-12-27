import os
from io import BytesIO
from unittest import mock

import pytest
from attr import dataclass

ACCOUNT_ID = "123456789012"
REGION = "us-east-1"
FINDING_ID = "test_finding_id"
MEMBER_DETAILS = [{"AccountId": ACCOUNT_ID, "Email": "test@example.com"}]
DETECTOR_ID = "test_detector_id"
GRAPH_ARN = "test_graph_arn"
S3_BUCKET_NAME = "test-bucket"
TEST_FINDING = {
    "Findings": [
        {
            "Id": FINDING_ID,
            "Severity": 6,
            "Type": "UnauthorizedAccess:EC2/SSHBruteForce",
            "AccountId": ACCOUNT_ID,
            "Region": REGION,
        }
    ]
}
SNS_TOPIC_ARN = "arn:aws:sns:us-east-1:123456789012:my-test-topic"
EVENT = {
    "version": "0",
    "id": "sample-event-id",
    "detail-type": "GuardDuty Finding",
    "source": "aws.guardduty",
    "account": ACCOUNT_ID,
    "time": "2024-10-18T11:40:01Z",
    "region": REGION,
    "resources": [],
    "detail": {
        "schemaVersion": "2.0",
        "accountId": "123456789012",
        "region": "us-east-1",
        "id": FINDING_ID,
        "partition": "aws",
        "arn": f"arn:aws:guardduty:us-east-1:123456789012:detector/sample-detector/finding/{FINDING_ID}",
        "type": "UnauthorizedAccess:EC2/SSHBruteForce",
        "severity": 5.0,
        "service": {
            "serviceName": "guardduty",
            "detectorId": "sample-detector",
            "action": {
                "actionType": "NETWORK_CONNECTION",
                "networkConnectionAction": {"remoteIpDetails": {"ipAddressV4": "8.8.8.8"}},
            },
        },
        "resource": {
            "resourceType": "Instance",
            "instanceDetails": {"instanceId": "i-1234567890abcdef0"},
        },
    },
}


@pytest.fixture()
def get_detective_list_graphs_response():
    return {"GraphList": [{"Arn": GRAPH_ARN}], "NextToken": None}


@pytest.fixture()
def get_detective_list_members_response():
    return {"MemberDetails": MEMBER_DETAILS, "NextToken": None}


@pytest.fixture()
def mock_detective_client(get_detective_list_graphs_response, get_detective_list_members_response):
    detective_client = mock.MagicMock(name="MockDetectiveClient")
    detective_client.list_graphs.return_value = get_detective_list_graphs_response
    detective_client.list_members.return_value = get_detective_list_members_response
    return detective_client


@pytest.fixture()
def mock_guardduty_client():
    guardduty_client = mock.MagicMock(name="MockGuardDutyClient")
    guardduty_client.get_detector.return_value = {"DetectorId": DETECTOR_ID}
    guardduty_client.get_findings.return_value = TEST_FINDING
    return guardduty_client


@pytest.fixture()
def mock_s3_client():
    s3_client = mock.MagicMock(name="MockS3Client")
    s3_client.create_bucket.return_value = {"Location": S3_BUCKET_NAME}
    s3_client.upload_fileobj.return_value = None
    s3_client.put_object.return_value = None
    return s3_client


@pytest.fixture()
def mock_sns_client():
    sns_client = mock.MagicMock(name="MockSNSClient")
    sns_client.create_topic.return_value = {"TopicArn": SNS_TOPIC_ARN}
    sns_client.publish.return_value = {"MessageId": "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"}
    return sns_client


@pytest.fixture()
def get_bedrock_invoke_model_response():
    return {"body": BytesIO(b'{"content": [{"text": "Test AI Insights"}]}')}


@pytest.fixture()
def mock_bedrock_client(get_bedrock_invoke_model_response):
    bedrock_client = mock.MagicMock(name="MockBedrockClient")
    bedrock_client.invoke_model.return_value = get_bedrock_invoke_model_response
    return bedrock_client


@pytest.fixture()
def mock_events_client():
    events_client = mock.MagicMock(name="MockEventsClient")
    return events_client


# Generates a mock lambda context
@pytest.fixture(autouse=True)
def lambda_context():
    @dataclass
    class context:
        function_name = "test"
        memory_limit_in_mb = 128
        invoked_function_arn = f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:test"
        aws_request_id = "52fdfc07-2182-154f-163f-5f0f9a621d72"

    return context


# Generate mock environment variables for testing
@pytest.fixture(autouse=True)
def aws_credentials():
    """Mocked AWS Credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_REGION"] = REGION
    os.environ["AWS_DEFAULT_REGION"] = REGION
    os.environ["AWS_ACCOUNT"] = ACCOUNT_ID
    os.environ["POWERTOOLS_METRICS_NAMESPACE"] = "Test"
    os.environ["POWERTOOLS_SERVICE_NAME"] = "ProductPackaging"
    os.environ["LOG_LEVEL"] = "DEBUG"
    os.environ["AI_REPORTS_TOPIC_ARN"] = SNS_TOPIC_ARN
    os.environ["AI_REPORTS_BUCKET_NAME"] = S3_BUCKET_NAME
    os.environ["BEDROCK_MODEL_ID"] = "anthropic.claude-3-5-sonnet-20240620-v1:0"
    os.environ["body_args_anthropic_version"] = "dummy"


@pytest.fixture()
def get_guardduty_event():
    return EVENT

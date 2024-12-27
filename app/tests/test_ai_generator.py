import json
from unittest import mock

import assertpy
import pytest
from botocore.exceptions import ClientError

from app.ai_generator import index
from app.ai_generator.index import (
    generate_pdf,
    get_all_detective_entities,
    get_graph_arn,
    get_guardduty_finding,
    invoke_bedrock_model,
    send_sns_notification,
)
from app.tests.conftest import (
    DETECTOR_ID,
    FINDING_ID,
    GRAPH_ARN,
    MEMBER_DETAILS,
    SNS_TOPIC_ARN,
    TEST_FINDING,
)


def test_get_guardduty_finding(mock_guardduty_client):
    finding = get_guardduty_finding(mock_guardduty_client, DETECTOR_ID, FINDING_ID)
    assertpy.assert_that(finding).is_not_none()
    assertpy.assert_that(finding["Id"]).is_equal_to(FINDING_ID)


def test_get_graph_arn(mock_detective_client):
    graph_arn = get_graph_arn(mock_detective_client)
    assertpy.assert_that(graph_arn).is_not_none()
    assertpy.assert_that(graph_arn).is_equal_to(GRAPH_ARN)


def test_get_all_detective_entities(mock_detective_client):
    entities = get_all_detective_entities(mock_detective_client, GRAPH_ARN)
    assertpy.assert_that(entities).is_not_empty()
    assertpy.assert_that(entities).is_equal_to(MEMBER_DETAILS)


def test_invoke_bedrock_model(mock_bedrock_client, lambda_context, get_guardduty_event):
    ai_insights = invoke_bedrock_model(
        mock_bedrock_client, TEST_FINDING, DETECTOR_ID, get_guardduty_event, lambda_context
    )
    assertpy.assert_that(ai_insights).is_not_none()
    assertpy.assert_that(ai_insights).is_equal_to("Test AI Insights")


def test_generate_pdf():
    ai_insights = "Test AI Insights"
    guardduty_finding = {
        "Id": FINDING_ID,
        "Severity": 6,
        "Type": "UnauthorizedAccess:EC2/SSHBruteForce",
    }
    pdf_buffer = generate_pdf(ai_insights, guardduty_finding)
    assertpy.assert_that(pdf_buffer).is_not_none()
    assertpy.assert_that(len(pdf_buffer.getvalue())).is_greater_than(0)


def test_sns_notification(mock_sns_client):
    pre_signed_url = "https://example.com/pre-signed-url"
    pre_signed_url2 = pre_signed_url.strip().replace(" ", "%20")
    message = {
        "default": "New GuardDuty finding with enriched PDF. Click the link to download.",
        "email": (
            "New GuardDuty finding. Enriched PDF with AI remediation's can be downloaded here: "
            f"{pre_signed_url2}"
        ),
    }
    send_sns_notification(mock_sns_client, pre_signed_url, SNS_TOPIC_ARN)
    mock_sns_client.publish.assert_called_once_with(
        TopicArn=SNS_TOPIC_ARN,
        Message=json.dumps(message),
        Subject="GuardDuty Finding Enrichment Report",
        MessageStructure="json",
    )


# Configure boto3 client mock to return the correct client based on input
@pytest.fixture
def boto_client_side_effect():
    # Create a unique mock for each AWS service client
    # Create a unique mock for each AWS service client with a specified name
    mock_sns_client = mock.Mock(name="MockSNSClient")
    mock_guardduty_client = mock.Mock(name="MockGuardDutyClient")
    mock_detective_client = mock.Mock(name="MockDetectiveClient")
    mock_bedrock_client = mock.Mock(name="MockBedrockClient")
    mock_s3_client = mock.Mock(name="MockS3Client")
    mock_events_client = mock.Mock(name="MockEventsClient")

    # Define the side effect function
    def client_side_effect(service_name, *args, **kwargs):
        if service_name == "sns":
            return mock_sns_client
        elif service_name == "guardduty":
            return mock_guardduty_client
        elif service_name == "detective":
            return mock_detective_client
        elif service_name == "bedrock-runtime":
            return mock_bedrock_client
        elif service_name == "s3":
            return mock_s3_client
        elif service_name == "events":
            return mock_events_client
        else:
            raise ValueError(f"Unexpected service: {service_name}")

    # Return the side effect function and each mock client for test configuration
    return client_side_effect, {
        "sns": mock_sns_client,
        "guardduty": mock_guardduty_client,
        "detective": mock_detective_client,
        "bedrock": mock_bedrock_client,
        "s3": mock_s3_client,
        "events": mock_events_client,
    }


@mock.patch("boto3.client")
def test_lambda_handler(
    mock_boto_client,
    boto_client_side_effect,
    lambda_context,
    get_bedrock_invoke_model_response,
    get_detective_list_graphs_response,
    get_detective_list_members_response,
    get_guardduty_event,
):
    # Mock return values for each AWS service client
    client_side_effect, mock_clients = boto_client_side_effect
    mock_boto_client.side_effect = client_side_effect

    mock_clients["guardduty"].get_findings.return_value = TEST_FINDING
    mock_clients["detective"].list_members.return_value = get_detective_list_members_response
    mock_clients["detective"].list_graphs.return_value = get_detective_list_graphs_response
    mock_clients["bedrock"].invoke_model.return_value = get_bedrock_invoke_model_response
    mock_clients["s3"].put_object.return_value = None
    mock_clients["s3"].generate_presigned_url.return_value = "https://dummyurl"
    mock_clients["sns"].publish.return_value = None
    response = index.lambda_handler(get_guardduty_event, lambda_context)
    assertpy.assert_that(response).is_not_none()
    assertpy.assert_that(response["statusCode"]).is_equal_to(200)
    assertpy.assert_that(json.loads(response["body"])).is_equal_to("Test AI Insights")
    mock_clients["guardduty"].get_findings.assert_called_once()
    mock_clients["detective"].list_members.assert_called_once()
    mock_clients["detective"].list_graphs.assert_called_once()
    mock_clients["bedrock"].invoke_model.assert_called_once()
    mock_clients["s3"].put_object.assert_called_once()
    mock_clients["s3"].generate_presigned_url.assert_called_once()
    mock_clients["sns"].publish.assert_called_once()


@mock.patch("boto3.client")
def test_lambda_handler_bedrock_throttling(
    mock_boto_client,
    boto_client_side_effect,
    lambda_context,
    get_bedrock_invoke_model_response,
    get_detective_list_graphs_response,
    get_detective_list_members_response,
    get_guardduty_event,
):
    client_side_effect, mock_clients = boto_client_side_effect
    mock_boto_client.side_effect = client_side_effect

    mock_clients["guardduty"].get_findings.return_value = TEST_FINDING
    mock_clients["detective"].list_members.return_value = get_detective_list_members_response
    mock_clients["detective"].list_graphs.return_value = get_detective_list_graphs_response
    mock_clients["bedrock"].invoke_model.side_effect = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}, "InvokeModel"
    )
    mock_clients["events"].put_events.return_value = None
    response = index.lambda_handler(get_guardduty_event, lambda_context)
    mock_clients["guardduty"].get_findings.assert_called_once()
    mock_clients["detective"].list_members.assert_called_once()
    mock_clients["detective"].list_graphs.assert_called_once()
    mock_clients["bedrock"].invoke_model.assert_called_once()
    assertpy.assert_that(response).is_not_none()
    assertpy.assert_that(response["statusCode"]).is_equal_to(200)
    assertpy.assert_that(json.loads(response["body"])).is_equal_to("Event scheduled.")

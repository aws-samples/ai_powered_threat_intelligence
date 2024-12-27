import json
import logging
import os
import random
import re
import uuid
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO

import boto3
from botocore.exceptions import ClientError
from fpdf import FPDF

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def convert_to_json_serializable(data):
    """Recursively convert Decimal and other non-serializable types to JSON-compatible types."""
    if isinstance(data, dict):
        return {key: convert_to_json_serializable(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [convert_to_json_serializable(item) for item in data]
    elif isinstance(data, Decimal):
        return float(data)  # Convert Decimal to float for JSON serialization
    elif isinstance(data, datetime):
        return data.isoformat()  # Convert datetime to an ISO 8601 formatted string
    else:
        return data  # Return as is


def convert_to_string(data):
    """Recursively convert float values in a dictionary to string."""
    if isinstance(data, dict):
        return {key: convert_to_string(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [convert_to_string(item) for item in data]
    elif isinstance(data, float):
        try:
            return str(data)  # Convert float to string
        except InvalidOperation:
            return "0"  # Fallback to zero or another default value as a string
    else:
        return data  # Return as is


def get_guardduty_finding(client: boto3.client, detector_id: str, finding_id: str):
    """Retrieve details of a GuardDuty finding."""
    try:
        finding = client.get_findings(DetectorId=detector_id, FindingIds=[finding_id])["Findings"][
            0
        ]
        logger.info("Successfully retrieved GuardDuty finding details")
        return finding
    except Exception as e:
        logger.error("Error retrieving GuardDuty finding: %s", e)
        raise


def get_graph_arn(client: boto3.client):
    """Retrieve the graph ARN for Amazon Detective."""
    try:
        graphs = client.list_graphs()
        if not graphs.get("GraphList", []):
            raise Exception("No graphs found in Amazon Detective.")
        graph_arn = graphs["GraphList"][0]["Arn"]
        logger.info("Retrieved Amazon Detective graph ARN: %s", graph_arn)
        return graph_arn
    except Exception as e:
        logger.error("Error retrieving Amazon Detective graph ARN: %s", e)
        raise


def get_entity_details(client: boto3.client, graph_arn: str, account_id: str):
    """Retrieve entity details from Amazon Detective."""
    try:
        entity_data = client.get_members(GraphArn=graph_arn, AccountIds=[account_id])
        entity_details = entity_data["MemberDetails"][0]
        logger.info("Successfully retrieved entity details from Amazon Detective")
        return entity_details
    except Exception as e:
        logger.error("Error retrieving entity details from Detective: %s", e)
        raise


def list_datasource_packages(client: boto3.client, graph_arn):
    """List data source packages in Detective."""
    try:
        response = client.list_datasource_packages(GraphArn=graph_arn)
        logger.info("Successfully retrieved datasource packages from Amazon Detective")
        return response["DatasourcePackages"]
    except Exception as e:
        logger.error(f"Error retrieving data source packages: {e}")
        return None


def get_all_detective_entities(client: boto3.client, graph_arn: str) -> list:
    """
    Retrieve all entity details from Amazon Detective.

    Args:
        client (boto3.client): The boto3 Detective client.
        graph_arn (str): The ARN of the Detective graph.

    Returns:
        list: A list of member details.

    Raises:
        ClientError: If there's an issue with the AWS API call.
        Exception: For any other unexpected errors.
    """
    try:
        # Call list_members directly since it's not paginated
        response = client.list_members(GraphArn=graph_arn)
        all_members = response.get("MemberDetails", [])

        logger.info(
            f"Successfully retrieved {len(all_members)} entity details from Amazon Detective"
        )
        return all_members

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_message = e.response["Error"]["Message"]
        logger.error(
            f"AWS API error when retrieving entities from Detective: {error_code} - {error_message}"
        )
        raise

    except Exception as e:
        logger.error(f"Unexpected error retrieving entities from Detective: {str(e)}")
        raise


def invoke_bedrock_model(
    client: boto3.client, finding: dict, detective_entities: dict, event: dict, context: dict
):
    """Invoke the Bedrock model and retrieve AI insights."""
    try:
        messages = [
            {
                "role": "user",
                "content": (
                    "You are a cybersecurity assistant that specializes in providing actionable"
                    " solutions for security threats detected by AWS services. Here is the"
                    " GuardDuty finding and relevant enrichment data from Amazon Detective:"
                    f" {json.dumps(finding, indent=4)}. "
                    f"Detective entities involved:"
                    f" {json.dumps(detective_entities, indent=4)}. "
                    "Based on this information,determine if this was a successful breach or a blocked attempt. Also,"
                    " provide information on the entities involved and if a security group is"
                    " impacted and needs intervention.Also, provide specific actions I should take"
                    " to remediate this issue and prevent future occurrences. "
                    "The actions should come with a section header containing \"Remediation Actions:\""
                ),
            }
        ]
        model_id = os.environ.get('BEDROCK_MODEL_ID', 'anthropic.claude-3-5-sonnet-20240620-v1:0')
        # Construct body arguments
        body_args = {
            "messages": messages,
            "max_tokens": 5000,
            "temperature": 0.7,
        }

        # Add additional body arguments from environment variables
        for key, value in os.environ.items():
            if key.startswith('body_args_'):
                arg_name = key[10:]  # Remove 'body_args_' prefix
                # Try to parse the value as JSON, if it fails, use the string value
                try:
                    body_args[arg_name] = json.loads(value)
                except json.JSONDecodeError:
                    body_args[arg_name] = value
        logger.info(f"Body args:{json.dumps(body_args)}")

        ai_response = client.invoke_model(
            modelId=model_id,
            accept="application/json",
            body=json.dumps(body_args)
        )

        ai_insights = json.loads(ai_response["body"].read().decode("utf-8"))
        logger.info(f"AI Response: {json.dumps(ai_insights)}")
        return ai_insights.get("content", [{}])[0].get("text", "")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ThrottlingException":
            # Handle throttling by scheduling a retry event
            return schedule_retry(event, context)
        else:
            logger.error("Error performing AI analysis with Bedrock: %s", e)
            raise
    except Exception as e:
        logger.error("Unexpected error: %s", e)
        raise


def schedule_retry(event: dict, context: dict) -> str:
    client = boto3.client("events")
    """Schedule a one-time retry event with a random delay (up to 10 minutes)."""
    delay_seconds = random.randint(1, 600)  # Random delay between 1 and 600 seconds
    future_time = datetime.utcnow() + timedelta(seconds=delay_seconds)
    event_id = str(uuid.uuid4())

    # Extract relevant details from the original event
    try:
        account_id = event["account"]
        region = event["region"]
        finding_id = event["detail"]["id"]
        detector_id = event["detail"]["service"]["detectorId"]
    except KeyError as e:
        logger.error(f"Missing expected key in event: {e}")
        raise ValueError("Invalid event structure")

    logger.info(f"Scheduling a retry in {delay_seconds} seconds.")

    # Format future time into a cron expression
    cron_expression = (
        f"cron({future_time.minute} {future_time.hour} {future_time.day} {future_time.month} ?"
        f" {future_time.year})"
    )

    logger.info(
        f"Attempting to schedule rule: Retry-{event_id} with ScheduleExpression: {cron_expression}"
    )

    try:
        # Create a one-time EventBridge rule to invoke the Lambda function
        rule_name = f"RetryLambdaInvocation-{event_id}"
        client.put_rule(Name=rule_name, ScheduleExpression=cron_expression, State="ENABLED")
        logger.info(f"Rule {rule_name} created successfully.")

        # Add a target for the EventBridge rule to invoke this Lambda function
        lambda_arn = f"arn:aws:lambda:{region}:{account_id}:function:{context.function_name}"
        client.put_targets(
            Rule=rule_name,
            Targets=[
                {
                    "Id": event_id,
                    "Arn": lambda_arn,
                    "Input": json.dumps(
                        {
                            "version": event["version"],
                            "id": event["id"],
                            "detail-type": event["detail-type"],
                            "source": event["source"],
                            "account": account_id,
                            "time": event["time"],
                            "region": region,
                            "resources": event["resources"],
                            "detail": {
                                "schemaVersion": event["detail"]["schemaVersion"],
                                "accountId": account_id,
                                "region": region,
                                "partition": event["detail"]["partition"],
                                "id": finding_id,
                                "service": {"detectorId": detector_id},
                                "retryRuleName": f"RetryLambdaInvocation-{event_id}",
                            },
                        }
                    ),
                }
            ],
        )
        logger.info(f"Retry scheduled with a {delay_seconds}-second delay.")
        return "rescheduled"

    except ClientError as e:
        logger.error("Failed to schedule retry: %s", e)
    except Exception as e:
        logger.error("An unexpected error occurred: %s", e)


def generate_pdf(ai_insights, guardduty_finding) -> BytesIO:
    """Generate a PDF file with AI insights and GuardDuty finding details, including formatting improvements.
    """

    # Create a PDF using FPDF
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Add Title
    pdf.set_font("Arial", "B", 16)
    pdf.cell(200, 10, txt="GuardDuty Finding Report", ln=True, align="C")
    pdf.cell(200, 10, txt=guardduty_finding.get("Type", "N/A"), ln=True, align="C")

    # Metadata (generation time)
    pdf.set_font("Arial", "", 12)
    pdf.cell(200, 10, txt=f"Generated on: {datetime.utcnow().isoformat()}", ln=True, align="C")

    # Add Section for GuardDuty Finding Details
    pdf.ln(10)
    pdf.set_font("Arial", "B", 14)
    pdf.cell(200, 10, txt="GuardDuty Finding Details", ln=True)

    # GuardDuty Finding Information
    pdf.set_font("Arial", "", 12)
    finding_details = (
        f"Finding Type: {guardduty_finding.get('Type', 'N/A')}\n"
        f"Finding ID: {guardduty_finding.get('Id', 'N/A')}\n"
        f"Severity: {guardduty_finding.get('Severity', 'N/A')}\n"
        f"Account ID: {guardduty_finding.get('AccountId', 'N/A')}\n"
        f"Region: {guardduty_finding.get('Region', 'N/A')}\n"
    )
    pdf.multi_cell(0, 10, txt=finding_details)

    # Construct GuardDuty and Detective Links
    region = guardduty_finding.get("Region", "us-east-1")
    finding_id = guardduty_finding.get("Id", "unknown")

    guardduty_link = (
        f"https://{region}.console.aws.amazon.com/guardduty/home?region={region}#/findings?"
        f"search=id%3D{finding_id}&macros=current"
    )
    detective_link = (
        f"https://{region}.console.aws.amazon.com/detective/home?region={region}#search?"
        f"searchType=Finding&searchText={finding_id}"
    )

    # Add clickable GuardDuty and Detective links
    pdf.ln(10)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(200, 10, txt="Relevant Links", ln=True)

    pdf.set_font("Arial", "", 12)
    pdf.set_text_color(0, 0, 255)  # Blue for links
    pdf.cell(200, 10, txt="View Finding in GuardDuty Console", ln=True, link=guardduty_link)
    pdf.cell(200, 10, txt="View Finding in Detective Console", ln=True, link=detective_link)

    # Reset text color
    pdf.set_text_color(0, 0, 0)

    # Add a Section for AI Insights with Proper Formatting and Line Breaks
    pdf.ln(10)
    pdf.set_font("Arial", "B", 14)
    pdf.cell(200, 10, txt="AI Insights", ln=True)

    # Parse AI insights line by line, handling double newlines
    insights_lines = re.split(r"\n\s*\n", ai_insights.strip())  # Split by double newlines

    for section in insights_lines:
        for line in section.split("\n"):
            # Check for specific headers
            if line.strip() in ["Analysis:", "Remediation Actions:", "Recommended Actions:"]:
                pdf.set_font("Arial", "B", 12)  # Set font for H3
                pdf.cell(0, 10, txt=line.strip(), ln=True)  # Add header
            elif line.strip() in [
                "Entities Involved:",
                "Security Group Impact:",
                "Attempt Status:",
            ]:
                pdf.set_font("Arial", "B", 10)  # Set font for H3
                pdf.cell(0, 10, txt=line.strip(), ln=True)  # Add header
            else:
                pdf.set_font("Arial", "", 10)  # Set back to normal font
                pdf.multi_cell(0, 10, txt=line.strip())  # Add regular text

        pdf.ln(5)  # Add some space between sections

    # Add Summary or Conclusion Section
    pdf.ln(10)
    pdf.set_font("Arial", "B", 14)
    pdf.cell(200, 10, txt="Conclusion and Recommended Actions", ln=True)

    summary_text = (
        "The above insights and recommendations provide detailed information on mitigating the"
        " identified threat. Please ensure the recommended security actions are promptly applied to"
        " minimize future risks."
    )
    pdf.set_font("Arial", "", 12)
    pdf.multi_cell(0, 10, txt=summary_text)

    # Generate PDF in memory
    pdf_buffer = BytesIO()
    pdf_output = pdf.output(dest="S").encode("latin1")  # Return as string and encode
    pdf_buffer.write(pdf_output)
    pdf_buffer.seek(0)

    return pdf_buffer


def upload_pdf_to_s3(client: boto3.client, pdf_buffer: BytesIO, file_name: str, bucket_name: str):
    """Upload the PDF to S3 and return the pre-signed URL."""
    try:
        # Upload the PDF file to S3
        client.put_object(
            Bucket=bucket_name, Key=file_name, Body=pdf_buffer, ContentType="application/pdf"
        )

        # Generate a pre-signed URL for the PDF
        pre_signed_url = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket_name, "Key": file_name},
            ExpiresIn=3600,  # URL expires in 1 hour
        )

        return pre_signed_url
    except Exception as e:
        logger.error(f"Error uploading PDF to S3: {e}")
        raise


def send_sns_notification(client: boto3.client, pre_signed_url: str, topic_arn: str):
    """Send SNS notification with the pre-signed URL."""
    try:
        # Ensure URL is stripped and encoded
        pre_signed_url = pre_signed_url.strip().replace(" ", "%20")
        logger.info(
            f"Encoded Pre-signed URL: {pre_signed_url}"
        )  # Log the encoded URL for debugging

        # Compose message in a simplified HTML format
        message = (
            "New GuardDuty finding. Enriched PDF with AI remediation's can be downloaded here: "
            f"{pre_signed_url}"
        )

        # Create the SNS message structure with JSON to support HTML
        message_structure = {
            "default": "New GuardDuty finding with enriched PDF. Click the link to download.",
            "email": message,
        }

        # Publish to SNS
        client.publish(
            TopicArn=topic_arn,
            Message=json.dumps(message_structure),
            Subject="GuardDuty Finding Enrichment Report",
            MessageStructure="json",
        )

        logger.info("Notification sent to SNS")
    except Exception as e:
        logger.error(f"Error sending SNS notification: {e}")
        raise


def remove_retry_event_rule(client: boto3.client, event_rule_name: str):
    try:
        logger.info(f"Deleting EventBridge rule: {event_rule_name}")
        client.delete_rule(Name=event_rule_name)
        logger.info(f"Deleted EventBridge rule: {event_rule_name}")
    except Exception as e:
        logger.error(f"Error deleting EventBridge rule: {e}")


def lambda_handler(event, context):
    logger.info("Received event: %s", json.dumps(event, indent=4))
    sns_topic_arn = os.getenv("AI_REPORTS_TOPIC_ARN")
    s3_bucket_name = os.getenv("AI_REPORTS_BUCKET_NAME")
    detective_client = boto3.client("detective")
    guardduty_client = boto3.client("guardduty")
    bedrock_client = boto3.client("bedrock-runtime")
    s3_client = boto3.client("s3")
    sns_client = boto3.client("sns")
    if not s3_bucket_name:
        logger.error("Environment variable AI_REPORTS_BUCKET_NAME is not set")
        raise ValueError("Environment variable AI_REPORTS_BUCKET_NAME is not set")
    if not sns_topic_arn:
        logger.error("Environment variable AI_REPORTS_TOPIC_ARN is not set")
        raise ValueError("Environment variable AI_REPORTS_TOPIC_ARN is not set")
    try:
        finding_id = event["detail"]["id"]
        detector_id = event["detail"]["service"]["detectorId"]
        logger.info(
            f"Processing GuardDuty finding: {finding_id} for detector with ID: {detector_id}"
        )
        # Get GuardDuty finding details
        finding = get_guardduty_finding(guardduty_client, detector_id, finding_id)
        # only proceed if severity if bigger then 4.0
        if finding["Severity"] < 4.0:
            logger.info(
                f"Finding {finding_id} has severity of {finding['Severity']} not processing"
            )
            return {
                "statusCode": 200,
                "body": json.dumps(
                    f"Finding {finding_id} has severity of {finding['Severity']} not processing"
                ),
            }

        # Get the graph ARN for Amazon Detective
        graph_arn = get_graph_arn(detective_client)

        # Get all entity details from Amazon Detective
        detective_entities = get_all_detective_entities(detective_client, graph_arn)

        # Convert enriched_data to use Decimal for float types
        finding = convert_to_json_serializable(finding)
        detective_entities = convert_to_json_serializable(detective_entities)

        # AI Analysis with Amazon Bedrock
        ai_insights = invoke_bedrock_model(
            bedrock_client, finding, detective_entities, event, context
        )
        if ai_insights == "rescheduled":
            return {"statusCode": 200, "body": json.dumps("Event scheduled.")}
        # Generate PDF with AI insights and GuardDuty information
        pdf_buffer = generate_pdf(ai_insights, finding)

        # Upload PDF to S3 and get pre-signed URL
        file_name = f"{finding_id}.pdf"

        pre_signed_url = upload_pdf_to_s3(s3_client, pdf_buffer, file_name, s3_bucket_name)

        # Send SNS notification with pre-signed URL
        send_sns_notification(sns_client, pre_signed_url, sns_topic_arn)

        # if case this is a rescheduled event, lets clean it to keep the event bridge clean
        # Check if 'retryRuleName' exists and remove the retry event rule if it does
        retry_rule_name = event["detail"].get("retryRuleName")  # Use get() to avoid KeyError
        if retry_rule_name:
            remove_retry_event_rule(sns_client, retry_rule_name)
    except Exception as e:
        logger.error("Error in processing: %s", e)
        return {"statusCode": 500, "body": json.dumps(f"Error in processing: {e}")}
    return {"statusCode": 200, "body": json.dumps(ai_insights)}

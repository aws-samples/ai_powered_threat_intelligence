# L3LambdaPython CDK Construct

## Overview

The L3LambdaPython construct is a high-level (L3) AWS CDK construct that simplifies the process of creating and configuring AWS Lambda functions using Python. This construct provides a convenient way to set up Lambda functions with common configurations and best practices.

## Features

- Easy creation of Python-based Lambda functions
- Automatic handling of dependencies and packaging
- Configurable memory and timeout settings
- Built-in logging configuration
- Optional VPC and security group configuration
- Simplified IAM role and policy management

## Installation

To use this construct in your CDK project, ensure you have the AWS CDK installed and then install this construct:

## Usage

```
from aws_cdk import Stack
from constructs import Construct
from your_module import L3LambdaPython

class MyStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        lambda_function = L3LambdaPython(
            self,
            "MyLambdaFunction",
            function_name="my-lambda-function",
            handler="index.handler",
            code_dir="./lambda",
            memory_size=256,
            timeout=30
        )

        # You can now use lambda_function for further configurations or integrations

```

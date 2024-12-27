#!/usr/bin/env python3

"""
CDK app that creates resources.
"""

import aws_cdk as cdk
import cdk_nag
import constants
from l3constructs.helpers.helper import Helper
from stacks.ai_security_recommendations import AISecurityRecommendations

helper = Helper(tags=constants.TAGS)

app = cdk.App(context={"@aws-cdk/core:bootstrapQualifier": helper.get_qualifier()})
AISecurityRecommendations(app, "AiSecurityRecommendations")

# Run cdk nag checks on CDK app scope
cdk.Aspects.of(app).add(cdk_nag.AwsSolutionsChecks(verbose=True))

app.synth()

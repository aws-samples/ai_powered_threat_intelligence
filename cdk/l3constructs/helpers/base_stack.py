"""
Base stack contains a class that modifies the regular Stack functionality
by adding custom logic to it.
"""

import constants
from aws_cdk import Stack
from constructs import Construct
from l3constructs.helpers.helper import Helper


class BaseStack(Stack):
    """
    BaseStack class inherits from the default CDK Stack construct and
    adds custom logic to it, to meet project requirements.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        helper = Helper(tags=constants.TAGS)

        cdk_env = helper.get_cdk_env()
        qualifier = helper.get_qualifier()

        # construct_id = f"{qualifier}-{construct_id}"
        construct_id = f"{construct_id}"

        # Set class attributes available in implementing stacks via self.
        self.qualifier = qualifier
        self.cdk_env = cdk_env
        self.prefix = helper.prefix

        super().__init__(scope, construct_id, **kwargs)

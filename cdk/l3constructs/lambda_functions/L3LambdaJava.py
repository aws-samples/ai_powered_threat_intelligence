import os
import re
import subprocess
from typing import List, Mapping, Optional

import aws_cdk
from aws_cdk import Duration, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms, aws_lambda
from constructs import Construct
from jsii import implements, member

from .L3Lambda import L3Lambda


@implements(aws_cdk.ILocalBundling)
class MyLocalBundler:
    def __init__(self, lambda_root: str) -> None:
        self._lambda_root = lambda_root

    @member(jsii_name="tryBundle")
    def try_bundle(self, output_dir: str, options: aws_cdk.BundlingOptions) -> bool:
        if os.environ.get("OS", "") == "Windows_NT":
            subprocess.run([f"cd {self._lambda_root}", "mvn clean install"])
        else:
            subprocess.run(
                ["bash", "-c", " && ".join([f"cd {self._lambda_root}, mvn clean install"])]
            )
        return True


class L3LambdaJava(L3Lambda):
    def __init__(
        self,
        scope: Construct,
        id: str,
        code: str,
        handler: str,
        function_name: str,
        runtime: aws_lambda.Runtime = aws_lambda.Runtime.JAVA_21,
        role: Optional[iam.Role] = None,
        vpc: Optional[str] = None,
        environment: Optional[Mapping] = None,
        environment_encryption: Optional[aws_kms.Key] = None,
        security_groups: Optional[list] = None,
        layers: Optional[List[aws_lambda.LayerVersion]] = None,
        description: Optional[str] = None,
        memory: int = 128,
        timeout: Duration = Duration.seconds(60),
    ):
        super(L3LambdaJava, self).__init__(
            scope=scope,
            id=id,
            code=L3LambdaJava.bundle_locally(
                lambda_root=code, runtime=runtime, function_name=function_name
            ),
            handler=handler,
            runtime=runtime or None,
            role=role or None,
            vpc=vpc or None,
            description=description or None,
            layers=layers or None,
            environment=environment or None,
            environment_encryption=environment_encryption or None,
            security_groups=security_groups or None,
            timeout=timeout,
            memory_size=memory,
        )

    @staticmethod
    def format_dockerfile(
        scope: Construct,
        id: str,
        code: str,
        runtime: aws_lambda.Runtime,
        docker_file: str = "Dockerfile.python",
    ) -> aws_lambda.Code:
        input_docker_file_path = f"./cdk/l3_constructs/lambda_functions/docker_files/{docker_file}"
        output_docker_file_name = f"Dockerfile.{Stack.of(scope).stack_name}.{id}"
        output_docker_file_path = f"{code}/{output_docker_file_name}"

        with open(input_docker_file_path, "r") as docker_file_r:
            file = docker_file_r.read()
            file_content = file.format(
                **{"RUNTIME": re.sub(r"([a-z_-]+)", r"\g<1>:", runtime.to_string(), 1)}
            )

        with open(output_docker_file_path, "w") as docker_file_w:
            docker_file_w.write(file_content)

        docker_build = aws_lambda.Code.from_docker_build(
            path=os.path.abspath(code), file=output_docker_file_name, platform="linux/amd64"
        )

        return docker_build

    @staticmethod
    def bundle_locally(lambda_root: str, runtime: aws_lambda.Runtime, function_name: str):
        asset_hash = aws_cdk.FileSystem.fingerprint(lambda_root)

        current_dir = "."
        code = aws_lambda.Code.from_asset(
            path=current_dir,
            bundling=aws_cdk.BundlingOptions(
                image=runtime.bundling_image,
                command=[
                    f"rsync -r {lambda_root}/target/{function_name}.jar"
                    f" /asset-output/{lambda_root}/"
                ],
                local=MyLocalBundler(lambda_root=lambda_root),
            ),
            asset_hash=asset_hash,
            asset_hash_type=aws_cdk.AssetHashType.CUSTOM,
        )
        return code

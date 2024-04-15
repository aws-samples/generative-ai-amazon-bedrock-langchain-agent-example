# Clean up
---

To avoid charges in your AWS account, please clean up the solution's provisioned resources.

## Step 1: Revoke GitHub Personal Access Token

GitHub PATs are configured with an expiration value. If you want to ensure that your PAT cannot be used for programmatic access to your forked Amplify GitHub repository before it reaches its expiry, you can revoke the PAT by following [GitHub's instructions](https://docs.github.com/en/organizations/managing-programmatic-access-to-your-organization/reviewing-and-revoking-personal-access-tokens-in-your-organization).

## Step 2: Delete `GenAI-FSI-Agent.yml` CloudFormation Stack and Other Solution Resources
The following commands use the default stack name. If you customized the stack name, adjust the commands accordingly.

```sh
# export STACK_NAME=<YOUR-STACK-NAME>
./delete-stack.sh
```

#### Solution Deletion Automation Script
The [delete-stack.sh](../shell/delete-stack.sh) shell script deletes the resources that were originally provisioned using the solution deployment automation script, including the [GenAI-FSI-Agent.yml](../cfn/GenAI-FSI-Agent.yml) CloudFormation stack.

```sh
echo "Deleting Kendra Data Source: $KENDRA_WEBCRAWLER_DATA_SOURCE_ID"
aws kendra delete-data-source --id $KENDRA_WEBCRAWLER_DATA_SOURCE_ID --index-id $KENDRA_INDEX_ID --region $AWS_REGION

echo "Emptying and Deleting S3 Bucket: $S3_ARTIFACT_BUCKET_NAME"
aws s3 rm s3://$S3_ARTIFACT_BUCKET_NAME --region $AWS_REGION --recursive
aws s3 rb s3://$S3_ARTIFACT_BUCKET_NAME} --region $AWS_REGION

echo "Deleting CloudFormation Stack: $STACK_NAME"
aws cloudformation delete-stack --stack-name $STACK_NAME --region $AWS_REGION
aws cloudformation wait stack-delete-complete --stack-name $STACK_NAME --region $AWS_REGION

echo "Deleting Secrets Manager Secret: $GITHUB_TOKEN_SECRET_NAME"
aws secretsmanager delete-secret --secret-id $GITHUB_TOKEN_SECRET_NAME --region $AWS_REGION
```

---

[Back to README](../README.md)

---

Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0

# cd generative-ai-amazon-bedrock-langchain-agent-example/shell/
# chmod u+x delete-stack.sh
# ./delete-stack.sh

echo "Deleting Kendra Data Source: $KENDRA_WEBCRAWLER_DATA_SOURCE_ID"
aws kendra delete-data-source --id $KENDRA_WEBCRAWLER_DATA_SOURCE_ID --index-id $KENDRA_INDEX_ID

echo "Emptying and Deleting S3 Bucket: $S3_ARTIFACT_BUCKET_NAME"
aws s3 rm s3://${S3_ARTIFACT_BUCKET_NAME} --recursive
aws s3 rb s3://${S3_ARTIFACT_BUCKET_NAME}

echo "Deleting CloudFormation Stack: $STACK_NAME"
aws cloudformation delete-stack --stack-name $STACK_NAME
aws cloudformation wait stack-delete-complete --stack-name $STACK_NAME

echo "Deleting Secrets Manager Secret: $GITHUB_TOKEN_SECRET_NAME"
aws secretsmanager delete-secret --secret-id $GITHUB_TOKEN_SECRET_NAME

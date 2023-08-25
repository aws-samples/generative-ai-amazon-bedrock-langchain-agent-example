# cd generative-ai-amazon-bedrock-langchain-agent-example/shell/
# chmod u+x delete-stack.sh
# ./delete-stack.sh

aws kendra delete-data-source --id $KENDRA_WEBCRAWLER_DATA_SOURCE_ID --index-id $KENDRA_INDEX_ID

aws s3 rm s3://${S3_ARTIFACT_BUCKET_NAME} --recursive
aws s3 rb s3://${S3_ARTIFACT_BUCKET_NAME}

aws cloudformation delete-stack --stack-name $STACK_NAME
aws cloudformation wait stack-delete-complete --stack-name $STACK_NAME

aws secretsmanager delete-secret --secret-id $GITHUB_TOKEN_SECRET_NAME
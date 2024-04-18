# If not already forked, fork the remote repository (https://github.com/aws-samples/generative-ai-amazon-bedrock-langchain-agent-example) and change working directory to shell folder
# cd generative-ai-amazon-bedrock-langchain-agent-example/shell/
# chmod u+x create-stack.sh
# source ./create-stack.sh

export UNIQUE_IDENTIFIER=$(uuidgen | tr '[:upper:]' '[:lower:]' | tr -d '-' | cut -c 1-5)
export S3_ARTIFACT_BUCKET_NAME=$STACK_NAME-$UNIQUE_IDENTIFIER
export DATA_LOADER_S3_KEY="agent/lambda/data-loader/loader_deployment_package.zip"
export LAMBDA_HANDLER_S3_KEY="agent/lambda/agent-handler/agent_deployment_package.zip"
export LEX_BOT_S3_KEY="agent/bot/lex.zip"

echo "STACK_NAME: $STACK_NAME"
echo "S3_ARTIFACT_BUCKET_NAME: $S3_ARTIFACT_BUCKET_NAME"

aws s3 mb s3://$S3_ARTIFACT_BUCKET_NAME --region $AWS_REGION
aws s3 cp ../agent/ s3://$S3_ARTIFACT_BUCKET_NAME/agent/ --region $AWS_REGION --recursive --exclude ".DS_Store" --exclude "*/.DS_Store"

export BEDROCK_LANGCHAIN_PDFRW_LAYER_ARN=$(aws lambda publish-layer-version \
    --layer-name bedrock-langchain-pdfrw \
    --description "Bedrock LangChain pdfrw layer" \
    --license-info "MIT" \
    --content S3Bucket=$S3_ARTIFACT_BUCKET_NAME,S3Key=agent/lambda/lambda-layers/bedrock-langchain-pdfrw.zip \
    --compatible-runtimes python3.11 \
    --region $AWS_REGION \
    --query LayerVersionArn --output text)

export CFNRESPONSE_LAYER_ARN=$(aws lambda publish-layer-version \
    --layer-name cfnresponse \
    --description "cfnresponse Layer" \
    --license-info "MIT" \
    --content S3Bucket=$S3_ARTIFACT_BUCKET_NAME,S3Key=agent/lambda/lambda-layers/cfnresponse-layer.zip \
    --compatible-runtimes python3.11 \
    --region $AWS_REGION \
    --query LayerVersionArn --output text)

export GITHUB_TOKEN_SECRET_NAME=$(aws secretsmanager create-secret --name $STACK_NAME-git-pat \
--secret-string $GITHUB_PAT --region $AWS_REGION --query Name --output text)

aws cloudformation create-stack \
--stack-name $STACK_NAME \
--template-body file://../cfn/GenAI-FSI-Agent.yml \
--parameters \
ParameterKey=S3ArtifactBucket,ParameterValue=$S3_ARTIFACT_BUCKET_NAME \
ParameterKey=DataLoaderS3Key,ParameterValue=$DATA_LOADER_S3_KEY \
ParameterKey=LambdaHandlerS3Key,ParameterValue=$LAMBDA_HANDLER_S3_KEY \
ParameterKey=LexBotS3Key,ParameterValue=$LEX_BOT_S3_KEY \
ParameterKey=BedrockLangChainPDFRWLayerArn,ParameterValue=$BEDROCK_LANGCHAIN_PDFRW_LAYER_ARN \
ParameterKey=CfnresponseLayerArn,ParameterValue=$CFNRESPONSE_LAYER_ARN \
ParameterKey=GitHubTokenSecretName,ParameterValue=$GITHUB_TOKEN_SECRET_NAME \
ParameterKey=KendraWebCrawlerUrl,ParameterValue=$KENDRA_WEBCRAWLER_URL \
ParameterKey=AmplifyRepository,ParameterValue=$AMPLIFY_REPOSITORY \
--capabilities CAPABILITY_NAMED_IAM \
--region $AWS_REGION

aws cloudformation describe-stacks --stack-name $STACK_NAME --region $AWS_REGION --query "Stacks[0].StackStatus"
aws cloudformation wait stack-create-complete --stack-name $STACK_NAME --region $AWS_REGION
aws cloudformation describe-stacks --stack-name $STACK_NAME --region $AWS_REGION --query "Stacks[0].StackStatus"

export LEX_BOT_ID=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $AWS_REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`LexBotID`].OutputValue' --output text)

export LAMBDA_ARN=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $AWS_REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`LambdaARN`].OutputValue' --output text)

aws lexv2-models update-bot-alias --bot-alias-id 'TSTALIASID' --bot-alias-name 'TestBotAlias' --bot-id $LEX_BOT_ID --bot-version 'DRAFT' --bot-alias-locale-settings "{\"en_US\":{\"enabled\":true,\"codeHookSpecification\":{\"lambdaCodeHook\":{\"codeHookInterfaceVersion\":\"1.0\",\"lambdaARN\":\"${LAMBDA_ARN}\"}}}}" --region $AWS_REGION

aws lexv2-models build-bot-locale --bot-id $LEX_BOT_ID --bot-version "DRAFT" --locale-id "en_US" --region $AWS_REGION

export KENDRA_INDEX_ID=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $AWS_REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`KendraIndexID`].OutputValue' --output text)

export KENDRA_DATA_SOURCE_ROLE_ARN=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $AWS_REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`KendraDataSourceRoleARN`].OutputValue' --output text)

export KENDRA_WEBCRAWLER_DATA_SOURCE_ID=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $AWS_REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`KendraWebCrawlerDataSourceID`].OutputValue' --output text)

aws kendra create-faq \
    --index-id $KENDRA_INDEX_ID \
    --name $STACK_NAME-S3Faq \
    --description "AnyCompany S3 FAQ" \
    --s3-path Bucket=$S3_ARTIFACT_BUCKET_NAME,Key="agent/assets/AnyCompany-FAQs.csv" \
    --role-arn $KENDRA_DATA_SOURCE_ROLE_ARN \
    --file-format "CSV_WITH_HEADER" \
    --region $AWS_REGION

aws kendra start-data-source-sync-job --id $KENDRA_WEBCRAWLER_DATA_SOURCE_ID --index-id $KENDRA_INDEX_ID --region $AWS_REGION

export AMPLIFY_APP_ID=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $AWS_REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`AmplifyAppID`].OutputValue' --output text)

export AMPLIFY_BRANCH=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $AWS_REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`AmplifyBranch`].OutputValue' --output text)

aws amplify start-job --app-id $AMPLIFY_APP_ID --branch-name $AMPLIFY_BRANCH --job-type 'RELEASE' --region $AWS_REGION

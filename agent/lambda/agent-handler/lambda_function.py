import os
import json
import time
import boto3
import pdfrw
import difflib
import logging
import datetime
import dateutil.parser

from boto3.dynamodb.conditions import Key
from langchain.llms.bedrock import Bedrock
from langchain.chat_models import BedrockChat
from langchain.schema import HumanMessage
from chat import Chat
from fsi_agent import FSIAgent

# Create reference to DynamoDB tables
loan_application_table_name = os.environ['USER_PENDING_ACCOUNTS_TABLE']
user_accounts_table_name = os.environ['USER_EXISTING_ACCOUNTS_TABLE']
s3_artifact_bucket = os.environ['S3_ARTIFACT_BUCKET_NAME']

# Instantiate boto3 clients and resources
boto3_session = boto3.Session(region_name=os.environ['AWS_REGION'])
dynamodb = boto3.resource('dynamodb',region_name=os.environ['AWS_REGION'])
s3_client = boto3.client('s3',region_name=os.environ['AWS_REGION'],config=boto3.session.Config(signature_version='s3v4',))
s3_object = boto3.resource('s3')
bedrock_client = boto3_session.client(service_name="bedrock-runtime")

# --- Lex v2 request/response helpers (https://docs.aws.amazon.com/lexv2/latest/dg/lambda-response-format.html) ---

def elicit_slot(session_attributes, active_contexts, intent, slot_to_elicit, message):
    response = {
        'sessionState': {
            'activeContexts':[{
                'name': 'intentContext',
                'contextAttributes': active_contexts,
                'timeToLive': {
                    'timeToLiveInSeconds': 86400,
                    'turnsToLive': 20
                }
            }],
            'sessionAttributes': session_attributes,
            'dialogAction': {
                'type': 'ElicitSlot',
                'slotToElicit': slot_to_elicit
            },
            'intent': intent,
        },
        'messages': [{
            "contentType": "PlainText",
            "content": message,
        }]
    }

    return response

def confirm_intent(active_contexts, session_attributes, intent, message):
    response = {
        'sessionState': {
            'activeContexts': [active_contexts],
            'sessionAttributes': session_attributes,
            'dialogAction': {
                'type': 'ConfirmIntent'
            },
            'intent': intent
        }
    }

    return response

def close(session_attributes, active_contexts, fulfillment_state, intent, message):
    response = {
        'sessionState': {
            'activeContexts':[{
                'name': 'intentContext',
                'contextAttributes': active_contexts,
                'timeToLive': {
                    'timeToLiveInSeconds': 86400,
                    'turnsToLive': 20
                }
            }],
            'sessionAttributes': session_attributes,
            'dialogAction': {
                'type': 'Close',
            },
            'intent': intent,
        },
        'messages': [{'contentType': 'PlainText', 'content': message}]
    }

    return response

def elicit_intent(intent_request, session_attributes, message):
    response = {
        'sessionState': {
            'dialogAction': {
                'type': 'ElicitIntent'
            },
            'sessionAttributes': session_attributes
        },
        'messages': [
            {
                'contentType': 'PlainText', 
                'content': message
            },
            {
                'contentType': 'ImageResponseCard',
                'imageResponseCard': {
                    "buttons": [
                        {
                            "text": "Loan Application",
                            "value": "Loan Application"
                        },
                        {
                            "text": "Loan Calculator",
                            "value": "Loan Calculator"
                        },
                        {
                            "text": "Ask GenAI",
                            "value": "What kind of questions can the Assistant answer?"
                        }
                    ],
                    "title": "How can I help you?"
                }
            }     
        ]
    }

    return response

def delegate(session_attributes, active_contexts, intent, message):
    response = {
        'sessionState': {
            'activeContexts':[{
                'name': 'intentContext',
                'contextAttributes': active_contexts,
                'timeToLive': {
                    'timeToLiveInSeconds': 86400,
                    'turnsToLive': 20
                }
            }],
            'sessionAttributes': session_attributes,
            'dialogAction': {
                'type': 'Delegate',
            },
            'intent': intent,
        },
        'messages': [{'contentType': 'PlainText', 'content': message}]
    }

    return response

def initial_message(intent_name):
    response = {
            'sessionState': {
                'dialogAction': {
                    'type': 'ElicitSlot',
                    'slotToElicit': 'UserName' if intent_name=='MakePayment' else 'PickUpCity'
                },
                'intent': {
                    'confirmationState': 'None',
                    'name': intent_name,
                    'state': 'InProgress'
                }
            }
    }
    
    return response

def build_response_card(title, subtitle, options):
    """
    Build a responseCard with a title, subtitle, and an optional set of options which should be displayed as buttons.
    """
    buttons = None
    if options is not None:
        buttons = []
        for i in range(min(5, len(options))):
            buttons.append(options[i])

    return {
        'contentType': 'ImageResponseCard',
        'imageResponseCard': {
            'title': title,
            'subTitle': subtitle,
            'buttons': buttons
        }
    }

def build_slot(intent_request, slot_to_build, slot_value):
    intent_request['sessionState']['intent']['slots'][slot_to_build] = {
        'shape': 'Scalar', 'value': 
        {
            'originalValue': slot_value, 'resolvedValues': [slot_value], 
            'interpretedValue': slot_value
        }
    }

def build_validation_result(isvalid, violated_slot, message_content):
    print("Build Validation")
    return {
        'isValid': isvalid,
        'violatedSlot': violated_slot,
        'message': message_content
    }
    
# --- Utility helper functions ---

def isvalid_date(date):
    try:
        dateutil.parser.parse(date, fuzzy=True)
        print("TRUE DATE")
        return True
    except ValueError as e:
        print("DATE PARSER ERROR = " + str(e))
        return False

def isvalid_yes_or_no(word):
    # Reference words
    reference_words = ['yes', 'no', 'yep', 'nope']
    similarity_threshold = 0.7  # Adjust this threshold as needed

    # Calculate similarity using difflib
    similarity_scores = [difflib.SequenceMatcher(None, word.lower(), ref_word).ratio() for ref_word in reference_words]

    # Check if the word is close to 'yes' or 'no' based on similarity threshold
    return any(score >= similarity_threshold for score in similarity_scores)

def isvalid_credit_score(credit_score):
    if int(credit_score) < 851 and int(credit_score) > 300:
        return True
    return False

def isvalid_zero_or_greater(value):
    if int(value) >= 0:
        return True
    return False

def safe_int(n):
    if n is not None:
        return int(n)
    return n

def create_presigned_url(bucket_name, object_name, expiration=600):
    # Generate a presigned URL for the S3 object
    try:
        response = s3_client.generate_presigned_url('get_object',
                                                    Params={'Bucket': bucket_name,
                                                            'Key': object_name},
                                                    ExpiresIn=expiration)
    except Exception as e:
        print(e)
        logging.error(e)
        return "Error"

    # The response contains the presigned URL
    return response

def try_ex(value):
    """
    Safely access Slots dictionary values.
    """
    if value is not None:
        if value['value']['resolvedValues']:
            return value['value']['interpretedValue']
        elif value['value']['originalValue']:
            return value['value']['originalValue']
        else:
            return None
    else:
        return None

# --- Intent fulfillment functions --- 

def isvalid_pin(userName, pin):
    """
    Validates the user-provided PIN using a DynamoDB table lookup.
    """
    plans_table = dynamodb.Table(user_accounts_table_name)

    try:
        # Set up the query parameters
        params = {
            'KeyConditionExpression': 'userName = :c',
            'ExpressionAttributeValues': {
                ':c': userName
            }
        }

        # Execute the query and get the result
        response = plans_table.query(**params)

        # iterate over the items returned in the response
        if len(response['Items']) > 0:
            pin_to_compare = int(response['Items'][0]['pin'])
            # check if the password in the item matches the specified password
            if pin_to_compare == int(pin):
                return True

        return False

    except Exception as e:
        print(e)
        return e

def isvalid_username(userName):
    """
    Validates the user-provided username exists in the 'user_accounts_table_name' DynamoDB table.
    """
    plans_table = dynamodb.Table(user_accounts_table_name)

    try:
        # Set up the query parameters
        params = {
            'KeyConditionExpression': 'userName = :c',
            'ExpressionAttributeValues': {
                ':c': userName
            }
        }

        # Execute the query and get the result
        response = plans_table.query(**params)

        # Check if any items were returned
        if response['Count'] != 0:
            return True
        else:
            return False
    except Exception as e:
        print(e)
        return e

def validate_pin(intent_request, slots):
    """
    Performs slot validation for username and PIN. Invoked as part of 'verify_identity' intent fulfillment.
    """
    username = try_ex(slots['UserName'])
    pin = try_ex(slots['Pin'])

    if username is not None:
        if not isvalid_username(username):
            return build_validation_result(
                False,
                'UserName',
                'Our records indicate there is no profile belonging to the username, {}. Please enter a valid username'.format(username)
            )
        session_attributes = intent_request['sessionState'].get("sessionAttributes") or {}
        session_attributes['UserName'] = username
        intent_request['sessionState']['sessionAttributes']['UserName'] = username

    else:
        return build_validation_result(
            False,
            'UserName',
            'Our records indicate there are no accounts belonging to that username. Please try again.'
        )

    if pin is not None:
        if  not isvalid_pin(username, pin):
            return build_validation_result(
                False,
                'Pin',
                'You have entered an incorrect PIN. Please try again.'.format(pin)
            )
    else:
        message = "Thank you for choosing AnyCompany, {}. Please confirm your 4-digit PIN before we proceed.".format(username)
        return build_validation_result(
            False,
            'Pin',
            message
        )

    return {'isValid': True}

def verify_identity(intent_request):
    """
    Performs dialog management and fulfillment for username verification.
    Beyond fulfillment, the implementation for this intent demonstrates the following:
    1) Use of elicitSlot in slot validation and re-prompting.
    2) Use of sessionAttributes {UserName} to pass information that can be used to guide conversation.
    """
    slots = intent_request['sessionState']['intent']['slots']
    pin = try_ex(slots['Pin'])
    username=try_ex(slots['UserName'])

    confirmation_status = intent_request['sessionState']['intent']['confirmationState']
    session_attributes = intent_request['sessionState'].get("sessionAttributes") or {}
    intent = intent_request['sessionState']['intent']
    active_contexts = {}

    # Validate any slots which have been specified.  If any are invalid, re-elicit for their value
    validation_result = validate_pin(intent_request, intent_request['sessionState']['intent']['slots'])
    session_attributes['UserName'] = username

    if not validation_result['isValid']:
        slots = intent_request['sessionState']['intent']['slots']
        slots[validation_result['violatedSlot']] = None

        return elicit_slot(
            session_attributes,
            active_contexts,
            intent_request['sessionState']['intent'],
            validation_result['violatedSlot'],
            validation_result['message']
        )
    else:
        if confirmation_status == 'None':
            # Query DDB for user information before offering intents
            plans_table = dynamodb.Table(user_accounts_table_name)

            try:
                # Query the table using the partition key
                response = plans_table.query(
                    KeyConditionExpression=Key('userName').eq(username)
                )

                # TODO: Customize account readout based on account type
                messages = []
                items = response['Items']

                for item in items:
                    if item['planName'].lower() == 'mortgage':
                        message = "Your mortgage account summary includes a ${:,.2f} loan at {}% interest with ${:,.2f} of unpaid principal. Your next payment of ${:,.2f} is scheduled for {}.".format(float(item['loanAmount']), float(item['loanInterest']), float(item['unpaidPrincipal']), float(item['amountDue']), item['dueDate'])
                    elif item['planName'].lower() == 'checking':
                        message = "I see you have a Checking account with AnyCompany. Your account balance is ${:,.2f} and your next payment amount of ${:,.2f} is scheduled for {}.".format(float(item['unpaidPrincipal']), float(item['paymentAmount']), item['dueDate'])
                    elif item['planName'].lower() == 'loan':
                        message = "I see you have a Loan account with AnyCompany. Your account balance is ${:,.2f} and your next payment amount of ${:,.2f} is scheduled for {}.".format(float(item['unpaidPrincipal']), float(item['paymentAmount']), item['dueDate'])
                    
                    messages.append(message)

                # Convert messages list to a single string
                message = '\n'.join(messages)

                # Return the response without JSON serialization
                return elicit_intent(intent_request, session_attributes, 
                    'Thank you for confirming your username and PIN, {}. {}'.format(username, message)
                )

            except Exception as e:
                print(e)
                return e

def validate_loan_application(intent_request, slots):
    """
    Performs dialog management and fulfillment for completing a loan application.
    Beyond fulfillment, the implementation for this intent demonstrates the following:
    1) Use of elicitSlot in slot validation and re-prompting.
    2) Use of sessionAttributes to pass information that can be used to guide conversation.
    """
    username = try_ex(slots['UserName'])
    loan_value = try_ex(slots['LoanValue'])
    monthly_income = try_ex(slots['MonthlyIncome'])
    work_history = try_ex(slots['WorkHistory'])
    credit_score = try_ex(slots['CreditScore'])
    housing_expense = try_ex(slots['HousingExpense'])
    debt_amount = try_ex(slots['DebtAmount'])
    down_payment = try_ex(slots['DownPayment'])
    coborrow = try_ex(slots['Coborrow'])
    closing_date = try_ex(slots['ClosingDate'])

    confirmation_status = intent_request['sessionState']['intent']['confirmationState']
    session_attributes = intent_request['sessionState'].get("sessionAttributes") or {}
    active_contexts = {}

    if username is not None:
        if not isvalid_username(username):
            return build_validation_result(
                False,
                'UserName',
                'Our records indicate there is no profile belonging to the username, {}. Please enter a valid username'.format(username)
            )
    else:
        try:
            session_username = intent_request['sessionState']['sessionAttributes']['UserName']
            build_slot(intent_request, 'UserName', session_username)
        except KeyError:
            return build_validation_result(
                False,
                'UserName',
                'We cannot find an account under that username. Please try again with a valid username.'
            )

    if loan_value is not None:
        if loan_value.isnumeric():
            if not isvalid_zero_or_greater(loan_value):
                return build_validation_result(False, 'LoanValue', 'Please enter a value greater than $0.')
        else:
            prompt = "The user was just asked to provide their loan value on a loan application and this was their response: " + intent_request['inputTranscript']
            message = invoke_fm(prompt)
            reply = message + " \n\nWhat is your desired loan amount?"

            return build_validation_result(False, 'LoanValue', reply)
    else:
        return build_validation_result(
            False,
            'LoanValue',
            "What is your desired loan amount? In other words, how much are looking to borrow?"
        )

    if monthly_income is not None:
        if monthly_income.isnumeric():
            if not isvalid_zero_or_greater(monthly_income):
                return build_validation_result(False, 'MonthlyIncome', 'Monthly income amount must be greater than $0. Please try again.')
        else:
            prompt = "The user was just asked to provide their monthly income on a loan application and this was their response: " + intent_request['inputTranscript']
            message = invoke_fm(prompt)
            reply = message + " \n\nWhat is your monthly income?"

            return build_validation_result(False, 'MonthlyIncome', reply)
    else:
        return build_validation_result(
            False,
            'MonthlyIncome',
            "What is your monthly income?"
        )

    if work_history is not None:
        if not isvalid_yes_or_no(work_history):
            prompt = "The user was just asked to confirm their continuous two year work history on a loan application and this was their response: " + intent_request['inputTranscript']
            message = invoke_fm(prompt)
            reply = message + " \n\nDo you have a two-year continuous work history?"

            return build_validation_result(False, 'WorkHistory', reply)
    else:
        return build_validation_result(
            False,
            'WorkHistory',
            "Do you have a two-year continuous work history?"
        )

    if credit_score is not None:
        if credit_score.isnumeric():
            if not isvalid_credit_score(credit_score):
                return build_validation_result(False, 'CreditScore', 'Credit score entries must be between 300 and 850. Please enter a valid credit score.')
        else:
            prompt = "The user was just asked to provide their credit score on a loan application and this was their response: " + intent_request['inputTranscript']
            message = invoke_fm(prompt)
            reply = message + " \n\nWhat do you think your current credit score is?"

            return build_validation_result(False, 'CreditScore', reply)
    else:
        return build_validation_result(
            False,
            'CreditScore',
            "What do you think your current credit score is?"
        )

    if housing_expense is not None:
        if housing_expense.isnumeric():
            if not isvalid_zero_or_greater(housing_expense):
                return build_validation_result(False, 'HousingExpense', 'Your housing expense must be a value greater than or equal to $0. Please try again.')
        else:
            prompt = "The user was just asked to provide their monthly housing expense on a loan application and this was their response: " + intent_request['inputTranscript']
            message = invoke_fm(prompt)
            reply = message + " \n\nHow much are you currently paying for housing each month?"

            return build_validation_result(False, 'HousingExpense', reply)
    else:
        return build_validation_result(
            False,
            'HousingExpense',
            "How much are you currently paying for housing each month?"
        )

    if debt_amount is not None:
        if debt_amount.isnumeric():
            if not isvalid_zero_or_greater(debt_amount):
                return build_validation_result(False, 'DebtAmount', 'Your debt amount must be a value greater than or equal to $0. Please try again.')
        else:
            prompt = "The user was just asked to provide their monthly debt amount on a loan application and this was their response: " + intent_request['inputTranscript']
            message = invoke_fm(prompt)
            reply = message + " \n\nWhat is your estimated credit card or student loan debt?"

            return build_validation_result(False, 'DebtAmount', reply)
    else:
        return build_validation_result(
            False,
            'DebtAmount',
            "What is your estimated credit card or student loan debt?"
        )

    if down_payment is not None:
        if down_payment.isnumeric():
            if not isvalid_zero_or_greater(down_payment):
                return build_validation_result(False, 'DownPayment', 'Your estimate down payment must be a value greater than or equal to $0. Please try again.')
        else:
            prompt = "The user was just asked to provide their estimated down payment on a loan application and this was their response: " + intent_request['inputTranscript']
            message = invoke_fm(prompt)
            reply = message + " \n\nWhat do you have saved for a down payment?"

            return build_validation_result(False, 'DownPayment', reply)
    else:
        return build_validation_result(
            False,
            'DownPayment',
            "What do you have saved for a down payment?"
        )

    if coborrow is not None:
        if not isvalid_yes_or_no(coborrow):
            prompt = "The user was just asked to confirm if they will have a co-borrow on a loan application and this was their response: " + intent_request['inputTranscript']
            message = invoke_fm(prompt)
            reply = message + " \n\nDo you have a co-borrower?"

            return build_validation_result(False, 'Coborrow', reply)
    else:
        return build_validation_result(
            False,
            'Coborrow',
            "Do you have a co-borrower?"
        )

    if closing_date is not None:
        if not isvalid_date(closing_date):
            prompt = "The user was just asked to provide their real estate closing date on a loan application and this was their response: " + intent_request['inputTranscript']
            message = invoke_fm(prompt)
            reply = message + " \n\nWhen are you looking to close?"

            return build_validation_result(False, 'ClosingDate', reply)  
        #if datetime.datetime.strptime(closing_date, '%Y-%m-%d').date() <= datetime.date.today():
        #    return build_validation_result(False, 'ClosingDate', 'Closing dates must be scheduled at least one day in advance.  Please try a different date.')   
    else:
        print("## ClosingDate")
        return build_validation_result(
            False,
            'ClosingDate',
            'When are you looking to close?'
        )

    return {'isValid': True}

def loan_application(intent_request):
    """
    Performs dialog management and fulfillment for booking a car.
    Beyond fulfillment, the implementation for this intent demonstrates the following:
    1) Use of elicitSlot in slot validation and re-prompting
    2) Use of sessionAttributes to pass information that can be used to guide conversation
    """
    slots = intent_request['sessionState']['intent']['slots']

    username = try_ex(slots['UserName'])
    loan_value = try_ex(slots['LoanValue'])
    monthly_income = try_ex(slots['MonthlyIncome'])
    work_history = try_ex(slots['WorkHistory'])
    credit_score = try_ex(slots['CreditScore'])
    housing_expense = try_ex(slots['HousingExpense'])
    debt_amount = try_ex(slots['DebtAmount'])
    down_payment = try_ex(slots['DownPayment'])
    coborrow = try_ex(slots['Coborrow'])
    closing_date = try_ex(slots['ClosingDate'])

    confirmation_status = intent_request['sessionState']['intent']['confirmationState']
    session_attributes = intent_request['sessionState'].get("sessionAttributes") or {}
    intent = intent_request['sessionState']['intent']
    active_contexts = {}
    
    if intent_request['invocationSource'] == 'DialogCodeHook':

        # Validate any slots which have been specified. If any are invalid, re-elicit for their value
        validation_result = validate_loan_application(intent_request, intent_request['sessionState']['intent']['slots'])
        print("LOAN APPLICATION - validation_result = " + str(validation_result))
        if 'isValid' in validation_result:
            if validation_result['isValid'] == False:   
                if validation_result['violatedSlot'] == 'CreditScore' and confirmation_status == 'Denied':
                    print("Invalid credit score")
                    validation_result['violatedSlot'] = 'UserName'
                    intent['slots'] = {}
                slots[validation_result['violatedSlot']] = None
                return elicit_slot(
                    session_attributes,
                    active_contexts,
                    intent,
                    validation_result['violatedSlot'],
                    validation_result['message']
                )  

    if username and monthly_income:
        application = {
            'LoanValue': loan_value,
            'MonthlyIncome': monthly_income,
            'CreditScore': credit_score,
            'DownPayment': down_payment
        }

        # Convert the JSON document to a string
        application_string = json.dumps(application)

        # Write the JSON document to DynamoDB
        loan_application_table = dynamodb.Table(loan_application_table_name)

        print("DYNAMODB username = " + str(username))

        response = loan_application_table.put_item(
            Item={
                'userName': username,
                'planName': 'Loan',
                'document': application_string
            }
        )

        # Determine if the intent (and current slot settings) has been denied.  The messaging will be different
        # if the user is denying a reservation he initiated or an auto-populated suggestion.
        if confirmation_status == 'Denied' or confirmation_status == 'None':
            return delegate(session_attributes, active_contexts, intent, 'How else can I help you?')

        if confirmation_status == 'Confirmed':
            intent['confirmationState']="Confirmed"
            intent['state']="Fulfilled"

        s3_client.download_file(s3_artifact_bucket, 'agent/assets/Mortgage-Loan-Application.pdf', '/tmp/Mortgage-Loan-Application.pdf')

        print("initializing reader")
        reader = pdfrw.PdfReader('/tmp/Mortgage-Loan-Application.pdf')
        acroform = reader.Root.AcroForm

        fields_to_update = {
            'name': username,
            'monthlyNet9': monthly_income,
            'creditScore3': credit_score,
            'requestedLoan4': loan_value,
            'downPayment12': down_payment
        }

        # Get the fields from the PDF
        fields = reader.Root.AcroForm.Fields

        # Loop through the fields and print their names and values
        for field in fields:
            field_name = field.T if hasattr(field, 'T') else ''
            field_value = field.V if hasattr(field, 'V') else ''
            print(f"Field Name: {field_name}, Field Value: {field_value}")

        print("acroform")
        if acroform is not None and '/Fields' in acroform:
            fields = acroform['/Fields']
            for field in fields:
                field_name = field['/T'][1:-1]  # Extract field name without '/'
                if field_name in fields_to_update:
                    field.update(pdfrw.PdfDict(V=fields_to_update[field_name]))

        print("initializing writer")
        writer = pdfrw.PdfWriter()
        writer.addpage(reader.pages[0])  # Assuming you're updating the first page

        print("writing to output file")
        with open('/tmp/Mortgage-Loan-Application-Completed.pdf', 'wb') as output_stream:
            writer.write(output_stream)

            
        s3_client.upload_file('/tmp/Mortgage-Loan-Application-Completed.pdf', s3_artifact_bucket, 'agent/assets/Mortgage-Loan-Application-Completed.pdf')

        # Create loan application doc in S3
        URLs=[]

        # create_presigned_url(bucket_name, object_name, expiration=600):
        URLs.append(create_presigned_url(s3_artifact_bucket,'agent/assets/Mortgage-Loan-Application-Completed.pdf',3600))
        
        mortgage_app = 'Your loan application is nearly complete! Please follow the link for the last few bits of information: ' + URLs[0]

        return elicit_intent(
            intent_request,
            session_attributes,
            mortgage_app
        )

def loan_calculator(intent_request):
    """
    Performs dialog management and fulfillment for calculating loan details.
    This is an empty function framework intended for the user to develope their own intent fulfillment functions.
    """
    session_attributes = intent_request['sessionState'].get("sessionAttributes") or {}

    # def elicit_intent(intent_request, session_attributes, message)
    return elicit_intent(
        intent_request,
        session_attributes,
        'This is where you would implement LoanCalculator intent fulfillment.'
    )

def invoke_fm(prompt):
    """
    Invokes Foundational Model endpoint hosted on Amazon Bedrock and parses the response.
    """
    print("DEBUG: Invoking Foundational Model with prompt:", prompt)
    chat = Chat(prompt)
    llm = Bedrock(client=bedrock_client, model_id="anthropic.claude-v2", region_name=os.environ['AWS_REGION']) # "anthropic.claude-instant-v1"
    llm.model_kwargs = {'max_tokens_to_sample': 350}
    lex_agent = FSIAgent(llm, chat.memory)
    formatted_prompt = "\n\nHuman: " + prompt + " \n\nAssistant:"
    
    try:
        message = lex_agent.run(input=formatted_prompt)
    except ValueError as e:
        message = str(e)
        if not message.startswith("Could not parse LLM output:"):
            raise e
        message = message.removeprefix("Could not parse LLM output: `").removesuffix("`")

    return message

def genai_intent(intent_request):
    """
    Performs dialog management and fulfillment for user utterances that do not match defined intents (i.e., FallbackIntent).
    Sends user utterance to Foundational Model endpoint via 'invoke_fm' function.
    """
    session_attributes = intent_request['sessionState'].get("sessionAttributes") or {}
    
    if intent_request['invocationSource'] == 'DialogCodeHook':
        prompt = intent_request['inputTranscript']
        output = invoke_fm(prompt)
        
        return elicit_intent(intent_request, session_attributes, output)

# --- Intents ---

def dispatch(intent_request):
    """
    Routes the incoming request based on intent.
    """
    slots = intent_request['sessionState']['intent']['slots']
    username = slots['UserName'] if 'UserName' in slots else None
    intent_name = intent_request['sessionState']['intent']['name']

    print("Here")
    if intent_name == 'VerifyIdentity':
        return verify_identity(intent_request)
    elif intent_name == 'LoanApplication':
        return loan_application(intent_request)
    elif intent_name == 'LoanCalculator':
        return loan_calculator(intent_request)
    else:
        return genai_intent(intent_request)

    raise Exception('Intent with name ' + intent_name + ' not supported')
        
# --- Main handler ---

def handler(event, context):
    """
    Invoked when the user provides an utterance that maps to a Lex bot intent.
    The JSON body of the user request is provided in the event slot.
    """
    os.environ['TZ'] = 'America/New_York'
    time.tzset()

    return dispatch(event)

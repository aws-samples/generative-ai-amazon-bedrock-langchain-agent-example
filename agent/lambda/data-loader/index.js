const fs = require('fs');
const AWS = require('aws-sdk');
const util = require('util');
const response = require('cfn-response');

const user_accounts_table_name = process.env.USER_EXISTING_ACCOUNTS_TABLE;
const docClient = new AWS.DynamoDB.DocumentClient({
    region: process.env.AWS_REGION
});
const batchSize = 25;

exports.handler = function (event, context, callback) {

    console.log("Reading input from event:\n", util.inspect(event, {depth: 5}));
    const input = event.ResourceProperties;

    if (event.RequestType === 'Delete') {
        response.send(event, context, response.SUCCESS, {});
    }

    var obj = JSON.parse(fs.readFileSync('MOCK_DATA.json', 'utf8'));

    var batchPutPromises = [];
    var itemArray = []
    for (var i = 0; i < obj.length; i++) {
        if (i % batchSize === 0 && i !== 0) {
            var param = {RequestItems: {}};
            param['RequestItems'][user_accounts_table_name] = itemArray;
            batchPutPromises.push(docClient.batchWrite(param).promise());
            itemArray = [];
        }
        itemArray.push({PutRequest: {Item: obj[i]}});
    }
    var param = {RequestItems: {}};
    param['RequestItems'][user_accounts_table_name] = itemArray;
    batchPutPromises.push(docClient.batchWrite(param).promise());

    Promise.all(batchPutPromises).then(data => {
        console.log("done loading " + obj.length + " rows.");
        response.send(event, context, response.SUCCESS, {});
    }).catch(err => {
        console.error(err);
        response.send(event, context, response.FAILED, err);
    })
}


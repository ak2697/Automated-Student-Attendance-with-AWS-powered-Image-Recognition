from flask import Flask, request, jsonify, redirect, url_for, render_template
import subprocess
from datetime import datetime
import boto3
import os
import time
import threading
import argparse
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
sqs = boto3.client('sqs', region_name='us-east-1')
s3 = boto3.client('s3')
messages = []
num = 0
it = 1
run_ = False
ids = []
messages = []
queue = []
responseMap = {}

def index():
    while True:
        global messages
        messages = get_messages_from_queue('<SQS_RESPONSE_QUEUE_URL>')
        print(messages)
        return render_template('index.html', messages=messages)
        time.sleep(2)

def get_messages_from_queue(queue_url):
    while True:
        global responseMap
        try:
            response = sqs.receive_message(
                QueueUrl=queue_url,
                AttributeNames=['All'],
                MaxNumberOfMessages=1,
                MessageAttributeNames=['All'],
                VisibilityTimeout=10,
                WaitTimeSeconds=5
            )

            if 'Messages' in response:
                for message in response['Messages']:
                    id, body = message['Body'].split('@')
                    responseMap[id] = body
                    messages.append(message['Body'])
                    receipt_handle = message['ReceiptHandle']
                    sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
        except Exception as e:
            pass

def receive_latest_message_from_queue(queue_url):
    try:
        response = sqs.receive_message(
            QueueUrl=queue_url,
            AttributeNames=['All'],
            MaxNumberOfMessages=1,
            MessageAttributeNames=['All'],
            VisibilityTimeout=100,
            WaitTimeSeconds=5
        )

        if 'Messages' in response:
            message = response['Messages'][0]
            receipt_handle = message['ReceiptHandle']
            body = message['Body']
            sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
            return body
    except Exception as e:
        pass

    return None

def get_value_from_s3(bucket_name, filename):
    try:
        response = s3.get_object(Bucket=bucket_name, Key=filename)
        value = response['Body'].read().decode('utf-8')
        return value
    except Exception as e:
        print(f"Error getting value from S3: {e}")
        return None

def send_message_to_queue(queue_url, message_body):
    response = sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=message_body
    )
    return response

def upload_result_to_s3(bucket_name, filename, result):
    try:
        s3.put_object(
            Bucket=bucket_name,
            Key=filename,
            Body=result.encode('utf-8')
        )
        return True
    except Exception as e:
        print(f"Error uploading result to S3: {e}")
        return False

def receive_message_from_queue(queue_url):
    response = sqs.receive_message(
        QueueUrl=queue_url,
        AttributeNames=['All'],
        MaxNumberOfMessages=1,
        MessageAttributeNames=['All'],
        VisibilityTimeout=10,
        WaitTimeSeconds=5
    )
    if 'Messages' in response:
        message = response['Messages'][0]
        receipt_handle = message['ReceiptHandle']
        body = message['Body']
        image_name = body
        sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
        return image_name

    return None

def check_queue_for_messages(queue_url):
    response = sqs.get_queue_attributes(
        QueueUrl=queue_url,
        AttributeNames=['ApproximateNumberOfMessages']
    )
    num_messages = int(response['Attributes']['ApproximateNumberOfMessages'])
    return num_messages

def terminate_instance(instance_id):
    ec2 = boto3.client('ec2', region_name='us-east-1')
    response = ec2.terminate_instances(
        InstanceIds=[instance_id],
        DryRun=False
    )
    print(f'Terminating instance {instance_id}')

def classify_image():
    global messages
    global it
    global num
    print("Classifier")
    p1_request_queue_url = '<SQS_REQUEST_QUEUE_URL>'
    while (True):
        print("CLASSIFIER")
        try:
            receivedMessage = receive_message_from_queue(p1_request_queue_url).split('@')
            image_name = receivedMessage[1]
            idRequest = receivedMessage[0]
            print("IMAGE_NAME : :" + image_name + ":")
            fn = image_name
            print(image_name)

            result = subprocess.run(['python3', 'image_classification.py', image_name], universal_newlines=True, stdout=subprocess.PIPE)
            classification_result = result.stdout
            if os.path.exists(image_name):
                os.remove(image_name)
            c = classification_result.split(',')[-1]
            response = image_name + ":" + c
            print("CLASSIFICATIPION :: " + response)
            p1_response_queue_url = '<SQS_RESPONSE_QUEUE_URL>'
            upload_result_to_s3('p1-output', fn, c)
            send_message_to_queue(p1_response_queue_url, idRequest + "@" + response)
        except Exception as e:
            print(e)
            pass

@app.route('/', methods=['POST'])
def upload_image():
    global queue
    image_file = request.files['myfile']
    fn = (str(image_file)).split("'")[1]
    image_name = fn
    image_file.save(fn)
    queue.append(fn)
    s3.upload_file(fn, 'p1-input', fn)
    p1_request_queue_url = '<SQS_REQUEST_QUEUE_URL>'
    send_message_to_queue(p1_request_queue_url, fn + "@" + fn)
    requestQueueSize = check_queue_for_messages(p1_request_queue_url)
        
    while(fn not in responseMap):
        time.sleep(2)
    top = queue[0]
    queue.pop(0)
    return responseMap[fn]

def createInstance():
    global ids
    global queue
    while True:
        if len(ids) < len(queue) and len(ids) < 20:
            ec2 = boto3.client('ec2', region_name='us-east-1')
            response = ec2.run_instances(
                ImageId='<AMI_ID>',
                MinCount=1,
                MaxCount=1,
                InstanceType='t2.micro',
                KeyName='<KEY_PAIR_NAME>',
                SecurityGroupIds=['<SECURITY_GROUP_ID>'],
                UserData='''#!/bin/bash
                    # Add your server startup script or commands here
                    su ubuntu
                    cd /home/ubuntu/app-tier
                    chmod 777 classify.py
                    chmod 777 image_classification.py
                    sudo -u ubuntu python3 classify.py
                '''
            )
            instance_id = response['Instances'][0]['InstanceId']
            ids.append(instance_id)
            print(instance_id)
            ec2.create_tags(Resources=[instance_id], Tags=[{'Key': 'Name', 'Value': 'app-instance' + str(len(ids))}])

def termination():
    global queue
    global ids
    time.sleep(5)
    while True:
        try:
            num_mess = len(queue)
            if len(queue) < len(ids) and len(ids) > 0:
                terminate_instance(ids[-1])
                print("TERMINATING INSTANCE")
                ids.pop()
        except Exception as e:
            pass
        time.sleep(2)

if __name__ == '__main__':
    responseQ = '<SQS_RESPONSE_QUEUE_URL>'
    getMessageThread = threading.Thread(target=get_messages_from_queue, args=(responseQ,))
    getMessageThread.start()
    createInstanceThread = threading.Thread(target=createInstance)
    createInstanceThread.start()
    terminateThread = threading.Thread(target=termination)
    terminateThread.start()
    app.run(host='0.0.0.0', port=3000)

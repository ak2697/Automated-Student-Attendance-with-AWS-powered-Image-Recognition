import boto3
import os
import subprocess
import time
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Retrieve sensitive data from environment variables
aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
region_name = os.getenv('REGION_NAME')
p1_request_queue_url = os.getenv('P1_REQUEST_QUEUE_URL')
p1_response_queue_url = os.getenv('P1_RESPONSE_QUEUE_URL')

# Initialize AWS clients with environment variables
sqs = boto3.client('sqs', region_name=region_name, aws_access_key_id=aws_access_key, aws_secret_access_key=aws_secret_key)
s3 = boto3.client('s3', aws_access_key_id=aws_access_key, aws_secret_access_key=aws_secret_key)
ec2 = boto3.client('ec2', region_name=region_name, aws_access_key_id=aws_access_key, aws_secret_access_key=aws_secret_key)

ids = []

def check_queue_for_messages(queue_url):
    response = sqs.get_queue_attributes(QueueUrl=queue_url, AttributeNames=['ApproximateNumberOfMessages'])
    num_messages = int(response['Attributes']['ApproximateNumberOfMessages'])
    return num_messages

def createInstance():
    response = ec2.run_instances(
        ImageId='ami-05929a9d0a5fc7764',  # Replace with your desired AMI ID
        MinCount=1,
        MaxCount=1,
        InstanceType='t2.micro',  # Replace with your desired instance type
        KeyName='mkey',  # Replace with your key pair name
        SecurityGroupIds=['sg-0a96b0f3d55a4df4e'],  # Replace with your security group ID
        UserData='''#!/bin/bash
                # Add your server startup script or commands here
                su ubuntu
                cd /home/ubuntu/app-tier
                chmod 777 classify.py
                chmod 777 image_classification.py
                sudo -u ubuntu python3 autoscale.py
        '''
    )
    instance_id = response['Instances'][0]['InstanceId']
    ids.append(instance_id)
    print(instance_id)
    ec2.create_tags(Resources=[instance_id], Tags=[{'Key': 'Name', 'Value': 'app-instance' + str(len(ids))}])

def terminateInstance(instance_id):
    response = ec2.terminate_instances(InstanceIds=[instance_id], DryRun=False)
    print(f'Terminating instance {instance_id}')

def scaleOut():
    global n
    num = 0
    while True:
        num = max(num, check_queue_for_messages(p1_request_queue_url))
        while n < min(20, num):
            createInstance()
            n += 1
            time.sleep(5)

def scaleIn():
    global n
    while True:
        num = check_queue_for_messages(p1_request_queue_url)
        while n > num and len(ids) > 0:
            terminateInstance(ids[-1])
            ids.pop()
            n -= 1
        time.sleep(2)

def upload_result_to_s3(bucket_name, filename, result):
    try:
        s3.put_object(Bucket=bucket_name, Key=filename, Body=result.encode('utf-8'))
        return True
    except Exception as e:
        print(f"Error uploading result to S3: {e}")
        return False

def send_message_to_queue(queue_url, message_body):
    response = sqs.send_message(QueueUrl=queue_url, MessageBody=message_body)
    return response

def receive_message_from_queue(queue_url):
    response = sqs.receive_message(QueueUrl=queue_url, AttributeNames=['All'], MaxNumberOfMessages=1, MessageAttributeNames=['All'], VisibilityTimeout=10, WaitTimeSeconds=5)
    if 'Messages' in response:
        message = response['Messages'][0]
        receipt_handle = message['ReceiptHandle']
        body = message['Body']
        return [body, receipt_handle]
    return None

def classify_image():
    print("Classifier")
    while True:
        try:
            receive = receive_message_from_queue(p1_request_queue_url)
            if receive:
                receivedMessage = receive[0].split('@')
                image_name = receivedMessage[1]
                idRequest = receivedMessage[0]
                s3.download_file('p1-input', image_name, image_name)
                subprocess.run(['python3', 'image_classification.py', image_name], stdout=open(image_name + '.result', 'w'))
                with open(image_name + '.result', 'r') as f:
                    classification_result = f.read()
                if os.path.exists(image_name):
                    os.remove(image_name)
                if os.path.exists(image_name + '.result'):
                    os.remove(image_name + '.result')
                c = classification_result.split(',')[-1]
                response = image_name + ":" + c
                upload_result_to_s3('p1-output', image_name, c)
                send_message_to_queue(p1_response_queue_url, idRequest + "@" + response)
                sqs.delete_message(QueueUrl=p1_response_queue_url, ReceiptHandle=receive[1])
        except Exception as e:
            print(e)
            pass

if __name__ == '__main__':
    classify_image()
